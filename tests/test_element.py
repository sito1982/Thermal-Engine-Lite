"""Tests for ThemeElement defaults used by the DMD components."""

from element import ThemeElement


def test_max_value_is_clamped_positive():
    element = ThemeElement("bar_gauge", max_value=0)
    assert element.max_value > 0


def test_dmd_component_fields_round_trip():
    element = ThemeElement(
        "segmented_bar",
        segments=12,
        gap=2,
        color_empty="#112233",
        line_width=3,
    )
    assert element.segments == 12
    assert element.gap == 2
    assert element.color_empty == "#112233"
    assert element.line_width == 3


def test_defaults_for_new_dmd_types():
    gauge = ThemeElement("gauge_circle_dmd")
    assert gauge.segments >= 3
    assert gauge.line_width >= 1

    chart = ThemeElement("bar_chart")
    assert chart.show_background is True


def test_lite_source_prefix_is_normalized():
    element = ThemeElement.from_dict(
        {"type": "text", "source": "lite.cpu_temp"})
    assert element.source == "cpu_temp"


def test_lite_sources_list_prefix_is_normalized():
    element = ThemeElement.from_dict(
        {"type": "dmd_panel", "sources": ["lite.cpu_temp", "cpu_fan"]})
    assert element.sources == ["cpu_temp", "cpu_fan"]


def test_non_lite_source_untouched():
    element = ThemeElement.from_dict(
        {"type": "text", "source": "cpu_percent"})
    assert element.source == "cpu_percent"


def test_tap_screen_next_prev_round_trip():
    element = ThemeElement.from_dict(
        {"type": "rectangle", "tap_action": "transition", "tap_screen": "next"})
    assert element.tap_screen == "next"
    clone = ThemeElement.from_dict(element.to_dict())
    assert clone.tap_screen == "next"
    assert ThemeElement("rectangle", tap_screen=3).tap_screen == 3
