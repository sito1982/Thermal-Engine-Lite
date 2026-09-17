"""Regression tests for the configurable circle gauge thickness and the
removal of the analog clock element."""

from constants import ELEMENT_FIELD_VISIBILITY, ELEMENT_TYPES
from element import ThemeElement


def test_analog_clock_type_removed():
    assert "analog_clock" not in ELEMENT_TYPES
    assert "analog_clock" not in ELEMENT_FIELD_VISIBILITY


def test_legacy_circle_gauge_defaults_to_thickness_15():
    element = ThemeElement.from_dict({"type": "circle_gauge", "radius": 120})
    assert element.line_width == 15


def test_circle_gauge_thickness_round_trip():
    element = ThemeElement("circle_gauge", line_width=40)
    restored = ThemeElement.from_dict(element.to_dict())
    assert restored.line_width == 40


def test_dmd_component_fields_round_trip():
    element = ThemeElement(
        "segmented_bar", segments=12, gap=2, color_empty="#102030", max_value=250
    )
    restored = ThemeElement.from_dict(element.to_dict())
    assert restored.segments == 12
    assert restored.gap == 2
    assert restored.color_empty == "#102030"
    assert restored.max_value == 250
