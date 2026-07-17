from __future__ import annotations

import re
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from agent_template_builder.ocr.base import OCRResult


DEFAULT_SERVER_NAME_ROLES = frozenset({"account_servers", "selected_server", "server_name"})
DEFAULT_COMMON_TERM_ROLES = frozenset({"current_task", "dialog_text", "dialog_options"})
DEFAULT_CONFUSION_SUBSTITUTIONS = (
    ("条", "务"),
    ("受", "兽"),
    ("品", "晶"),
    ("君", "居"),
    ("闾", "阁"),
)
_CHINESE_SEGMENT = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
_NONEMPTY_LINE = re.compile(r"[^\r\n]+")


@dataclass(frozen=True)
class TextCorrection:
    start: int
    end: int
    original: str
    replacement: str
    vocabulary: str


@dataclass(frozen=True)
class PostprocessedOCRResult:
    original: OCRResult
    corrected_text: str
    corrections: tuple[TextCorrection, ...] = ()

    @property
    def original_text(self) -> str:
        return self.original.text

    @property
    def confidence(self) -> float:
        return self.original.confidence

    @property
    def changed(self) -> bool:
        return self.original_text != self.corrected_text


def load_vocab(path: Path) -> tuple[str, ...]:
    """Load non-empty, non-comment vocabulary entries in file order."""
    entries: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#") or entry in seen:
            continue
        entries.append(entry)
        seen.add(entry)
    return tuple(entries)


def load_confusions(path: Path) -> tuple[tuple[str, str], ...]:
    """Load validated, directional OCR character substitutions."""
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("OCR confusion config must be an object with version 1")
    substitutions = payload.get("substitutions")
    if not isinstance(substitutions, list):
        raise ValueError("OCR confusion config substitutions must be a list")

    pairs: list[tuple[str, str]] = []
    for item in substitutions:
        if not isinstance(item, dict):
            raise ValueError("OCR confusion substitution must be an object")
        pairs.append((item.get("observed"), item.get("expected")))
    return _clean_confusions(pairs)


class OCRPostprocessor:
    """Apply conservative, role-aware vocabulary corrections to OCR evidence."""

    def __init__(
        self,
        *,
        server_names: Iterable[str] = (),
        common_terms: Iterable[str] = (),
        confusion_substitutions: Iterable[tuple[str, str]] = DEFAULT_CONFUSION_SUBSTITUTIONS,
        min_confidence: float = 0.9,
        min_similarity: float = 0.75,
        server_name_roles: Iterable[str] = DEFAULT_SERVER_NAME_ROLES,
        common_term_roles: Iterable[str] = DEFAULT_COMMON_TERM_ROLES,
    ) -> None:
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        if not 0.0 <= min_similarity <= 1.0:
            raise ValueError("min_similarity must be between 0 and 1")

        self._server_names = _clean_entries(server_names)
        self._common_terms = _clean_entries(common_terms)
        self._confusion_substitutions = frozenset(_clean_confusions(confusion_substitutions))
        self._min_confidence = min_confidence
        self._min_similarity = min_similarity
        self._server_name_roles = frozenset(server_name_roles)
        self._common_term_roles = frozenset(common_term_roles)

    @classmethod
    def from_files(
        cls,
        *,
        server_names_path: Path | None = None,
        common_terms_path: Path | None = None,
        confusions_path: Path | None = None,
        **kwargs: object,
    ) -> "OCRPostprocessor":
        server_names = load_vocab(server_names_path) if server_names_path is not None else ()
        common_terms = load_vocab(common_terms_path) if common_terms_path is not None else ()
        if confusions_path is not None:
            if "confusion_substitutions" in kwargs:
                raise ValueError("use confusions_path or confusion_substitutions, not both")
            kwargs["confusion_substitutions"] = load_confusions(confusions_path)
        return cls(server_names=server_names, common_terms=common_terms, **kwargs)

    def process(self, result: OCRResult, semantic_role: str | None) -> PostprocessedOCRResult:
        if result.confidence < self._min_confidence or not result.text.strip():
            return PostprocessedOCRResult(original=result, corrected_text=result.text)

        if semantic_role in self._server_name_roles:
            vocabulary = self._server_names
            vocabulary_name = "server_names"
            spans = _server_field_spans(result.text, semantic_role)
        elif semantic_role in self._common_term_roles:
            vocabulary = self._common_terms
            vocabulary_name = "common_terms"
            spans = tuple((match.start(), match.end()) for match in _CHINESE_SEGMENT.finditer(result.text))
        else:
            return PostprocessedOCRResult(original=result, corrected_text=result.text)

        corrected_text, corrections = _correct_unique_matches(
            result.text,
            vocabulary,
            vocabulary_name,
            self._min_similarity,
            self._confusion_substitutions,
            spans,
        )
        return PostprocessedOCRResult(
            original=result,
            corrected_text=corrected_text,
            corrections=corrections,
        )


def _clean_entries(entries: Iterable[str]) -> tuple[str, ...]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw_entry in entries:
        entry = raw_entry.strip()
        if entry and entry not in seen:
            cleaned.append(entry)
            seen.add(entry)
    return tuple(cleaned)


def _clean_confusions(entries: Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    cleaned: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for entry in entries:
        if not isinstance(entry, tuple) or len(entry) != 2:
            raise ValueError("OCR confusion entries must be observed/expected pairs")
        observed, expected = entry
        if not isinstance(observed, str) or not isinstance(expected, str):
            raise ValueError("OCR confusion characters must be strings")
        if len(observed) != 1 or len(expected) != 1 or observed == expected:
            raise ValueError("OCR confusion entries must contain two different single characters")
        if entry not in seen:
            cleaned.append(entry)
            seen.add(entry)
    return tuple(cleaned)


def _server_field_spans(text: str, semantic_role: str | None) -> tuple[tuple[int, int], ...]:
    if semantic_role == "account_servers":
        spans: list[tuple[int, int]] = []
        for match in _NONEMPTY_LINE.finditer(text):
            raw = match.group(0)
            leading = len(raw) - len(raw.lstrip())
            trailing = len(raw) - len(raw.rstrip())
            start = match.start() + leading
            end = match.end() - trailing
            if start < end:
                spans.append((start, end))
        return tuple(spans)

    leading = len(text) - len(text.lstrip())
    trailing = len(text) - len(text.rstrip())
    start = leading
    end = len(text) - trailing
    return ((start, end),) if start < end else ()


def _correct_unique_matches(
    text: str,
    vocabulary: tuple[str, ...],
    vocabulary_name: str,
    min_similarity: float,
    confusion_substitutions: frozenset[tuple[str, str]],
    spans: tuple[tuple[int, int], ...],
) -> tuple[str, tuple[TextCorrection, ...]]:
    if not vocabulary:
        return text, ()

    by_length: dict[int, tuple[str, ...]] = {}
    for length in sorted({len(entry) for entry in vocabulary}, reverse=True):
        by_length[length] = tuple(entry for entry in vocabulary if len(entry) == length)

    proposals: list[TextCorrection] = []
    for segment_start, segment_end in spans:
        segment = text[segment_start:segment_end]
        for length, candidates in by_length.items():
            if length > len(segment):
                continue
            for offset in range(len(segment) - length + 1):
                observed = segment[offset : offset + length]
                if observed in candidates:
                    continue
                matches = [
                    candidate
                    for candidate in candidates
                    if _is_conservative_match(
                        observed,
                        candidate,
                        min_similarity,
                        confusion_substitutions,
                    )
                ]
                if len(matches) != 1:
                    continue
                start = segment_start + offset
                proposals.append(
                    TextCorrection(
                        start=start,
                        end=start + length,
                        original=observed,
                        replacement=matches[0],
                        vocabulary=vocabulary_name,
                    )
                )

    corrections = _discard_overlapping(proposals)
    corrected = text
    for correction in reversed(corrections):
        corrected = (
            corrected[: correction.start]
            + correction.replacement
            + corrected[correction.end :]
        )
    return corrected, corrections


def _positional_similarity(left: str, right: str) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    return sum(a == b for a, b in zip(left, right)) / len(left)


def _is_conservative_match(
    left: str,
    right: str,
    min_similarity: float,
    confusion_substitutions: frozenset[tuple[str, str]],
) -> bool:
    if len(left) != len(right) or len(left) < 2:
        return False
    mismatches = sum(a != b for a, b in zip(left, right))
    if mismatches != 1:
        return False
    observed, expected = next((a, b) for a, b in zip(left, right) if a != b)
    if (observed, expected) not in confusion_substitutions:
        return False
    return len(left) <= 3 or _positional_similarity(left, right) >= min_similarity


def _discard_overlapping(proposals: list[TextCorrection]) -> tuple[TextCorrection, ...]:
    unique = list(dict.fromkeys(proposals))
    accepted: list[TextCorrection] = []
    for index, proposal in enumerate(unique):
        overlaps = any(
            index != other_index
            and proposal.start < other.end
            and other.start < proposal.end
            for other_index, other in enumerate(unique)
        )
        if not overlaps:
            accepted.append(proposal)
    return tuple(sorted(accepted, key=lambda item: item.start))
