"""Tests for the DMD element catalogue and defaults in constants.py."""

from constants import (
    DMD_DEFAULT_ELEMENT_PROPS,
    DMD_ELEMENT_TYPES,
    ELEMENT_FIELD_VISIBILITY,
)

NEW_DMD_TYPES = ("gauge_circle_dmd", "segmented_bar", "bar_chart")


def test_new_dmd_types_are_registered():
    for element_type in NEW_DMD_TYPES:
        assert element_type in DMD_ELEMENT_TYPES
        assert element_type in DMD_DEFAULT_ELEMENT_PROPS
        assert element_type in ELEMENT_FIELD_VISIBILITY


def test_gauge_circle_dmd_defaults():
    defaults = DMD_DEFAULT_ELEMENT_PROPS["gauge_circle_dmd"]
    assert defaults["radius"] > 0
    assert defaults["segments"] >= 3
    assert defaults["line_width"] >= 1
    assert defaults["max_value"] == 100


def test_segmented_bar_defaults():
    defaults = DMD_DEFAULT_ELEMENT_PROPS["segmented_bar"]
    assert defaults["segments"] >= 1
    assert defaults["gap"] >= 0
    assert "color_empty" in defaults


def test_bar_chart_defaults():
    defaults = DMD_DEFAULT_ELEMENT_PROPS["bar_chart"]
    assert defaults["width"] > 0
    assert defaults["height"] > 0
    assert defaults["max_value"] == 100


def test_visibility_flags_match_component_features():
    gauge = ELEMENT_FIELD_VISIBILITY["gauge_circle_dmd"]
    assert gauge["radius"] and gauge["segments"] and gauge["line_width"]

    segmented = ELEMENT_FIELD_VISIBILITY["segmented_bar"]
    assert segmented["segments"] and segmented["gap"] and segmented["color_empty"]

    bars = ELEMENT_FIELD_VISIBILITY["bar_chart"]
    assert bars["show_background"] and bars["segments"] and bars["gap"]
