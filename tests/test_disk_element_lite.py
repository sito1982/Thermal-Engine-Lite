"""Tests del Disk Element en ThermalEngineLite (render y fuentes de disco)."""

import disks
from constants import DMD_ELEMENT_TYPES, LCD_WIDGET_TYPES, SOURCE_UNITS
from element import ThemeElement
from lcd_widgets import render_element


def test_disk_element_registered_lcd_only():
    assert "disk_element" in LCD_WIDGET_TYPES
    assert "disk_element" not in DMD_ELEMENT_TYPES


def test_disk_sources_available_and_registered():
    sources = disks.disk_sources()
    assert sources
    ids = {s[0] for s in sources}
    assert "disk.all.used" in ids and "disk.all.percent" in ids
    disks.register_units(SOURCE_UNITS)
    assert SOURCE_UNITS["disk.all.used"]["symbol"] == "GB"


def test_disk_element_renders_with_panel_values():
    element = ThemeElement("disk_element", x=0, y=0, width=460, height=150,
                           source="disk.all.percent", value=62,
                           sources=["disk.all.used", "disk.all.free",
                                    "disk.all.total", "disk.all.read",
                                    "disk.all.write"])
    element.panel_values = {"disk.all.used": 320.5, "disk.all.free": 130.2,
                            "disk.all.total": 450.7, "disk.all.read": 42.3,
                            "disk.all.write": 8.1}
    pixels = render_element("disk_element", element, 460, 150)
    assert pixels.shape == (150, 460, 4)
    assert int(pixels[..., 3].max()) > 0


def test_bar_mode_round_trip():
    clone = ThemeElement.from_dict(
        {"type": "disk_element", "bar_mode": "used", "show_sparklines": False})
    assert clone.bar_mode == "used"
    assert clone.show_sparklines is False


def test_disk_icon_draws_in_left_region():
    element = ThemeElement("disk_element", x=0, y=0, width=460, height=150)
    pixels = render_element("disk_element", element, 460, 150)
    left = pixels[:, :150, 3]
    assert int(left.max()) > 0
