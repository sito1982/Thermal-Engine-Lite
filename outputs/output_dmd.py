"""Salida DMD: render offscreen + envio RGB565 por TCP con transiciones."""

import time

from PySide6.QtCore import QTimer

from canvas import DMDCanvas
from dmd_screens import DMDScreen
from dmd_transitions import blend, render_screen_rgb, rgb_to_rgb565_le
from outputs.base import OutputBase


class OutputDMD(OutputBase):
    name = "dmd"

    def __init__(self, runtime):
        super().__init__(runtime)
        self.canvas = None
        self.sender = None
        self.timer = None
        # Estado del ciclo de pantallas.
        self._play_index = 0
        self._play_elapsed = 0.0
        self._play_phase = "show"
        self._play_progress = 0.0
        self._play_last = 0.0

    def _start(self):
        from device_dmd import DMDSenderThread

        cfg = self.config or {}
        ip = cfg.get("ip")
        port = int(cfg.get("port", 8889))
        fps = max(1, int(cfg.get("fps", 12)))
        theme = self.runtime.theme
        width = int(cfg.get("width") or getattr(theme, "dmd_width", 128) or 128)
        height = int(cfg.get("height") or getattr(theme, "dmd_height", 32) or 32)

        if not ip:
            raise ValueError("DMD sin 'ip' configurada")

        self.canvas = DMDCanvas(width, height)
        self.canvas.set_background_color("#000000")
        self.sender = DMDSenderThread(ip, port, width, height, fps)
        self.sender.start()

        self._reset_playback()
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(int(1000 / fps))
        print(f"[DMD] Enviando a {ip}:{port} ({width}x{height} @ {fps}fps)")

    def _stop(self):
        if self.timer is not None:
            self.timer.stop()
            self.timer = None
        if self.sender is not None:
            self.sender.stop()
            self.sender = None
        self.canvas = None

    def _reset_playback(self):
        self._play_index = 0
        self._play_elapsed = 0.0
        self._play_phase = "show"
        self._play_progress = 0.0
        self._play_last = 0.0

    # ------------------------------------------------------------- tick --
    def tick(self):
        if self.sender is None or self.canvas is None:
            return
        if self.canvas.dmd_width != self.sender.width \
                or self.canvas.dmd_height != self.sender.height:
            return
        try:
            sensor_data = self.runtime.get_sensor_data()
            rgb = self._next_frame(sensor_data)
            self.sender.push(rgb_to_rgb565_le(rgb))
        except Exception as e:
            print(f"[DMD] Error en envio: {e}")

    def _next_frame(self, sensor_data):
        theme = self.runtime.theme
        screens = getattr(theme, "dmd_screens", None) or [DMDScreen()]
        transitions = getattr(theme, "dmd_transitions_enabled", True)

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

    # ----------------------------------------------------------- estado --
    def status(self):
        data = super().status()
        if self.sender is not None:
            stats = self.sender.stats()
            data.update(stats)
            data["ip"] = self.sender.ip
            data["port"] = self.sender.port
        return data
