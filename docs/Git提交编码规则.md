# Git 提交编码规则

这份文档规定 Agent Template Builder 的轻量提交编号和标题规则。

本项目参考 Holmas 的八位编号方案，但保持轻量：使用 commit-msg hook 做本地提交校验，不引入编号登记 JSON 或自动提交建议脚本。编号用于长期检索模块历史，并在提交时阻止明显不符合规则的标题和正文。

## 标题格式

提交标题固定为：

```text
[TMMSSSSS] 类型：摘要
```

含义：

- `T`：一级大类。
- `MM`：二级模块。
- `SSSSS`：该模块内递增流水号。

示例：

```text
[25000001] 规则：新增提交编码规则
[61000001] 工具：新增模板覆盖率报告
[31000001] 资产：补齐主世界模板锚点
```

历史提交不回填。规则启用后的新提交从对应模块的 `00001` 开始递增。

## 模块编号表

```text
1xxxxxxx 核心代码
110xxxxx schema / AgentData 输出契约
120xxxxx matcher / hash / 视觉识别
130xxxxx OCR 接口与适配
140xxxxx analyze pipeline / 导出流程
150xxxxx package 基础设施 / paths / 初始化

2xxxxxxx 文档与长期记忆
210xxxxx README / 项目总览
220xxxxx 架构说明 / 边界规则
230xxxxx 模板资产规则 / Agent 输出契约文档
240xxxxx 公开参考图 / 外部资料说明
250xxxxx 迭代记录 / Git 规则 / 项目记忆

3xxxxxxx 模板资产与样本
310xxxxx game config / templates JSON
320xxxxx screenshots 样本
330xxxxx expected AgentData JSON
340xxxxx public references / manifest
350xxxxx vocab / OCR 词表

5xxxxxxx 测试与验证
510xxxxx 单元测试 / 回归测试
520xxxxx 模板审计 / 覆盖率验证
530xxxxx 样本校准验证 / 手工验收记录

6xxxxxxx 工具与脚本
610xxxxx template audit / coverage / CLI 工具
620xxxxx 样本生成 / 校准辅助脚本
630xxxxx repo maintenance / 开发辅助脚本
```

## 标题类型

- `代码`：核心实现变化。
- `识别`：matcher、hash 或模板识别变化。
- `OCR`：OCR 接口或引擎变化。
- `契约`：schema 或 `AgentData` 输出变化。
- `文档`：说明文档变化。
- `规则`：长期规则、提交规则、项目记忆变化。
- `资产`：模板 JSON、参考图、词表变化。
- `样本`：screenshots 或 expected 变化。
- `测试`：测试和验证变化。
- `工具`：CLI、报告、维护脚本变化。

## 正文格式

提交正文固定为：

```text
- 完成：说明本次改动的结果
- 验证：说明跑过的测试或检查
- 后续：说明遗留缺口；没有则写“无”
```

如果本次提交只改文档，也要写验证方式，例如“人工检查链接”或“无需运行测试，未改代码”。

## 归类规则

- 优先按“本次改动的主要长期资产”归类，不按文件数量归类。
- 代码加测试同提时，编号归到代码主模块。
- 文档只是同步说明时，跟随主改动模块；纯文档改动才使用 `2xxxxxxx`。
- 模板 JSON、截图样本、expected JSON 分别使用 `310 / 320 / 330`，不要混成一个模块。
- 多条无关主线混在一起时，默认不建议提交，应拆成多个提交。
- 如果一次改动横跨多个模块但服务同一个目的，选最能代表长期资产归属的模块，并在正文说明覆盖范围。

## 查号方式

`SSSSS` 按模块独立递增。准备提交前，用模块前三位查历史：

```bash
git log --oneline | rg '^[0-9a-f]+ \[250'
```

如果当前历史没有该模块编号，从 `00001` 开始。

## Hook 校验

本仓库使用 `.githooks/commit-msg` 校验提交信息。首次克隆或 hooks 失效时执行：

```bash
sh tools/repo_maintenance/install_git_hooks.sh
```

hook 会校验：

- 标题符合 `[TMMSSSSS] 类型：摘要`。
- 模块编号存在于本文档的模块表。
- 标题类型属于本文档列出的允许类型。
- 模块流水号从 `00001` 开始，并按当前 git history 推算下一个编号。
- 正文包含 `- 完成：`、`- 验证：`、`- 后续：` 三段。

为了支持 amend，若提交标题与当前 `HEAD` 标题完全一致，hook 允许保留原编号。

## 常用示例

```text
[25000001] 规则：新增提交编码规则
[61000001] 工具：新增模板覆盖率报告
[31000001] 资产：补齐主世界模板锚点
[33000001] 样本：新增 NPC 对话 expected 输出
[12000001] 识别：接入区域 hash 匹配权重
```

## 当前启用口径

- 旧提交不回填、不占号。
- 启用 `.githooks/commit-msg` 做本地提交校验。
- 暂不维护编号登记 JSON。
- 暂不新增自动提交建议脚本。
- 需要提交建议时，按本文件人工判断模块和下一个编号。
