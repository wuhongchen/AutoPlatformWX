from datetime import datetime
import re
from modules.state_machine import PipelineState

class InspirationSyncEngine:
    """
    同步引擎 (Sync Engine)
    核心任务：将已审核的灵感从“灵感库”同步到“流水线库”
    """
    def __init__(self, feishu_client, inspiration_table_id, pipeline_table_id):
        self.feishu = feishu_client
        self.inspiration_table_id = inspiration_table_id
        self.pipeline_table_id = pipeline_table_id

    def _field_to_text(self, field_val):
        if not field_val:
            return ""
        if isinstance(field_val, dict):
            return str(field_val.get("url", "") or field_val.get("link", "") or field_val.get("text", "")).strip()
        if isinstance(field_val, list) and len(field_val) > 0:
            first = field_val[0]
            if isinstance(first, dict):
                return str(first.get("url", "") or first.get("link", "") or first.get("text", "")).strip()
            return str(first).strip()
        return str(field_val).strip()

    def _extract_doc_token(self, field_val):
        val_str = self._field_to_text(field_val)
        if not val_str:
            return None
        m_url = re.search(r"feishu\.cn/docx/([A-Za-z0-9]{27,})", val_str)
        if m_url:
            return m_url.group(1)
        if re.fullmatch(r"[A-Za-z0-9]{27,60}", val_str):
            return val_str
        return None

    def _normalize_doc_url(self, field_val):
        token = self._extract_doc_token(field_val)
        if token:
            return f"https://www.feishu.cn/docx/{token}"
        return ""

    def sync_to_pipeline(self, record_id, record_fields):
        """同步单条记录"""
        print(f"🚀 [同步] 正在流转灵感: {record_fields.get('标题')}")
        
        # 构造流水线条目
        # 这里的映射关系：灵感库 -> 小龙虾智能内容库
        # 提取真实的文档链接，避免写过去变成标题文本或复杂对象
        doc_url = self._normalize_doc_url(record_fields.get("原文文档")) or self._normalize_doc_url(record_fields.get("原文文档链接"))
        revised_doc_url = self._normalize_doc_url(record_fields.get("改后文档链接"))
            
        pipeline_data = {
            "文章 URL": record_fields.get("文章 URL", ""),
            "标题": record_fields.get("标题", ""),
            "原文文档链接": doc_url,
            "备注": f"来自灵感库。AI 推荐评分: {record_fields.get('AI 爆款潜力评分')}。理由: {record_fields.get('AI 推荐理由')}",
            "数据流程状态": PipelineState.QUEUED_REWRITE, # 同步过去后进入待改写节点
            "负责人": "AI-Sync"
        }
        # 仅当灵感库已存在“改后文档链接”时才同步，避免误触发“待改写”去重跳过
        if revised_doc_url:
            pipeline_data["改后文档链接"] = revised_doc_url
        
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
