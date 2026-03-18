import os
import sys

# 兼容 OpenClaw 运行方式：确保能从项目根目录找到 modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from modules.collector import ContentCollector
from modules.processor import ContentProcessor
from modules.xhs_processor import MPContentProcessor
from modules.mp_processor import DeepMPProcessor
from modules.discovery import DiscoverProcessor, ContentSearchAgent
from modules.publisher import WeChatPublisher
from modules.models import MODEL_POOL
from modules.state_machine import PipelineState, canonical_pipeline_status, is_rewrite_stage, is_publish_stage
from config import Config

from modules.feishu import FeishuBitable
import time
import re

class AutoPlatformManager:
    def __init__(self):
        self.feishu = FeishuBitable(
            app_id=Config.FEISHU_APP_ID,
            app_secret=Config.FEISHU_APP_SECRET,
            app_token=Config.FEISHU_APP_TOKEN
        )
        self.processing_records = set()
        self.collector = ContentCollector()
        self.processor = ContentProcessor(volc_ak=Config.VOLCENGINE_AK, volc_sk=Config.VOLCENGINE_SK)
        self.xhs_processor = MPContentProcessor()
        self.mp_processor = DeepMPProcessor(feishu_client=self.feishu)
        self.search_agent = ContentSearchAgent(max_results=3)
        self.discovery_processor = DiscoverProcessor(self.mp_processor.client)
        self.publisher = WeChatPublisher(
            appid=Config.WECHAT_APPID, 
            secret=Config.WECHAT_SECRET,
            author=Config.WECHAT_AUTHOR
        )
        self.table_ids = {}
        self._refresh_table_cache()
        self.smart_table_id = self.table_ids.get("pipeline")

        if self._should_run_schema_check():
            self._ensure_table_fields()

    def _refresh_table_cache(self):
        """缓存核心表 ID，避免每次流程都重复扫全表列表。"""
        tables = self.feishu.list_tables()
        if not tables:
            return

        def _pick_id(matchers):
            for t in tables:
                name = t.get("name", "")
                if any(m in name for m in matchers):
                    return t.get("table_id")
            return None

        self.table_ids["pipeline"] = _pick_id([Config.FEISHU_PIPELINE_TABLE, "智能内容库", "自动化发布队列"])
        self.table_ids["inspiration"] = _pick_id([Config.FEISHU_INSPIRATION_TABLE, "内容灵感库"])
        self.table_ids["publish_log"] = _pick_id([Config.FEISHU_PUBLISH_LOG_TABLE, "发布记录"])

    def _resolve_table_id(self, key, refresh=False):
        """按业务键获取表 ID，必要时自动刷新缓存。"""
        if refresh or not self.table_ids.get(key):
            self._refresh_table_cache()
        return self.table_ids.get(key)

    def _schema_stamp_path(self):
        out_dir = Config.OUTPUT_DIR or PROJECT_ROOT
        os.makedirs(out_dir, exist_ok=True)
        token_tag = re.sub(r"[^A-Za-z0-9_-]", "_", str(Config.FEISHU_APP_TOKEN or "default"))
        return os.path.join(out_dir, f".schema_checked_{token_tag}.stamp")

    def _should_run_schema_check(self):
        """减少 OpenClaw 定时调用时的重复建字段请求。"""
        if os.getenv("OPENCLAW_SCHEMA_CHECK_ENABLED", "1") != "1":
            return False

        try:
            interval = int(os.getenv("OPENCLAW_SCHEMA_CHECK_INTERVAL_SEC", "21600"))
        except Exception:
            interval = 21600

        if interval <= 0:
            return True

        stamp_path = self._schema_stamp_path()
        if not os.path.exists(stamp_path):
            return True

        try:
            with open(stamp_path, "r", encoding="utf-8") as f:
                last_ts = float((f.read() or "0").strip())
            return (time.time() - last_ts) >= interval
        except Exception:
            return True

    def _mark_schema_checked(self):
        try:
            with open(self._schema_stamp_path(), "w", encoding="utf-8") as f:
                f.write(str(time.time()))
        except Exception:
            pass

    def _field_to_text(self, field_val):
        """将飞书字段值统一转成可解析文本。"""
        if not field_val:
            return ""
        if isinstance(field_val, dict):
            return str(field_val.get('url', '') or field_val.get('link', '') or field_val.get('text', '')).strip()
        if isinstance(field_val, list) and len(field_val) > 0:
            first = field_val[0]
            if isinstance(first, dict):
                return str(first.get('url', '') or first.get('link', '') or first.get('text', '')).strip()
            return str(first).strip()
        return str(field_val).strip()

    def _extract_doc_token(self, *field_vals):
        """从多个字段里提取 docx token（优先 URL，再退化到纯 token 文本）。"""
        for field_val in field_vals:
            val_str = self._field_to_text(field_val)
            if not val_str:
                continue

            # 优先从标准 docx URL 中提取，避免标题里的英文串误判
            m_url = re.search(r'feishu\.cn/docx/([A-Za-z0-9]{27,})', val_str)
            if m_url:
                return m_url.group(1)

            # 兼容只保存 token 的场景
            if re.fullmatch(r'[A-Za-z0-9]{27,60}', val_str):
                return val_str
        return None

    def _resolve_publish_doc_token(self, fields):
        """
        发布阶段解析文档 token：
        1) 改后文档链接
        2) 备注
        3) 原文文档链接
        4) 原文文档
        返回: (token, normalized_url, source_field)
        """
        candidates = [
            ("改后文档链接", fields.get("改后文档链接")),
            ("备注", fields.get("备注")),
            ("原文文档链接", fields.get("原文文档链接")),
            ("原文文档", fields.get("原文文档")),
        ]
        for source_field, value in candidates:
            token = self._extract_doc_token(value)
            if token:
                return token, f"https://www.feishu.cn/docx/{token}", source_field
        return None, "", ""

    def _update_pipeline_failure(self, table_id, record_id, status, reason):
        """失败状态回写兜底：优先精细状态，失败则退化为通用失败，再退化为仅备注。"""
        payload = {
            "数据流程状态": status,
            "备注": reason
        }
        if self.feishu.update_record(table_id, record_id, payload):
            return True

        # 某些单选字段可能不包含“❌ 改写失败/❌ 发布失败”
        fallback_payload = {
            "数据流程状态": PipelineState.FAILED,
            "备注": reason
        }
        if self.feishu.update_record(table_id, record_id, fallback_payload):
            return True

        # 最后至少保留原因，防止“失败但无原因”问题
        return self.feishu.update_record(table_id, record_id, {"备注": reason})

    def _normalize_model_key(self, raw_key):
        """标准化 model_key，支持别名。"""
        key = self._field_to_text(raw_key).strip()
        if not key:
            return ""
        if key in MODEL_POOL:
            return key

        low = key.lower()
        if low in MODEL_POOL:
            return low

        alias = {
            "doubao": "volcengine",
            "volc": "volcengine",
            "ark": "volcengine",
            "qwen": "qwen3.5-plus",
            "bailian": "qwen3.5-plus",
            "kimi": "kimi-k2.5",
            "k2.5": "kimi-k2.5",
            "zhipu": "glm-5",
            "glm": "glm-5",
            "minimax": "MiniMax-M2.5",
            "m2.5": "MiniMax-M2.5",
        }
        mapped = alias.get(low, "")
        if mapped in MODEL_POOL:
            return mapped
        return ""

    def _resolve_pipeline_rewrite_config(self, fields):
        """流水线改写配置：飞书字段优先，环境变量兜底。"""
        raw_role = self._field_to_text(fields.get("改写角色")) or os.getenv("OPENCLAW_PIPELINE_ROLE", "tech_expert")
        role_key = (raw_role or "tech_expert").strip()
        if not role_key:
            role_key = "tech_expert"

        default_model = os.getenv("OPENCLAW_PIPELINE_MODEL", "kimi-k2.5")
        model_key = self._normalize_model_key(fields.get("改写模型"))
        if not model_key:
            model_key = self._normalize_model_key(default_model)
        if not model_key:
            model_key = "volcengine"

        return role_key, model_key

    def _ensure_table_fields(self):
        """确保流水线表格包含必要的字段"""
        try:
            tid = self._resolve_table_id("pipeline", refresh=True)
            if tid:
                # 1: 文本 (使用文本确保 API 读取到的是完整 URL 而非标题)
                self.feishu.create_field(tid, "原文文档链接", 1)
                self.feishu.create_field(tid, "改后文档链接", 1)
                self.feishu.create_field(tid, "改写模型", 1)
                self.feishu.create_field(tid, "改写角色", 1)
                self.feishu.create_field(tid, "备注", 1)
                self._mark_schema_checked()
        except Exception as e:
            print(f"⚠️ 初始化流水线字段检查失败: {e}")

    # --- 记录管理: 全链路同步至飞书三个表格 ---
    def log_to_all_feishu_tables(self, data, source_record_id=None):
        """将运行结果同步至：1.内容灵感库(溯源) 2.小龙虾智能内容库(流水线) 3.发布记录表(归档)"""
        # 1. 更新 [内容灵感库] 的状态 (溯源)
        inbox_table_id = self._resolve_table_id("inspiration")
        if inbox_table_id and data.get("url"):
            # 尝试通过“文章 URL”反查灵感库 ID
            records = self.feishu.list_records(inbox_table_id).get('items', [])
            for r in records:
                fields = r.get('fields', {})
                if fields.get('文章 URL') == data['url'] or fields.get('原链接') == data['url']:
                    # 注意：原状态字段可能是“处理状态”或变种值，先保守写“已处理”
                    self.feishu.update_record(inbox_table_id, r['record_id'], {"处理状态": "已处理"})
                    break

        # 2. 已在流水线中直接更新，无需额外逻辑
        
        # 3. 更新 [发布记录表] (最终发布清单)
        publish_table_id = self._resolve_table_id("publish_log")
        if publish_table_id:
            publish_fields = {
                "发布标题": data.get("title", ""),
                "发布时间": int(time.time() * 1000),
                "发布平台": "微信公众号",
                "草稿/文章 ID": data.get("draft_id", ""),
                "负责人": Config.WECHAT_AUTHOR or "System"
            }
            self.feishu.add_records(publish_table_id, [publish_fields])
            
        print(f"📊 已完成全链路数据同步。")

    # --- 步骤 1: 内容抓取 ---
    def step_collect(self, url):
        print(f"\n📥 [步骤 1/3] 正在抓取内容: {url}")
        article_data = self.collector.fetch(url)
        if not article_data:
            print("❌ 抓取失败")
            return None
        char_count = len(article_data.get('content_raw', ''))
        img_count = len(article_data.get('images', []))
        print(f"   ✅ 抓取成功: {article_data['title']} ({char_count}字, {img_count}图)")
        article_data['url'] = url
        return article_data

    # --- 步骤 2: 内容改写 (AI 创作) ---
    def step_rewrite(self, article_data, role_key, model_key):
        print(f"\n🤖 [步骤 2/3] 正在进行 AI 角色改写 (模型: {model_key}, 角色: {role_key})")
        
        if role_key == "tech_expert" and model_key == "volcengine":
            # 升级版公众号深度专家模式 (MP-Deep-Pro)
            result = self.mp_processor.process(article_data['url'], article_data, publisher=self.publisher)
            
            content_len = len(result.get("full_content", ""))
            if content_len < 300:
                print(f"   ⚠️ [预警] AI 生成内容较短 ({content_len} 字)")
            else:
                print(f"   📊 [生成成功] 共 {content_len} 字。")

            return {
                "title": result.get("title", "公众号精选标题"),
                "content": result.get("full_content", ""),
                "digest": "深度重构的长文逻辑",
                "originality": 92
            }
        elif role_key == "tech_expert" and model_key != "volcengine":
            print("   ℹ️ 当前模型非 volcengine，自动切换为通用改写流程以兼容多模型。")
            
        rewritten = self.processor.rewrite(article_data, role_key=role_key, model_key=model_key)
        if not rewritten:
            print("❌ 改写失败")
            return None
        print(f"   ✅ 改写完成: {rewritten['title']}")
        return rewritten

    # --- 步骤 3: 内容发布 (微信 + 封面图) ---
    def step_publish(self, rewritten_data, original_images=[]):
        print(f"\n📤 [步骤 3/3] 正在同步至微信公众平台...")
        
        # A. 封面图生成（带容错）
        thumb_media_id = ""
        try:
            cover_path = self.processor.generate_cover(f"为文章 '{rewritten_data['title']}' 生成一张高质量封面图")
            if cover_path and os.path.exists(cover_path):
                thumb_media_id = self.publisher.upload_material(cover_path)
        except Exception as e:
            print(f"   ⚠️ 封面生成失败，尝试使用备用封面: {e}")
            
        if not thumb_media_id:
            fallback_url = (original_images[0] if original_images else None) or Config.DEFAULT_COVER_URL
            if fallback_url:
                print(f"   🖼️ 使用备用封面...")
                thumb_media_id = self.publisher.upload_from_url(fallback_url)

        if not thumb_media_id:
            raise Exception("封面图上传失败（即梦生图失败且备用封面也无法上传），终止发布以避免微信 40007 错误")
        
        # B. 处理正文图片与标题清洗
        content_html = rewritten_data['content']
        img_urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content_html)
        for src in set(img_urls):
            if src.startswith('feishu://'):
                img_bytes = self.feishu._download_image(src)
                if img_bytes:
                    wx_url = self.publisher.upload_article_image(img_bytes)
                    if wx_url:
                        content_html = content_html.replace(src, wx_url)
            elif src.startswith('local://wechat_ad_image'):
                ad_path = (Config.WECHAT_AD_IMAGE_PATH or "").strip()
                if ad_path and os.path.exists(ad_path):
                    try:
                        with open(ad_path, "rb") as f:
                            img_bytes = f.read()
                        wx_url = self.publisher.upload_article_image(img_bytes)
                        if wx_url:
                            content_html = content_html.replace(src, wx_url)
                        else:
                            print(f"   ⚠️ 广告图片上传失败，将保留原占位: {ad_path}")
                    except Exception as e:
                        print(f"   ⚠️ 读取广告图片失败: {e}")
                else:
                    print(f"   ⚠️ 未找到广告图片路径: {ad_path}")

        # 深度应用微信公众号排版样式与标题清理
        from modules.mp_processor import WeChatFormatter
        content_html = WeChatFormatter.deep_optimize_format(content_html)
        clean_title = WeChatFormatter.optimize_title(rewritten_data['title'])
        
        draft_id = self.publisher.publish_draft(
            title=clean_title,
            content_html=content_html,
            digest=rewritten_data['digest'],
            thumb_media_id=thumb_media_id
        )
        
        if draft_id:
            print(f"   ✅ 微信同步成功! 草稿 ID: {draft_id}")
        return draft_id

    def run_pipeline_step_1(self, record_id, fields):
        """环节 1: AI 改写"""
        force_rewrite = os.getenv("OPENCLAW_FORCE_REWRITE", "0") == "1"

        # 去重保护：如果已经有可读取的改后文档，则直接复用，避免重复调用模型
        if not force_rewrite:
            existing_token = self._extract_doc_token(fields.get("改后文档链接"), fields.get("备注"))
            if existing_token:
                existing_meta = self.feishu.get_docx_meta(existing_token)
                if existing_meta:
                    normalized_url = f"https://www.feishu.cn/docx/{existing_meta['document_id']}"
                    self.feishu.update_record(fields.get('_table_id'), record_id, {
                        "数据流程状态": PipelineState.REVIEW_READY,
                        "改后文档链接": normalized_url,
                        "备注": f"检测到已有改后稿，已跳过重复改写：{normalized_url}"
                    })
                    print(f"   ♻️ 检测到已有可用改后稿，跳过重复改写: {normalized_url}")
                    return

        doc_link = fields.get("原文文档链接") or fields.get("原文文档")
        url = fields.get("文章 URL")
        
        article_data = None
        doc_token = self._extract_doc_token(doc_link)
        if doc_token:
            article_data = self.feishu.get_docx_content(doc_token)
            if article_data:
                article_data['url'] = url
        
        if not article_data and url:
            article_data = self.step_collect(url)
            
        if not article_data:
            raise Exception("无法获取原文内容（原文文档读取与URL抓取均失败）")

        role_key, model_key = self._resolve_pipeline_rewrite_config(fields)
        print(f"   🧠 [流水线配置] role={role_key}, model={model_key}")
        rewritten = self.step_rewrite(article_data, role_key=role_key, model_key=model_key)
        if not rewritten:
            raise Exception("AI 改写返回空结果")

        new_doc_id, new_doc_url = self.feishu.create_docx(title=f"【AI改后稿】{rewritten['title']}")
        if not new_doc_id or not new_doc_url:
            raise Exception("AI 改写文档创建失败，未获取到有效文档链接")

        self.feishu.set_tenant_manageable(new_doc_id)
        admin_id = os.getenv("FEISHU_ADMIN_USER_ID")
        if admin_id:
            self.feishu.add_collaborator(new_doc_id, admin_id, "full_access")
        blocks, _ = self.feishu.html_to_docx_blocks(rewritten['content'], new_doc_id)
        if blocks and not self.feishu.append_docx_blocks(new_doc_id, blocks):
            raise Exception("AI 改写文档写入失败")

        doc_token = self._extract_doc_token(new_doc_url)
        if not doc_token:
            raise Exception(f"AI 改写文档链接无效: {new_doc_url}")

        normalized_url = f"https://www.feishu.cn/docx/{doc_token}"
            
        update_fields = {
            "数据流程状态": PipelineState.REVIEW_READY,
            "备注": f"AI 已生成草稿：{normalized_url}（模型: {model_key}）",
            "改写模型": model_key,
            "改写角色": role_key,
            "改后文档链接": normalized_url
        }
        if not self.feishu.update_record(fields.get('_table_id'), record_id, update_fields):
            raise Exception("改写结果回写飞书失败")

    def run_pipeline_step_2(self, record_id, fields):
        """环节 2: 确认发布"""
        # 优先使用改后文档；缺失时回退原文文档字段，避免因历史回填缺失导致发布失败
        doc_token, normalized_url, source_field = self._resolve_publish_doc_token(fields)
        if not doc_token:
            raise Exception("无法从‘改后文档链接/备注/原文文档链接’中解析有效 Feishu Doc Token")

        # 自动自愈：若 token 来自回退字段，补齐改后文档链接，便于后续发布流程稳定运行
        if source_field != "改后文档链接":
            old_remark = self._field_to_text(fields.get("备注"))
            marker = "[AutoBackfill]"
            repair_note = f"{marker} 发布阶段已从“{source_field}”回填改后文档链接：{normalized_url}"
            if marker in old_remark:
                new_remark = old_remark
            else:
                new_remark = f"{old_remark} {repair_note}".strip()
            self.feishu.update_record(fields.get('_table_id'), record_id, {
                "改后文档链接": normalized_url,
                "备注": new_remark
            })

        final_article = self.feishu.get_docx_content(doc_token)
        if not final_article:
            raise Exception(f"读取确认稿失败（token={doc_token}）")

        clean_title = re.sub(r'^【AI改后稿】\s*', '', final_article['title'])
        clean_title = re.sub(r'^[标题|Title][:：]\s*', '', clean_title)
        clean_title = re.sub(r'^#+\s*', '', clean_title).strip()

        digest_clean = final_article['content_raw'].replace('\n', ' ').strip()
        draft_id = self.step_publish({
            "title": clean_title,
            "content": final_article['content_html'],
            "digest": digest_clean[:54] + "..." if len(digest_clean) > 54 else digest_clean
        }, original_images=[])

        if not draft_id:
            raise Exception("微信草稿创建失败（未返回 draft_id）")

        if draft_id:
            self.feishu.update_record(fields.get('_table_id'), record_id, {
                "标题": clean_title,
                "草稿 ID": draft_id,
                "数据流程状态": PipelineState.PUBLISHED,
                "备注": f"已同步至草稿箱 ID: {draft_id}"
            })
            self.log_to_all_feishu_tables({
                "url": fields.get("文章 URL", ""),
                "title": clean_title,
                "draft_id": draft_id
            }, source_record_id=record_id)

    def run_with_params(self, url, role_key="tech_expert", model_key="volcengine"):
        """手动运行单篇文章的全流程"""
        # 1. 采集
        article_data = self.step_collect(url)
        if not article_data:
            print("❌ 采集流程中断。")
            return
        
        # 2. 改写
        rewritten = self.step_rewrite(article_data, role_key, model_key)
        if not rewritten:
            print("❌ AI 改写流程中断。")
            return
        
        # 3. 发布
        draft_id = self.step_publish(rewritten, article_data.get('images', []))
        
        if draft_id:
            print(f"\n✨ 手动任务执行成功！草稿 ID: {draft_id}")
            # 同步数据
            self.log_to_all_feishu_tables({
                "url": url,
                "title": rewritten['title'],
                "draft_id": draft_id
            })
        else:
            print("❌ 微信发布流程中断。")

    def run_pipeline_once(self):
        """执行单次全流水线巡检"""
        pipeline_table_id = self._resolve_table_id("pipeline", refresh=True)
        if not pipeline_table_id:
            print("⚠️ 未找到流水线表，跳过本轮巡检。")
            return

        records_data = self.feishu.list_records(pipeline_table_id)
        try:
            batch_size = int(os.getenv("OPENCLAW_PIPELINE_BATCH_SIZE", "3"))
        except Exception:
            batch_size = 3

        handled = 0
        for record in records_data.get('items', []):
            fields = record.get('fields', {})
            status = canonical_pipeline_status(fields.get('数据流程状态', ''))
            record_id = record.get('record_id')
            if record_id in self.processing_records: continue
            fields['_table_id'] = pipeline_table_id

            if is_rewrite_stage(status):
                print(f"🚀 开始改写: {fields.get('标题')}")
                try:
                    self.feishu.update_record(fields['_table_id'], record_id, {"数据流程状态": PipelineState.REWRITE_RUNNING})
                    self.processing_records.add(record_id)
                    self.run_pipeline_step_1(record_id, fields)
                except Exception as e:
                    print(f"❌ 改写步骤异常: {e}")
                    self._update_pipeline_failure(
                        fields['_table_id'],
                        record_id,
                        PipelineState.REWRITE_FAILED,
                        f"AI 改写或排版失败，原因: {str(e)}"
                    )
                finally:
                    if record_id in self.processing_records:
                        self.processing_records.remove(record_id)
                handled += 1

            elif is_publish_stage(status):
                print(f"📤 开始发布: {fields.get('标题')}")
                try:
                    self.feishu.update_record(fields['_table_id'], record_id, {"数据流程状态": PipelineState.PUBLISH_RUNNING})
                    self.processing_records.add(record_id)
                    self.run_pipeline_step_2(record_id, fields)
                except Exception as e:
                    print(f"❌ 发布步骤异常: {e}")
                    self._update_pipeline_failure(
                        fields['_table_id'],
                        record_id,
                        PipelineState.PUBLISH_FAILED,
                        f"推送到微信失败，原因: {str(e)}"
                    )
                finally:
                    if record_id in self.processing_records:
                        self.processing_records.remove(record_id)
                handled += 1

            if batch_size > 0 and handled >= batch_size:
                print(f"⏸️ 已达到本轮批处理上限({batch_size})，等待下次巡检继续。")
                break

    def start_pipeline_loop(self, interval=30):
        print(f"🕵️ [流水线] 监听中...")
        while True:
            try:
                self.run_pipeline_once()
            except Exception as e: print(f"❌ 循环异常: {e}")
            time.sleep(interval)

if __name__ == "__main__":
    manager = AutoPlatformManager()
    if len(sys.argv) < 2:
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "pipeline":
        manager.start_pipeline_loop()
    elif cmd == "pipeline-once":
        manager.run_pipeline_once()
    else:
        # 单篇模式参数优先级：CLI > OPENCLAW_* 环境变量 > 默认值
        role = sys.argv[2] if len(sys.argv) > 2 else os.getenv("OPENCLAW_ROLE", "tech_expert")
        model = sys.argv[3] if len(sys.argv) > 3 else os.getenv("OPENCLAW_MODEL", "volcengine")
        manager.run_with_params(cmd, role, model)
