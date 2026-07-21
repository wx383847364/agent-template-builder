# Agent Rows 字段编号规划

本文档定义 Agent Rows 稳定编号的长期治理规则。它不替代运行时配置，而是规定后续如何维护编号、发布字段、废弃字段和同步文档。

## 定位

当前项目有三层输出口径：

- `AgentData` 是运行时权威结构，代码定义以 `src/agent_template_builder/schema/agent_data.py` 为准。
- `agent_fields.json` 是当前 Agent Rows 运行时字段事实源，决定实际导出的字段编号和 semantic role 映射。
- 本文档是编号治理规范，用于规划未来字段编号、区间归属和兼容策略。

如果本文档与当前运行时行为存在冲突，以 `agent_fields.json` 当前实现为准。后续真正发布规划字段时，必须同步更新 `agent_fields.json`、测试、样例输出和必要 expected 资产。

## 输出形态

Agent Rows 面向外部 agent 的兼容 JSON 是扁平 index/value 对象：

```json
{
  "3": "",
  "4": "",
  "6": ""
}
```

这只描述 CLI 和外部消费形态。内部仍可以使用 `AgentRowsOutput.rows[]` 这类结构化对象承载 `key`、`type`、`semantic_role` 等元数据。

内部 `AgentRowsOutput.rows[]` 可以保留 `agent_fields.json` 中配置的全部字段，并按 index 升序排列。当 OCR 尚未接入、OCR 未读到文本或识别结果没有对应文本时，内部字段值保持空字符串。面向外部 agent 的扁平 index/value JSON 只输出有值字段，空字符串字段必须省略。

## 字段状态

字段表必须标注状态，避免把规划字段误认为当前可用字段。

| 状态 | 含义 |
| --- | --- |
| `published runtime` | 已在 `agent_fields.json` 发布，并由运行时 Agent Rows 输出。 |
| `expected legacy` | 编号只存在于 expected 样本字典中的历史兼容字段，不代表运行时 Agent Rows 已经输出。 |
| `planned` | 规划字段，尚未进入运行时输出。 |
| `reserved/deprecated` | 保留或废弃字段，不应被新消费方依赖。 |

## 编号空间

`0` 是永久保留哨兵值，不作为运行时字段输出。实际运行时字段编号从 `1` 开始。

| 范围 | 用途 |
| --- | --- |
| `0` | 永久保留，不使用。 |
| `1-999` | 基础通用字段区。当前 `agent_fields.json` 的 `1-999` 是粗粒度保留，本文档进一步细分治理。 |
| `1000-1999` | 角色核心状态，例如等级、气血、法力、经验、金钱和角色状态。 |
| `2000-2999` | 战斗状态与技能槽，例如回合、选中目标、技能名和冷却。 |
| `3000-3999` | 任务、NPC、对话扩展字段。 |
| `4000-4999` | 弹窗、系统提示、阻塞状态字段。 |
| `5000-5999` | 奖励、背包、物品、经济相关字段。 |
| `6000-6999` | 地图、导航、场景、坐标扩展字段。 |
| `7000-7999` | 系统面板、表单、输入框字段。 |
| `8000-8999` | agent 行动提示、可执行意图摘要字段。 |
| `9000-9999` | 调试、兼容、实验字段；稳定消费方不应依赖。 |

## 1-999 基础区细分

| 范围 | 用途 |
| --- | --- |
| `1-99` | 第一代 expected 兼容基础字段。运行时只发布其中已进入 `agent_fields.json` 的字段。 |
| `100-199` | 游戏与客户端基础信息。 |
| `200-299` | 截图与识别基础信息。 |
| `300-399` | 账号与登录流程。 |
| `400-499` | 服务器选择。 |
| `500-599` | 角色选择。 |
| `600-699` | 通用页面文本。 |
| `700-799` | 通用按钮和操作文本。 |
| `800-899` | 通用状态和流程标志。 |
| `900-999` | 兼容、迁移、废弃占位。 |

## 当前字段与规划字段

| 编号 | key | semantic role | 状态 | 说明 |
| --- | --- | --- | --- | --- |
| `1` | `account_name` | - | `expected legacy` | expected 样本字典中的账号名称。 |
| `2` | `password` | - | `expected legacy` | expected 样本字典中的密码。 |
| `3` | `server_name` | `selected_server` | `published runtime` | 兼容字段，语义跟随 `400 selected_server`。 |
| `4` | `current_task` | `current_task` | `published runtime` | 主世界当前任务追踪文本。 |
| `5` | `npc_name` | - | `expected legacy` | expected 样本字典中的 NPC 名称。 |
| `6` | `dialog_text` | `dialog_text` | `published runtime` | NPC 对话正文。 |
| `7` | `dialog_options` | `dialog_options` | `published runtime` | NPC 对话选项。 |
| `8` | `modal_text` | - | `expected legacy` | expected 样本字典中的阻塞弹窗正文。 |
| `9` | `modal_confirm_label` | - | `expected legacy` | expected 样本字典中的确认按钮文本。 |
| `10` | `modal_cancel_label` | - | `expected legacy` | expected 样本字典中的取消按钮文本。 |
| `11` | `system_notice` | - | `expected legacy` | expected 样本字典中的系统公告或系统提示文本。 |
| `12` | `battle_status` | `battle_status` | `published runtime` | 战斗状态或战斗日志文本。 |
| `13` | `panel_title` | `panel_title` | `published runtime` | 系统面板标题。 |
| `100` | `game_id` | - | `planned` | 游戏标识；进入运行时前不得假定会输出。 |
| `101` | `client_type` | - | `planned` | 客户端类型；进入运行时前不得假定会输出。 |
| `200` | `screenshot_name` | - | `planned` | 截图文件名；进入运行时前不得假定会输出。 |
| `201` | `screenshot_time` | - | `planned` | 截图时间；进入运行时前不得假定会输出。 |
| `202` | `screen_type` | `screen_type` | `published runtime` | 当前识别到的前景界面类型；v1 只表示前景模板，不表示完整 UI 栈。 |
| `203` | `template_id` | `template_id` | `published runtime` | 当前命中的前景模板 ID。 |
| `204` | `screen_confidence` | `screen_confidence` | `published runtime` | 当前模板识别置信度，固定三位小数字符串。 |
| `205` | `resolution_width` | - | `planned` | 截图宽度；进入运行时前不得假定会输出。 |
| `206` | `resolution_height` | - | `planned` | 截图高度；进入运行时前不得假定会输出。 |
| `207` | `fallback_reason` | - | `planned` | 模板 fallback 原因；进入运行时前不得假定会输出。 |
| `300` | `login_account_input` | - | `planned` | 登录账号输入框文本；进入运行时前不得假定会输出。 |
| `301` | `login_password_input` | - | `planned` | 登录密码输入框文本；进入运行时前不得假定会输出。 |
| `302` | `login_guard_prompt` | - | `planned` | 登录安全验证提示；进入运行时前不得假定会输出。 |
| `303` | `start_game_button` | `start_game_button` | `published runtime` | 登录瀑布界面的开始游戏按钮，值格式为 `开始游戏@[left, top, right, bottom]`。 |
| `304` | `login_qr_code` | `login_qr_code` | `published runtime` | 二维码登录界面的二维码目标区域，默认四周外扩 50 像素，值格式为 `二维码@[left, top, right, bottom]`。 |
| `400` | `selected_server` | `selected_server` | `published runtime` | 当前选中的服务器，值格式为 `服务器名@[left, top, right, bottom]`。 |
| `401` | `account_servers` | `account_servers` | `published runtime` | 当前账号已建立角色的服务器列表，值格式为 `服务器名@[left, top, right, bottom];服务器名@[left, top, right, bottom]`。 |
| `402` | `common_login_characters` | `common_login_characters` | `published runtime` | 服务器选择界面右侧常用登录角色卡片；每项包含角色可读信息和整张截图坐标 bbox，多项用英文分号分隔。 |
| `4000` | `blocking_modal` | `blocking_modal` | `published runtime` | 阻塞状态；`1` 表示阻塞，`0` 表示已知无阻塞且必须保留输出。 |
| `500` | `selected_character` | `selected_character` | `published runtime` | 当前选中角色信息及角色卡片整图 bbox；默认取角色选择列表中的第一张已选中卡片。 |
| `501` | `selected_character_level` | - | `planned` | 当前选中角色等级；进入运行时前不得假定会输出。 |
| `502` | `character_selection_list` | `character_selection_list` | `published runtime` | 可选择角色卡片列表，每张卡片包含可读角色信息和整图 bbox，多项用英文分号分隔。 |
| `503` | `enter_game_button` | `enter_game_button` | `published runtime` | 角色选择界面的进入游戏按钮，值格式为 `进入游戏@[left, top, right, bottom]`。 |
| `5000` | `reward_text` | `reward_text` | `published runtime` | 奖励弹窗标题或提示文本。 |
| `5001` | `reward_items` | `reward_items` | `published runtime` | 奖励弹窗中的物品文本。 |
| `8000` | `available_intents` | `available_intents` | `published runtime` | 当前前景模板声明的可执行意图，按模板顺序用英文分号分隔；为空时外部稀疏 JSON 省略。 |
| `9000` | `window_center_offset` | `window_center_offset` | `published runtime` | 1920×1080 基准窗口中心偏移诊断；仅任一轴绝对值大于 5 px 时输出，格式为 `window_center_offset@[dx, dy]`。 |

## 前景界面上下文字段 v1

`202/203/204/4000/8000` 是当前已发布的 metadata rows，用于让外部 agent 在不解析完整 `AgentData` 的情况下快速判断前景界面：

- `202 screen_type` 是下游快速判断界面的主字段。
- `203 template_id` 用于追踪具体模板命中。
- `204 screen_confidence` 固定输出三位小数字符串。
- `4000 blocking_modal` 始终输出 `1` 或 `0`；`0` 是已知无阻塞，不按空值省略。
- `8000 available_intents` 保留模板声明顺序，intent 名称限定为 `[a-z0-9_]+` 风格，并用英文分号连接。

v1 只表示当前识别到的前景模板，不表示完整 UI 栈或“同时打开了哪些界面”。暂不发布 `8001 agent_context`；稳定消费方应直接读取这些原子字段。

## 发布和废弃规则

- 新字段发布前，先确认编号所属区间，再追加到 `agent_fields.json`。
- 已发布编号不得改含义；如果语义需要替换，新增编号并将旧编号标为 `reserved/deprecated`。
- 新字段必须同时补齐 `fields`、`mappings`、测试和必要样例输出。
- `planned` 字段不得被外部消费方当作稳定输出。
- `9000-9999` 只用于调试、兼容和实验；稳定消费方不应依赖。
- expected 样本字典中的历史编号可以保留为说明资产，但不自动成为运行时 Agent Rows 字段。

## 坐标值格式

可点击目标字段允许把像素 bbox 混入文本值，以保持外部输出仍是纯扁平 index/value JSON。

- 单个目标格式：`名称@[left, top, right, bottom]`。
- 多个目标使用英文分号分隔：`名称@[left, top, right, bottom];名称@[left, top, right, bottom]`。
- bbox 是截图坐标系中的整数 `[left, top, right, bottom]`，不是归一化模板 bbox，也不是点击中心点。
- 字段值只输出已识别到的目标；无法确认名称或 bbox 时，不输出该项。
- `3` 是兼容字段，语义跟随 `400`，新消费方应优先读取 `400` 和 `401`。
- `402 common_login_characters` 每张角色卡片独立输出一个 bbox；推荐值格式为 `角色名|转生等级|种族|服务器@[left, top, right, bottom]`，实际文字以局部 OCR 可确认内容为准。
- `500 selected_character` 与 `502 character_selection_list` 的推荐角色信息格式为 `角色名|转生等级|种族@[left, top, right, bottom]`；`502` 中每张卡片独立绑定 bbox，`500` 跟随当前选中的第一张卡片。
- `503 enter_game_button` 使用完整截图坐标系中的按钮 bbox，不输出点击中心点。
- `303 start_game_button` 的文字来自登录瀑布模板静态证据，bbox 来自按钮区域在当前截图坐标系中的像素换算结果。
## Template Static 来源

服务器选择字段 `400 selected_server`、`401 account_servers` 和兼容字段 `3 server_name` 可以由两类输入共同形成：

- 动态文本：后续 OCR 或人工替代输入提供服务器名。
- 模板静态槽位：`template_static` 元素提供可点击 bbox，导出层直接输出该像素 bbox。

输出格式保持不变：

```json
{
  "400": "水晶宫@[397, 729, 534, 772]",
  "401": "水晶宫@[51, 207, 191, 247];爱你万年@[205, 207, 346, 247]"
}
```

只有名称和 bbox 都可确认时才输出字段；空值继续省略。`3 server_name` 继续跟随 `400 selected_server`，新消费方优先读取 `400` 和 `401`。
