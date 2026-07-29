# Agent Template Builder 架构

Agent Template Builder 是一个模板优先的数据导出工具。它通过本地视觉匹配判断屏幕类型，避免整屏 OCR；随后只对动态文本区域执行 OCR，并输出可供 Agent 使用的 JSON。

## 流水线

```text
screenshot (1920×1080 only)
  -> 图像元数据和精确分辨率检查
  -> 加载游戏模板包
  -> 使用锚点和固定 UI 区域进行模板匹配
  -> 仅对动态区域执行 OCR
  -> AgentData JSON
```

未知界面的离线生产旁路与稳定运行时完全分开：

```text
1920×1080 screenshot
  -> prepare discovery request/schema/prompt
  -> Codex 客户端高召回视觉识别
  -> 本地 bbox/schema 校验和标注图
  -> 视觉审核子代理
  -> immutable DiscoveryData + review.json
  -> 人工 keep/discard/修正
  -> ReviewedDiscoveryData
```

Discovery 不调用 `AgentRowsExporter`，不产生 `available_intents` 或确认点击，
也不写入 `configs/games/*/templates`。未来 API provider 只替换模型输入边界，
下游 schema、校验、标注和 review 保持不变。

## 匹配策略

匹配器按成本从低到高分层执行：

1. 精确 `1920×1080` 分辨率检查。
2. 面板矩形、按钮区域、图标等整图固定布局锚点。
3. 窗口化页面先以客户端标题栏共享的高熵像素 probe 定位全局统一窗口偏移；随后用页面 anchor 校验。全屏页面使用固定整图 anchor。
4. 小图模板匹配，等真实样本到位后再补充。
5. 只有在屏幕候选已知之后，才使用 OCR 作为兜底。

## OCR 策略

版本 1 不使用 OCR 判断整体屏幕类型。OCR 只用于带有 `ocr_required: true` 的模板元素，例如：

- 当前任务文本；
- NPC 对话正文；
- 阻塞弹窗正文；
- 奖励或提示文本。

固定标签和按钮应尽可能通过模板、区域或图标识别。

## 模板包

`configs/games/dhxy2_classic_pc` 是第一个模板包，包含：

- `game.json`：客户端标识、唯一运行时分辨率、窗口基准与流水线默认值；
- `templates/*.json`：屏幕模板和元素区域；
- `vocab/*.txt`：用于 OCR 后处理的业务词典；`vocab/ocr_confusions.json` 记录有真实证据的定向字符混淆规则。

## 坐标策略

模板区域使用归一化屏幕比例，而不是固定像素：

```json
"bbox": [0.72, 0.12, 0.99, 0.44]
```

运行时只接受 `1920×1080`，并先按该尺寸换算 bbox。窗口化模板从整图客户端标题栏 probe 搜索同一个 `dx/dy`，页面 anchor 只作模板校验；再把该偏移整体应用至 OCR ROI、元素和 Agent Rows 点击区域。全屏模板使用固定整图坐标；没有 `game_view` 或多分辨率 profile 换算。

Discovery 的 bbox 不使用模板归一化坐标，也不应用窗口偏移：它始终描述输入
截图当前可见位置，格式为完整 1920×1080 原图整数像素
`[left,top,right,bottom)`。
