import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from dotenv import load_dotenv
from modules.models import get_runtime_default_model_key, has_openclaw_proxy_config

load_dotenv()
load_dotenv(os.path.join(PROJECT_ROOT, "../mp-draft-push/.env"))


def first_non_empty(*keys):
    for key in keys:
        val = (os.getenv(key) or "").strip()
        if val:
            return val
    return ""


def check_required():
    missing = []
    if not first_non_empty("WECHAT_APPID"):
        missing.append("WECHAT_APPID")
    if not first_non_empty("WECHAT_SECRET"):
        missing.append("WECHAT_SECRET")
    if not first_non_empty("FEISHU_APP_ID"):
        missing.append("FEISHU_APP_ID")
    if not first_non_empty("FEISHU_APP_SECRET"):
        missing.append("FEISHU_APP_SECRET")
    if not first_non_empty("FEISHU_APP_TOKEN"):
        missing.append("FEISHU_APP_TOKEN")
    return missing


def print_model_route():
    provider = (first_non_empty("OPENCLAW_MODEL_PROVIDER", "OPENCLAW_MODEL_SOURCE") or "auto").lower()
    default_model = get_runtime_default_model_key()
    proxy_endpoint = first_non_empty(
        "OPENCLAW_PROXY_ENDPOINT",
        "OPENCLAW_LLM_ENDPOINT",
        "OPENCLAW_ENDPOINT",
        "OPENAI_BASE_URL",
        "OPENAI_API_BASE",
    )
    proxy_key = first_non_empty(
        "OPENCLAW_PROXY_API_KEY",
        "OPENCLAW_LLM_API_KEY",
        "OPENCLAW_API_KEY",
        "OPENAI_API_KEY",
    )

    print("\n=== 模型路由检查 ===")
    print(f"OPENCLAW_MODEL_PROVIDER: {provider}")
    print(f"运行时默认模型: {default_model}")
    print(f"检测到 OpenClaw 代理配置: {'是' if has_openclaw_proxy_config() else '否'}")
    print(f"代理 endpoint: {'已配置' if proxy_endpoint else '未配置'}")
    print(f"代理 key: {'已配置' if proxy_key else '未配置'}")


def print_cover_route():
    provider = (first_non_empty("COVER_IMAGE_PROVIDER") or "auto").lower()
    ark_key = first_non_empty("ARK_IMAGE_API_KEY", "VOLC_ARK_API_KEY")
    ark_endpoint = first_non_empty("ARK_IMAGE_GENERATE_ENDPOINT", "ARK_IMAGE_ENDPOINT", "VOLC_ARK_ENDPOINT")
    jimeng_ak = first_non_empty("VOLCENGINE_AK")
    jimeng_sk = first_non_empty("VOLCENGINE_SK")

    print("\n=== 封面生图路由检查 ===")
    print(f"COVER_IMAGE_PROVIDER: {provider}")
    print(f"方舟 key: {'已配置' if ark_key else '未配置'}")
    print(f"方舟 endpoint: {'已配置' if ark_endpoint else '未配置'}")
    print(f"即梦 AK/SK: {'已配置' if (jimeng_ak and jimeng_sk) else '未配置'}")

    if provider == "ark" and (not ark_key or not ark_endpoint):
        print("⚠️ 当前为 ark 模式，但方舟生图配置不完整。")
    if provider == "jimeng" and (not jimeng_ak or not jimeng_sk):
        print("⚠️ 当前为 jimeng 模式，但即梦 AK/SK 配置不完整。")
    if provider == "auto" and not ((ark_key and ark_endpoint) or (jimeng_ak and jimeng_sk)):
        print("⚠️ auto 模式下未检测到可用生图配置，将回退默认封面。")


def main():
    print("=== 环境变量体检 ===")
    print(f"项目目录: {PROJECT_ROOT}")

    env_file = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_file):
        print(".env 文件: 已找到")
    else:
        print(".env 文件: 未找到（可执行: cp .env.example .env）")

    missing = check_required()
    if missing:
        print("\n必填项缺失:")
        for key in missing:
            print(f"- {key}")
        print("\n微信公众号参数获取入口: https://developers.weixin.qq.com/platform")
    else:
        print("\n必填项检查: 通过")

    print_model_route()
    print_cover_route()

    print("\n下一步建议:")
    print("1) 运行表结构初始化: python3 scripts/setup/setup_inspiration_library.py && python3 scripts/setup/setup_content_library.py")
    print("2) 跑单次流水线巡检: OPENCLAW_NON_INTERACTIVE=1 OPENCLAW_AUTO_INSTALL=0 ./run.sh pipeline-once")
    print("3) 跑单篇验证: OPENCLAW_NON_INTERACTIVE=1 OPENCLAW_AUTO_INSTALL=0 ./run.sh \"<URL>\" \"tech_expert\" \"auto\"")


if __name__ == "__main__":
    main()
