"""Tests de pantallas DMD y transiciones."""

import numpy as np

from canvas import DMDCanvas
from dmd_screens import DMDScreen, screens_from_dmd
from dmd_transitions import blend, frame_payload, render_screen_rgb, rgb_to_rgb565_le
from element import ThemeElement


def test_screen_round_trip():
    screen = DMDScreen(
        name="A", background_color="#101010", duration_s=7.0,
        transition="slide_left", transition_ms=300,
        elements=[ThemeElement("text", text="hi")])
    restored = DMDScreen.from_dict(screen.to_dict())
    assert restored.name == "A"
    assert restored.duration_s == 7.0
    assert restored.transition == "slide_left"
    assert restored.transition_ms == 300
    assert restored.elements[0].text == "hi"


def test_screens_from_dmd_legacy_single_screen():
    screens = screens_from_dmd({"background_color": "#000", "elements": [
        {"type": "text", "text": "x"}]})
    assert len(screens) == 1
    assert screens[0].elements[0].text == "x"


def test_screens_from_dmd_new_format():
    screens = screens_from_dmd({"screens": [
        {"name": "S1", "elements": []},
        {"name": "S2", "elements": [], "transition": "wipe"}]})
    assert [s.name for s in screens] == ["S1", "S2"]
    assert screens[1].transition == "wipe"


def _frames():
    a = np.zeros((32, 128, 3), np.uint8)
    b = np.full((32, 128, 3), 255, np.uint8)
    return a, b


def test_blend_cut_and_fade():
    a, b = _frames()
    assert np.array_equal(blend(a, b, "cut", 0.0), a)
    assert np.array_equal(blend(a, b, "cut", 1.0), b)
    assert np.array_equal(blend(a, b, "fade", 0.0), a)
    assert np.array_equal(blend(a, b, "fade", 1.0), b)


def test_blend_effects_return_full_frame():
    a, b = _frames()
    for effect in ("wipe", "dissolve", "slide_left", "slide_right",
                   "slide_up", "slide_down"):
        out = blend(a, b, effect, 1.0)
        assert out.shape == (32, 128, 3)
        assert np.array_equal(out, b), effect


def test_frame_payload_size_and_header():
    rgb = np.zeros((32, 128, 3), np.uint8)
    payload = frame_payload(rgb, 128, 32)
    assert payload[:4] == bytes([0xAA, 0x55, 128, 32])
    assert len(payload) == 4 + 128 * 32 * 2
    assert rgb_to_rgb565_le(rgb) == bytes(8192)


def test_render_screen_rgb(qapp):
    canvas = DMDCanvas(128, 32)
    screen = DMDScreen(elements=[
        ThemeElement("text", x=2, y=2, text="HI", font_size=8)])
    rgb = render_screen_rgb(canvas, screen, {})
    assert rgb.shape == (32, 128, 3)
