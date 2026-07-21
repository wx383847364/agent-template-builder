# Agent Template Builder

Agent Template Builder 用于创建可复用的屏幕模板，并为本地 Agent 或 LLM 导出结构化数据。

首个模板包面向 `dhxy2_classic_pc`，也就是《大话西游2》经典版 PC 客户端。版本 1 聚焦于让任务流程可读的屏幕：

- 尽可能在不依赖 OCR 的情况下识别当前屏幕模板；
- 检测任务面板、对话框、地图、弹窗等固定 UI 元素；
- 只对任务文本、对话正文、弹窗内容等动态区域执行 OCR；
- 为每个关键字段输出带置信度和证据的 JSON。

## 目录结构

```text
configs/games/dhxy2_classic_pc/   游戏专用模板和词表
samples/dhxy2_classic_pc/         截图样本和预期 JSON 输出
src/agent_template_builder/       模板构建与导出流水线
docs/                             架构说明、参考资料和长期项目记忆
tests/                            Schema 和配置加载的单元测试
```

## 快速开始

```bash
cd /Users/bruce/work/agent-template-builder
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m agent_template_builder.pipeline.analyze samples/dhxy2_classic_pc/screenshots/example.png
```

示例命令需要一张真实截图。在补充截图之前，可以先用测试验证项目骨架：

```bash
python -m pytest
```

Codex 新会话与长期项目记忆入口见 [docs/项目总览.md](docs/项目总览.md)。

实时截图目录可以用下面命令分析。截图文件名只用于追踪和排序，不参与模板识别：

```bash
.venv/bin/agent-template-builder-analyze-screenshots references/dhxy2_public/legacy --latest --agent-data
.venv/bin/agent-template-builder-analyze-screenshots references/dhxy2_public/legacy --jsonl
```

实时截图接入口径见 [docs/实时截图接入.md](docs/实时截图接入.md)。

## 目前已实现

- 已定义 `AgentData`、屏幕、元素、证据、运行状态等导出 schema。
- 已提供《大话西游2》经典版 PC 的首个模板包，覆盖登录、服务器选择、角色选择、主世界、NPC 对话、系统面板、战斗占位和阻塞弹窗。
- 运行时只接受 1920×1080 整图截图；模板通过整图 anchor 搜索统一窗口偏移并校准全部导出 bbox。
- 已实现归一化 bbox 到像素坐标的转换，以及基于区域平均哈希的锚点匹配能力。
- 已接入 OCR 引擎接口和空实现，占位等待后续接入 PaddleOCR、Tesseract 或其他本地 OCR。
- 已提供模板包审计命令和单元测试，覆盖配置加载、模板排序、bbox 换算和基础截图分析流程。

## 第一个里程碑

1. 为首批模板各采集 3-10 张截图：主世界、NPC 对话、阻塞弹窗、地图/导航、奖励/提示弹窗。
2. 为每个模板锚点填入真实区域哈希或图像锚点。
3. 在 `samples/dhxy2_classic_pc/expected/final_expected.json` 中补齐对应截图的预期字段值。
4. 将 OCR 限制在标记为 `ocr_required: true` 的区域内。

模板 bbox 使用屏幕比例而不是固定像素，因此同一个模板可以适配多种共享受支持宽高比的分辨率。

## 本地游戏路径配置

本机游戏安装目录和截图目录写在 `configs/local.json`，该文件已加入 `.gitignore`，不随仓库提交。可提交的配置示例是 `configs/local.example.json`。

默认截图目录检索顺序：

1. 环境变量 `AGENT_TEMPLATE_BUILDER_SCREENSHOT_DIR`
2. `configs/local.json` 中的 `games.dhxy2_classic_pc.screenshot_dir`
3. 已知默认路径 `G:/大话/大话西游2_经典版/screen`
4. 项目样本目录 `samples/dhxy2_classic_pc/screenshots`

配置完成后，实时截图分析命令可以省略目录参数：

```powershell
.\.venv\Scripts\python.exe -m agent_template_builder.pipeline.analyze_screenshots --latest
.\.venv\Scripts\python.exe -m agent_template_builder.pipeline.analyze_screenshots --latest --agent-data
```
