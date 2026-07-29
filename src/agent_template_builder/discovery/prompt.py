from __future__ import annotations


PROMPT_VERSION = "ui_discovery_v1"


PROMPT_TEMPLATE = """# 大话西游2 1920×1080 UI Discovery

你正在为 Agent Template Builder 识别一张完整 1920×1080 桌面截图。

## 目标

以高召回方式找出截图中所有可见且有意义的游戏 UI：

- 当前场景以及所有可见面板；
- 按钮、页签、列表项、输入框、复选框、图标和关闭按钮；
- 玩家属性、技能名称、宠物名称、任务、状态、资源数值和提示文字；
- 可能需要 click/read/input/select/close/inspect 的候选操作。

宁可保留不确定候选并降低 confidence，也不要遗漏有用 UI。纯装饰可输出，
但必须使用 category="decoration"。

## 强制边界

- 坐标始终是完整原图的整数像素 `[left, top, right, bottom)`。
- 原图固定为 1920×1080，不使用 game_view，不输出归一化坐标。
- 只识别截图中可见的内容，不推测隐藏按钮或点击后的结果。
- 排除 Windows 桌面、任务栏和 Moonlight 外部区域。
- panels 和 elements 都是平铺数组。禁止 parent_id、panel_id、z_index、
  row、column、children、group 或任何布局关系字段。
- interaction_bbox_guess 只是候选操作区域；interaction_safety 固定为
  "candidate_only"。
- review_status 固定为 "pending"。
- 每个 id 在自身数组内唯一。
- evidence 必须能解释重要的按钮、面板或数据识别依据。

## 输出

只写符合 `model_output.schema.json` 的一个 JSON 对象，不要 Markdown 代码块，
不要附加解释。文字无法确定时保留空字符串或候选原文，不要编造。

截图：{screenshot}
截图 SHA256：{sha256}
运行 ID：{run_id}
"""


def build_prompt(*, screenshot: str, sha256: str, run_id: str) -> str:
    return PROMPT_TEMPLATE.format(
        screenshot=screenshot,
        sha256=sha256,
        run_id=run_id,
    )
