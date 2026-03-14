import os
import sys

# 兼容 OpenClaw 运行方式：确保能从项目根目录找到 modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

import json
from modules.collector import ContentCollector
from modules.processor import ContentProcessor
from modules.xhs_processor import MPContentProcessor
from modules.mp_processor import DeepMPProcessor
from modules.discovery import DiscoverProcessor, ContentSearchAgent
from modules.publisher import WeChatPublisher
from config import Config

from modules.feishu import FeishuBitable
import time
from datetime import datetime

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
        # 获取核心表 ID
        tables = self.feishu.list_tables()
        table = next((t for t in tables if "智能内容库" in t['name']), None)
        self.smart_table_id = table['table_id'] if table else None
        
        self._ensure_table_fields()

    def _ensure_table_fields(self):
        """确保流水线表格包含必要的字段"""
        try:
            tables = self.feishu.list_tables()
            table = next((t for t in tables if "智能内容库" in t['name']), None)
            if table:
                tid = table['table_id']
                # 1: 文本 (使用文本确保 API 读取到的是完整 URL 而非标题)
                self.feishu.create_field(tid, "原文文档链接", 1) 
                self.feishu.create_field(tid, "改后文档链接", 1)
                self.feishu.create_field(tid, "备注", 1)
        except: pass

    # --- 流程扩展: 关键词驱动内容发现 ---
    def perform_discovery(self, keyword):
        """关键词发现模式：搜索关键词 -> 抓取多信源 -> 进行全网调研综述"""
        print(f"\n🌟 [Discovery Mode] 开启全网调研：{keyword}")
        
        # 1. 搜索
        links = self.search_agent.search_topics(keyword)
        if not links: return None
        
        # 2. 批量抓取 (采集前 3 个)
        scraped_articles = []
        for url in links[:3]:
            art = self.collector.fetch(url)
            if art: scraped_articles.append(art)
            
        if not scraped_articles: return None
        
        # 3. 融合总结
        brief_report = self.discovery_processor.fuse_and_summarize(keyword, scraped_articles)
        
        # 4. 同步至飞书内容灵感库 (作为未来创作的素材储备)
        inbox_table = next((t for t in self.feishu.list_tables() if t['name'] == "内容灵感库"), None)
        if inbox_table:
            fields = {
                "标题": f"【调研报告】{keyword}",
                "文章 URL": links[0], # 取第一个作为主参考
                "处理状态": "待分析",
                "AI 推荐理由": f"全网多信源调研总结 (汇集 {len(scraped_articles)} 篇内容)"
            }
            # 这里简单直接写入总结后的文本的一部分
            # 后续您可以扩展专门的字段来存放调研简报
            self.feishu.add_records(inbox_table['table_id'], [fields])
            
        print(f"✅ 全网调研报告已生成并同步至飞书灵感库！关键词: {keyword}")
        return brief_report

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
        
        # 角色路由逻辑
        if role_key == "xhs":
            # 小红书专家模式 (暂时启用)
            result = self.xhs_processor.process(article_data['url'], article_data)
            return {
                "title": result.get("title", "小红书标题"),
                "content": result.get("full_content", ""),
                "digest": "小红书爆款内容改写",
                "originality": 90
            }
        elif role_key == "tech_expert":
            # 升级版公众号深度专家模式 (MP-Deep-Pro)
            result = self.mp_processor.process(article_data['url'], article_data, publisher=self.publisher)
            
            # --- 字数监控保护 ---
            content_len = len(result.get("full_content", ""))
            if content_len < 300:
                print(f"   ⚠️ [预警] AI 生成内容较短 ({content_len} 字)，请检查原文采集是否完整。")
            else:
                print(f"   📊 [生成成功] 长文内容已构建，共 {content_len} 字。")

            return {
                "title": result.get("title", "公众号精选标题"),
                "content": result.get("full_content", ""),
                "digest": "深度重构的长文逻辑",
                "originality": 92
            }
            
        rewritten = self.processor.rewrite(article_data, role_key=role_key, model_key=model_key)
        if not rewritten:
            print("❌ 改写失败")
            return None
        print(f"   ✅ 改写完成: {rewritten['title']}")
        return rewritten

    # --- 步骤 3: 内容发布 (微信 + 封面图) ---
    def step_publish(self, rewritten_data, original_images=[]):
        print(f"\n📤 [步骤 3/3] 正在同步至微信公众平台...")
        
        # A. 生成/下载封面图
        cover_path = self.processor.generate_cover(f"为文章 '{rewritten_data['title']}' 生成一张高质量封面图")
        
        thumb_media_id = ""
        if cover_path and os.path.exists(cover_path):
            thumb_media_id = self.publisher.upload_material(cover_path)
            
        if not thumb_media_id:
            fallback_url = original_images[0] if original_images else Config.DEFAULT_COVER_URL
            if fallback_url:
                thumb_media_id = self.publisher.upload_from_url(fallback_url)
        
        # B. 处理正文图片与标题
        import re
        content_html = rewritten_data['content']
        # 提取所有图片 src
        img_urls = re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', content_html)
        for src in set(img_urls):
            # 将 feishu:// 的内部素材下载并上传到微信正文图片库
            if src.startswith('feishu://'):
                img_bytes = self.feishu._download_image(src)
                if img_bytes:
                    wx_url = self.publisher.upload_article_image(img_bytes)
                    if wx_url:
                        content_html = content_html.replace(src, wx_url)

        # 清除 AI 改后稿、标题：、## 等不必要的标题前缀
        clean_title = rewritten_data['title']
        clean_title = re.sub(r'^【AI改后稿】\s*', '', clean_title)
        clean_title = re.sub(r'^[标题|Title][:：]\s*', '', clean_title)
        clean_title = re.sub(r'^#+\s*', '', clean_title).strip()
        
        # C. 同步草稿
        draft_id = self.publisher.publish_draft(
            title=clean_title,
            content_html=content_html,
            digest=rewritten_data['digest'],
            thumb_media_id=thumb_media_id or ""
        )
        
        if draft_id:
            print(f"   ✅ 微信同步成功! 草稿 ID: {draft_id}")
        return draft_id

    # --- 记录管理: 全链路同步至飞书三个表格 ---
    def log_to_all_feishu_tables(self, data, source_record_id=None):
        """将运行结果同步至：1.内容灵感库(溯源) 2.小龙虾智能内容库(流水线) 3.发布记录表(归档)"""
        tables = self.feishu.list_tables()
        if not tables: return
        
        # 1. 尝试更新 [内容灵感库] (如果能找到对应记录)
        inbox_table = next((t for t in tables if t['name'] == "内容灵感库"), None)
        if inbox_table:
            inbox_fields = {
                "处理状态": "已发布",
                "AI 推荐理由": f"✅ 已于 {datetime.now().strftime('%m-%d %H:%M')} 完成 AI 深加工并发布"
            }
            # 如果没有直接的 ID，尝试通过 URL 匹配记录
            matched_id = None
            if not source_record_id:
                url = data.get("url")
                if url:
                    records = self.feishu.list_records(inbox_table['table_id'], filter_cond=f'CurrentValue.[文章 URL]="{url}"')
                    if records.get('items'):
                        matched_id = records['items'][0].get('record_id')
            else:
                matched_id = source_record_id

            if matched_id:
                self.feishu.update_record(inbox_table['table_id'], matched_id, inbox_fields)
                print(f"📊 已更新灵感库记录状态: {matched_id}")

        # 2. 更新 [小龙虾智能内容库] (加工流水线库)
        library_table = next((t for t in tables if "智能内容库" in t['name']), None)
        if library_table:
            library_fields = {
                "文章 URL": data.get("url", ""),
                "标题": data.get("title", ""),
                "原创度": data.get("originality", 85),
                "草稿 ID": data.get("draft_id", ""),
                "备注": f"模型: {data.get('model')}, 角色: {data.get('role')}",
                "数据流程状态": "✨ 流程全通",
                "负责人": Config.WECHAT_AUTHOR or "System"
            }
            if source_record_id:
                self.feishu.update_record(library_table['table_id'], source_record_id, library_fields)
            else:
                self.feishu.add_records(library_table['table_id'], [library_fields])

        # 3. 更新 [发布记录表] (最终发布清单)
        publish_table = next((t for t in tables if "发布记录" in t['name']), None)
        if publish_table:
            publish_fields = {
                "发布标题": data.get("title", ""),
                "发布时间": int(time.time() * 1000),
                "发布平台": "微信公众号",
                "草稿/文章 ID": data.get("draft_id", ""),
                "负责人": Config.WECHAT_AUTHOR or "System"
            }
            self.feishu.add_records(publish_table['table_id'], [publish_fields])
            
        print(f"📊 已完成全链路数据同步。")

    def run_pipeline_step_1(self, record_id, fields):
        """
        阶段一：基于飞书文档内容进行 AI 改写，并生成“改后文档”
        """
        # doc_link 有可能是 attachment 结构也可能是 URL 字符串
        doc_link = fields.get("原文文档链接") or fields.get("原文文档")
        url = fields.get("文章 URL")
        
        # 1. 优先读取飞书文档内容（实现人工干预）
        article_data = None
        doc_token = None
        
        if isinstance(doc_link, dict): # 处理超链接字段 (11)
            doc_link = doc_link.get('url', '')
        elif isinstance(doc_link, list) and len(doc_link) > 0:
            doc_link = doc_link[0].get('text', '') or doc_link[0].get('url', '')
        
        if doc_link and ("docx" in str(doc_link) or "file" in str(doc_link) or "http" in str(doc_link)):
            import re
            match = re.search(r'([a-zA-Z0-9]{27,})', str(doc_link))
            doc_token = match.group(1) if match else str(doc_link).split('/')[-1].split('?')[0]
            if len(doc_token) >= 27:
                article_data = self.feishu.get_docx_content(doc_token)
                article_data['url'] = url # 必须注入 URL，供后续改写引擎使用
                if article_data:
                    char_count = len(article_data.get('content_raw', ''))
                    print(f"   📊 成功提取飞书内容: {char_count} 字")
                else:
                    print(f"   ❌ 飞书文档内容提取失败")
            else:
                print(f"⚠️ 提取到的 Token 格式不正确: {doc_token}")
        
        # 兜底：如果读不到文档，则按 URL 抓取
        if not article_data and url:
            print(f"⚠️ 飞书文档读取失败或不存在，回退至 URL 直接抓取: {url}")
            article_data = self.step_collect(url)
            
        if not article_data:
            print("❌ 无法获取任何原始内容，中止任务。")
            return

        # 2. 调用 AI 进行角色化改写 (默认深度模式)
        rewritten = self.step_rewrite(article_data, role_key="tech_expert", model_key="volcengine")
        if not rewritten: return

        # 3. 创建“改后文档”供用户在线确认
        print(f"📄 正在创建 [改后专家稿] 文档...")
        new_doc_id, new_doc_url = self.feishu.create_docx(title=f"【AI改后稿】{rewritten['title']}")
        if new_doc_id:
            # 配置权限：企业内员工可编辑，并添加管理员
            self.feishu.set_tenant_manageable(new_doc_id)
            admin_id = os.getenv("FEISHU_ADMIN_USER_ID")
            if admin_id:
                self.feishu.add_collaborator(new_doc_id, admin_id, "full_access")
                
            # 将 HTML 转为块并回写
            blocks, _ = self.feishu.html_to_docx_blocks(rewritten['content'], new_doc_id)
            if blocks:
                self.feishu.append_docx_blocks(new_doc_id, blocks)
            
        rewritten_doc_link = fields.get("改后文档链接")
        if isinstance(rewritten_doc_link, dict):
            rewritten_doc_link = rewritten_doc_link.get('url', '')
        elif isinstance(rewritten_doc_link, list) and len(rewritten_doc_link) > 0:
            rewritten_doc_link = rewritten_doc_link[0].get('url', '') or rewritten_doc_link[0].get('text', '')
        
        # 尝试从主字段提取 Token
        import re
        doc_token = ""
        if rewritten_doc_link:
            match = re.search(r'([a-zA-Z0-9]{27,})', str(rewritten_doc_link))
            if match: doc_token = match.group(1)

        # 兜底：从备注字段尝试提取
        if not doc_token:
            memo = str(fields.get("备注", ""))
            match = re.search(r'([a-zA-Z0-9]{27,})', memo)
            if match:
                doc_token = match.group(1)
                print(f"   💡 从备注字段成功恢复 Token: {doc_token}")

        mgmt_url = "https://t0woxppdywz.feishu.cn/base/KkDFb19FNazzaNs7tNRcdyZNnWb"
        if len(doc_token) < 27:
            print(f"❌ 链接无效，无法提取 Token")
            self.feishu.update_record(fields.get('_table_id'), record_id, {
                "数据流程状态": f"✨ 已改写(待审)\n环节 2: 链接解析失败，请检查备注\n后台链接: {mgmt_url}",
                "备注": f"⚠️ 链接解析失败。请手动确保‘改后文档链接’单元格包含完整的 URL。"
            })
            return
        mgmt_url = "https://t0woxppdywz.feishu.cn/base/KkDFb19FNazzaNs7tNRcdyZNnWb"
        
        update_fields = {
            "标题": rewritten['title'],
            "改后文档链接": new_doc_url,
            "数据流程状态": f"✨ 已改写(待审)\n环节 2: 请审查改后文档并确认发布\n后台链接: {mgmt_url}",
            "备注": (
                f"【AI 文档备份】{new_doc_url}\n"
                f"AI 已生成初稿。请在‘改后文档’审查后，点击‘确认发布’复选框。"
            )
        }
        
        self.feishu.update_record(fields.get('_table_id'), record_id, update_fields)
        print(f"✅ 阶段一完成：AI 改写稿已创建，请在飞书表格中查看并一键发布。")

    def run_pipeline_step_2(self, record_id, fields):
        """
        阶段二：确认发布。读取“改后文档”最新内容并正式推送至微信。
        """
        rewritten_doc_link = fields.get("改后文档链接")
        print(f"DEBUG: All fields keys: {list(fields.keys())}")
        for k, v in fields.items():
            if '文档' in k or '链接' in k:
                print(f"DEBUG: Field '{k}' value: {v} (type={type(v)})")
        print(f"DEBUG: rewritten_doc_link type={type(rewritten_doc_link)} value={rewritten_doc_link}")
        if isinstance(rewritten_doc_link, dict):
            rewritten_doc_link = rewritten_doc_link.get('url', '')
        elif isinstance(rewritten_doc_link, list) and len(rewritten_doc_link) > 0:
            # 处理富文本/多项记录链接
            rewritten_doc_link = rewritten_doc_link[0].get('url', '') or rewritten_doc_link[0].get('text', '')
        
        if not rewritten_doc_link:
            print("❌ 找不到改后文档链接，请先通过 AI 改写生成。")
            self.feishu.update_record(fields.get('_table_id'), record_id, {"数据流程状态": "❌ 失败", "备注": "缺失改后文档"})
            return

        mgmt_url = "https://t0woxppdywz.feishu.cn/base/KkDFb19FNazzaNs7tNRcdyZNnWb"
        
        # 优化 token 提取
        import re
        match = re.search(r'([a-zA-Z0-9]{27,})', str(rewritten_doc_link))
        doc_token = match.group(1) if match else str(rewritten_doc_link).split('/')[-1].split('?')[0]
        
        if len(doc_token) < 27:
            print(f"❌ 链接无效，无法提取 Token: {doc_token}")
            self.feishu.update_record(fields.get('_table_id'), record_id, {
                "数据流程状态": f"✨ 已改写(待审)\n环节 2: 链接无效，请修正\n后台链接: {mgmt_url}", # 退回状态
                "备注": "⚠️ 链接字段被污染，请手动将正确的飞书文档 URL 粘贴回此单元格。"
            })
            return

        # 更新状态为“发布中”
        self.feishu.update_record(fields.get('_table_id'), record_id, {
            "数据流程状态": f"正在发布：{fields.get('标题', '')[:10]}... (环节 2: 公众号同步中)\n后台预览: {mgmt_url}"
        })

        print(f"📤 [最终发布] 正在从确认稿读取最新修改并同步: {doc_token}")
        final_article = self.feishu.get_docx_content(doc_token)
        if not final_article:
            raise Exception("读取确认稿失败，请检查文档链接是否有效")

        # 清除标题内的 AI 冗余前缀
        import re
        clean_title = final_article['title']
        clean_title = re.sub(r'^【AI改后稿】\s*', '', clean_title)
        clean_title = re.sub(r'^[标题|Title][:：]\s*', '', clean_title)
        clean_title = re.sub(r'^#+\s*', '', clean_title).strip()

        digest_clean = final_article['content_raw'].replace('\n', ' ').strip()
        draft_id = self.step_publish({
            "title": clean_title,
            "content": final_article['content_html'],
            "digest": digest_clean[:54] + "..." if len(digest_clean) > 54 else digest_clean
        }, original_images=[])

        if draft_id:
            # 标记为全通
            mgmt_url = "https://t0woxppdywz.feishu.cn/base/KkDFb19FNazzaNs7tNRcdyZNnWb"
            update_fields = {
                "标题": clean_title,
                "草稿 ID": draft_id,
                "数据流程状态": f"✨ 流程全通\n已同步至草稿箱 (无需后续操作)\n后台链接: {mgmt_url}",
                "备注": f"文章已成功作为草稿同步至微信公众号 (ID: {draft_id})。流程圆满结束。"
            }
            self.feishu.update_record(fields.get('_table_id'), record_id, update_fields)
            
            # 归档
            self.log_to_all_feishu_tables({
                "url": fields.get("文章 URL", ""),
                "title": clean_title,
                "draft_id": draft_id,
                "role": "tech_expert",
                "model": "volcengine"
            }, source_record_id=record_id)
            print(f"✨ 发布任务圆满完成！草稿 ID: {draft_id}")

    def run_with_params(self, url, role_key, model_key, source_record_id=None):
        start_time = time.time()
        
        # 1. 抓取
        article_data = self.step_collect(url)
        if not article_data: return

        # 2. 改写
        rewritten = self.step_rewrite(article_data, role_key, model_key)
        if not rewritten: return

        # 3. 发布
        draft_id = self.step_publish(rewritten, original_images=article_data.get('images', []))
        
        if draft_id:
            # 同步到所有飞书表格
            self.log_to_all_feishu_tables({
                "url": url,
                "title": rewritten['title'],
                "originality": rewritten.get('originality', 85),
                "draft_id": draft_id,
                "model": model_key,
                "role": role_key
            }, source_record_id=source_record_id)
            
            total_time = round(time.time() - start_time, 2)
            print(f"\n✨ 全流程自动化完成! 总耗时: {total_time}s")

    # --- 核心流水线控制: 监听内容库状态 ---
    def start_pipeline_loop(self, interval=30):
        """扫描 [小龙虾智能内容库] 表格，处理状态为 '✅ 采集完成' 的选题"""
        print(f"🕵️ [流水线] 监听程序已启动，扫描间隔: {interval}s")
        
        while True:
            try:
                tables = self.feishu.list_tables()
                inbox_table = next((t for t in tables if "智能内容库" in t['name']), None)
                
                if not inbox_table:
                    print("⚠️ 找不到 [小龙虾智能内容库] 表格")
                    time.sleep(interval)
                    continue

                # 扫描记录
                records_data = self.feishu.list_records(inbox_table['table_id'])
                
                if not records_data or not records_data.get('items'):
                    time.sleep(interval)
                    continue
                
                found_task = False

                for record in records_data.get('items', []):
                    fields = record.get('fields', {})
                    status = fields.get('数据流程状态')
                    record_id = record.get('record_id')
                    
                    if record_id in self.processing_records:
                        continue # 跳过当前正在执行的任务
                        
                    fields['_table_id'] = inbox_table['table_id'] # 传递上下文

                    status_str = str(status) if status else ""

                    # 流程一：发现新采集任务 -> AI 改写（若卡在‘处理中’也会尝试接管）
                    if "✅ 采集完成" in status_str or "正在处理" in status_str or status_str == "处理中":
                        print(f"\n" + "="*50)
                        print(f"🚀 [环节 1: AI 深度改写] 开始处理: {fields.get('标题')}")
                        print(f"📍 目标表: 小龙虾智能内容库")
                        print(f"🔗 管理后台: https://t0woxppdywz.feishu.cn/base/KkDFb19FNazzaNs7tNRcdyZNnWb")
                        print("="*50)
                        
                        # 更新状态为“处理中”
                        mgmt_url = "https://t0woxppdywz.feishu.cn/base/KkDFb19FNazzaNs7tNRcdyZNnWb"
                        self.feishu.update_record(self.smart_table_id, record_id, {
                            "数据流程状态": f"正在处理：{fields.get('标题', '')[:10]}... (环节 1: AI 深度改写中)\n后台预览: {mgmt_url}"
                        })
                        self.processing_records.add(record_id)
                        try:
                            self.run_pipeline_step_1(record_id, fields)
                            print(f"✅ [改写完成] 已生成文档并等待人工审核。")
                        except Exception as e:
                            print(f"❌ 阶段一执行失败: {e}")
                            self.feishu.update_record(inbox_table['table_id'], record_id, {"数据流程状态": "❌ 失败", "备注": str(e)})
                        finally:
                            self.processing_records.remove(record_id)

                    # 流程二：人工审核通过 -> 确认发布
                    elif "🚀 确认发布" in status_str or "正在发布" in status_str or status_str == "发布中":
                        print(f"\n" + "="*50)
                        print(f"🚀 [环节 2: 微信同步收尾] 正在推送至草稿箱...")
                        print(f"🔗 管理后台: https://t0woxppdywz.feishu.cn/base/KkDFb19FNazzaNs7tNRcdyZNnWb")
                        print("="*50)
                        
                        self.feishu.update_record(inbox_table['table_id'], record_id, {"数据流程状态": "发布中"})
                        self.processing_records.add(record_id)
                        try:
                            self.run_pipeline_step_2(record_id, fields)
                            print(f"✅ [发布成功] 请前往公众号后台查看草稿。")
                        except Exception as e:
                            print(f"❌ 阶段二执行失败: {e}")
                            self.feishu.update_record(inbox_table['table_id'], record_id, {"数据流程状态": "❌ 审核错误", "备注": str(e)})
                        finally:
                            self.processing_records.remove(record_id)

            except Exception as e:
                print(f"❌ 循环异常: {e}")
            
            time.sleep(interval)

if __name__ == "__main__":
    manager = AutoPlatformManager()
    
    # 命令行用法: 
    # 1. 处理单条: python manager.py <URL> [角色] [模型]
    # 2. 开启流水线模式: python manager.py pipeline
    
    if len(sys.argv) < 2:
        print("用法:")
        print("  单条处理: python manager.py <文章URL> [角色KEY] [模型KEY]")
        print("  监听模式: python manager.py pipeline")
        sys.exit(1)
        
    arg1 = sys.argv[1]
    
    if arg1 == "pipeline":
        manager.start_pipeline_loop()
    else:
        url = arg1
        role = sys.argv[2] if len(sys.argv) > 2 else "tech_expert"
        model = sys.argv[3] if len(sys.argv) > 3 else "volcengine"
        manager.run_with_params(url, role, model)
