"""Tests de orientacion al cargar temas en ThermalEngineLite.

Un tema cuadrado despues de uno vertical debe resetear la orientacion (hoy el
guard `disp_w != disp_h` lo impedia). Se prueba `_apply_theme` sobre un stub
ligero para no arrancar hilos de psutil/sensores.
"""

from types import SimpleNamespace

from runtime import ThemeRuntime
from theme import Theme


class _Stub:
    def __init__(self):
        self.config = {"targets": {}}
        self._vertical_mode = False
        self._last_jpeg_data = None
        self.renderer = SimpleNamespace(
            _vertical_mode=False, lcd_elements=[], lcd_background_color="#000000")

    def set_vertical_mode(self, enabled):
        self._vertical_mode = bool(enabled)
        self.renderer._vertical_mode = bool(enabled)

    def apply_targets(self, targets):
        self._targets = targets


def _apply(runtime, width, height):
    theme = Theme.from_dict({
        "name": "t", "targets": {"lcd": True},
        "lcd": {"display_width": width, "display_height": height, "elements": []},
    })
    ThemeRuntime._apply_theme(runtime, theme, source="test")


def test_square_theme_resets_vertical_orientation():
    runtime = _Stub()
    _apply(runtime, 480, 1920)
    assert runtime._vertical_mode is True

    _apply(runtime, 800, 800)
    assert runtime._vertical_mode is False

    _apply(runtime, 1920, 480)
    assert runtime._vertical_mode is False
