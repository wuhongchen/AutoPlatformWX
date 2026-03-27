---
name: autoinfo-manager
description: OpenClaw 自动化运营总控技能。用于灵感扫描、流水线改写发布、单篇紧急处理；优先使用 pipeline-once 提高调度稳定性与效率。
metadata: {"openclaw":{"emoji":"🚀","requires":{"python":">=3.9"}}}
---

# autoinfo-manager

## 1) 技能用途
本技能用于驱动本仓库的三类任务：
1. 灵感库扫描与评估
2. 内容流水线改写与发布
3. 单篇文章即时处理

当用户出现以下意图时应触发本技能：
1. “启动灵感扫描 / 分析选题 / 看看最近有什么可写”
2. “跑流水线 / 自动发布 / 处理待发布队列”
3. “把这篇文章改写并发布：<URL>”
4. “修复改写失败/发布失败记录”

## 2) OpenClaw 调用总原则
1. 默认优先单次巡检：`pipeline-once`，不要默认起常驻进程。
2. 默认非交互调用：设置 `OPENCLAW_NON_INTERACTIVE=1`。
3. 默认关闭重复依赖安装：设置 `OPENCLAW_AUTO_INSTALL=0`（环境已就绪时）。
4. 大队列分批跑：设置 `OPENCLAW_PIPELINE_BATCH_SIZE=3`（可调 1~5）。
5. 除非用户明确要求，不要强制重改写（不要默认设 `OPENCLAW_FORCE_REWRITE=1`）。

## 3) 标准动作与命令

### Action A: 环境诊断/初始化
适用：用户说“检查环境”、“初始化飞书表结构”、“字段不对”。

执行命令：
```bash
python3 scripts/internal/diagnose.py
python3 scripts/setup/setup_inspiration_library.py
python3 scripts/setup/setup_content_library.py
```

### Action B: 灵感扫描
适用：用户说“开始收集灵感”、“分析灵感库”。

执行命令：
```bash
python3 core/manager_inspiration.py
```

### Action C: 流水线单次巡检（推荐）
适用：OpenClaw 定时任务、批处理场景。

执行命令（推荐）：
```bash
OPENCLAW_NON_INTERACTIVE=1 OPENCLAW_AUTO_INSTALL=0 OPENCLAW_PIPELINE_BATCH_SIZE=3 ./run.sh pipeline-once
```

等价命令：
```bash
OPENCLAW_PIPELINE_BATCH_SIZE=3 python3 core/manager.py pipeline-once
```

### Action D: 流水线守护模式（仅用户明确要求）
适用：用户明确要求“持续监听”。

执行命令：
```bash
OPENCLAW_NON_INTERACTIVE=1 OPENCLAW_AUTO_INSTALL=0 ./run.sh pipeline
```

### Action E: 单篇即时处理
适用：用户给定 URL，要立即改写/发布。

执行命令：
```bash
OPENCLAW_NON_INTERACTIVE=1 OPENCLAW_AUTO_INSTALL=0 ./run.sh "<URL>" "tech_expert" "auto"
```

也可直接：
```bash
python3 core/manager.py "<URL>" "tech_expert" "auto"
```

## 4) 模型与参数约定
模型优先级：
1. CLI 第三个参数（单篇模式）
2. 飞书记录字段 `改写模型`（流水线单条）
3. 环境变量 `OPENCLAW_PIPELINE_MODEL`（流水线默认）
4. 自动模型路由（`OPENCLAW_MODEL_PROVIDER`）
5. 兜底模型

常用可选模型 key：
1. `auto`（推荐：优先 OpenClaw 代理，无则回退独立模型）
2. `openclaw`（强制走 OpenClaw 代理）
3. `kimi-k2.5`
4. `qwen3.5-plus`
5. `qwen3-max-2026-01-23`
6. `qwen3-coder-next`
7. `qwen3-coder-plus`
8. `glm-5`
9. `glm-4.7`
10. `MiniMax-M2.5`
11. `volcengine`

OpenClaw 代理读取规则（无需额外改代码）：
1. 端点优先读取：`OPENCLAW_PROXY_ENDPOINT` / `OPENCLAW_LLM_ENDPOINT` / `OPENCLAW_ENDPOINT` / `OPENAI_BASE_URL`
2. Key 优先读取：`OPENCLAW_PROXY_API_KEY` / `OPENCLAW_LLM_API_KEY` / `OPENCLAW_API_KEY` / `OPENAI_API_KEY`
3. 模型优先读取：`OPENCLAW_PROXY_MODEL` / `OPENCLAW_LLM_MODEL` / `OPENAI_MODEL`

角色字段：
1. `改写角色`（飞书字段）
2. 默认 `tech_expert`

封面生图路由（新增）：
1. `COVER_IMAGE_PROVIDER=auto`（推荐）：优先方舟生图，失败自动回退即梦。
2. `COVER_IMAGE_PROVIDER=ark`：只走方舟 `images/generations`。
3. `COVER_IMAGE_PROVIDER=jimeng`：只走即梦 AK/SK。
4. 方舟参数：`ARK_IMAGE_API_KEY`、`ARK_IMAGE_ENDPOINT`、`ARK_IMAGE_MODEL`、`ARK_IMAGE_SIZE`、`ARK_IMAGE_RESPONSE_FORMAT`。
   - 推荐模型：`doubao-seedream-5-0-260128`（默认）
   - 备选模型：`doubao-seedream-4-5-251128`
5. 即梦参数：`VOLCENGINE_AK`、`VOLCENGINE_SK`。

## 5) 流水线状态机（必须按新状态识别）
1. `🧲 待改写`
2. `✍️ 改写中`
3. `🧾 待审核`
4. `🚀 待发布`
5. `📤 发布中`
6. `✅ 已发布`
7. `❌ 改写失败`
8. `❌ 发布失败`
9. `❌ 失败`

兼容旧状态文案时，交给系统内部 canonical 映射处理，不要在技能层写死旧状态推进逻辑。

## 6) OpenClaw 运行效率约定
1. 触发频率高时，固定用 `pipeline-once`，让外部调度器重复调用。
2. 批大小由 `OPENCLAW_PIPELINE_BATCH_SIZE` 控制，避免单次处理过多导致超时。
3. 字段检查已支持间隔控制：
   - `OPENCLAW_SCHEMA_CHECK_ENABLED=1`
   - `OPENCLAW_SCHEMA_CHECK_INTERVAL_SEC=21600`
4. `run.sh` 已支持依赖哈希缓存，`requirements.txt` 未变化会跳过安装。

## 7) 失败处理与自动处置
看到以下错误时按对应动作处理：
1. `No module named ...`
   - 执行：`python3 -m pip install -r requirements.txt`
2. `Missing environment variables` 或鉴权失败
   - 检查并补全 `.env`：`FEISHU_*`, `WECHAT_*`, `LLM/模型相关 key`
   - 微信公众号 `AppID/AppSecret` 获取入口：`https://developers.weixin.qq.com/platform`
   - 必填项：`WECHAT_APPID=...`、`WECHAT_SECRET=...`
3. `document_id max len is 27` / 无法解析 doc token
   - 优先检查飞书字段 `改后文档链接` 是否为 `https://www.feishu.cn/docx/...`
   - 必要时执行修复脚本：
```bash
python3 scripts/internal/repair_failed_records.py
```
4. 改写失败但无失败备注
   - 回写失败原因并重跑到 `🧲 待改写` 后再执行 `pipeline-once`
5. 封面未生成（方舟/即梦）
   - 先检查 `COVER_IMAGE_PROVIDER` 是否与配置匹配
   - `ark` 模式需至少有 `ARK_IMAGE_API_KEY + ARK_IMAGE_ENDPOINT`
   - `jimeng` 模式需 `VOLCENGINE_AK + VOLCENGINE_SK`
   - `auto` 模式会先尝试方舟，再自动回退即梦

## 8) 推荐环境变量模板
```bash
OPENCLAW_NON_INTERACTIVE=1
OPENCLAW_AUTO_INSTALL=0
OPENCLAW_PIPELINE_BATCH_SIZE=3
OPENCLAW_MODEL_PROVIDER=auto
OPENCLAW_PIPELINE_MODEL=auto
OPENCLAW_PIPELINE_ROLE=tech_expert
OPENCLAW_SCHEMA_CHECK_ENABLED=1
OPENCLAW_SCHEMA_CHECK_INTERVAL_SEC=21600
COVER_IMAGE_PROVIDER=auto
```

独立模型模式（不走 OpenClaw 代理）可选补充：
```bash
OPENCLAW_MODEL_PROVIDER=independent
OPENCLAW_INDEPENDENT_MODEL=kimi-k2.5
```

## 9) 执行边界
1. 本技能负责“调度与发布链路”。
2. 不在技能层硬编码业务表字段迁移逻辑，字段变更优先走 `scripts/setup/*`。
3. 未经用户要求，不做 destructive 操作（删表、批量删记录、清库）。
