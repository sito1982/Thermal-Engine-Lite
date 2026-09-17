"""Tests para el target HDMI: monitores, canvas, letterbox y esquema."""

from PySide6.QtGui import QImage

import monitors
from canvas import HDMICanvas
from device_hdmi import HDMIOutputWindow
from lite_config import DEFAULT_CONFIG
from security import validate_preset_schema


def _mon(name, is_hdmi=False, primary=False, width=1920, height=1080, model="X"):
    mon = {
        "index": 0,
        "name": name,
        "connector": monitors.connector_type(name),
        "is_hdmi": is_hdmi or monitors.is_hdmi(name),
        "logical_width": width,
        "logical_height": height,
        "width": width,
        "height": height,
        "dpr": 1.0,
        "refresh": 60.0,
        "manufacturer": "LG",
        "model": model,
        "serial": "123",
        "primary": primary,
    }
    mon["id"] = monitors.monitor_id(mon)
    return mon


def test_connector_detection():
    assert monitors.connector_type("HDMI-A-1") == "HDMI"
    assert monitors.connector_type("DP-1") == "DP"
    assert monitors.connector_type("eDP-1") == "eDP"
    assert monitors.connector_type("DVI-D-0") == "DVI"
    assert monitors.connector_type("unknown") == "OTHER"
    assert monitors.is_hdmi("HDMI-A-2")
    assert not monitors.is_hdmi("DP-1")


def test_monitor_id_and_label():
    mon = _mon("HDMI-A-1", model="LG X")
    assert monitors.monitor_id(mon) == "HDMI-A-1|LG_X|123"
    label = monitors.display_label(mon)
    assert "HDMI-A-1" in label
    assert "1920×1080" in label
    assert "HDMI" in label


def test_resolve_monitor_by_id_and_fallback():
    a = _mon("DP-1", model="A")
    b = _mon("HDMI-A-1", is_hdmi=True, model="B")
    b["id"] = monitors.monitor_id(b)
    assert monitors.resolve_monitor(b["id"], [a, b]) is b
    # Sin id: prefiere el primer HDMI
    assert monitors.resolve_monitor(None, [a, b]) is b
    # Sin HDMI: cae al primario
    a["primary"] = True
    assert monitors.resolve_monitor(None, [a]) is a


def test_list_monitors_shape(qapp):
    mons = monitors.list_monitors()
    assert mons  # el backend offscreen también reporta una pantalla
    for mon in mons:
        assert {"index", "name", "width", "height", "connector", "id"} <= set(mon)
        assert mon["width"] > 0 and mon["height"] > 0


def test_hdmi_canvas_frame_rgb888(qapp):
    canvas = HDMICanvas(320, 180)
    canvas.set_hdmi_size(320, 180)
    assert (canvas.hdmi_width, canvas.hdmi_height) == (320, 180)
    image = canvas.get_frame_rgb888()
    assert isinstance(image, QImage)
    assert image.width() == 320 and image.height() == 180
    assert image.format() == QImage.Format.Format_RGB888


def test_letterbox_exact_and_pillarbox():
    assert HDMIOutputWindow.letterbox_rect(1920, 1080, 1920, 1080) == \
        (0.0, 0.0, 1920.0, 1080.0)
    x, y, w, h = HDMIOutputWindow.letterbox_rect(1920, 1080, 3840, 1080)
    assert (w, h) == (1920.0, 540.0)
    assert x == 0.0 and y == 270.0
    # Entrada inválida no debe dividir por cero
    assert HDMIOutputWindow.letterbox_rect(0, 0, 100, 100) == (0.0, 0.0, 0.0, 0.0)


def test_schema_accepts_hdmi_keys():
    data = {
        "name": "hdmi_theme",
        "targets": {"web": False, "lcd": False, "dmd": False, "hdmi": True},
        "hdmi_config": {"screen_id": "HDMI-A-1|X|123", "width": 1920, "height": 1080},
        "hdmi": {"width": 1920, "height": 1080, "background_color": "#000000",
                 "elements": []},
    }
    ok, errors = validate_preset_schema(data)
    assert ok, errors


def test_settings_defaults_include_hdmi():
    assert "hdmi" in DEFAULT_CONFIG["targets"]
    assert DEFAULT_CONFIG["targets"]["hdmi"] is False
    assert "hdmi_config" in DEFAULT_CONFIG


def test_element_action_roundtrip_and_schema():
    from element import ThemeElement

    element = ThemeElement(
        "text", tap_action="command", tap_command="/bin/echo",
        tap_args=["a", "b"], tap_workdir="/tmp",
    )
    data = element.to_dict()
    restored = ThemeElement.from_dict(data)
    assert restored.tap_action == "command"
    assert restored.tap_command == "/bin/echo"
    assert restored.tap_args == ["a", "b"]
    assert restored.tap_workdir == "/tmp"

    ok, errors = validate_preset_schema({"name": "t", "elements": [data]})
    assert ok, errors

    bad = dict(data)
    bad["tap_action"] = "rm-rf"
    ok, errors = validate_preset_schema({"name": "t", "elements": [bad]})
    assert not ok


def test_element_action_defaults_none():
    from element import ThemeElement

    element = ThemeElement("text")
    assert element.tap_action == "none"
    assert element.tap_command == ""
    assert element.tap_args == []

