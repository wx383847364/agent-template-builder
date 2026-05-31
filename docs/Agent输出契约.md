# Agent 输出契约

这份文档记录 `AgentData` 输出的长期兼容口径。代码定义以 `src/agent_template_builder/schema/agent_data.py` 为准。

## 顶层结构

`AgentData` 当前包含：

- `game`：游戏和客户端标识。
- `screen`：屏幕类型、模板 ID、置信度和分辨率。
- `elements`：模板元素、bbox、文本、可见性和证据。
- `state`：运行状态，例如阻塞弹窗和可用意图。
- `task`：当前任务文本的快捷状态，可为空。
- `raw`：调试和追踪信息。

## 证据原则

- 每个可解释的输出字段应尽量关联 `Evidence`。
- 模板识别证据使用 `source="template"`。
- OCR 文本证据使用 `source="ocr"`。
- OCR 证据需要保留 `region_id` 和 `template_id`。

## 置信度原则

- `screen.confidence` 表示当前模板匹配置信度。
- 元素置信度默认继承模板匹配置信度。
- OCR 元素置信度应同时考虑模板匹配和 OCR 结果。
- 置信度用于排序和风险提示，不应被当作绝对真假值。

## 兼容性原则

- 新增字段优先保持可选或提供默认值。
- 重命名或删除字段前，需要先记录迁移原因。
- schema 变化应同步更新测试和本文档。
- `raw` 可以扩展调试信息，但稳定消费方不应依赖未经确认的 `raw` 字段。

## 当前缺口

- OCR 引擎仍为空实现。
- expected JSON 尚未建立真实样本基线。
- 部分模板只有布局锚点，缺少可度量 hash。
