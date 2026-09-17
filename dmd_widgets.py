"""Librería de widgets DMD (HWMON·32) para pantallas 128×32.

Implementa los 13 estilos descritos en el diseño de referencia. Todos los
widgets se dibujan primero en un búfer lógico de **128×32** con las fuentes
bitmap de :mod:`dmd_font` (Tiny 3×5, Medium 5×7, Large 10×14, Giant 15×21) y
se escalan por vecino más cercano al tamaño real del lienzo DMD.

El color es RGB565 (renderizado a RGBA y compuesto por el editor). El tramado
*checkerboard* actúa como "gris" para los estados apagados y las zonas.
"""

from __future__ import annotations

import math
import time

import numpy as np

from constants import SOURCE_UNITS
from dmd_font import measure, text_bitmap

LOGICAL_W = 128
LOGICAL_H = 32


# --------------------------------------------------------------------------
# Utilidades
# --------------------------------------------------------------------------
def _rgb(color):
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        return (int(color[0]), int(color[1]), int(color[2]))
    text = str(color or "#00ff96").lstrip("#")
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except (ValueError, IndexError):
        return (0, 255, 150)


def format_value(value, source):
    """Compact value string with unit, e.g. ``68%``, ``72°C``, ``45W``."""
    info = SOURCE_UNITS.get(source, {"symbol": "%", "type": "percent"})
    symbol = info.get("symbol", "%")
    unit = info.get("type", "percent")
    if unit in ("size", "speed"):
        return f"{value:.1f}{symbol}"
    return f"{value:.0f}{symbol}"


_HISTORY = {}
_LAST_PUSH = {}


def history_for(element, value, length=48):
    """Per-element sample history (rate-limited), seeded with the value."""
    key = getattr(element, "name", id(element))
    now = time.time()
    samples = _HISTORY.get(key)
    if samples is None:
        samples = [float(value)] * length
        _HISTORY[key] = samples
    if now - _LAST_PUSH.get(key, 0.0) >= 0.05:
        samples.append(float(value))
        del samples[:-length]
        _LAST_PUSH[key] = now
    return samples


class Buf:
    """Small RGBA drawing buffer with the primitives the widgets need."""

    def __init__(self, width=LOGICAL_W, height=LOGICAL_H):
        self.w = width
        self.h = height
        self.a = np.zeros((height, width, 4), dtype=np.uint8)

    def pixel(self, x, y, color, alpha=255):
        x = int(x)
        y = int(y)
        if 0 <= x < self.w and 0 <= y < self.h and alpha > 0:
            self.a[y, x] = (color[0], color[1], color[2], alpha)

    def rect(self, x, y, width, height, color, alpha=255):
        if width <= 0 or height <= 0:
            return
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(self.w, int(x) + int(width))
        y1 = min(self.h, int(y) + int(height))
        if x0 < x1 and y0 < y1:
            self.a[y0:y1, x0:x1] = (color[0], color[1], color[2], alpha)

    def hline(self, x0, x1, y, color, alpha=255):
        if x1 < x0:
            x0, x1 = x1, x0
        for x in range(int(x0), int(x1) + 1):
            self.pixel(x, y, color, alpha)

    def vline(self, x, y0, y1, color, alpha=255):
        if y1 < y0:
            y0, y1 = y1, y0
        for y in range(int(y0), int(y1) + 1):
            self.pixel(x, y, color, alpha)

    def rect_outline(self, x, y, width, height, color, alpha=255):
        self.hline(x, x + width - 1, y, color, alpha)
        self.hline(x, x + width - 1, y + height - 1, color, alpha)
        self.vline(x, y, y + height - 1, color, alpha)
        self.vline(x + width - 1, y, y + height - 1, color, alpha)

    def dither_rect(self, x, y, width, height, color, pattern="50", alpha=255):
        if width <= 0 or height <= 0:
            return
        for yy in range(int(y), int(y) + int(height)):
            for xx in range(int(x), int(x) + int(width)):
                if pattern == "25":
                    on = (xx % 4 == 0 and yy % 2 == 0)
                else:  # 50 % checkerboard
                    on = (xx + yy) % 2 == 0
                if on:
                    self.pixel(xx, yy, color, alpha)

    def text(self, value, size, x, y, color, anchor="left", alpha=255):
        value = "" if value is None else str(value)
        if not value:
            return
        grid = text_bitmap(value, size)
        gh, gw = grid.shape
        if anchor == "right":
            x = int(x) - gw
        elif anchor == "center":
            x = int(x) - gw // 2
        x = int(x)
        y = int(y)
        ys, xs = np.nonzero(grid)
        for gy, gx in zip(ys, xs):
            self.pixel(x + gx, y + gy, color, alpha)

    def arc(self, cx, cy, radius, start_deg, end_deg, color, width=1, alpha=255):
        """Stroke an arc (angles in degrees, 0 = 3 o'clock, clockwise)."""
        steps = max(8, int(abs(end_deg - start_deg) * radius / 30))
        for i in range(steps + 1):
            angle = math.radians(start_deg + (end_deg - start_deg) * i / steps)
            for w in range(width):
                r = radius - w
                self.pixel(cx + r * math.cos(angle), cy + r * math.sin(angle),
                           color, alpha)

    def ring(self, cx, cy, radius, width, color, alpha=255):
        for yy in range(cy - radius, cy + radius + 1):
            for xx in range(cx - radius, cx + radius + 1):
                d = math.hypot(xx - cx, yy - cy)
                if radius - width < d <= radius:
                    self.pixel(xx, yy, color, alpha)

    def scaled(self, width, height):
        if width == self.w and height == self.h:
            return self.a
        ys = (np.arange(height) * self.h / max(1, height)).astype(int)
        xs = (np.arange(width) * self.w / max(1, width)).astype(int)
        ys = np.clip(ys, 0, self.h - 1)
        xs = np.clip(xs, 0, self.w - 1)
        return self.a[ys][:, xs]


class Ctx:
    """Everything a widget needs, resolved from the element + canvas size."""

    def __init__(self, element):
        self.el = element
        self.color = _rgb(getattr(element, "color", "#00ff96"))
        self.empty = _rgb(getattr(element, "color_empty", "#12303a"))
        self.dim = tuple(int(v * 0.45) for v in self.color)
        self.value = float(getattr(element, "value", 0) or 0)
        self.max_value = max(float(getattr(element, "max_value", 100) or 100), 0.0001)
        self.label = getattr(element, "text", "") or ""
        self.source = getattr(element, "source", "static")
        self.target = float(getattr(element, "target", 0) or 0)
        self.segments = max(1, int(getattr(element, "segments", 8) or 8))
        self.gap = max(0, int(getattr(element, "gap", 1)))
        self.stride = max(1, int(getattr(element, "line_width", 1) or 1))
        self.sources = list(getattr(element, "sources", []) or [])
        self.panel_values = dict(getattr(element, "panel_values", {}) or {})
        self.buf = Buf()

    def ratio(self, value=None):
        value = self.value if value is None else value
        return max(0.0, min(1.0, float(value) / self.max_value))

    def fmt(self, value=None):
        return format_value(self.value if value is None else value, self.source)


# --------------------------------------------------------------------------
# Widgets (coordenadas lógicas 128×32)
# --------------------------------------------------------------------------
def w_classic_bar(c):
    b = c.buf
    b.text(c.label, "medium", 0, 0, c.color)
    b.text(c.fmt(), "medium", LOGICAL_W, 0, c.color, anchor="right")
    bx, by, bw, bh = 0, 11, LOGICAL_W, 13
    b.dither_rect(bx, by, bw, bh, c.empty, "50")
    b.rect(bx, by, int(bw * c.ratio()), bh, c.color)
    for frac in (0.25, 0.5, 0.75):
        b.vline(bx + int(bw * frac), by, by + bh - 1, c.dim)
    b.rect_outline(bx, by, bw, bh, c.dim)


def w_value_bar(c):
    b = c.buf
    by, bh = 5, 18
    b.dither_rect(0, by, LOGICAL_W, bh, c.empty, "50")
    b.rect(0, by, int(LOGICAL_W * c.ratio()), bh, c.color)
    value = c.fmt()
    w, h = measure(value, "large")
    x = (LOGICAL_W - w) // 2
    y = by + (bh - h) // 2
    # "Negativo": the number is punched out of the fill, drawn on empty pixels.
    total = int(LOGICAL_W * c.ratio())
    grid = text_bitmap(value, "large")
    ys, xs = np.nonzero(grid)
    for gy, gx in zip(ys, xs):
        px = x + gx
        inside = px < total
        b.pixel(px, y + gy, (0, 0, 0) if inside else c.color)
    b.text(c.label, "tiny", 1, 0, c.color)


def w_blocks(c):
    b = c.buf
    b.text(c.fmt(), "medium", 0, 0, c.color)
    b.text(c.label, "medium", LOGICAL_W, 0, c.color, anchor="right")
    count = 20
    bw = 5
    gap = 1
    total = count * bw + (count - 1) * gap
    x0 = (LOGICAL_W - total) // 2
    by, bh = 13, 8
    active = c.ratio() * count
    for i in range(count):
        x = x0 + i * (bw + gap)
        if (i + 0.5) <= active:
            b.rect(x, by, bw, bh, c.color)
        else:
            b.dither_rect(x, by, bw, bh, c.empty, "50")
    marker = x0 + int((total - 1) * 0.85)
    b.vline(marker, by - 2, by + bh + 1, c.dim)
    b.text("0", "tiny", x0, 24, c.dim)
    b.text("50", "tiny", x0 + total // 2, 24, c.dim, anchor="center")
    b.text("100", "tiny", x0 + total, 24, c.dim, anchor="right")


def w_zones(c):
    b = c.buf
    value = c.fmt()
    b.text(value, "large", 1, 9, c.color)
    vw, _ = measure(value, "large")
    bx = vw + 6
    bw = LOGICAL_W - bx - 1
    by, bh = 4, 22
    fine = c.max_value * 0.70
    coarse = c.max_value * 0.85
    b.dither_rect(bx, by, bw, bh, c.empty, "50")
    safe = int(bw * min(1.0, fine / c.max_value))
    b.rect(bx, by, safe, bh, c.color)
    if c.value > fine:
        fx = int(bw * min(1.0, fine / c.max_value))
        tx = int(bw * min(1.0, coarse / c.max_value))
        b.dither_rect(bx + fx, by, max(0, tx - fx), bh, c.color, "25")
    if c.value > coarse:
        cx = int(bw * min(1.0, coarse / c.max_value))
        b.dither_rect(bx + cx, by, bw - cx, bh, c.color, "50")
    marker = bx + int(bw * c.ratio())
    b.vline(marker, by - 2, by + bh + 1, (255, 255, 255))
    b.rect_outline(bx, by, bw, bh, c.dim)


def w_big_number(c):
    b = c.buf
    b.text(c.label, "tiny", LOGICAL_W // 2, 0, c.color, anchor="center")
    value = c.fmt()
    w, h = measure(value, "large")
    x = (LOGICAL_W - w) // 2
    y = 5
    b.text(value, "large", x, y, c.color)
    b.rect(x, y + h + 1, w, 3, c.color)


def w_giant_number(c):
    b = c.buf
    b.text(c.label, "tiny", 1, 0, c.color)
    value = c.fmt()
    w, h = measure(value, "giant")
    x = (LOGICAL_W - w) // 2
    y = max(0, (LOGICAL_H - h) // 2)
    b.text(value, "giant", x, y, c.color)


def _draw_sparkline(b, x, y, w, h, samples, color, target=None):
    b.dither_rect(x, y, w, h, color, "25")
    n = max(2, min(len(samples), w))
    data = samples[-n:]
    step = w / (n - 1)
    prev = None
    for i, value in enumerate(data):
        r = max(0.0, min(1.0, value / 100.0))
        px = x + i * step
        py = y + h - 1 - r * (h - 1)
        if prev is not None:
            b.hline(prev[0], px, py, color)
            if py != prev[1]:
                b.vline(px, min(py, prev[1]), max(py, prev[1]), color)
        prev = (px, py)
    if target:
        ty = y + h - 1 - max(0.0, min(1.0, target / 100.0)) * (h - 1)
        for xx in range(int(x), int(x + w), 2):
            b.pixel(xx, ty, (255, 255, 255))


def w_sparkline(c):
    b = c.buf
    value = c.fmt()
    b.text(value, "large", 1, 9, c.color)
    vw, _ = measure(value, "large")
    sep = vw + 3
    for yy in range(0, LOGICAL_H, 2):
        b.pixel(sep, yy, c.dim)
    samples = history_for(c.el, c.value, 62)
    _draw_sparkline(b, sep + 3, 2, LOGICAL_W - sep - 4, LOGICAL_H - 4, samples, c.color)


def w_histogram(c):
    b = c.buf
    value = c.fmt()
    b.text(value, "large", 1, 9, c.color)
    vw, _ = measure(value, "large")
    bx = vw + 5
    bw = LOGICAL_W - bx - 1
    by, bh = 2, LOGICAL_H - 4
    samples = history_for(c.el, c.value, 20)
    data = samples[-20:]
    while len(data) < 20:
        data.insert(0, 0.0)
    col = 2
    for i, sample in enumerate(data):
        r = max(0.0, min(1.0, sample / 100.0))
        x = bx + i * col
        hgt = max(1, int(r * bh))
        b.rect(x, by + bh - hgt, col - 1, hgt, c.color)
    if c.target:
        ty = by + bh - int(max(0.0, min(1.0, c.target / 100.0)) * bh)
        for xx in range(bx, bx + bw, 2):
            b.pixel(xx, ty, (255, 255, 255))


def w_strip(c):
    b = c.buf
    b.text(c.fmt(), "large", 1, 9, c.color)
    b.text(f"max {c.max_value:.0f}", "tiny", LOGICAL_W, 0, c.dim, anchor="right")
    vw, _ = measure(c.fmt(), "large")
    bx = vw + 5
    bw = LOGICAL_W - bx - 1
    by, bh = 8, 8
    samples = history_for(c.el, c.value, 42)
    data = samples[-42:]
    cell = max(1, bw // 42)
    for i, sample in enumerate(data):
        r = max(0.0, min(1.0, sample / c.max_value))
        x = bx + i * cell
        if r > 0:
            b.rect(x, by + bh - max(1, int(r * bh)), cell - 1,
                   max(1, int(r * bh)), c.color)
        else:
            b.pixel(x, by + bh - 1, c.empty)


def w_arc(c):
    b = c.buf
    radius = 22
    cx = 26
    cy = LOGICAL_H - 2
    b.arc(cx, cy, radius, 180, 360, c.dim, width=1)
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        angle = math.radians(180 + 180 * frac)
        for r in range(radius - 4, radius + 1):
            b.pixel(cx + r * math.cos(angle), cy + r * math.sin(angle), c.dim)
    end = 180 + 180 * c.ratio()
    b.arc(cx, cy, radius - 2, 180, end, c.color, width=2)
    angle = math.radians(end)
    nx = cx + (radius - 6) * math.cos(angle)
    ny = cy + (radius - 6) * math.sin(angle)
    b.hline(cx, nx, cy, (255, 255, 255))
    b.vline(nx, cy, ny, (255, 255, 255))
    value = c.fmt()
    b.text(value, "large", LOGICAL_W - 3, 9, c.color, anchor="right")
    b.text(c.label, "tiny", LOGICAL_W - 3, 0, c.color, anchor="right")


def w_ring(c):
    b = c.buf
    cx, cy, radius = 16, LOGICAL_H // 2, 14
    b.ring(cx, cy, radius, 4, c.empty)
    b.arc(cx, cy, radius - 1, -90, -90 + 360 * c.ratio(), c.color, width=4)
    value = c.fmt()
    b.text(value, "large", cx + radius + 6, 8, c.color)
    b.text(c.label, "tiny", cx + radius + 6, 0, c.color)


def w_fan(c):
    b = c.buf
    value = f"{int(round(c.value))}RPM"
    w, _ = measure(value, "large")
    b.text(value, "large", 1, 9, c.color)
    b.text(c.label or "FAN", "tiny", LOGICAL_W, 0, c.color, anchor="right")
    bx = w + 6
    bw = LOGICAL_W - bx - 1
    by, bh = 6, 20
    red_from = 0.8 if c.max_value <= 3000 else 0.75
    b.dither_rect(bx, by, bw, bh, c.empty, "50")
    red_x = bx + int(bw * red_from)
    b.dither_rect(red_x, by, bx + bw - red_x, bh, (255, 60, 60), "50")
    marker = bx + int(bw * c.ratio())
    b.vline(marker, by - 1, by + bh, (255, 255, 255))
    b.vline(marker - 1, by, by + bh - 1, c.color)
    b.vline(marker + 1, by, by + bh - 1, c.color)
    b.rect_outline(bx, by, bw, bh, c.dim)


_SHORT_LABELS = {
    "cpu_percent": "CPU%", "cpu_temp": "CPU°", "cpu_power": "CPU W",
    "cpu_clock": "CPU M", "gpu_percent": "GPU%", "gpu_temp": "GPU°",
    "gpu_power": "GPU W", "gpu_clock": "GPU M", "gpu_memory_percent": "VRAM%",
    "gpu_memory_clock": "GMEM", "gpu_memory_used": "VRAM", "ram_percent": "RAM",
    "ram_used": "RAM U", "ram_available": "RAM A", "net_download": "DWN",
    "net_upload": "UP", "cpu_fan": "CPU F", "gpu_fan": "GPU F",
    "gpu_fan_percent": "GPU F%", "sys_fan": "SYS F", "pump": "PUMP",
    "game_fps": "FPS", "disk_read": "RD", "disk_write": "WR",
    "uptime": "UP", "nvme_temp": "NVME", "mainboard_temp": "BOARD",
    "static": "VAL",
}


def w_panel(c):
    b = c.buf
    sources = c.sources[:8]
    if not sources:
        sources = [c.source]
    count = len(sources)
    if count <= 1:
        cols, rows = 1, 1
    elif count == 2:
        cols, rows = 2, 1
    elif count <= 4:
        cols, rows = 2, 2
    else:
        cols, rows = 4, 2
    cell_w = LOGICAL_W // cols
    cell_h = LOGICAL_H // rows
    for index, source in enumerate(sources):
        col = index % cols
        row = index // cols
        if row >= rows:
            break
        x = col * cell_w
        y = row * cell_h
        value = float(c.panel_values.get(source, 0) or 0)
        label = _SHORT_LABELS.get(source, source.upper().replace("_", " ")[:5])
        b.text(label, "tiny", x + 1, y + 1, c.color)
        b.text(format_value(value, source), "tiny", x + cell_w - 2, y + 1,
               c.color, anchor="right")
        ratio = max(0.0, min(1.0, value / 100.0))
        b.dither_rect(x + 1, y + cell_h - 4, cell_w - 2, 3, c.empty, "50")
        b.rect(x + 1, y + cell_h - 4, int((cell_w - 2) * ratio), 3, c.color)
        if col:
            for yy in range(y, y + cell_h, 2):
                b.pixel(x, yy, c.dim)
        if row:
            b.hline(x, x + cell_w - 1, y, c.dim)


WIDGETS = {
    "dmd_bar": w_classic_bar,
    "dmd_value_bar": w_value_bar,
    "dmd_blocks": w_blocks,
    "dmd_zones": w_zones,
    "dmd_big_number": w_big_number,
    "dmd_giant_number": w_giant_number,
    "dmd_sparkline": w_sparkline,
    "dmd_histogram": w_histogram,
    "dmd_strip": w_strip,
    "dmd_arc": w_arc,
    "dmd_ring": w_ring,
    "dmd_fan": w_fan,
    "dmd_panel": w_panel,
}


def render_widget(element_type, element, out_w=LOGICAL_W, out_h=LOGICAL_H):
    """Render a DMD widget to an RGBA numpy array of size (out_h, out_w)."""
    draw = WIDGETS.get(element_type)
    if draw is None:
        return np.zeros((out_h, out_w, 4), dtype=np.uint8)
    ctx = Ctx(element)
    draw(ctx)
    return ctx.buf.scaled(out_w, out_h)
