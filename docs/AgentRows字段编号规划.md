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
| `3` | `server_name` | `server_list` | `published runtime` | 服务器名称或服务器列表文本。 |
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
| `202` | `screen_type` | - | `planned` | 屏幕类型；进入运行时前不得假定会输出。 |
| `203` | `template_id` | - | `planned` | 模板 ID；进入运行时前不得假定会输出。 |
| `204` | `screen_confidence` | - | `planned` | 模板匹配置信度；进入运行时前不得假定会输出。 |
| `205` | `resolution_width` | - | `planned` | 截图宽度；进入运行时前不得假定会输出。 |
| `206` | `resolution_height` | - | `planned` | 截图高度；进入运行时前不得假定会输出。 |
| `207` | `fallback_reason` | - | `planned` | 模板 fallback 原因；进入运行时前不得假定会输出。 |
| `300` | `login_account_input` | - | `planned` | 登录账号输入框文本；进入运行时前不得假定会输出。 |
| `301` | `login_password_input` | - | `planned` | 登录密码输入框文本；进入运行时前不得假定会输出。 |
| `302` | `login_guard_prompt` | - | `planned` | 登录安全验证提示；进入运行时前不得假定会输出。 |
| `400` | `selected_server` | - | `planned` | 当前选中的服务器；进入运行时前不得假定会输出。 |
| `401` | `server_list_text` | - | `planned` | 服务器列表文本；进入运行时前不得假定会输出。 |
| `500` | `selected_character_name` | - | `planned` | 当前选中角色名称；进入运行时前不得假定会输出。 |
| `501` | `selected_character_level` | - | `planned` | 当前选中角色等级；进入运行时前不得假定会输出。 |
| `5000` | `reward_text` | `reward_text` | `published runtime` | 奖励弹窗标题或提示文本。 |
| `5001` | `reward_items` | `reward_items` | `published runtime` | 奖励弹窗中的物品文本。 |

## 发布和废弃规则

- 新字段发布前，先确认编号所属区间，再追加到 `agent_fields.json`。
- 已发布编号不得改含义；如果语义需要替换，新增编号并将旧编号标为 `reserved/deprecated`。
- 新字段必须同时补齐 `fields`、`mappings`、测试和必要样例输出。
- `planned` 字段不得被外部消费方当作稳定输出。
- `9000-9999` 只用于调试、兼容和实验；稳定消费方不应依赖。
- expected 样本字典中的历史编号可以保留为说明资产，但不自动成为运行时 Agent Rows 字段。
