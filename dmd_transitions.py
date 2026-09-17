"""Renderizado y transiciones de pantallas DMD.

Renderiza cada pantalla a un array RGB888 (usando un ``DMDCanvas`` offscreen) y
mezcla dos pantallas según el efecto y el progreso (0..1). El resultado se
convierte a RGB565 little-endian para enviarlo al panel.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage


def qimage_to_rgb_array(qimg: QImage) -> np.ndarray:
    """Convert a QImage to a contiguous ``(h, w, 3)`` uint8 array."""
    if qimg.format() != QImage.Format.Format_RGB888:
        qimg = qimg.convertToFormat(QImage.Format.Format_RGB888)
    width, height = qimg.width(), qimg.height()
    bytes_per_line = qimg.bytesPerLine()
    raw = np.frombuffer(bytes(qimg.constBits()), np.uint8)
    return raw.reshape(height, bytes_per_line)[:, :width * 3].reshape(height, width, 3).copy()


def render_screen_rgb(canvas, screen, sensor_data=None) -> np.ndarray:
    """Render ``screen`` with the given offscreen ``canvas`` to RGB888."""
    if sensor_data:
        from sensor_hub import resolve_sensor_value

        for element in screen.elements:
            source = getattr(element, "source", "static")
            if source != "static":
                value = resolve_sensor_value(sensor_data, source)
                if value is not None:
                    element.value = value
            if element.type == "dmd_panel":
                panel = {}
                for src in getattr(element, "sources", []):
                    value = resolve_sensor_value(sensor_data, src)
                    panel[src] = (value if value is not None
                                  else element.panel_values.get(src, 0))
                element.panel_values = panel
    canvas.set_background_color(screen.background_color)
    canvas.set_elements(screen.elements)
    return qimage_to_rgb_array(canvas.get_frame_rgb888())


def blend(a: np.ndarray, b: np.ndarray, effect: str, progress: float) -> np.ndarray:
    """Blend screen ``a`` into ``b`` according to ``effect`` at ``progress``."""
    t = max(0.0, min(1.0, float(progress)))
    if effect == "cut":
        return b if t >= 1.0 else a
    if effect == "fade":
        return (a.astype(np.float32) * (1.0 - t) + b.astype(np.float32) * t).astype(np.uint8)

    height, width = a.shape[:2]
    if effect == "wipe":
        out = a.copy()
        edge = int(width * t)
        if edge > 0:
            out[:, :edge] = b[:, :edge]
        return out
    if effect == "dissolve":
        yy, xx = np.mgrid[0:height, 0:width]
        mask = (((xx * 7 + yy * 13) % 256) < int(t * 256))
        out = a.copy()
        out[mask] = b[mask]
        return out
    if effect == "slide_left":
        offset = int((1.0 - t) * width)
        out = a.copy()
        if offset < width:
            out[:, offset:] = b[:, :width - offset]
        return out
    if effect == "slide_right":
        offset = int((1.0 - t) * width)
        out = a.copy()
        if offset < width:
            out[:, :width - offset] = b[:, offset:]
        return out
    if effect == "slide_up":
        offset = int((1.0 - t) * height)
        out = a.copy()
        if offset < height:
            out[offset:, :] = b[:height - offset, :]
        return out
    if effect == "slide_down":
        offset = int((1.0 - t) * height)
        out = a.copy()
        if offset < height:
            out[:height - offset, :] = b[offset:, :]
        return out
    # Efecto desconocido: corte.
    return b if t >= 1.0 else a


def rgb_to_rgb565_le(rgb: np.ndarray) -> bytes:
    """Convert an ``(h, w, 3)`` uint8 RGB array to little-endian RGB565 bytes."""
    r = (rgb[..., 0].astype(np.uint16) >> 3)
    g = (rgb[..., 1].astype(np.uint16) >> 2)
    b = (rgb[..., 2].astype(np.uint16) >> 3)
    value = (r << 11) | (g << 5) | b
    return value.astype("<u2").tobytes()


def frame_payload(rgb: np.ndarray, width: int, height: int) -> bytes:
    """Header (0xAA 0x55 w h) + RGB565 little-endian payload."""
    return bytes([0xAA, 0x55, int(width), int(height)]) + rgb_to_rgb565_le(rgb)
