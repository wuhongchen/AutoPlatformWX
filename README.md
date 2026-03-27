# OpenClaw AutoPlatform

基于 OpenClaw 技能理论开发的全自动信息发布与收集平台。

## 核心特性与工作流

1. **双擎架构 (灵感库 + 流水线)**：
   - **内容灵感库 (`manager_inspiration.py`)**: 自动监控并抓取待选文章（支持微信公众号、飞书文档），利用 AI 评估爆款潜力并打分，提取核心视角。
   - **智能内容流水线 (`manager.py pipeline`)**: 以飞书《小龙虾智能内容库》为核心中枢，流转已审核素材，执行长文改写、配图生成及发布全链路自动编排。
2. **AI 清洗与结构重塑**：
   - 自动提取文本结构并转化为优美的 HTML 富文本格式发往微信草稿箱（专属优化 H1/H2 等标题层级与内联样式）。
   - **智能 OCR 过滤**：AI 上下文语义识别，精准备份原文关键配图，并自动剔除“扫码关注”、“二维码”等相关营销引流图片与话术。
3. **健壮的容错机制**：
   - 处理微信公众平台图文保存时由于多图引发的 `access_token` 过期断连，实现底层主动侦探和无感续排获取 Token。
   - 确保飞书文档的多源形式自动适配转换，URL 绝对纯净萃取。
4. **一键配图封面**：支持“方舟生图 + 即梦回退”双路线生成 16:9 封面，并自动上传至公众号媒体库。

## 快速开始

首次进入项目，建议先看两份引导：
1. `.env` 配置引导：`docs/ENV_SETUP_GUIDE.md`
2. 测试引导：`docs/TESTING_GUIDE.md`

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境

在当前目录或 `mp-draft-push` 目录下的 `.env` 文件中配置以下密钥：

微信公众号参数获取入口：`https://developers.weixin.qq.com/platform`

获取与填写步骤（2 分钟）：
1. 打开上面的微信开放平台链接并登录公众号主体账号。
2. 在平台控制台找到公众号应用的 `AppID` 和 `AppSecret`。
3. 回到项目 `.env`，填入 `WECHAT_APPID` 与 `WECHAT_SECRET` 后保存。

也可以直接从模板生成：
```bash
cp .env.example .env
python3 scripts/internal/check_env.py
```

```bash
# 微信公众号 (必须)
WECHAT_APPID=...
WECHAT_SECRET=...

# AI 改写 (可选，用于自动改稿)
LLM_API_KEY=...
LLM_ENDPOINT=...

# 阿里百炼 (OpenAI 兼容)
BAILIAN_API_KEY=...
BAILIAN_ENDPOINT=https://coding.dashscope.aliyuncs.com/v1

# 智谱
ZHIPU_API_KEY=...
ZHIPU_ENDPOINT=https://open.bigmodel.cn/api/paas/v4

# Kimi
KIMI_API_KEY=...
KIMI_ENDPOINT=https://api.moonshot.cn/v1

# MiniMax
MINIMAX_API_KEY=...
MINIMAX_ENDPOINT=https://api.minimax.chat/v1

# 流水线默认改写模型（飞书表内“改写模型”字段优先级更高）
OPENCLAW_PIPELINE_MODEL=kimi-k2.5
OPENCLAW_PIPELINE_ROLE=tech_expert
OPENCLAW_PIPELINE_BATCH_SIZE=3

# OpenClaw 调度优化（可选）
OPENCLAW_SCHEMA_CHECK_ENABLED=1
OPENCLAW_SCHEMA_CHECK_INTERVAL_SEC=21600
OPENCLAW_AUTO_INSTALL=1
OPENCLAW_NON_INTERACTIVE=1

# 公号模板广告位（可选）
WECHAT_AD_ENABLED=0
WECHAT_AD_POSITION=bottom
WECHAT_AD_TITLE=推广信息
WECHAT_AD_TEXT=
WECHAT_AD_LINK_TEXT=
WECHAT_AD_LINK_URL=
WECHAT_AD_IMAGE_PATH=
WECHAT_AD_IMAGE_URL=
WECHAT_AD_IMAGE_LINK_URL=

# 火山引擎 (可选，用于自动生成封面图)
VOLCENGINE_AK=...
VOLCENGINE_SK=...

# 封面生图路由（可选）
# auto: 优先方舟，失败回退即梦
# ark: 仅方舟
# jimeng: 仅即梦
COVER_IMAGE_PROVIDER=auto
ARK_IMAGE_API_KEY=...
ARK_IMAGE_ENDPOINT=https://ark.cn-beijing.volces.com/api/v3
ARK_IMAGE_MODEL=doubao-seedream-5-0-260128
# 可选: doubao-seedream-4-5-251128
ARK_IMAGE_SIZE=1280x720
ARK_IMAGE_RESPONSE_FORMAT=b64_json
```

封面生图路由说明：
1. `COVER_IMAGE_PROVIDER=auto`：先走方舟 `images/generations`，失败自动回退即梦。
2. `COVER_IMAGE_PROVIDER=ark`：只使用方舟（未配方舟会直接跳过生图）。
3. `COVER_IMAGE_PROVIDER=jimeng`：只使用即梦 AK/SK 签名接口。

### 3. 运行发布

你可以直接使用运营助手脚本：
```bash
./run.sh "https://mp.weixin.qq.com/s/xxx"
```

指定模型运行（第三个参数为 `model_key`）：
```bash
./run.sh "https://mp.weixin.qq.com/s/xxx" tech_expert "qwen3.5-plus"
./run.sh "https://mp.weixin.qq.com/s/xxx" tech_expert "glm-5"
./run.sh "https://mp.weixin.qq.com/s/xxx" tech_expert "kimi-k2.5"
./run.sh "https://mp.weixin.qq.com/s/xxx" tech_expert "MiniMax-M2.5"
```

流水线模式下也可切模型：
1. 设置环境变量 `OPENCLAW_PIPELINE_MODEL`（全局默认）
2. 或在飞书流水线表中填写 `改写模型` 字段（单条记录优先）
3. 默认开启“改写去重”：若记录已存在可读取的 `改后文档链接`，会跳过重复调用模型。
如需强制重改，可设置 `OPENCLAW_FORCE_REWRITE=1`。
4. 可设置 `OPENCLAW_PIPELINE_BATCH_SIZE` 控制单次巡检处理条数（默认 3，适合 OpenClaw 定时触发）。

新版流水线节点（状态机）：
1. `🧲 待改写`
2. `✍️ 改写中`
3. `🧾 待审核`
4. `🚀 待发布`
5. `📤 发布中`
6. `✅ 已发布`
7. `❌ 改写失败 / ❌ 发布失败`

或者手动运行：
```bash
python3 core/manager.py "https://mp.weixin.qq.com/s/xxx" tech_expert "qwen3.5-plus"
```

## 目录说明

- `run.sh`: **运营操作入口**，提供交互式界面和环境检查。
- `manager.py`: 核心编排器，负责调度各模块。
- `config.py`: 配置管理，自动加载环境变量。
- `docs/`: 存放项目相关方案文档。
- `skills/`: **融合技能库 (Plug-in Skills)**
  - `mp-draft-push/`: 微信公众号高级发布技能。
  - `volcengine-jimeng-image/`: 即梦 AI 生图与视频处理技能。
  - `wechat-auto-publisher/`: 微信自动化运营 JS 工具包。
- `scripts/`:
  - `setup/`: 存放多维表格环境初始化脚本。
  - `utils/`: 存放独立的图片转码与上传验证工具。
- `modules/`:
  - `collector.py`: 内容抓取模块。
  - `feishu.py`: 飞书 API 封装，包含图片处理核心逻辑。
  - `processor.py`: AI 加工模块（改稿、生图）。
  - `publisher.py`: 公众号发布模块。
- `archive/`: 存放历史测试脚本与实验性代码。
- `output/`: 存放流程中的中间产物。
