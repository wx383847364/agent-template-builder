from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from agent_template_builder.discovery.schema import DiscoveryData


PANEL_COLOR = (255, 96, 96)
TYPE_COLORS = {
    "button": (80, 255, 110),
    "tab": (80, 220, 255),
    "list_item": (255, 210, 70),
    "input": (190, 100, 255),
    "checkbox": (255, 150, 70),
    "data_field": (70, 220, 255),
    "text": (245, 245, 80),
    "decoration": (160, 160, 160),
}
INTERACTION_COLOR = (255, 128, 0)


def render_annotated_screenshot(
    screenshot_path: Path,
    data: DiscoveryData,
    output_path: Path,
) -> None:
    with Image.open(screenshot_path) as source:
        image = source.convert("RGB")

    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for panel in data.panels:
        _draw_box(
            draw,
            panel.bbox,
            PANEL_COLOR,
            f"P:{panel.id}:{panel.type_guess}",
            font,
            width=3,
        )

    for element in data.elements:
        color = TYPE_COLORS.get(element.type, TYPE_COLORS.get(element.category, (255, 255, 255)))
        _draw_box(
            draw,
            element.bbox,
            color,
            f"E:{element.id}:{element.type}",
            font,
            width=2,
        )
        if element.interaction_bbox_guess is not None:
            _draw_box(
                draw,
                element.interaction_bbox_guess,
                INTERACTION_COLOR,
                f"I:{element.id}",
                font,
                width=1,
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")


def _draw_box(
    draw: ImageDraw.ImageDraw,
    bbox: tuple[int, int, int, int],
    color: tuple[int, int, int],
    label: str,
    font: ImageFont.ImageFont,
    *,
    width: int,
) -> None:
    left, top, right, bottom = bbox
    draw.rectangle(
        (left, top, right - 1, bottom - 1),
        outline=color,
        width=width,
    )
    label_bbox = draw.textbbox((left, top), label, font=font)
    label_width = label_bbox[2] - label_bbox[0] + 4
    label_height = label_bbox[3] - label_bbox[1] + 4
    label_top = max(0, top - label_height)
    draw.rectangle(
        (left, label_top, left + label_width, label_top + label_height),
        fill=(0, 0, 0),
    )
    draw.text((left + 2, label_top + 2), label, fill=color, font=font)
