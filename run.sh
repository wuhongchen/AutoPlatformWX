#!/bin/bash

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}   🚀 OpenClaw 全自动运营发布工具      ${NC}"
echo -e "${BLUE}=======================================${NC}"

pick_env_file() {
    if [ -f ".env" ]; then
        echo ".env"
        return
    fi
    if [ -f "../mp-draft-push/.env" ]; then
        echo "../mp-draft-push/.env"
        return
    fi
    echo ""
}

has_config_key() {
    local key="$1"
    if [ -n "${!key}" ]; then
        return 0
    fi
    if [ -n "${ENV_FILE}" ] && grep -Eq "^[[:space:]]*${key}[[:space:]]*=[[:space:]]*[^[:space:]#]+" "${ENV_FILE}"; then
        return 0
    fi
    return 1
}

has_any_config_key() {
    local key
    for key in "$@"; do
        if has_config_key "$key"; then
            return 0
        fi
    done
    return 1
}

calc_requirements_hash() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 requirements.txt | awk '{print $1}'
    elif command -v sha256sum >/dev/null 2>&1; then
        sha256sum requirements.txt | awk '{print $1}'
    else
        # 兜底：低概率场景（仅用于判断是否变化，不做安全用途）
        md5 -q requirements.txt 2>/dev/null || cat requirements.txt
    fi
}

# 1. 检查环境变量
ENV_FILE="$(pick_env_file)"
WECHAT_CONSOLE_URL="https://developers.weixin.qq.com/platform"

if [ -z "${ENV_FILE}" ]; then
    echo -e "${YELLOW}⚠️  警告: 未找到 .env 配置文件，请先配置微信公众号参数。${NC}"
    echo -e "${YELLOW}🔗 参数获取入口: ${WECHAT_CONSOLE_URL}${NC}"
    echo -e "${YELLOW}📘 首次配置引导: docs/ENV_SETUP_GUIDE.md${NC}"
    echo -e "${YELLOW}🧪 测试引导: docs/TESTING_GUIDE.md${NC}"
    echo -e "${YELLOW}📌 请在 .env 中设置: WECHAT_APPID=... 和 WECHAT_SECRET=...${NC}"
    echo -e "${YELLOW}💡 快速开始: cp .env.example .env && python3 scripts/internal/check_env.py${NC}"
else
    if ! has_config_key "WECHAT_APPID" || ! has_config_key "WECHAT_SECRET"; then
        echo -e "${YELLOW}⚠️  检测到微信公众号参数未完整配置。${NC}"
        echo -e "${YELLOW}🔗 参数获取入口: ${WECHAT_CONSOLE_URL}${NC}"
        echo -e "${YELLOW}📘 首次配置引导: docs/ENV_SETUP_GUIDE.md${NC}"
        echo -e "${YELLOW}📌 请在 ${ENV_FILE} 中补全 WECHAT_APPID 和 WECHAT_SECRET。${NC}"
    fi
fi

# 2. 依赖检查（OpenClaw 调用优化：requirements 不变时跳过安装）
if [ "${OPENCLAW_AUTO_INSTALL:-1}" = "1" ]; then
    CACHE_DIR=".openclaw_cache"
    HASH_FILE="${CACHE_DIR}/requirements.sha256"
    mkdir -p "${CACHE_DIR}"

    CUR_HASH="$(calc_requirements_hash)"
    PREV_HASH="$(cat "${HASH_FILE}" 2>/dev/null)"

    if [ "${CUR_HASH}" != "${PREV_HASH}" ]; then
        echo -e "${BLUE}📦 检测到依赖变化，正在安装 Python 依赖...${NC}"
        python3 -m pip install -r requirements.txt > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo "${CUR_HASH}" > "${HASH_FILE}"
            echo -e "${GREEN}✅ 依赖项已就绪${NC}"
        else
            echo -e "${YELLOW}⚠️  自动安装依赖失败，您可以尝试手动运行: python3 -m pip install -r requirements.txt${NC}"
        fi
    else
        echo -e "${GREEN}✅ 依赖未变化，跳过安装${NC}"
    fi
else
    echo -e "${YELLOW}ℹ️ 已通过 OPENCLAW_AUTO_INSTALL=0 跳过依赖安装${NC}"
fi

# 3. 获取文章 URL 及可选参数
ARTICLE_URL=$1
ROLE=$2
MODEL=$3
MODEL_EFFECTIVE="${MODEL:-${OPENCLAW_MODEL:-auto}}"
ROLE_EFFECTIVE="${ROLE:-${OPENCLAW_ROLE:-tech_expert}}"

if [ -z "$ARTICLE_URL" ]; then
    if [ "${OPENCLAW_NON_INTERACTIVE:-0}" = "1" ]; then
        echo -e "${RED}❌ 非交互模式下未提供参数。请传入 URL 或 pipeline/pipeline-once。${NC}"
        exit 1
    fi
    echo -e "${YELLOW}请输入要采集的文章 URL:${NC}"
    read -r -p "> " ARTICLE_URL
fi

if [ -z "$ARTICLE_URL" ]; then
    echo -e "${RED}❌ 错误: 未提供有效的文章 URL，程序退出。${NC}"
    exit 1
fi

if [ "${MODEL_EFFECTIVE}" = "auto" ] || [ "${MODEL_EFFECTIVE}" = "openclaw" ]; then
    if ! has_any_config_key "OPENCLAW_PROXY_ENDPOINT" "OPENCLAW_LLM_ENDPOINT" "OPENCLAW_CHAT_ENDPOINT" "OPENCLAW_ENDPOINT" "OPENCLAW_BASE_URL" "OPENAI_BASE_URL" "OPENAI_API_BASE" \
       || ! has_any_config_key "OPENCLAW_PROXY_API_KEY" "OPENCLAW_LLM_API_KEY" "OPENCLAW_API_KEY" "OPENAI_API_KEY"; then
        echo -e "${YELLOW}⚠️  未检测到完整的 OpenClaw 代理配置，当前将回退到独立模型。${NC}"
        echo -e "${YELLOW}ℹ️  如需强制走 OpenClaw 代理，请配置 endpoint + key（OPENCLAW_* 或 OPENAI_*）。${NC}"
    fi
fi

# 4. 执行主程序
echo -e "${BLUE}⚙️  正在启动自动化发布流程...${NC}"
if [ "$ARTICLE_URL" = "pipeline" ] || [ "$ARTICLE_URL" = "pipeline-once" ]; then
    echo -e "${BLUE}🧵 流水线模式: ${ARTICLE_URL}${NC}"
    python3 core/manager.py "$ARTICLE_URL"
else
    echo -e "${BLUE}🎭 角色: ${ROLE_EFFECTIVE} | 🧠 模型: ${MODEL_EFFECTIVE}${NC}"
    python3 core/manager.py "$ARTICLE_URL" "${ROLE_EFFECTIVE}" "${MODEL_EFFECTIVE}"
fi

if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}=======================================${NC}"
    echo -e "${GREEN}✨ 任务执行成功！请登录公众平台确认草稿箱。${NC}"
    echo -e "${GREEN}=======================================${NC}"
else
    echo -e "\n${RED}‼️  流程执行中遇到错误，请检查日志输出。${NC}"
    echo -e "${YELLOW}提示: 如果是因为模型请求失败，请检查 .env 中的 API Key 是否正确。${NC}"
fi
