from agent_template_builder.tools.validate_commit_message import (
    expected_next_sequence,
    validate_commit_message,
)


VALID_MESSAGE = """[25000001] 规则：新增提交编码规则

- 完成：新增提交编码规则
- 验证：人工检查规则文档
- 后续：无
"""


def test_accepts_valid_first_module_commit() -> None:
    assert validate_commit_message(VALID_MESSAGE, history_subjects=["Initial commit"]) == []


def test_rejects_invalid_title_shape() -> None:
    errors = validate_commit_message(
        "规则: 新增提交编码规则\n\n- 完成：x\n- 验证：x\n- 后续：无\n",
        history_subjects=[],
    )

    assert any("提交标题必须符合" in error for error in errors)


def test_rejects_missing_body_sections() -> None:
    errors = validate_commit_message("[25000001] 规则：新增提交编码规则\n", history_subjects=[])

    assert any("- 完成：" in error for error in errors)
    assert any("- 验证：" in error for error in errors)
    assert any("- 后续：" in error for error in errors)


def test_rejects_wrong_module_sequence() -> None:
    errors = validate_commit_message(
        "[25000003] 规则：新增提交编码规则\n\n- 完成：x\n- 验证：x\n- 后续：无\n",
        history_subjects=["[25000001] 规则：已有规则提交"],
    )

    assert any("下一个流水号应为 00002" in error for error in errors)


def test_allows_amending_head_with_same_title() -> None:
    assert (
        validate_commit_message(
            VALID_MESSAGE,
            history_subjects=["[25000001] 规则：新增提交编码规则"],
        )
        == []
    )


def test_expected_next_sequence_ignores_other_modules() -> None:
    assert expected_next_sequence(
        "250",
        [
            "[61000001] 工具：新增覆盖率报告",
            "[25000002] 规则：更新提交规则",
            "Initial commit",
        ],
    ) == 3
