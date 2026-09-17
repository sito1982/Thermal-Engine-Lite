"""Pantallas/transiciones HDMI: parseo de tema y mezcla."""

from canvas import HDMICanvas
from dmd_screens import screens_from_block
from dmd_transitions import blend, render_screen_rgb
from outputs.output_hdmi import OutputHDMI
from theme import Theme


def _theme(block):
    return {
        "name": "hdmi",
        "targets": {"web": False, "lcd": False, "dmd": False, "hdmi": True},
        "lcd": {"elements": []},
        "dmd": {"screens": [{"elements": []}]},
        "hdmi": block,
    }


def test_hdmi_screens_parsed():
    theme = Theme.from_dict(_theme({
        "width": 640, "height": 360,
        "transitions_enabled": True,
        "defaults": {"duration_s": 3.0, "transition": "wipe", "transition_ms": 200},
        "screens": [
            {"name": "A", "elements": [{"type": "text", "text": "A"}]},
            {"name": "B", "elements": [{"type": "text", "text": "B"}]},
        ],
    }))
    assert len(theme.hdmi_screens) == 2
    assert theme.hdmi_screens[0].name == "A"
    assert theme.hdmi_elements == theme.hdmi_screens[0].elements
    assert theme.hdmi_transitions_enabled
    assert theme.hdmi_default_transition == "wipe"


def test_hdmi_legacy_elements_become_one_screen():
    theme = Theme.from_dict(_theme({"elements": [{"type": "text", "text": "X"}]}))
    assert len(theme.hdmi_screens) == 1
    assert len(theme.hdmi_elements) == 1


def test_screens_from_block_legacy():
    screens = screens_from_block({"elements": [{"type": "text", "text": "X"}]})
    assert len(screens) == 1
    assert len(screens[0].elements) == 1


def test_render_and_blend_hdmi_screens(qapp):
    theme = Theme.from_dict(_theme({
        "width": 320, "height": 180,
        "screens": [
            {"background_color": "#000000", "elements": []},
            {"background_color": "#ffffff", "elements": []},
        ],
    }))
    canvas = HDMICanvas(320, 180)
    a = render_screen_rgb(canvas, theme.hdmi_screens[0], {})
    b = render_screen_rgb(canvas, theme.hdmi_screens[1], {})
    assert a.shape == (180, 320, 3)
    mid = blend(a, b, "fade", 0.5)
    assert mid.shape == (180, 320, 3)
    assert int(mid.mean()) > 0


def test_output_hdmi_next_frame(qapp):
    theme = Theme.from_dict(_theme({
        "width": 320, "height": 180,
        "transitions_enabled": False,
        "screens": [{"background_color": "#204060", "elements": []}],
    }))

    class _Stub:
        def __init__(self, t):
            self.theme = t

        def get_sensor_data(self):
            return {}

    out = OutputHDMI(_Stub(theme))
    out.canvas = HDMICanvas(320, 180)
    rgb = out._next_frame({})
    assert rgb.shape == (180, 320, 3)
