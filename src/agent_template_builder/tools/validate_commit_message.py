from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
import argparse
import re
import subprocess
import sys


MODULES: dict[str, str] = {
    "110": "schema / AgentData 输出契约",
    "120": "matcher / hash / 视觉识别",
    "130": "OCR 接口与适配",
    "140": "analyze pipeline / 导出流程",
    "150": "package 基础设施 / paths / 初始化",
    "210": "README / 项目总览",
    "220": "架构说明 / 边界规则",
    "230": "模板资产规则 / Agent 输出契约文档",
    "240": "公开参考图 / 外部资料说明",
    "250": "迭代记录 / Git 规则 / 项目记忆",
    "310": "game config / templates JSON",
    "320": "screenshots 样本",
    "330": "expected AgentData JSON",
    "340": "public references / manifest",
    "350": "vocab / OCR 词表",
    "510": "单元测试 / 回归测试",
    "520": "模板审计 / 覆盖率验证",
    "530": "样本校准验证 / 手工验收记录",
    "610": "template audit / coverage / CLI 工具",
    "620": "样本生成 / 校准辅助脚本",
    "630": "repo maintenance / 开发辅助脚本",
}

TITLE_TYPES = {
    "代码",
    "识别",
    "OCR",
    "契约",
    "文档",
    "规则",
    "资产",
    "样本",
    "测试",
    "工具",
}

REQUIRED_BODY_PREFIXES = ("- 完成：", "- 验证：", "- 后续：")
TITLE_RE = re.compile(r"^\[(?P<number>\d{8})\] (?P<type>[^：:\s]+)：(?P<summary>.+)$")
NUMBER_RE = re.compile(r"^\[(?P<number>\d{8})\]")


@dataclass(frozen=True)
class ParsedTitle:
    number: str
    module: str
    sequence: int
    title_type: str
    summary: str


def parse_commit_title(title: str) -> tuple[ParsedTitle | None, list[str]]:
    match = TITLE_RE.match(title)
    if not match:
        return None, [
            "提交标题必须符合 `[TMMSSSSS] 类型：摘要`，并使用中文冒号 `：`。"
        ]

    number = match.group("number")
    module = number[:3]
    sequence = int(number[3:])
    title_type = match.group("type")
    summary = match.group("summary").strip()
    errors: list[str] = []

    if module not in MODULES:
        errors.append(f"未知模块编号 `{module}`。请查看 docs/Git提交编码规则.md。")
    if sequence <= 0:
        errors.append("模块流水号必须从 00001 开始，不能使用 00000。")
    if title_type not in TITLE_TYPES:
        errors.append(
            f"未知标题类型 `{title_type}`。允许类型：{', '.join(sorted(TITLE_TYPES))}。"
        )
    if not summary:
        errors.append("提交标题摘要不能为空。")

    return ParsedTitle(number, module, sequence, title_type, summary), errors


def validate_commit_message(
    message: str,
    history_subjects: Iterable[str] = (),
    enforce_sequence: bool = True,
) -> list[str]:
    lines = _meaningful_lines(message)
    if not lines:
        return ["提交信息不能为空。"]

    title = lines[0]
    parsed, errors = parse_commit_title(title)
    if parsed is None:
        return errors

    errors.extend(_validate_body(lines[1:]))
    if enforce_sequence and not _looks_like_amend_of_head(title, history_subjects):
        expected = expected_next_sequence(parsed.module, history_subjects)
        if parsed.sequence != expected:
            errors.append(
                f"模块 `{parsed.module}` 的下一个流水号应为 {expected:05d}，"
                f"当前为 {parsed.sequence:05d}。"
            )

    return errors


def expected_next_sequence(module: str, history_subjects: Iterable[str]) -> int:
    highest = 0
    for subject in history_subjects:
        match = NUMBER_RE.match(subject.strip())
        if not match:
            continue
        number = match.group("number")
        if number[:3] == module:
            highest = max(highest, int(number[3:]))
    return highest + 1


def _meaningful_lines(message: str) -> list[str]:
    return [
        line.rstrip()
        for line in message.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _validate_body(body_lines: list[str]) -> list[str]:
    body = "\n".join(body_lines)
    errors = [
        f"提交正文缺少 `{prefix}`。"
        for prefix in REQUIRED_BODY_PREFIXES
        if prefix not in body
    ]
    return errors


def _looks_like_amend_of_head(title: str, history_subjects: Iterable[str]) -> bool:
    history = list(history_subjects)
    return bool(history and history[0].strip() == title.strip())


def _history_subjects(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), "log", "--format=%s"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return []
    return result.stdout.splitlines()


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Agent Template Builder commit messages.")
    parser.add_argument("commit_msg_file", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--no-sequence", action="store_true", help="Skip module sequence validation.")
    args = parser.parse_args()

    message = args.commit_msg_file.read_text(encoding="utf-8")
    errors = validate_commit_message(
        message,
        history_subjects=_history_subjects(args.repo_root),
        enforce_sequence=not args.no_sequence,
    )
    if errors:
        print("提交标题编号校验失败：", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        print("", file=sys.stderr)
        print("规则见 docs/Git提交编码规则.md", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
