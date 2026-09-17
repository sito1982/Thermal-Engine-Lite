"""Tests del modelo de tema de ThermalEngineLite."""

import pytest

from security import validate_preset_schema
from theme import Theme, ThemeError

DUAL = {
    "name": "Dual",
    "targets": {"web": True, "lcd": True, "dmd": True, "hdmi": False},
    "lcd_model": "trofeo_9_16",
    "dmd_config": {"ip": "10.0.0.2", "port": 8889},
    "lcd": {
        "background_color": "#010203",
        "display_width": 1920,
        "display_height": 480,
        "elements": [{"type": "text", "name": "a", "x": 1, "y": 2, "text": "hi"}],
    },
    "dmd": {
        "width": 128,
        "height": 32,
        "elements": [{"type": "text", "name": "b", "x": 0, "y": 0, "text": "x"}],
    },
    "hdmi": {
        "background_color": "#000000",
        "width": 1024,
        "height": 600,
        "elements": [{"type": "rectangle", "name": "c"}],
    },
}


def test_parses_dual_format():
    theme = Theme.from_dict(DUAL)
    assert theme.name == "Dual"
    assert theme.lcd_background_color == "#010203"
    assert theme.lcd_width == 1920 and theme.lcd_height == 480
    assert len(theme.lcd_elements) == 1
    assert theme.dmd_width == 128 and theme.dmd_height == 32
    assert len(theme.dmd_screens) == 1
    assert len(theme.dmd_screens[0].elements) == 1
    assert len(theme.hdmi_elements) == 1
    assert theme.targets["dmd"] is True
    assert theme.dmd_config["ip"] == "10.0.0.2"


def test_parses_legacy_format():
    legacy = {
        "name": "Legacy",
        "background_color": "#000000",
        "display_width": 1280,
        "display_height": 480,
        "elements": [{"type": "text", "name": "t"}],
    }
    theme = Theme.from_dict(legacy)
    assert theme.lcd_width == 1280
    assert len(theme.lcd_elements) == 1
    assert theme.dmd_screens and len(theme.dmd_screens) == 1


def test_roundtrip_to_dict():
    theme = Theme.from_dict(DUAL)
    data = theme.to_dict()
    again = Theme.from_dict(data)
    assert again.name == theme.name
    assert len(again.lcd_elements) == len(theme.lcd_elements)
    assert again.dmd_width == theme.dmd_width


def test_invalid_theme_raises():
    with pytest.raises(ThemeError):
        Theme.from_dict(["not", "a", "dict"])


def test_unknown_key_is_rejected():
    with pytest.raises(ThemeError):
        Theme.from_dict({"name": "x", "surprise": True})


def test_lite_block_is_accepted():
    """El bloque `lite` viaja en el tema publicado; Lite debe aceptarlo."""
    ok, errors = validate_preset_schema(
        {"name": "x", "lite": {"url": "http://host:4241", "port": 4241}})
    assert ok, errors
    theme = Theme.from_dict({"name": "x", "lite": {"url": "http://host:4241"}})
    assert theme.name == "x"
