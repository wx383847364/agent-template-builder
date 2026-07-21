from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image

from agent_template_builder.matcher.hash import hamming_distance, region_hash_image
from agent_template_builder.schema.templates import TemplateSpec, denormalize_bbox


BBox = tuple[int, int, int, int]


class UnsupportedResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class AnchorMatch:
    id: str
    score: float
    actual_hash: Optional[str] = None
    expected_hash: Optional[str] = None
    hamming_distance: Optional[int] = None


@dataclass(frozen=True)
class CalibrationResult:
    status: str
    reason: Optional[str]
    offset: tuple[int, int]
    reference_center: tuple[float, float]
    actual_center: tuple[float, float]


@dataclass(frozen=True)
class MatchResult:
    template: TemplateSpec
    confidence: float
    width: int
    height: int
    anchor_matches: list[AnchorMatch]
    calibration: CalibrationResult
    fallback_reason: Optional[str] = None
    measurable_template_count: int = 0


class TemplateMatcher:
    """1920×1080 整图模板匹配器，并以 anchor 搜索窗口的统一平移量。"""

    def __init__(
        self,
        templates: list[TemplateSpec],
        *,
        resolution: tuple[int, int],
        reference_window_bbox: BBox,
        min_confidence: float = 0.65,
    ) -> None:
        if not templates:
            raise ValueError("至少需要一个模板")
        self._templates = templates
        self._resolution = resolution
        self._reference_window_bbox = reference_window_bbox
        self._min_confidence = min_confidence
        left, top, right, bottom = reference_window_bbox
        self._reference_center = ((left + right) / 2, (top + bottom) / 2)

    def match(self, screenshot_path: Path) -> MatchResult:
        with Image.open(screenshot_path) as image:
            return self.match_image(image)

    def match_image(self, image: Image.Image) -> MatchResult:
        if image.size != self._resolution:
            width, height = image.size
            expected_width, expected_height = self._resolution
            raise UnsupportedResolutionError(
                f"unsupported_resolution: expected {expected_width}x{expected_height}, got {width}x{height}"
            )

        measurable_template_count = sum(1 for template in self._templates if template.measurable_anchor_count)
        scored = [self._score_template(image, template) for template in self._templates]
        score, template, offset, anchor_matches = max(
            scored,
            key=lambda item: (item[0], item[1].priority),
        )
        fallback_reason = None
        status = "calibrated"
        reason = None

        if not anchor_matches or not any(match.score > 0 for match in anchor_matches):
            status, reason = "failed", "no_anchor_hash_match"
            fallback_reason = reason
        elif score < self._min_confidence:
            status, reason = "failed", "low_anchor_score_match"
            fallback_reason = reason
        elif template.calibration_status != "confirmed_1920":
            status, reason = "pending", "template_not_1920_calibrated"

        dx, dy = offset
        ref_x, ref_y = self._reference_center
        calibration = CalibrationResult(
            status=status,
            reason=reason,
            offset=offset,
            reference_center=self._reference_center,
            actual_center=(ref_x + dx, ref_y + dy),
        )
        return MatchResult(
            template=template,
            confidence=round(score, 3),
            width=image.width,
            height=image.height,
            anchor_matches=anchor_matches,
            calibration=calibration,
            fallback_reason=fallback_reason,
            measurable_template_count=measurable_template_count,
        )

    def _score_template(
        self,
        image: Image.Image,
        template: TemplateSpec,
    ) -> tuple[float, TemplateSpec, tuple[int, int], list[AnchorMatch]]:
        anchors = [anchor for anchor in template.anchors if anchor.measurable_hashes]
        if not anchors:
            return (0.0, template, (0, 0), [])

        base_bboxes = [(anchor, denormalize_bbox(anchor.bbox, image.width, image.height)) for anchor in anchors]
        offset = self._find_best_offset(image, base_bboxes)
        anchor_score, matches = self._score_offset(image, base_bboxes, offset)
        return (anchor_score * 0.9 + min(template.priority, 100) / 1000, template, offset, matches)

    def _find_best_offset(
        self,
        image: Image.Image,
        anchors: list[tuple[object, BBox]],
    ) -> tuple[int, int]:
        bounds = self._offset_bounds(image, anchors)
        best = self._best_of(image, anchors, self._grid(bounds, 32, include=(0, 0)))[0]
        for step in (8, 1):
            radius = 32 if step == 8 else 8
            candidates = [
                (dx, dy)
                for dx in range(best[0] - radius, best[0] + radius + 1, step)
                for dy in range(best[1] - radius, best[1] + radius + 1, step)
                if self._in_bounds((dx, dy), bounds)
            ]
            best = self._best_of(image, anchors, candidates)[0]
        return best

    def _offset_bounds(self, image: Image.Image, anchors: list[tuple[object, BBox]]) -> tuple[int, int, int, int]:
        window_left, window_top, window_right, window_bottom = self._reference_window_bbox
        min_dx, max_dx = -window_left, image.width - window_right
        min_dy, max_dy = -window_top, image.height - window_bottom
        for _, (left, top, right, bottom) in anchors:
            min_dx, max_dx = max(min_dx, -left), min(max_dx, image.width - right)
            min_dy, max_dy = max(min_dy, -top), min(max_dy, image.height - bottom)
        return (min_dx, max_dx, min_dy, max_dy)

    def _grid(
        self,
        bounds: tuple[int, int, int, int],
        step: int,
        *,
        include: tuple[int, int],
    ) -> list[tuple[int, int]]:
        min_dx, max_dx, min_dy, max_dy = bounds
        candidates = [
            (dx, dy)
            for dx in range(min_dx, max_dx + 1, step)
            for dy in range(min_dy, max_dy + 1, step)
        ]
        if self._in_bounds(include, bounds):
            candidates.append(include)
        return candidates

    @staticmethod
    def _in_bounds(offset: tuple[int, int], bounds: tuple[int, int, int, int]) -> bool:
        dx, dy = offset
        min_dx, max_dx, min_dy, max_dy = bounds
        return min_dx <= dx <= max_dx and min_dy <= dy <= max_dy

    def _best_of(
        self,
        image: Image.Image,
        anchors: list[tuple[object, BBox]],
        candidates: list[tuple[int, int]],
    ) -> tuple[tuple[int, int], float]:
        best = (0, 0)
        best_score = -1.0
        for offset in candidates:
            score, _ = self._score_offset(image, anchors, offset)
            if score > best_score or (score == best_score and offset == (0, 0)):
                best, best_score = offset, score
        return best, best_score

    def _score_offset(
        self,
        image: Image.Image,
        anchors: list[tuple[object, BBox]],
        offset: tuple[int, int],
    ) -> tuple[float, list[AnchorMatch]]:
        dx, dy = offset
        weighted_score = 0.0
        total_weight = 0.0
        matches: list[AnchorMatch] = []
        for anchor, (left, top, right, bottom) in anchors:
            bbox = (left + dx, top + dy, right + dx, bottom + dy)
            actual_hash = region_hash_image(image, bbox)
            expected_hash, distance = min(
                ((value, hamming_distance(actual_hash, value)) for value in anchor.measurable_hashes),
                key=lambda item: item[1],
            )
            score = max(0.0, 1.0 - distance / max(anchor.max_hamming_distance, 1))
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
        return (weighted_score / total_weight if total_weight else 0.0, matches)
