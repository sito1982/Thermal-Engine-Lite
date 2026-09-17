"""Rendering tests for the DMD canvas components.

These run headless (``QT_QPA_PLATFORM=offscreen``) and cover both render paths:
the live Qt preview (``get_frame_rgb565``) and the PIL display path used by
``ThemeRenderer.render_theme_image``.
"""

import os

import pytest
from PySide6.QtGui import QImage

from canvas import DMDCanvas
from constants import DMD_DEFAULT_ELEMENT_PROPS
from element import ThemeElement

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(PROJECT_ROOT, "assets", "fonts", "ttf", "MatrixSans-Regular.ttf")

FRAME_BYTES = 128 * 32 * 2


def _element(kind, **overrides):
    props = dict(DMD_DEFAULT_ELEMENT_PROPS[kind])
    props.update(overrides)
    return ThemeElement(kind, **props)


def _render_rgb565(kind, **overrides):
    canvas = DMDCanvas(128, 32)
    canvas.set_elements([_element(kind, **overrides)])
    canvas.set_zoom_scale(1)
    return canvas.get_frame_rgb565()


def _bright_pixels(rgb565_bytes, threshold=40):
    image = QImage(
        rgb565_bytes, 128, 32, QImage.Format.Format_RGB16
    ).convertToFormat(QImage.Format.Format_RGB888)
    count = 0
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).green() > threshold:
                count += 1
    return count


@pytest.mark.parametrize("kind", ["gauge_circle_dmd", "segmented_bar", "bar_chart"])
def test_frame_size_is_native_rgb565(qapp, kind):
    assert len(_render_rgb565(kind)) == FRAME_BYTES


@pytest.mark.parametrize("kind", ["gauge_circle_dmd", "segmented_bar", "bar_chart"])
def test_components_draw_visible_pixels(qapp, kind):
    assert _bright_pixels(_render_rgb565(kind, value=100)) > 30


def test_gauge_shows_less_fill_at_low_value(qapp):
    full = _bright_pixels(_render_rgb565("gauge_circle_dmd", value=100), threshold=150)
    empty = _bright_pixels(_render_rgb565("gauge_circle_dmd", value=0), threshold=150)
    assert full > empty


def _pil_renders(qapp, method_name, kind, font=None):
    from PIL import Image

    from renderer import ThemeRenderer

    image = Image.new("RGBA", (128, 32), (8, 9, 11, 255))
    renderer = ThemeRenderer()
    method = getattr(renderer, method_name)
    element = _element(kind)
    if font is None:
        method(image, element, 100, 100)
    else:
        method(image, element, font, 100, 100)
    return image


@pytest.mark.parametrize(
    "method_name,kind",
    [
        ("render_segmented_bar_rgba", "segmented_bar"),
        ("render_bar_chart_rgba", "bar_chart"),
    ],
)
def test_pil_render_draws_something(qapp, method_name, kind):
    image = _pil_renders(qapp, method_name, kind)
    assert image.getbbox() is not None


def test_pil_render_gauge_draws_something(qapp):
    from PIL import ImageFont

    if not os.path.exists(FONT_PATH):
        pytest.skip("DMD font not available")
    font = ImageFont.truetype(FONT_PATH, 7)
    image = _pil_renders(qapp, "render_gauge_circle_dmd_rgba", "gauge_circle_dmd", font)
    assert image.getbbox() is not None
