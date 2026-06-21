from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent_template_builder.matcher.hash import hamming_distance, image_size, region_hash
from agent_template_builder.matcher.roi import GameView, denormalize_bbox_in_view, detect_game_view
from agent_template_builder.schema.templates import TemplateSpec


@dataclass(frozen=True)
class AnchorMatch:
    id: str
    score: float
    actual_hash: Optional[str] = None
    expected_hash: Optional[str] = None
    hamming_distance: Optional[int] = None


@dataclass(frozen=True)
class AspectRatioProfile:
    label: str
    ratio: float
    tolerance: float = 0.04


@dataclass(frozen=True)
class MatchResult:
    template: TemplateSpec
    confidence: float
    width: int
    height: int
    game_view: GameView
    anchor_matches: list[AnchorMatch]
    aspect_ratio_label: Optional[str] = None
    fallback_reason: Optional[str] = None
    measurable_template_count: int = 0


class TemplateMatcher:
    """快速首轮匹配器。

    已有实测锚点哈希的模板优先胜出。在真实截图锚点尚未补齐时，
    匹配器会回退到主世界模板，而不是高优先级弹窗模板。坐标使用
    归一化比例，因此模板可以适配宽高比兼容的多种分辨率。
    """

    def __init__(
        self,
        templates: list[TemplateSpec],
        supported_sizes: set[tuple[int, int]],
        aspect_profiles: list[AspectRatioProfile],
    ) -> None:
        if not templates:
            raise ValueError("至少需要一个模板")
        self._templates = templates
        self._supported_sizes = supported_sizes
        self._aspect_profiles = aspect_profiles

    def match(self, screenshot_path: Path) -> MatchResult:
        width, height = image_size(screenshot_path)
        game_view = detect_game_view(screenshot_path)
        aspect_label, size_score = self._score_viewport(game_view.width, game_view.height)
        measurable_template_count = sum(1 for template in self._templates if template.measurable_anchor_count)

        scored = [
            (self._score_template(screenshot_path, template, game_view, size_score), template)
            for template in self._templates
        ]
        best, template = max(scored, key=lambda item: (item[0][0], item[1].priority))
        confidence, anchor_matches = best
        fallback_reason = None
        fallback_confidence = 0.35 * size_score

        if measurable_template_count == 0:
            template = self._default_template()
            confidence = 0.70 * size_score
            anchor_matches = []
            fallback_reason = "no_measurable_anchor_hash"
        elif anchor_matches and not any(match.score > 0 for match in anchor_matches):
            template = self._default_template()
            confidence = fallback_confidence
            fallback_reason = "no_anchor_hash_match"
        elif template.screen_type != "main_world" and confidence < fallback_confidence:
            template = self._default_template()
            confidence = fallback_confidence
            fallback_reason = "low_anchor_score_match"

        return MatchResult(
            template=template,
            confidence=round(confidence, 3),
            width=width,
            height=height,
            game_view=game_view,
            anchor_matches=anchor_matches,
            aspect_ratio_label=aspect_label,
            fallback_reason=fallback_reason,
            measurable_template_count=measurable_template_count,
        )

    def _score_viewport(self, width: int, height: int) -> tuple[Optional[str], float]:
        if (width, height) in self._supported_sizes:
            return ("fixed_window", 1.0)

        if not self._aspect_profiles:
            return (None, 1.0 if not self._supported_sizes else 0.55)

        actual_ratio = width / height
        best = min(self._aspect_profiles, key=lambda profile: abs(actual_ratio - profile.ratio))
        delta = abs(actual_ratio - best.ratio)
        if delta <= best.tolerance:
            score = max(0.75, 1.0 - (delta / best.tolerance) * 0.25)
            return (best.label, score)
        return (None, 0.45)

    def _score_template(
        self,
        screenshot_path: Path,
        template: TemplateSpec,
        game_view: GameView,
        size_score: float,
    ) -> tuple[float, list[AnchorMatch]]:
        measurable = [anchor for anchor in template.anchors if anchor.measurable_hashes]
        if not measurable:
            return (0.0, [])

        weighted_score = 0.0
        total_weight = 0.0
        matches: list[AnchorMatch] = []

        for anchor in measurable:
            bbox = denormalize_bbox_in_view(anchor.bbox, game_view)
            actual_hash = region_hash(screenshot_path, bbox)
            expected_hash, distance = min(
                (
                    (expected_hash, hamming_distance(actual_hash, expected_hash))
                    for expected_hash in anchor.measurable_hashes
                ),
                key=lambda item: item[1],
            )
            score = max(0.0, 1.0 - (distance / max(anchor.max_hamming_distance, 1)))
            weighted_score += score * anchor.weight
            total_weight += anchor.weight
            matches.append(
                AnchorMatch(
                    id=anchor.id,
                    score=round(score, 3),
                    actual_hash=actual_hash,
                    expected_hash=expected_hash,
                    hamming_distance=distance,
                )
            )

        anchor_score = weighted_score / total_weight if total_weight else 0.0
        priority_score = min(template.priority, 100) / 1000
        return (anchor_score * 0.9 * size_score + priority_score, matches)

    def _default_template(self) -> TemplateSpec:
        for template in self._templates:
            if template.screen_type == "main_world":
                return template
        return self._templates[-1]
