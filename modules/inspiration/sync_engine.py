from datetime import datetime

class InspirationSyncEngine:
    """
    同步引擎 (Sync Engine)
    核心任务：将已审核的灵感从“灵感库”同步到“流水线库”
    """
    def __init__(self, feishu_client, inspiration_table_id, pipeline_table_id):
        self.feishu = feishu_client
        self.inspiration_table_id = inspiration_table_id
        self.pipeline_table_id = pipeline_table_id

    def sync_to_pipeline(self, record_id, record_fields):
        """同步单条记录"""
        print(f"🚀 [同步] 正在流转灵感: {record_fields.get('标题')}")
        
        # 构造流水线条目
        # 这里的映射关系：灵感库 -> 小龙虾智能内容库
        # 提取真实的文档链接，避免写过去变成带标题的复杂对象和文本
        doc_link = record_fields.get("原文文档", "")
        doc_url = ""
        if isinstance(doc_link, dict):
            doc_url = doc_link.get('link', '') or doc_link.get('url', '') or doc_link.get('text', '')
        elif isinstance(doc_link, list) and len(doc_link) > 0:
            if isinstance(doc_link[0], dict):
                doc_url = doc_link[0].get('link', '') or doc_link[0].get('url', '') or doc_link[0].get('text', '')
            else:
                doc_url = str(doc_link[0])
        else:
            doc_url = str(doc_link)
            
        pipeline_data = {
            "文章 URL": record_fields.get("文章 URL", ""),
            "标题": record_fields.get("标题", ""),
            "原文文档链接": doc_url,
            "备注": f"来自灵感库。AI 推荐评分: {record_fields.get('AI 爆款潜力评分')}。理由: {record_fields.get('AI 推荐理由')}",
            "数据流程状态": "✅ 采集完成", # 同步过去后，初始状态为采集完成
            "负责人": "AI-Sync"
        }
        
        # 1. 写入流水线库
        res = self.feishu.add_records(self.pipeline_table_id, [pipeline_data])
        if res:
            # 2. 更新灵感库状态为“已采用”，防止重复同步
            update_fields = {
                "处理状态": "已采用",
                "同步时间": int(datetime.now().timestamp() * 1000)
            }
            self.feishu.update_record(self.inspiration_table_id, record_id, update_fields)
            print(f"✅ [同步] 成功同步至流水线库。")
            return True
        return False
