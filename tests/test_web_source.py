"""Fuente Web (web.source), resolucion libre y canvas Custom."""

import copy

from lite_config import DEFAULT_CONFIG
from runtime import ThemeRuntime
from security import validate_preset_schema
from theme import Theme

FULL_THEME = {
    "name": "full",
    "targets": {"web": True, "lcd": True, "dmd": False, "hdmi": True,
                "custom": True},
    "lcd_model": "trofeo_9_16",
    "dmd_config": None,
    "hdmi_config": {"width": 640, "height": 360, "scale_mode": "letterbox"},
    "custom_config": {"width": 800, "height": 480, "name": "Custom"},
    "lcd": {"background_color": "#101010", "display_width": 640,
            "display_height": 480,
            "elements": [{"type": "ring_gauge", "x": 0, "y": 0,
                          "width": 120, "height": 120, "arc_span": 220}]},
    "dmd": {"width": 128, "height": 32, "screens": [{"elements": []}]},
    "hdmi": {"width": 640, "height": 360, "background_color": "#000000",
             "screens": [{"background_color": "#204060", "elements": []}]},
    "custom": {"width": 800, "height": 480, "background_color": "#000000",
               "screens": [{"background_color": "#301020", "elements": []}]},
    "web": {"source": "hdmi"},
}

WEB_ONLY = {
    "name": "web-only",
    "targets": {"web": True, "lcd": False, "dmd": False, "hdmi": False,
                "custom": False},
    "lcd": {"background_color": "#000000", "display_width": 1920,
            "display_height": 480,
            "elements": [{"type": "text", "x": 0, "y": 0, "width": 100,
                          "height": 30, "text": "X"}]},
    "dmd": {"screens": [{"elements": []}]},
    "hdmi": {"screens": [{"elements": []}]},
    "web": {"source": "auto", "width": 1024, "height": 600},
}


def test_schema_accepts_full_theme_and_transition():
    ok, errors = validate_preset_schema(FULL_THEME)
    assert ok, errors
    data = {"name": "t", "elements": [
        {"type": "text", "tap_action": "transition", "tap_screen": 1}]}
    ok, errors = validate_preset_schema(data)
    assert ok, errors


def test_theme_parses_web_and_custom():
    theme = Theme.from_dict(FULL_THEME)
    assert theme.web_source == "hdmi"
    assert theme.custom_config["width"] == 800
    assert theme.custom_width == 800 and theme.custom_height == 480
    assert len(theme.custom_screens) == 1
    restored = theme.to_dict()
    assert restored["web"]["source"] == "hdmi"
    assert restored["custom"]["width"] == 800
    assert restored["custom_config"]["height"] == 480


def test_theme_parses_web_canvas_size():
    theme = Theme.from_dict(WEB_ONLY)
    assert theme.web_width == 1024 and theme.web_height == 600


def _runtime():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["targets"] = {"web": False, "lcd": False, "dmd": False, "hdmi": False}
    cfg["watch_theme"] = False
    return ThemeRuntime(cfg)


def test_web_canvas_size_applies_to_lcd(qapp):
    """Resolucion libre solo-Web: el canvas LCD se renderiza a web.width/height."""
    rt = _runtime()
    try:
        rt.load_theme_dict(WEB_ONLY)
        assert rt.renderer._lcd_display_width == 1024
        assert rt.renderer._lcd_display_height == 600
        assert rt._effective_web_source() == "lcd"
        assert rt.render_web_source_image().size == (1024, 600)
    finally:
        rt.stop()


def test_render_web_source_selection(qapp):
    rt = _runtime()
    try:
        rt.load_theme_dict(FULL_THEME)

        # hdmi explicito con target activo
        rt._active_targets = {"web": True, "lcd": True, "dmd": False,
                              "hdmi": True}
        assert rt._effective_web_source() == "hdmi"
        assert rt.render_web_source_image().size == (640, 360)

        # auto sin target hdmi: con Custom presente -> custom
        rt._active_targets = {"web": True, "lcd": True, "dmd": False,
                              "hdmi": False}
        rt.theme.web_source = "auto"
        assert rt._effective_web_source() == "custom"
        assert rt.render_web_source_image().size == (800, 480)

        # forzado a lcd (usa las dimensiones del bloque lcd)
        rt.theme.web_source = "lcd"
        assert rt._effective_web_source() == "lcd"
        assert rt.render_web_source_image().size == (640, 480)
    finally:
        rt.stop()
