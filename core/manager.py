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
        # 获取核心表 ID
        tables = self.feishu.list_tables()
        table = next((t for t in tables if Config.FEISHU_PIPELINE_TABLE in t['name']), None)
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

    # --- 记录管理: 全链路同步至飞书三个表格 ---
    def log_to_all_feishu_tables(self, data, source_record_id=None):
        """将运行结果同步至：1.内容灵感库(溯源) 2.小龙虾智能内容库(流水线) 3.发布记录表(归档)"""
        tables = self.feishu.list_tables()
        
        # 1. 更新 [内容灵感库] 的状态 (溯源)
        inbox_table = next((t for t in tables if t['name'] == "内容灵感库"), None)
        if inbox_table and data.get("url"):
            # 尝试通过“文章 URL”反查灵感库 ID
            records = self.feishu.list_records(inbox_table['table_id']).get('items', [])
            for r in records:
                fields = r.get('fields', {})
                if fields.get('文章 URL') == data['url'] or fields.get('原链接') == data['url']:
                    self.feishu.update_record(inbox_table['table_id'], r['record_id'], {"处理状态": "已处理"}) # 注意：原状态字段可能是 处理状态 或者什么，先标记为已处理
                    break

        # 2. 已在流水线中直接更新，无需额外逻辑
        
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
        
        if role_key == "tech_expert":
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
            
        rewritten = self.processor.rewrite(article_data, role_key=role_key, model_key=model_key)
        if not rewritten:
            print("❌ 改写失败")
            return None
        print(f"   ✅ 改写完成: {rewritten['title']}")
        return rewritten

    # --- 步骤 3: 内容发布 (微信 + 封面图) ---
    def step_publish(self, rewritten_data, original_images=[]):
        print(f"\n📤 [步骤 3/3] 正在同步至微信公众平台...")
        
        cover_path = self.processor.generate_cover(f"为文章 '{rewritten_data['title']}' 生成一张高质量封面图")
        
        thumb_media_id = ""
        if cover_path and os.path.exists(cover_path):
            thumb_media_id = self.publisher.upload_material(cover_path)
            
        if not thumb_media_id:
            fallback_url = original_images[0] if original_images else Config.DEFAULT_COVER_URL
            if fallback_url:
                thumb_media_id = self.publisher.upload_from_url(fallback_url)
        
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

        # 深度应用微信公众号排版样式与标题清理
        from modules.mp_processor import WeChatFormatter
        content_html = WeChatFormatter.deep_optimize_format(content_html)
        clean_title = WeChatFormatter.optimize_title(rewritten_data['title'])
        
        draft_id = self.publisher.publish_draft(
            title=clean_title,
            content_html=content_html,
            digest=rewritten_data['digest'],
            thumb_media_id=thumb_media_id or ""
        )
        
        if draft_id:
            print(f"   ✅ 微信同步成功! 草稿 ID: {draft_id}")
        return draft_id

    def run_pipeline_step_1(self, record_id, fields):
        """环节 1: AI 改写"""
        doc_link = fields.get("原文文档链接") or fields.get("原文文档")
        url = fields.get("文章 URL")
        
        article_data = None
        if isinstance(doc_link, dict): doc_link = doc_link.get('url', '')
        elif isinstance(doc_link, list) and len(doc_link) > 0: doc_link = doc_link[0].get('text', '') or doc_link[0].get('url', '')
        
        if doc_link and any(x in str(doc_link) for x in ["docx", "file", "http"]):
            match = re.search(r'([a-zA-Z0-9]{27,})', str(doc_link))
            doc_token = match.group(1) if match else str(doc_link).split('/')[-1].split('?')[0]
            if len(doc_token) >= 27:
                article_data = self.feishu.get_docx_content(doc_token)
                article_data['url'] = url
        
        if not article_data and url:
            article_data = self.step_collect(url)
            
        if not article_data: return

        rewritten = self.step_rewrite(article_data, role_key="tech_expert", model_key="volcengine")
        if not rewritten: return

        new_doc_id, new_doc_url = self.feishu.create_docx(title=f"【AI改后稿】{rewritten['title']}")
        if new_doc_id:
            self.feishu.set_tenant_manageable(new_doc_id)
            admin_id = os.getenv("FEISHU_ADMIN_USER_ID")
            if admin_id: self.feishu.add_collaborator(new_doc_id, admin_id, "full_access")
            blocks, _ = self.feishu.html_to_docx_blocks(rewritten['content'], new_doc_id)
            if blocks: self.feishu.append_docx_blocks(new_doc_id, blocks)
            
        update_fields = {
            "数据流程状态": "✨ 已改写(待审)",
            "备注": f"AI 已生成草稿：{new_doc_url}",
            "改后文档链接": new_doc_url
        }
        self.feishu.update_record(fields.get('_table_id'), record_id, update_fields)

    def run_pipeline_step_2(self, record_id, fields):
        """环节 2: 确认发布"""
        # 从改后文档链接或备注中提取 27 位文档 Token
        doc_token = None
        for field_val in [fields.get("改后文档链接"), fields.get("备注")]:
            if not field_val: continue
            
            val_str = ""
            if isinstance(field_val, dict): val_str = field_val.get('url', '') or field_val.get('text', '')
            elif isinstance(field_val, list) and len(field_val) > 0: val_str = field_val[0].get('url', '') or field_val[0].get('text', '')
            else: val_str = str(field_val)
            
            match = re.search(r'([a-zA-Z0-9]{27,})', val_str)
            if match:
                doc_token = match.group(1)
                break
                
        if not doc_token or len(doc_token) < 27:
            print("❌ 无法从数据记录中解析有效的 Feishu Document Token。")
            return

        final_article = self.feishu.get_docx_content(doc_token)
        if not final_article: raise Exception("读取确认稿失败")

        clean_title = re.sub(r'^【AI改后稿】\s*', '', final_article['title'])
        clean_title = re.sub(r'^[标题|Title][:：]\s*', '', clean_title)
        clean_title = re.sub(r'^#+\s*', '', clean_title).strip()

        digest_clean = final_article['content_raw'].replace('\n', ' ').strip()
        draft_id = self.step_publish({
            "title": clean_title,
            "content": final_article['content_html'],
            "digest": digest_clean[:54] + "..." if len(digest_clean) > 54 else digest_clean
        }, original_images=[])

        if draft_id:
            self.feishu.update_record(fields.get('_table_id'), record_id, {
                "标题": clean_title,
                "草稿 ID": draft_id,
                "数据流程状态": "✨ 流程全通",
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

    def start_pipeline_loop(self, interval=30):
        print(f"🕵️ [流水线] 监听中...")
        while True:
            try:
                tables = self.feishu.list_tables()
                inbox_table = next((t for t in tables if "智能内容库" in t['name']), None)
                if not inbox_table: 
                    time.sleep(interval)
                    continue
                records_data = self.feishu.list_records(inbox_table['table_id'])
                for record in records_data.get('items', []):
                    fields = record.get('fields', {})
                    status = str(fields.get('数据流程状态', ''))
                    record_id = record.get('record_id')
                    if record_id in self.processing_records: continue
                    fields['_table_id'] = inbox_table['table_id']

                    if status == "✅ 采集完成" or status == "处理中":
                        print(f"🚀 开始改写: {fields.get('标题')}")
                        try:
                            self.feishu.update_record(fields['_table_id'], record_id, {"数据流程状态": "处理中"})
                            self.processing_records.add(record_id)
                            self.run_pipeline_step_1(record_id, fields)
                        except Exception as e:
                            print(f"❌ 改写步骤异常: {e}")
                            self.feishu.update_record(fields['_table_id'], record_id, {
                                "数据流程状态": "❌ 改写失败",
                                "备注": f"AI 改写或排版失败，原因: {str(e)}"
                            })
                        finally:
                            if record_id in self.processing_records:
                                self.processing_records.remove(record_id)

                    elif status == "🚀 确认发布" or status == "发布中":
                        print(f"📤 开始发布: {fields.get('标题')}")
                        try:
                            self.feishu.update_record(fields['_table_id'], record_id, {"数据流程状态": "发布中"})
                            self.processing_records.add(record_id)
                            self.run_pipeline_step_2(record_id, fields)
                        except Exception as e:
                            print(f"❌ 发布步骤异常: {e}")
                            self.feishu.update_record(fields['_table_id'], record_id, {
                                "数据流程状态": "❌ 发布失败",
                                "备注": f"推送到微信失败，原因: {str(e)}"
                            })
                        finally:
                            if record_id in self.processing_records:
                                self.processing_records.remove(record_id)

            except Exception as e: print(f"❌ 循环异常: {e}")
            time.sleep(interval)

if __name__ == "__main__":
    manager = AutoPlatformManager()
    if len(sys.argv) < 2: sys.exit(1)
    if sys.argv[1] == "pipeline": manager.start_pipeline_loop()
    else: manager.run_with_params(sys.argv[1], "tech_expert", "volcengine")
