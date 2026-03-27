import os
from dotenv import load_dotenv

# 加载 .env 文件 (优先加载当前目录，其次加载 mp-draft-push 目录)
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "../mp-draft-push/.env"))


def _first_non_empty(*keys):
    for key in keys:
        val = (os.getenv(key) or "").strip()
        if val:
            return val
    return ""

class Config:
    # 微信配置
    WECHAT_APPID = os.getenv("WECHAT_APPID", "")
    WECHAT_SECRET = os.getenv("WECHAT_SECRET", "")
    WECHAT_AUTHOR = os.getenv("WECHAT_AUTHOR", "W 小龙虾")
    
    # 火山引擎配置 (即梦 AI)
    VOLCENGINE_AK = os.getenv("VOLCENGINE_AK")
    VOLCENGINE_SK = os.getenv("VOLCENGINE_SK")
    
    # LLM 配置
    # 支持 OpenClaw 代理与独立模型双模式
    LLM_API_KEY = _first_non_empty(
        "LLM_API_KEY",
        "VOLC_ARK_API_KEY",
        "OPENCLAW_PROXY_API_KEY",
        "OPENCLAW_LLM_API_KEY",
        "OPENCLAW_API_KEY",
        "OPENAI_API_KEY",
    )
    LLM_ENDPOINT = _first_non_empty(
        "LLM_ENDPOINT",
        "VOLC_ARK_ENDPOINT",
        "OPENCLAW_PROXY_ENDPOINT",
        "OPENCLAW_LLM_ENDPOINT",
        "OPENCLAW_ENDPOINT",
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
    ) or "https://ark.cn-beijing.volces.com/api/v3"
    VOLC_ARK_MODEL_ID = os.getenv("VOLC_ARK_MODEL_ID") or "doubao-seed-2-0-pro-260215"
    
    # 飞书多维表格配置
    FEISHU_APP_ID = os.getenv("FEISHU_APP_ID")
    FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET")
    FEISHU_APP_TOKEN = os.getenv("FEISHU_APP_TOKEN")
    FEISHU_INSPIRATION_TABLE = os.getenv("FEISHU_INSPIRATION_TABLE", "01_内容灵感库 (OpenClaw)")
    FEISHU_PIPELINE_TABLE = os.getenv("FEISHU_PIPELINE_TABLE", "02_自动化发布队列 (OpenClaw)")
    FEISHU_PUBLISH_LOG_TABLE = os.getenv("FEISHU_PUBLISH_LOG_TABLE", "发布记录")
    
    # 其他配置
    DEFAULT_COVER_URL = os.getenv("DEFAULT_COVER_URL")
    OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")

    # 公号广告位配置（用于发布模板注入）
    WECHAT_AD_ENABLED = os.getenv("WECHAT_AD_ENABLED", "0")
    WECHAT_AD_POSITION = os.getenv("WECHAT_AD_POSITION", "bottom")  # top | bottom | both
    WECHAT_AD_TITLE = os.getenv("WECHAT_AD_TITLE", "推广信息")
    WECHAT_AD_TEXT = os.getenv("WECHAT_AD_TEXT", "")
    WECHAT_AD_LINK_TEXT = os.getenv("WECHAT_AD_LINK_TEXT", "")
    WECHAT_AD_LINK_URL = os.getenv("WECHAT_AD_LINK_URL", "")
    WECHAT_AD_IMAGE_PATH = os.getenv("WECHAT_AD_IMAGE_PATH", "")  # 本地图片路径（推荐）
    WECHAT_AD_IMAGE_URL = os.getenv("WECHAT_AD_IMAGE_URL", "")    # 远程图片 URL（可选）
    WECHAT_AD_IMAGE_LINK_URL = os.getenv("WECHAT_AD_IMAGE_LINK_URL", "")
    
    @classmethod
    def check_keys(cls):
        """检查必要密钥是否完整"""
        missing = []
        openclaw_proxy_key = _first_non_empty(
            "OPENCLAW_PROXY_API_KEY",
            "OPENCLAW_LLM_API_KEY",
            "OPENCLAW_API_KEY",
            "OPENAI_API_KEY",
        )
        if not cls.WECHAT_APPID or not cls.WECHAT_SECRET:
            missing.append("WECHAT_APPID/SECRET")
        if not cls.LLM_API_KEY and not openclaw_proxy_key:
            missing.append("LLM_API_KEY 或 OPENCLAW_PROXY_API_KEY (用于 AI 改写)")
        if not cls.VOLCENGINE_AK or not cls.VOLCENGINE_SK:
            missing.append("VOLCENGINE AK/SK (用于封面生成)")
        return missing
