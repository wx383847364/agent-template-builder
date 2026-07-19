from agent_template_builder.tools.generate_qr_login_template import (
    DEFAULT_PADDING_PIXELS,
    DEFAULT_QR_BBOX,
    DEFAULT_SCREENSHOT_SIZE,
    expand_bbox,
    normalize_screen_bbox,
)


def test_default_qr_padding_is_calculated_in_full_screenshot_space() -> None:
    expanded = expand_bbox(
        DEFAULT_QR_BBOX,
        DEFAULT_PADDING_PIXELS,
        (0, 0, *DEFAULT_SCREENSHOT_SIZE),
    )

    assert expanded == (453, 398, 725, 669)
    assert normalize_screen_bbox(expanded, DEFAULT_SCREENSHOT_SIZE) == [
        0.2359375,
        0.368518519,
        0.377604167,
        0.619444444,
    ]
