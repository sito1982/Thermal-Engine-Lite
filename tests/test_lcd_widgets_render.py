"""Render de los 7 elementos LCD y touch_nav (PIL y Qt)."""

from PIL import Image

from canvas import HDMICanvas
from constants import LCD_WIDGET_TYPES
from element import ThemeElement
from renderer import ThemeRenderer

TYPES = list(LCD_WIDGET_TYPES) + ["touch_nav"]


def _element(kind):
    el = ThemeElement(kind, x=10, y=10, width=200, height=60,
                      source="cpu_percent", value=64)
    if kind == "touch_nav":
        el.nav_items = [{"label": "CPU"}, {"label": "GPU"}]
    return el


def test_pil_renders_each_type(qapp):
    renderer = ThemeRenderer()
    for kind in TYPES:
        img = Image.new("RGBA", (400, 120), (0, 0, 0, 0))
        renderer.render_element_with_opacity(img, _element(kind))
        assert img.getbbox() is not None, f"{kind} no dibuja nada"


def test_qt_draw_element_does_not_crash(qapp):
    canvas = HDMICanvas(400, 120)
    for kind in TYPES:
        canvas.set_elements([_element(kind)])
        image = canvas.get_frame_rgb888()
        assert image.width() == 400 and image.height() == 120


def test_from_dict_round_trip_new_fields():
    el = ThemeElement(
        "ring_gauge", arc_span=180, start_angle=90, show_ticks=True,
        thresholds=[60, 85], orientation="vertical",
        tap_screen=2, nav_position="left", nav_items=[{"label": "x"}],
    )
    restored = ThemeElement.from_dict(el.to_dict())
    assert restored.arc_span == 180
    assert restored.start_angle == 90
    assert restored.show_ticks is True
    assert restored.thresholds == [60, 85]
    assert restored.orientation == "vertical"
    assert restored.tap_screen == 2
    assert restored.nav_position == "left"
    assert restored.nav_items == [{"label": "x"}]


def test_defaults_match_studio():
    el = ThemeElement("text")
    assert el.arc_span == 270
    assert el.start_angle == -135
    assert el.show_ticks is False
    assert el.thresholds == [70, 90]
    assert el.orientation == "horizontal"
    assert el.tap_screen == 0
    assert el.nav_position == "bottom"
    assert el.nav_items == []
