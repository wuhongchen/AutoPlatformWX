# 首次配置 `.env` 完整引导

本引导面向第一次进入项目的同学，目标是 10 分钟内完成可运行配置。

## 1) 创建配置文件

```bash
cp .env.example .env
```

## 2) 填写必填项

必须填写 5 项：
1. `WECHAT_APPID`
2. `WECHAT_SECRET`
3. `FEISHU_APP_ID`
4. `FEISHU_APP_SECRET`
5. `FEISHU_APP_TOKEN`

微信公众号 `AppID/AppSecret` 获取入口：
`https://developers.weixin.qq.com/platform`

## 3) 选择模型运行模式

推荐默认：
```bash
OPENCLAW_MODEL_PROVIDER=auto
OPENCLAW_PIPELINE_MODEL=auto
OPENCLAW_MODEL=auto
```

`auto` 的行为：
1. 如果检测到 OpenClaw 代理配置，优先走 OpenClaw
2. 如果未检测到，自动回退到独立模型（默认 `OPENCLAW_INDEPENDENT_MODEL`）

## 4) 可选：OpenClaw 代理配置

如果你希望强制走 OpenClaw 代理，请至少配置：
1. endpoint（任意一个）：`OPENCLAW_PROXY_ENDPOINT` / `OPENCLAW_LLM_ENDPOINT` / `OPENCLAW_ENDPOINT` / `OPENAI_BASE_URL`
2. key（任意一个）：`OPENCLAW_PROXY_API_KEY` / `OPENCLAW_LLM_API_KEY` / `OPENCLAW_API_KEY` / `OPENAI_API_KEY`

## 5) 可选：独立模型配置

如果你不走 OpenClaw 代理，请配置至少一个可用模型 key，例如：
1. `KIMI_API_KEY`
2. 或 `BAILIAN_API_KEY`
3. 或 `ZHIPU_API_KEY`
4. 或 `MINIMAX_API_KEY`
5. 或 `VOLC_ARK_API_KEY`

## 6) 运行环境体检

```bash
python3 scripts/internal/check_env.py
```

体检通过后再进入测试引导：
`docs/TESTING_GUIDE.md`

## 7) 可选：封面生图路由（方舟 + 即梦）

推荐配置：
```bash
COVER_IMAGE_PROVIDER=auto
ARK_IMAGE_API_KEY=...
ARK_IMAGE_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3
ARK_IMAGE_MODEL=doubao-seedream-5-0-260128
# 可选: doubao-seedream-4-5-251128
ARK_IMAGE_SIZE=1280x720
ARK_IMAGE_RESPONSE_FORMAT=b64_json
VOLCENGINE_AK=...
VOLCENGINE_SK=...
```

路由规则：
1. `auto`：优先方舟，失败回退即梦。
2. `ark`：只走方舟。
3. `jimeng`：只走即梦。
