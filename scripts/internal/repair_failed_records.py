import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from config import Config
from modules.feishu import FeishuBitable
from modules.state_machine import PipelineState, canonical_pipeline_status


def field_to_text(field_val):
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


def extract_doc_token(*field_vals):
    for field_val in field_vals:
        val_str = field_to_text(field_val)
        if not val_str:
            continue
        m_url = re.search(r"feishu\.cn/docx/([A-Za-z0-9]{27,})", val_str)
        if m_url:
            return m_url.group(1)
        if re.fullmatch(r"[A-Za-z0-9]{27,60}", val_str):
            return val_str
    return None


def repair():
    feishu = FeishuBitable(
        Config.FEISHU_APP_ID,
        Config.FEISHU_APP_SECRET,
        Config.FEISHU_APP_TOKEN
    )
    if not feishu._get_token():
        print("❌ 获取飞书 token 失败")
        return

    table_id = feishu.get_table_id_by_name(Config.FEISHU_PIPELINE_TABLE) or feishu.get_table_id_by_name("小龙虾智能内容库")
    if not table_id:
        print("❌ 未找到流水线表")
        return

    items = feishu.list_records(table_id).get("items", [])

    fixed_publish_link = 0
    reset_publish_to_ready = 0
    reset_publish_to_rewrite = 0
    annotated_rewrite_fail = 0

    for item in items:
        record_id = item.get("record_id")
        fields = item.get("fields", {})
        status = canonical_pipeline_status(fields.get("数据流程状态", ""))
        remark = field_to_text(fields.get("备注"))

        if status == PipelineState.PUBLISH_FAILED:
            token = extract_doc_token(
                fields.get("改后文档链接"),
                fields.get("备注"),
                fields.get("原文文档链接"),
                fields.get("原文文档"),
            )
            if token:
                normalized_url = f"https://www.feishu.cn/docx/{token}"
                link_text = field_to_text(fields.get("改后文档链接"))
                new_remark = remark or ""
                if "[AutoRepair]" not in new_remark:
                    suffix = f" [AutoRepair] 已修复改后文档链接并回退到“{PipelineState.PUBLISH_READY}”，可重试发布。"
                    new_remark = (new_remark + suffix).strip()
                update_payload = {
                    "改后文档链接": normalized_url,
                    "备注": new_remark,
                    "数据流程状态": PipelineState.PUBLISH_READY
                }
                ok = feishu.update_record(table_id, record_id, update_payload)
                if ok:
                    if normalized_url != link_text:
                        fixed_publish_link += 1
                    reset_publish_to_ready += 1
            else:
                # 没有任何可用 token，无法直接发布；回退到改写入口重跑
                new_remark = (remark + f" [AutoRepair] 未解析到改后文档 token，已回退到“{PipelineState.QUEUED_REWRITE}”以便重跑改写。").strip()
                ok = feishu.update_record(table_id, record_id, {
                    "数据流程状态": PipelineState.QUEUED_REWRITE,
                    "改后文档链接": "",
                    "备注": new_remark
                })
                if ok:
                    reset_publish_to_rewrite += 1

        if status == PipelineState.REWRITE_FAILED:
            if "原因:" not in remark:
                ok = feishu.update_record(table_id, record_id, {
                    "备注": (remark + f" [AutoRepair] 历史失败记录缺少异常详情，请重置为“{PipelineState.QUEUED_REWRITE}”后重跑以生成可追踪失败原因。").strip()
                })
                if ok:
                    annotated_rewrite_fail += 1

    print(f"✅ 发布失败记录链接修复: {fixed_publish_link} 条")
    print(f"✅ 发布失败记录恢复待发布: {reset_publish_to_ready} 条")
    print(f"✅ 发布失败记录回退重跑: {reset_publish_to_rewrite} 条")
    print(f"✅ 改写失败记录备注补全: {annotated_rewrite_fail} 条")


if __name__ == "__main__":
    repair()
