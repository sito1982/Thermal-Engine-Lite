"""Tests del elemento "video" (LCD/HDMI, no DMD) y del encaje de frames."""

from PIL import Image

from constants import (
    DEFAULT_ELEMENT_PROPS,
    DMD_ELEMENT_TYPES,
    ELEMENT_FIELD_VISIBILITY,
    ELEMENT_TYPES,
)
from element import ThemeElement
from video_background import fit_frame


def test_video_type_registration():
    assert "video" in ELEMENT_TYPES
    assert "video" not in DMD_ELEMENT_TYPES
    assert "video" in ELEMENT_FIELD_VISIBILITY
    assert "video" in DEFAULT_ELEMENT_PROPS


def test_video_visibility_fields():
    visibility = ELEMENT_FIELD_VISIBILITY["video"]
    assert visibility["width"] and visibility["height"]
    assert visibility["video"] and visibility["video_fit"]
    assert not visibility["color"]


def test_video_element_round_trip():
    element = ThemeElement("video", video_path="/tmp/x.mp4",
                           video_fit_mode="fit_width")
    restored = ThemeElement.from_dict(element.to_dict())
    assert restored.video_path == "/tmp/x.mp4"
    assert restored.video_fit_mode == "fit_width"


def _frame():
    return Image.new("RGB", (80, 40), (200, 100, 50))


def test_fit_frame_modes_return_target_size():
    for mode in ("fit_height", "fit_width", "stretch", "contain"):
        out = fit_frame(_frame(), (128, 32), mode)
        assert out.size == (128, 32)


def test_fit_height_fills_height():
    out = fit_frame(_frame(), (128, 32), "fit_height")
    # Cover: the middle column must be opaque (no letterbox bars).
    assert out.getpixel((64, 16))[3] == 255
