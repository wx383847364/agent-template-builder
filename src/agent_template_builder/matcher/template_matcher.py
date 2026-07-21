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
class _ProbeSpec:
    measurable_hashes: tuple[str, ...]
    id: str = "window_center_probe"
    weight: float = 1.0
    max_hamming_distance: int = 8


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
        window_probe_bbox: Optional[BBox] = None,
        window_probe_hashes: tuple[str, ...] = (),
        window_probe_pixels: tuple[bytes, ...] = (),
        min_confidence: float = 0.65,
    ) -> None:
        if not templates:
            raise ValueError("至少需要一个模板")
        self._templates = templates
        self._resolution = resolution
        self._reference_window_bbox = reference_window_bbox
        self._window_probe_bbox = window_probe_bbox
        self._window_probe_hashes = tuple(value for value in window_probe_hashes if value)
        self._window_probe_pixels = tuple(value for value in window_probe_pixels if value)
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
        hash_image = image.convert("L")
        fixed_scores = [
            self._score_template(
                hash_image,
                template,
                allow_exhaustive=False,
                forced_offset=(0, 0),
                reject_without_window_offset=False,
            )
            for template in self._templates
            if template.calibration_mode == "fixed_screen"
        ]
        fixed_screen_hit = any(
            # A fixed-screen template may suppress window probing only on an
            # exact anchor confirmation.  A merely similar login hash must not
            # turn a moved window into an uncalibrated fixed-screen export.
            score >= self._min_confidence and matches and all(match.score >= 0.999 for match in matches)
            for score, _, _, matches in fixed_scores
        )
        # Fullscreen screens are already in screen coordinates.  Do not scan a
        # window-chrome probe (which is intentionally absent there) after an
        # unambiguous fullscreen anchor match.
        window_offset = None if fixed_screen_hit else self._find_window_probe_offset(hash_image)
        candidate_templates = self._templates
        if self._has_window_probe and window_offset is not None:
            # A found client chrome defines a windowed capture.  Historical or
            # generic anchors are not allowed to out-rank this shared physical
            # calibration merely because they happen to score at the baseline.
            candidate_templates = [
                template
                for template in self._templates
                if template.calibration_mode == "window_center"
            ]
        scored = [
            self._score_template(
                hash_image,
                template,
                allow_exhaustive=False,
                forced_offset=window_offset if template.calibration_mode == "window_center" else None,
                reject_without_window_offset=(
                    self._has_window_probe and template.calibration_mode == "window_center"
                ),
            )
            for template in candidate_templates
        ]
        if not self._has_window_probe and not any(match.score > 0 for _, _, _, matches in scored for match in matches):
            scored = [
                self._score_template(
                    hash_image,
                    template,
                    allow_exhaustive=template.calibration_status == "confirmed_1920",
                    forced_offset=None,
                    reject_without_window_offset=False,
                )
                for template in self._templates
            ]
        score, template, offset, anchor_matches = max(
            scored,
            key=lambda item: (item[0], item[1].priority),
        )
        fallback_reason = None
        status = "calibrated"
        reason = None

        if template.calibration_mode == "window_center" and window_offset is None:
            status, reason = "failed", "window_center_probe_not_found"
            fallback_reason = reason
        elif not anchor_matches or not any(match.score > 0 for match in anchor_matches):
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
        *,
        allow_exhaustive: bool,
        forced_offset: Optional[tuple[int, int]],
        reject_without_window_offset: bool,
    ) -> tuple[float, TemplateSpec, tuple[int, int], list[AnchorMatch]]:
        anchors = [anchor for anchor in template.anchors if anchor.measurable_hashes]
        if not anchors:
            return (0.0, template, (0, 0), [])

        base_bboxes = [(anchor, denormalize_bbox(anchor.bbox, image.width, image.height)) for anchor in anchors]
        export_bboxes = [
            denormalize_bbox(spec.bbox, image.width, image.height)
            for spec in [*template.elements, *template.static_outputs]
            if spec.bbox is not None
        ]
        if forced_offset is not None:
            bounds = self._offset_bounds(image, base_bboxes, export_bboxes)
            if not self._in_bounds(forced_offset, bounds):
                return (0.0, template, forced_offset, [])
            offset = forced_offset
        elif reject_without_window_offset:
            return (0.0, template, (0, 0), [])
        else:
            offset = self._find_best_offset(
                image,
                base_bboxes,
                export_bboxes,
                allow_exhaustive=allow_exhaustive,
            )
        anchor_score, matches = self._score_offset(image, base_bboxes, offset)
        return (anchor_score * 0.9 + min(template.priority, 100) / 1000, template, offset, matches)

    @property
    def _has_window_probe(self) -> bool:
        return self._window_probe_bbox is not None and bool(
            self._window_probe_pixels or self._window_probe_hashes
        )

    def _find_window_probe_offset(self, image: Image.Image) -> Optional[tuple[int, int]]:
        """Find one shared client-window translation before template ranking.

        A windowed screen is calibrated from chrome that is independent of the
        current panel.  This prevents a coarse hit from an unrelated template
        from suppressing an exact recovery of the real (non-grid) translation.
        """
        if not self._has_window_probe:
            return None
        assert self._window_probe_bbox is not None
        exact_offset = self._find_exact_window_probe_offset(image)
        if self._window_probe_pixels:
            # Raw pixels form a small, high-entropy probe.  It gives an exact
            # answer in linear time and makes an absent probe fail fast instead
            # of repeatedly cropping a wide title bar at every pixel.
            return exact_offset
        if exact_offset is not None:
            return exact_offset
        probe = _ProbeSpec(self._window_probe_hashes)
        bounds = self._offset_bounds(image, [(probe, self._window_probe_bbox)], [])
        best, best_score = self._best_of(image, [(probe, self._window_probe_bbox)], self._grid(bounds, 32, include=(0, 0)))
        if best_score <= 0:
            best = self._exhaustive_primary_anchor_offset(image, (probe, self._window_probe_bbox), bounds)
            best_score, _ = self._score_offset(image, [(probe, self._window_probe_bbox)], best)
        else:
            for step in (8, 1):
                radius = 32 if step == 8 else 8
                candidates = [
                    (dx, dy)
                    for dx in range(best[0] - radius, best[0] + radius + 1, step)
                    for dy in range(best[1] - radius, best[1] + radius + 1, step)
                    if self._in_bounds((dx, dy), bounds)
                ]
                best, best_score = self._best_of(image, [(probe, self._window_probe_bbox)], candidates)
        return best if best_score > 0 else None

    def _find_exact_window_probe_offset(self, image: Image.Image) -> Optional[tuple[int, int]]:
        if not self._window_probe_pixels or self._window_probe_bbox is None:
            return None
        left, top, right, bottom = self._window_probe_bbox
        probe_width, probe_height = right - left, bottom - top
        if probe_width <= 0 or probe_height <= 0:
            return None
        pixels = image.tobytes()
        bounds = self._offset_bounds(image, [], [])
        for target in self._window_probe_pixels:
            if len(target) != probe_width * probe_height:
                continue
            # The middle row is unique in the calibrated client chrome.  Find
            # it with bytes.find (C implementation), then verify the complete
            # small patch to reject any accidental row match.
            row_index = probe_height // 2
            row = target[row_index * probe_width : (row_index + 1) * probe_width]
            start = 0
            while True:
                found = pixels.find(row, start)
                if found < 0:
                    break
                start = found + 1
                y, x = divmod(found, image.width)
                candidate_left = x
                candidate_top = y - row_index
                if candidate_left + probe_width > image.width or candidate_top < 0 or candidate_top + probe_height > image.height:
                    continue
                if any(
                    pixels[(candidate_top + row_number) * image.width + candidate_left : (candidate_top + row_number) * image.width + candidate_left + probe_width]
                    != target[row_number * probe_width : (row_number + 1) * probe_width]
                    for row_number in range(probe_height)
                ):
                    continue
                offset = (candidate_left - left, candidate_top - top)
                if self._in_bounds(offset, bounds):
                    return offset
        return None

    def _find_best_offset(
        self,
        image: Image.Image,
        anchors: list[tuple[object, BBox]],
        export_bboxes: list[BBox],
        *,
        allow_exhaustive: bool,
    ) -> tuple[int, int]:
        bounds = self._offset_bounds(image, anchors, export_bboxes)
        best, best_score = self._best_of(image, anchors, self._grid(bounds, 32, include=(0, 0)))
        if best_score <= 0 and allow_exhaustive:
            return self._exhaustive_primary_anchor_offset(image, anchors[0], bounds)
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

    def _offset_bounds(
        self,
        image: Image.Image,
        anchors: list[tuple[object, BBox]],
        export_bboxes: list[BBox],
    ) -> tuple[int, int, int, int]:
        window_left, window_top, window_right, window_bottom = self._reference_window_bbox
        min_dx, max_dx = -window_left, image.width - window_right
        min_dy, max_dy = -window_top, image.height - window_bottom
        for _, (left, top, right, bottom) in anchors:
            min_dx, max_dx = max(min_dx, -left), min(max_dx, image.width - right)
            min_dy, max_dy = max(min_dy, -top), min(max_dy, image.height - bottom)
        for left, top, right, bottom in export_bboxes:
            min_dx, max_dx = max(min_dx, -left), min(max_dx, image.width - right)
            min_dy, max_dy = max(min_dy, -top), min(max_dy, image.height - bottom)
        return (min_dx, max_dx, min_dy, max_dy)

    def _exhaustive_primary_anchor_offset(
        self,
        image: Image.Image,
        anchor_entry: tuple[object, BBox],
        bounds: tuple[int, int, int, int],
    ) -> tuple[int, int]:
        """Guarantee arbitrary-pixel recovery when coarse hashes provide no gradient."""
        anchor, (left, top, right, bottom) = anchor_entry
        min_dx, max_dx, min_dy, max_dy = bounds
        best = (0, 0)
        best_score = -1.0
        for dx in range(min_dx, max_dx + 1):
            for dy in range(min_dy, max_dy + 1):
                actual_hash = region_hash_image(image, (left + dx, top + dy, right + dx, bottom + dy))
                distance = min(hamming_distance(actual_hash, value) for value in anchor.measurable_hashes)
                score = max(0.0, 1.0 - distance / max(anchor.max_hamming_distance, 1))
                if score > best_score or (score == best_score and (dx, dy) == (0, 0)):
                    best, best_score = (dx, dy), score
                if score == 1.0:
                    return (dx, dy)
        return best

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
