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

## 📂 协同技能列表 (Sub-Skills)

总控中心依赖以下原子技能：
- [x] **mp-draft-push**: 处理具体的微信草稿推送。
- [x] **volcengine-jimeng-image**: 负责 AI 封面图生成。
- [x] **wechat-auto-publisher**: (备用) 浏览器自动化运营。

---

## ⚙️ 环境变量要求

执行此总控技能前，请确保配置文件 `.env` 已具备：
- `FEISHU_*`: 飞书 API 权限（文档、表格）。
- `WECHAT_*`: 微信公众号后台权限。
- `VOLCENGINE_*` / `KIMI_*`: LLM 与图像生成权限。

---

## 🚀 模拟执行指令建议

如果您（OpenClaw）希望在命令行中模拟此流程：

**场景：用户输入 "帮我处理这篇文章 https://mp.weixin.qq.com/s/xxx"**

OpenClaw 动作：
```bash
# 模拟原子化执行
python3 manager.py "https://mp.weixin.qq.com/s/xxx" tech_expert volcengine
```
