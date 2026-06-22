# PaddleOCR PP-OCRv5 部署计划

## Summary

本文档用于记录 PaddleOCR PP-OCRv5 在当前项目中的落地计划。

- 部署目标：在当前 `.venv` 内安装 PaddleOCR + PaddlePaddle GPU，并锁定 PP-OCRv5 做局部 ROI OCR。
- 当前机器条件：Windows、Python `3.12.13`、RTX 4070、`nvidia-smi` 可用。
- 项目现状：已有 `OCREngine` / `NullOCREngine` 接口，可直接作为后续代码接入口。

## 环境现状

当前项目虚拟环境中尚未安装以下依赖：

- `paddleocr`
- `paddlepaddle`
- `paddlepaddle-gpu`

第一阶段不单独创建 OCR 环境，直接使用当前项目 `.venv`。

## 推荐安装路线

优先使用 GPU 版本 PaddlePaddle，并安装到当前 `.venv`。

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install paddlepaddle-gpu==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu130/
.\.venv\Scripts\python.exe -m pip install paddleocr
```

## GPU Wheel 回退方案

如果 `cu130` wheel 安装失败，先卸载已安装的 PaddlePaddle 包，再尝试 `cu126` 源。

```powershell
.\.venv\Scripts\python.exe -m pip uninstall -y paddlepaddle paddlepaddle-gpu
.\.venv\Scripts\python.exe -m pip install paddlepaddle-gpu==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
.\.venv\Scripts\python.exe -m pip install paddleocr
```

## CUDA 与 PaddleOCR 验证

安装完成后执行以下命令，确认 PaddlePaddle GPU 和 PaddleOCR 可用。

```powershell
.\.venv\Scripts\python.exe -c "import paddle, paddleocr; print(paddle.__version__); print(paddleocr.__version__); print(paddle.is_compiled_with_cuda()); print(paddle.device.cuda.device_count())"
```

期望结果：

- `paddle.__version__` 输出 `3.3.0` 或实际安装版本。
- `paddleocr.__version__` 正常输出版本号。
- `paddle.is_compiled_with_cuda()` 输出 `True`。
- `paddle.device.cuda.device_count()` 大于等于 `1`。

## PP-OCRv5 初始化示例

第一阶段使用 `PP-OCRv5_mobile_det` + `PP-OCRv5_mobile_rec`，优先速度和局部识别稳定性。

```python
from paddleocr import PaddleOCR

ocr = PaddleOCR(
    device="gpu",
    text_detection_model_name="PP-OCRv5_mobile_det",
    text_recognition_model_name="PP-OCRv5_mobile_rec",
    use_doc_orientation_classify=False,
    use_doc_unwarping=False,
    use_textline_orientation=False,
)
```

## 第一阶段 OCR 范围

第一阶段只做局部 OCR，不做整图 OCR，不改变当前模板识别主链路。

优先接入以下 ROI：

- `main_world.task_tracker`
- `blocking_modal` 文本区域
- `npc_dialog` 正文区域

服务器名 OCR 后续再接词表纠错。

## 接入方式

后续新增 `PaddleOCREngine` adapter，接入现有接口：

```python
OCREngine.read_region(image_path, bbox)
```

OCR 结果仍先进入：

```python
AgentData.elements[].text
```

不修改 Agent Rows 输出契约。

## Execution Steps

1. 写入部署文档。
2. 按文档在当前 `.venv` 安装 PaddleOCR。
3. 验证 CUDA 和 PaddleOCR 可用。
4. 用现有截图裁剪 ROI 做 smoke test。
5. 新增 `PaddleOCREngine` adapter，接入现有 `OCREngine.read_region(image_path, bbox)`。
6. 跑基准测试，目标热启动后达到 `>=10 ROI/s`。

## Test Plan

### 环境测试

确认以下命令输出的 CUDA 编译状态为 `True`。

```powershell
.\.venv\Scripts\python.exe -c "import paddle; print(paddle.is_compiled_with_cuda())"
```

### OCR Smoke Test

至少验证以下三个 ROI 能输出中文：

- 主界面任务追踪
- 阻断弹窗
- NPC 对话

### 性能测试

对 50 到 100 个 ROI 循环识别，并记录：

- 平均耗时
- P95
- ROI/s

目标：热启动后达到 `>=10 ROI/s`。

### 项目回归

```powershell
.\.venv\Scripts\python.exe -m agent_template_builder.tools.audit_templates
.\.venv\Scripts\python.exe -m agent_template_builder.tools.report_template_coverage
.\.venv\Scripts\python.exe -m agent_template_builder.tools.report_recognition_quality
.\.venv\Scripts\python.exe -m pytest -q
```

## Assumptions

- 使用当前 `.venv`，不单独建 OCR 环境。
- 第一阶段使用 `PP-OCRv5_mobile_det` + `PP-OCRv5_mobile_rec`，优先速度和局部识别稳定性。
- 不做整图 OCR，不改变当前模板识别主链路。
- 不修改 Agent Rows 输出契约；OCR 结果仍先进入 `AgentData.elements[].text`。
