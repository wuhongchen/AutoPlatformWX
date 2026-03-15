---
name: autoinfo-manager
description: OpenClaw 自动化运营平台总控中心。负责从选题分析、内容改写、AI 生图到微信发布的全链路调度。
metadata: {"openclaw":{"emoji":"🚀","requires":{"python":">=3.9"}}}
---

# autoinfo-manager (总控技能)

## 🎯 业务目标

作为 OpenClaw 系统的顶层调度器，它将多个原子技能串联起来，实现真正的“无人值守”自媒体运营方案。

## 📊 管理后台
- **飞书总控台**: [点击访问 OpenClaw 内容工厂](https://t0woxppdywz.feishu.cn/base/KkDFb19FNazzaNs7tNRcdyZNnWb)
- **核心表格**: 
  - `01_内容灵感库`: 用于选题筛选与 AI 打分。
  - `02_自动化发布队列`: 用于内容改写审核与微信推送。

---

## 🛠️ 触发指令

当你（OpenClaw Agent）接收到以下指令时，应激活此技能：
- "启动灵感扫描" / "分析选题"
- "运行内容流水线" / "开始自动化发布"
- "处理这篇文章：[URL]"

---

## 🧩 核心模式定义

### 1. 灵感分析模式 (选题漏斗)
- **执行命令**: `python3 core/manager_inspiration.py`
- **全环节流程**:
  1. **捕获**: 实时扫描《内容灵感库》中新增的文章 URL。
  2. **评估**: 调用 LLM 进行潜力打分 (1-10分) 与核心洞察提取。
  3. **固化**: 将原文内容转存为飞书文档，并提取所有配图至表格。
  4. **决策**: 如果评分 < 6 分自动标记为“跳过”，高分选题等待人工点选“已同步”。

### 2. 流水线自动化模式 (任务工厂)
- **执行命令**: `python3 core/manager.py pipeline`
- **全环节流程**:
  1. **监听**: 监控《智能内容库》中状态为 `✅ 采集完成` 的记录。
  2. **深度改写**: 调用 `DeepMPProcessor` 进行行业特稿级改写 (2000字+)。
  3. **视觉注入**: 借鉴 wenyan 排版美学，生成带视觉样式的 HTML 文档。
  4. **人工卡位**: 生成 `✨ 已改写(待审)` 转存文档，等待你在飞书内做最后润色。
  5. **终审推送**: 检测到 `🚀 确认发布` 状态后，自动上传图片至微信 CDN 并推送到草稿箱。

### 3. 单篇即时模式 (One-off Mode)
- **参数要求**：
    - `url`: 必填，文章链接。
    - `role`: 默认 `tech_expert`。
    - `model`: 默认 `volcengine` (豆包)。
- **执行逻辑**：调用 `./run.sh [url] [role] [model]`。

---

## 📂 原生能力支持

本总控中心不仅是一个调度器，它已经**完全内置融合了**以下高级能力，不再依赖外部技能碎片：
- **微信文章深度打磨**: 包含图文混排结构抽取与原生排版（直接支持多配图与无头防封机制）
- **AI 智能生图**: 基于火山引擎即梦 CV 模型直接产出 16:9 高清公众号封面图，内部封装了签名与鉴权闭环
- **图片智能 OCR 过滤**: 能主动剔除公众号原图中的引流广告、二维码信息，保证迁移到我们平台时的原创洁净度

---

## ⚙️ 环境变量要求

执行此总控技能前，请确保配置文件 `.env` 已具备：
- `FEISHU_*`: 飞书 API 权限（文档、表格）。
- `WECHAT_*`: 微信公众号后台权限。
- `VOLCENGINE_*` / `KIMI_*`: LLM 与图像生成权限。

---

## 🚀 平台驱动行动指南 (Agent Action List)

当你 (OpenClaw) 接到用户的宽泛意图时，请严格根据以下触发词，转换为后台脚本的工具调用 (`run_command`)：

### Action 1: 环境诊断与表格初始化 (Doctor)
- **触发意图**: "帮我检查一下环境配置"、"初始化一下系统"、"飞书表格结构不对"、"Token验证"
- **执行命令**:
  - `python3 scripts/internal/diagnose.py` (全局诊断)
  - `python3 scripts/setup/setup_inspiration_library.py` (初始化灵感库架构)
  - `python3 scripts/setup/setup_content_library.py` (初始化内容库流水线)

### Action 2: 启动灵感嗅探器 (Inspiration Engine)
- **触发意图**: "开始收集灵感", "帮我分析下最近有什么好写的", "监控新的输入Url"
- **执行命令**:
  - 交互式等待/后台守护: `python3 core/manager_inspiration.py` (使用 `WaitMsBeforeAsync` 派发后台任务，并在日志中观察扫描状态)
  - 单次触发RSS同步: `python3 scripts/sync_rss_to_inspiration.py`

### Action 3: 启动主控流水线 (Pipeline Engine)
- **触发意图**: "处理一下刚才准备好的发文"、"启动自动化发布"、"监控已同步的文章"
- **执行命令**:
  - 后台守护: `python3 core/manager.py pipeline` (这是平台的心脏组件，长时运行)
  
### Action 4: 单发测试/紧急响应 (Ad-hoc)
- **触发意图**: "直接帮我把这篇文章改写发到公众号：https://xxx.xxx"
- **执行命令**:
  - `python3 core/manager.py "https://xxx.xxx" tech_expert volcengine` 
  - (将 URL 换为用户提供的目标 URL)

---

## ⚠️ 常见故障排除 (Troubleshooting)
作为 OpenClaw Agent，如果你在执行以上 `Action` 时，发现终端返回包含以下关键词的错误，请主动进行处置：
1. **`No module named ...`**: 发现依赖缺失，请自行 `pip install -r requirements.txt`，不用等待用户确认。
2. **`Missing environment variables`**: 发现 `.env` 配置不全，请主动询问用户索要并更新 `.env` 文件。
3. **飞书多维表格列名对不上**: 主动运行 `setup_*` 脚本重新挂载列。
