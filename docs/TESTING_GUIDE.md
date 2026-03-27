# 测试引导（从 0 到可发布）

本引导按“最小风险”顺序验证：先测配置，再测链路，最后测流水线。

## 1) 配置体检

```bash
python3 scripts/internal/check_env.py
```

目标：
1. 必填项无缺失
2. 模型路由符合预期（OpenClaw 或独立模型）

## 2) 表结构初始化（首次必做）

```bash
python3 scripts/setup/setup_inspiration_library.py
python3 scripts/setup/setup_content_library.py
```

目标：
1. 飞书灵感库与流水线表存在且字段齐全

## 3) 单篇链路测试（推荐先做）

```bash
OPENCLAW_NON_INTERACTIVE=1 OPENCLAW_AUTO_INSTALL=0 ./run.sh "<文章URL>" "tech_expert" "auto"
```

目标：
1. 能完成采集 -> 改写 -> 发布到草稿箱
2. 飞书记录能回写 `改后文档链接` 与状态

## 4) 流水线单次巡检测试

```bash
OPENCLAW_NON_INTERACTIVE=1 OPENCLAW_AUTO_INSTALL=0 OPENCLAW_PIPELINE_BATCH_SIZE=1 ./run.sh pipeline-once
```

目标：
1. 仅处理 1 条，便于观察
2. 状态按 `待改写/待发布` 正确推进

## 5) 常见失败与定位

1. 微信鉴权失败
   - 检查 `WECHAT_APPID` / `WECHAT_SECRET`
   - 参数获取入口：`https://developers.weixin.qq.com/platform`
2. 改后文档链接为空或非 URL
   - 执行：`python3 scripts/internal/repair_failed_records.py`
3. OpenClaw 代理没生效
   - 看 `run.sh` 是否提示“回退到独立模型”
   - 补齐代理 endpoint + key
4. 飞书写入失败
   - 检查 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` / `FEISHU_APP_TOKEN`
   - 运行：`python3 scripts/internal/diagnose.py`

## 6) 一键全流程 Demo（灵感库起步）

使用内置 demo 从“灵感库新增 URL”开始跑完整链路：

```bash
python3 scripts/internal/demo_full_flow.py --url "https://mp.weixin.qq.com/s/wrsaOwVYDKd2lEDmRs65Jg"
```

如果你只想跑到改写完成，不执行发布：

```bash
python3 scripts/internal/demo_full_flow.py --url "https://mp.weixin.qq.com/s/wrsaOwVYDKd2lEDmRs65Jg" --skip-publish
```
