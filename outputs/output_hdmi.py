"""Salida HDMI: ventana fullscreen en un monitor a resolucion nativa.

Reproduce las pantallas HDMI (hasta 8) con transiciones, igual que el target
DMD, pero Renderizando a color completo con ``HDMICanvas``.

Requiere un servidor grafico (X11/Wayland). En contenedores headless la salida
se desactiva automaticamente si no hay pantallas disponibles.
"""

import time

import numpy as np
from PySide6.QtCore import QTimer
from PySide6.QtGui import QImage

from canvas import HDMICanvas
from device_hdmi import HDMIOutputWindow
from dmd_screens import DMDScreen
from dmd_transitions import blend, render_screen_rgb
from monitors import list_monitors, resolve_monitor
from outputs.base import OutputBase


def _scale_elements(elements, old_w, old_h, new_w, new_h):
    """Escala proporcionalmente x/y/ancho/alto/radio de una lista."""
    if not old_w or not old_h or (old_w, old_h) == (new_w, new_h):
        return
    fx = new_w / old_w
    fy = new_h / old_h
    for element in elements:
        for attr in ("x", "y", "width", "height", "radius"):
            value = getattr(element, attr, None)
            if isinstance(value, (int, float)):
                factor = fx if attr in ("x", "width") else fy
                setattr(element, attr, int(round(value * factor)))
        if hasattr(element, "x"):
            element.x = max(0, min(int(getattr(element, "x", 0)), new_w))
        if hasattr(element, "y"):
            element.y = max(0, min(int(getattr(element, "y", 0)), new_h))


def _rgb_to_qimage(rgb):
    """Convierte un array ``(h, w, 3)`` RGB888 a ``QImage``."""
    height, width = rgb.shape[:2]
    data = np.ascontiguousarray(rgb)
    return QImage(data.tobytes(), width, height, 3 * width,
                  QImage.Format.Format_RGB888).copy()


class OutputHDMI(OutputBase):
    name = "hdmi"

    def __init__(self, runtime):
        super().__init__(runtime)
        self.canvas = None
        self.window = None
        self.timer = None
        # Estado del ciclo de pantallas (espejo de OutputDMD).
        self._play_index = 0
        self._play_elapsed = 0.0
        self._play_phase = "show"
        self._play_progress = 0.0
        self._play_last = 0.0

    def _start(self):
        if not list_monitors():
            raise RuntimeError("No hay monitores disponibles (entorno headless)")

        theme = self.runtime.theme
        screen_id = (self.config or {}).get("screen_id")
        monitor = resolve_monitor(screen_id)
        if not isinstance(monitor, dict):
            raise RuntimeError(f"Monitor HDMI no encontrado: {screen_id}")

        width = int(monitor.get("width") or 1920)
        height = int(monitor.get("height") or 1080)
        # Escalar todas las pantallas si el tema se diseno a otra resolucion.
        old_w = theme.hdmi_width or width
        old_h = theme.hdmi_height or height
        for screen in getattr(theme, "hdmi_screens", []) or []:
            _scale_elements(screen.elements, old_w, old_h, width, height)

        self.canvas = HDMICanvas(width, height)
        self.window = HDMIOutputWindow()
        self.window.show_on_monitor(monitor)
        self._reset_playback()

        fps = max(1, int((self.config or {}).get("fps", 24)))
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(int(1000 / fps))
        print(f"[HDMI] Salida en {monitor.get('name')} {width}x{height} @ {fps}fps")

    def _stop(self):
        if self.timer is not None:
            self.timer.stop()
            self.timer = None
        if self.window is not None:
            try:
                self.window.close_output()
            except Exception:
                pass
            self.window = None
        self.canvas = None

    def _reset_playback(self):
        self._play_index = 0
        self._play_elapsed = 0.0
        self._play_phase = "show"
        self._play_progress = 0.0
        self._play_last = 0.0

    def tick(self):
        if self.canvas is None or self.window is None:
            return
        try:
            sensor_data = self.runtime.get_sensor_data()
            rgb = self._next_frame(sensor_data)
            self.window.render_frame(_rgb_to_qimage(rgb))
        except Exception as e:
            print(f"[HDMI] Error en render: {e}")

    def _next_frame(self, sensor_data):
        theme = self.runtime.theme
        screens = getattr(theme, "hdmi_screens", None) or [DMDScreen()]
        transitions = getattr(theme, "hdmi_transitions_enabled", True)

        now = time.perf_counter()
        if self._play_last == 0.0:
            self._play_last = now
        dt = max(0.0, min(0.5, now - self._play_last))
        self._play_last = now

        if not transitions or len(screens) <= 1:
            self._play_phase = "show"
            self._play_progress = 0.0
            if self._play_index >= len(screens):
                self._play_index = 0
            return render_screen_rgb(self.canvas, screens[self._play_index],
                                     sensor_data)

        if self._play_phase == "show":
            self._play_elapsed += dt
            screen = screens[self._play_index % len(screens)]
            if self._play_elapsed < max(0.1, float(screen.duration_s)):
                return render_screen_rgb(self.canvas, screen, sensor_data)
            self._play_elapsed = 0.0
            self._play_phase = "transition"
            self._play_progress = 0.0

        screen_a = screens[self._play_index % len(screens)]
        next_index = (self._play_index + 1) % len(screens)
        screen_b = screens[next_index]
        duration_ms = max(1, int(screen_a.transition_ms))
        self._play_progress += (dt * 1000.0) / duration_ms

        rgb_a = render_screen_rgb(self.canvas, screen_a, sensor_data)
        rgb_b = render_screen_rgb(self.canvas, screen_b, sensor_data)
        if self._play_progress >= 1.0:
            self._play_index = next_index
            self._play_phase = "show"
            self._play_elapsed = 0.0
            self._play_progress = 0.0
            return rgb_b
        return blend(rgb_a, rgb_b, screen_a.transition, self._play_progress)

    def status(self):
        data = super().status()
        if self.window is not None and isinstance(self.window.monitor, dict):
            data["monitor"] = self.window.monitor.get("name")
        return data
