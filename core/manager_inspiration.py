import os
import sys
import time

# 兼容 OpenClaw 运行方式：确保能从项目根目录找到 modules
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from dotenv import load_dotenv
from modules.feishu import FeishuBitable
from modules.inspiration.collector import InspirationCollector
from modules.inspiration.analyzer import InspirationAnalyzer
from modules.inspiration.sync_engine import InspirationSyncEngine

load_dotenv()

class InspirationManager:
    """
    灵感库主控程序
    """
    def __init__(self):
        # 初始化飞书客户端
        app_id = os.getenv("FEISHU_APP_ID")
        app_secret = os.getenv("FEISHU_APP_SECRET")
        app_token = os.getenv("FEISHU_APP_TOKEN")
        self.feishu = FeishuBitable(app_id, app_secret, app_token)
        
        # 获取表格 ID
        # 优化点：使用更具有标识性的名称，建议手动同步修改飞书上的表名
        self.inspiration_table_id = self.feishu.get_table_id_by_name("01_内容灵感库 (OpenClaw)") or self.feishu.get_table_id_by_name("内容灵感库")
        self.pipeline_table_id = self.feishu.get_table_id_by_name("02_自动化发布队列 (OpenClaw)") or self.feishu.get_table_id_by_name("小龙虾智能内容库")
        
        # 初始化组件
        self.collector = InspirationCollector()
        self.analyzer = InspirationAnalyzer()
        self.sync_engine = InspirationSyncEngine(self.feishu, self.inspiration_table_id, self.pipeline_table_id)

        # 自动化字段初始化：确保灵感库有这些关键字段
        if self.inspiration_table_id:
            self._ensure_fields()

    def _ensure_fields(self):
        """确保必要的字段存在"""
        required_fields = [
            ("标题", 1),
            ("AI 爆款潜力评分", 2),
            ("核心洞察", 1),
            ("所属领域", 1),
            ("原始标题", 1),
            ("AI 推荐理由", 1),
            ("建议改写方向", 1),
            ("处理状态", 1),
            ("文章 URL", 1),
            ("原文文档", 1), # 改回文本类型
            ("同步时间", 5), # 5 是日期时间，但简化用 1 也没关系
            ("图片", 17)    # 17 是附件/图片
        ]
        # 获取现有字段
        # Note: 这里的 feishu.py 可能没有 list_fields 的 alias，我直接用 create_field (API 会自动处理已存在的情况)
        print("🛠️ 正在检查/同步灵感库字段结构...")
        for name, ftype in required_fields:
            # create_field 内部如果 code=0 或 code=1254302(已存在) 都会返回
            self.feishu.create_field(self.inspiration_table_id, name, ftype)

    def run_once(self):
        """执行一个周期的任务"""
        print(f"\n🔄 [灵感库] 任务周期启动...")
        
        if not self.inspiration_table_id:
            print("❌ 找不到 [内容灵感库] 表格")
            return

        # 1. 处理待分析任务 (URL 存在但标题/分析为空)
        processed_count = 0
        records_data = self.feishu.list_records(self.inspiration_table_id)
        if records_data:
            items = records_data.get('items', [])
            for i, record in enumerate(items):
                fields = record.get('fields', {})
                if i == 0: # 仅对第一条记录输出可见列，方便调试字段名
                    print(f"🕵️ [灵感库] 检测到的列名: {list(fields.keys())}")
                record_id = record.get('record_id')
                url = fields.get('文章 URL')
                title = fields.get('标题')
                status = fields.get('处理状态')

                # 情况 A：有 URL 但没处理过，或者用户点击了“待分析”来触发重跑
                if url and (not title or title == "None" or status == "待分析"):
                    self._process_new_url(record_id, url)
                    processed_count += 1
                
                # 情况 B：用户改了状态为“已同步”，且状态仍为“已同步”时流转
                if status == "已同步":
                    self.sync_engine.sync_to_pipeline(record_id, fields)
                    processed_count += 1
            
        if processed_count == 0:
            print("😴 暂无待分析或待同步的任务，灵感库已全部处理完成。")
        else:
            print(f"✨ 本次周期处理完成，共计操作 {processed_count} 条记录。")

    def _process_new_url(self, record_id, url):
        """处理新入库的 URL"""
        print(f"✨ 正在处理新选题: {url}")
        
        article = None
        # 1. 识别并采集内容
        if "feishu.cn/docx/" in url or "feishu.cn/wiki/" in url:
            # 处理飞书文档或 Wiki 链接
            import re
            # docx 模式
            docx_match = re.search(r"/docx/([^/?]+)", url)
            # wiki 模式
            wiki_match = re.search(r"/wiki/([^/?]+)", url)
            
            target_id = None
            if docx_match:
                target_id = docx_match.group(1)
            elif wiki_match:
                # 注意：Wiki ID 需要通过接口转换成 docx_id，为了简化，这里先尝试直接匹配
                target_id = wiki_match.group(1)
            
            if target_id:
                print(f"🔍 检测到飞书文档/Wiki 链接，尝试通过 API 获取纯净内容...")
                article = self.feishu.get_docx_content(target_id)
        
        if not article:
            # 默认使用通用采集器 (微信等)
            article = self.collector.fetch_with_metrics(url)
            
        if not article:
            print(f"❌ 无法处理该链接的内容: {url}")
            # 如果抓取失败（如 403），回写一个状态，告知用户
            self.feishu.update_record(self.inspiration_table_id, record_id, {
                "处理状态": "待审",
                "AI 推荐理由": "⚠️ 页面抓取失败 (可能是被封禁)，请点击‘原文文档’手动检查并填入内容。"
            })
            return
        
        # 2. 分析
        if not article.get('title'): article['title'] = "未命名文章"
        analysis = self.analyzer.analyze(article)
        
        # 3. 创建飞书文档并解析 HTML 回写格式 (支持图片转存)
        doc_id, doc_url = self.feishu.create_docx(title=f"【灵感原文】{article['title']}")
        bitable_img_tokens = [] # 用于多维表格的图片 token 列表
        
        if doc_id:
            # 1. 提权：设置为企业内员工可编辑
            self.feishu.set_tenant_manageable(doc_id)
            
            # 2. 指派特定管理员 (从 .env 读取)
            admin_id = os.getenv("FEISHU_ADMIN_USER_ID")
            if admin_id:
                self.feishu.add_collaborator(doc_id, admin_id, role="full_access")
            
            print(f"📄 正在回写带格式的正文至飞书文档 (包含图片转存): {doc_url}")
            blocks, uploaded_docx_tokens = self.feishu.html_to_docx_blocks(article['content_html'], doc_id)
            if blocks:
                self.feishu.append_docx_blocks(doc_id, blocks)
            else:
                # 兜底：如果 HTML 解析不到块，则按纯文本追加
                self.feishu.append_docx_blocks(doc_id, [{"block_type": 2, "text": {"elements": [{"text_run": {"content": article['content_raw'][:5000]}}]}}])
        
        # 4. 图片转存至多维表格 (独立转存，因为 Bitable 需要 bitable_image 类型的 token)
        if article.get('images'):
            print(f"📸 正在转存 {len(article['images'])} 张图片至灵感库素材字段...")
            for img_url in article['images'][:5]: # 限制前 5 张，避免表格太臃肿
                token = self.feishu.upload_image(img_url, parent_node=None, force_docx=False)
                if token:
                    bitable_img_tokens.append({"file_token": token})

        # 5. 回写飞书多维表格 (增加字段检查)
        update_fields = {
            "标题": analysis.get('title_zh', article.get('title', '未命名')), # 优先使用中文译名
            "AI 爆款潜力评分": analysis['score'],
            "AI 推荐理由": analysis['reason'],
            "建议改写方向": analysis['rewrite_direction'],
            "处理状态": "待审" 
        }

        # 获取表格完整列清单 (确保空列也能回写)
        existing_cols = self.feishu.get_table_columns(self.inspiration_table_id)
        
        if doc_url and "原文文档" in existing_cols:
            update_fields["原文文档"] = doc_url

        # 扩展新字段
        extra_map = {
            "核心洞察": analysis.get('insight', ''),
            "所属领域": analysis.get('domain', ''),
            "原始标题": article.get('title', ''),
            "同步时间": int(time.time() * 1000)
        }
        for k, v in extra_map.items():
            if k in existing_cols:
                update_fields[k] = v

        # 6. 自动化过滤：如果评分过低，直接跳过，减少噪音
        if analysis['score'] < 6:
            print(f"📉 评分较低 ({analysis['score']})，自动标记为 [已跳过]")
            update_fields["处理状态"] = "已跳过"
        
        # 如果有图片，写入附件字段
        img_field = "图片" if "图片" in existing_cols else ("素材" if "素材" in existing_cols else None)
        if bitable_img_tokens and img_field:
            update_fields[img_field] = bitable_img_tokens
            
        print(f"📊 正在回填飞书记录: {record_id} (有效字段: {', '.join(update_fields.keys())})")
        success = self.feishu.update_record(self.inspiration_table_id, record_id, update_fields)
        if success:
            print(f"✅ 信息已回写灵感库。")
        else:
            print(f"❌ 关键字段更新失败，请检查字段名称是否匹配。")

    def start_loop(self, interval=30):
        """开启循环扫描"""
        print(f"\n" + "="*50)
        print(f"🚀 [灵感库] 选题扫描引擎已启动")
        print(f"📍 监控间隔: {interval}s")
        print(f"🔗 管理后台: https://t0woxppdywz.feishu.cn/base/KkDFb19FNazzaNs7tNRcdyZNnWb")
        print("="*50)
        
        while True:
            try:
                self.run_once()
            except Exception as e:
                print(f"❌ 循环执行异常: {e}")
            time.sleep(interval)

if __name__ == "__main__":
    manager = InspirationManager()
    manager.start_loop()
