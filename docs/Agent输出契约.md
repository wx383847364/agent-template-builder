# Agent 输出契约

这份文档记录 `AgentData` 输出的长期兼容口径。代码定义以 `src/agent_template_builder/schema/agent_data.py` 为准。

## DiscoveryData 不属于运行时输出

`agent_ui_discovery/v1` 是未知界面的离线高召回候选契约，不是
`AgentData` 的扩展。它允许未确认的面板、文字和
`interaction_bbox_guess`，且所有交互区域固定标记
`interaction_safety="candidate_only"`。

Discovery 流程不得调用 `AgentRowsExporter`，不得提供稳定字段编号、
`available_intents` 或确认点击，也不得被正式模板加载器扫描。人工应用
`review.json` 后得到的 `agent_ui_discovery_reviewed/v1` 仍然只是候选资产；
如需进入运行时，必须另行完成模板校准、anchor、expected 和回归审核。

具体 schema、目录和命令见 [AI界面发现规则.md](AI界面发现规则.md)。

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
- `samples/dhxy2_classic_pc/expected/final_expected.json` 已建立 expected 填写入口，首批 legacy 样本仍未人工确认 OCR 文本值。
- 部分模板只有布局锚点，缺少可度量 hash；主世界、战斗、登录瀑布和人物属性类系统面板已有首批可度量 anchor/hash。

## Agent Rows 兼容导出层

`AgentData` 仍然是运行时权威输出，代码定义以 `src/agent_template_builder/schema/agent_data.py` 为准。固定 index/value rows 是旁路兼容导出层，用于外部 agent 模块按稳定编号消费识别结果。

当前导出路径为：

```text
screenshot -> analyze_screenshot() -> AgentData -> AgentRowsExporter -> JSON rows
```

字段编号和 semantic role 映射来自根目录运行时配置 `agent_fields.json`。内部 `AgentRowsOutput.rows[]` 可以保留配置中的全部字段，并按 index 升序排列；当 OCR 或识别结果没有文本时，内部 `value` 保持空字符串。面向外部 agent 的扁平 index/value JSON 只输出有值字段，空字符串字段必须省略。普通业务字段只读取 `AgentData.elements[].text`；可点击目标字段额外读取同一元素或静态槽位的 bbox。两者都不从 `raw.match` 或 `confidence` 推断。

为了保持外部消费简单，可点击目标字段把像素 bbox 编码进字符串值。当前约定为 `名称@[left, top, right, bottom]`，多个目标用英文分号分隔，例如 `水晶宫@[610, 700, 700, 730];爱你万年@[120, 245, 275, 275]`。bbox 使用当前截图坐标系中的整数像素值。

Agent Rows 的长期编号区间、字段状态和发布规则见 [AgentRows字段编号规划.md](AgentRows字段编号规划.md)。`agent_fields.json` 仍是当前运行时事实源；规划字段只有进入该配置后才属于稳定运行时输出。

## Agent Rows Metadata 字段

Agent Rows v1 发布一组前景界面上下文字段，用于让下游 agent 快速判断当前截图是什么界面、是否阻塞、可做什么：

- `202 screen_type`：来自 `AgentData.screen.type`，表示当前识别到的前景界面类型。
- `203 template_id`：来自 `AgentData.screen.template_id`，表示当前命中的模板 ID。
- `204 screen_confidence`：来自 `AgentData.screen.confidence`，导出为固定三位小数字符串，例如 `0.880`。
- `4000 blocking_modal`：来自 `AgentData.state.blocking_modal`，导出为 `1` 或 `0`；`0` 表示已知无阻塞，不属于空值，外部稀疏 JSON 必须保留。
- `8000 available_intents`：来自 `AgentData.state.available_intents`，按模板声明顺序用英文分号连接，例如 `read_task;open_map;continue_navigation`；空列表导出为空字符串，外部稀疏 JSON 省略。

这些 metadata rows 是导出层例外：它们不从 `AgentData.elements[].text` 读取。普通业务字段仍只从元素文本读取，不能从 `raw`、`bbox` 或 `confidence` 推断业务 OCR 值。

v1 只表达当前识别到的前景模板，不表达完整 UI 栈，也不发布 `8001 agent_context` 摘要字段。后续如果需要“同时打开了哪些界面”，应通过 secondary detectors 或多模板并行检测另行设计，避免形成第二套不稳定契约。

## Template Static Evidence

- 模板识别后，`templates/*.json` 中的 `static_outputs` 会注入 `AgentData.elements[]`。
- 这类元素的 `evidence.source` 固定为 `template_static`，用于区分 OCR 文本和模板自带的固定 UI 文案、固定按钮、固定槽位。
- 如果 `static_outputs[].bbox` 存在，运行时按完整 1920×1080 截图换算并叠加窗口标题栏共享 probe 校准出的统一 `dx/dy`；可点击目标字段直接发布该 bbox。
- 外部 Agent Rows 仍保持扁平 index/value JSON；不会新增结构化 `action_targets`。

服务器选择使用模板静态槽位补全点击区域：当 `selected_server` 或 `account_servers` 已有服务器名但没有 bbox 时，导出层会按 `selected_server_slot` / `account_server_slot` 输出 `服务器名@[left, top, right, bottom]`。已经包含 bbox 的值原样保留；遗留的 `@x,y` 输入会按当前槽位重新绑定为 bbox。

固定按钮、点击槽位和定位图像区域可以通过模板 `static_outputs` 发布为坐标目标。Agent Rows 导出器会将 `type="button"`、`type="button_slot"` 或 `type="image_region"` 的非空文字格式化为 `文字@[left, top, right, bottom]`。所有界面的目标均使用经统一偏移校准后的完整 1920×1080 整数像素 bbox；不再输出点击中心点。登录瀑布模板通过 `303 start_game_button` 输出开始游戏按钮；二维码登录模板通过 `304 login_qr_code` 输出二维码外扩区域。

服务器选择模板通过 `402 common_login_characters` 输出右侧“常用角色”卡片。每张已识别角色卡片都是独立的局部 OCR 元素，值包含该卡片的可读角色信息与完整截图像素 bbox；多张卡片使用英文分号分隔。

当匹配确认窗口中心偏移任一轴超过 5 px 时，Rows 额外发布 `9000 window_center_offset`，格式为 `window_center_offset@[dx, dy]`。它是诊断字段，稳定业务消费方不得依赖。

角色选择模板通过 `502 character_selection_list` 输出每张可选择角色卡片的局部 OCR 信息与整图像素 bbox；`500 selected_character` 跟随第一张已选中卡片，`503 enter_game_button` 输出“进入游戏”按钮及整图 bbox。运行时只接受 1920×1080 截图，模板 bbox 直接以整张截图比例换算，并叠加统一窗口校准偏移，不存在 `game_view` 坐标换算。
