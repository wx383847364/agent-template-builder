# Codex 客户端单图 AI UI Discovery

UI Discovery 用于处理尚无稳定模板的游戏界面。当前 Codex 客户端任务充当
视觉模型：它查看一张完整 1920×1080 截图，尽量找全可见面板、按钮、页签、
列表、文字和玩家属性、技能名、宠物名等有用数据，再由视觉审核子代理和人工
review 收敛结果。

该能力是离线候选生产旁路，不是运行时识别回退。

## 安装与边界

Discovery 是可选功能：

```bash
pip install -e ".[discovery]"
```

v1 不安装 OpenAI SDK、不读取 API key，也不通过脚本控制 Codex/ChatGPT
客户端。`DiscoveryProvider` 只定义
`discover(screenshot, request) -> ModelDiscoveryOutput`；当前
`FileDiscoveryProvider` 读取 Codex 客户端生成的 JSON。未来接入 API 时新增
provider，不改变下游契约。

强制边界：

- 输入只能是完整 1920×1080 截图。
- bbox 是整图整数像素 `[left,top,right,bottom)`，不经过 `game_view`。
- panels 和 elements 均为平铺数组，不表达父子、归属、z-order、行列或分组。
- 识别 Windows 桌面、任务栏和 Moonlight 外部区域为排除项。
- `interaction_bbox_guess` 只是候选，不能导出为 Agent Rows 或正式点击。
- 运行目录在 `runtime/` 下，默认被 Git 忽略。

## 标准工作流

先准备一次运行：

```bash
agent-template-builder-prepare-discovery /absolute/path/to/screenshot.png
```

命令先验证分辨率，失败时不会创建可消费目录；成功后输出 `RUN_DIR`。Codex
查看原图和 `prompt.md`，按 `model_output.schema.json` 填写
`model_output.initial.json`，然后生成草稿：

```bash
agent-template-builder-finalize-discovery RUN_DIR \
  --draft --input model_output.initial.json
```

草稿阶段会裁剪越界 bbox、拒绝空框、对同类型且 IoU ≥ 0.85 的元素去重，并
生成 `draft.discovery.json` 与 `annotated.draft.png`。随后必须启动视觉审核
子代理，对照原图和标注图，把漏识别、误识别和 bbox 修正记录到 `audit.json`。

主代理按审核意见生成 `model_output.final.json`。若 final 内容相对已审核文件
发生变化，必须让审核子代理再次确认；`audit.json.status` 只有在通过后才能设为
`passed`，并且 `source_model_sha256` 必须绑定 final 文件。然后生成正式候选：

```bash
agent-template-builder-finalize-discovery RUN_DIR \
  --input model_output.final.json
```

正式 `discovery.json` 不允许覆盖。该命令同时生成 `annotated.png` 和绑定截图
SHA、run ID、discovery SHA 的 `review.json`。

用户可在 `review.json` 中将每项设为 `keep` 或 `discard`，或修改类型、bbox、
文字、semantic role、usefulness，并通过 `new_panels` / `new_elements` 补充
漏项。未显式 discard 的项目默认保留。应用审核：

```bash
agent-template-builder-apply-discovery-review RUN_DIR/review.json
```

输出 `reviewed.json` 和 `annotated_reviewed.png`；所有保留项会标记为
`review_status="keep"`。如果截图、run ID 或 discovery 摘要不匹配，命令拒绝
应用。

## 运行目录

```text
runtime/discovery/<截图名>__<sha256前8位>/<run-id>/
  request.json
  prompt.md
  model_output.schema.json
  model_output.initial.json
  draft.discovery.json
  annotated.draft.png
  audit.json
  model_output.final.json
  discovery.json
  annotated.png
  review.json
  reviewed.json
  annotated_reviewed.png
```

中间和 reviewed 文件按实际步骤出现。这里可能包含角色名、账号信息和聊天
内容，不得提交到 Git。

## 数据契约

`ModelDiscoveryOutput` 负责客户端模型交接；`DiscoveryData` 固定包含来源
SHA、分辨率、运行 ID、生成模式、prompt 版本、整图坐标声明、可选已有模板
上下文、scene、平铺 panels/elements、evidence、warnings 和 errors。

Element 支持 action/information/decoration 分类、候选交互区域、原始与规范化
文字、结构化 data field、建议动作、状态猜测、semantic role、usefulness、
confidence 和证据引用。低置信候选不会自动过滤；纯装饰由人工决定是否删除。

OCR 只复核模型已经发现的可读候选区域，不参与场景或面板类型判断。未安装
PaddleOCR 时保留 Codex 文字并记录 warning。
