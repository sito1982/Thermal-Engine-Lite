"""Librería de elementos/widgets de alta resolución para canvas normal (LCD/HDMI).

A diferencia de :mod:`dmd_widgets` (fuentes bitmap y tramado para 128×32), estos
elementos se renderizan con **PIL + supersampling** y devuelven una imagen RGBA
(``numpy`` de ``(out_h, out_w, 4)``) que consumen tanto el canvas (Qt,
``QImage``) como el render final (PIL), garantizando que la previsualización y
el frame enviado al panel sean idénticos.

Todos los elementos están pensados para **no** usarse en DMD: son el bloque de
construcción de los widgets de resumen (CPU, GPU, RAM...) y de los diseños
sueltos de alta resolución.
"""

from __future__ import annotations

import math
import os
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from constants import SOURCE_UNITS

# Supersampling: se dibuja a ``out * SS`` y se reduce con LANCZOS para obtener
# bordes suaves en arcos, gradientes y texto.
SS = 2


# ---------------------------------------------------------------------------
# Utilidades de color
# ---------------------------------------------------------------------------
def _rgb_tuple(color):
    """Normaliza cualquier color a una tupla ``(r, g, b)``."""
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        return (int(color[0]), int(color[1]), int(color[2]))
    text = str(color or "#00ff96").lstrip("#")
    try:
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
    except (ValueError, IndexError):
        return (0, 255, 150)


def _rgba(color, opacity=100):
    """Color RGBA con opacidad 0-100."""
    r, g, b = _rgb_tuple(color)
    a = int(round(255 * max(0, min(100, float(opacity))) / 100))
    return (r, g, b, a)


def _grad(stops, position):
    """Interpola un color de ``stops`` ``[(pos, color), ...]`` en ``position``."""
    if not stops:
        return (0, 255, 150)
    parsed = sorted((float(p), c) for p, c in stops)
    position = max(0.0, min(1.0, float(position)))
    if position <= parsed[0][0]:
        return _rgb_tuple(parsed[0][1])
    if position >= parsed[-1][0]:
        return _rgb_tuple(parsed[-1][1])
    for i in range(len(parsed) - 1):
        p0, c0 = parsed[i]
        p1, c1 = parsed[i + 1]
        if p0 <= position <= p1:
            span = (p1 - p0) or 1.0
            f = (position - p0) / span
            a = _rgb_tuple(c0)
            b = _rgb_tuple(c1)
            return tuple(int(a[j] + (b[j] - a[j]) * f) for j in range(3))
    return _rgb_tuple(parsed[-1][1])


def _auto_color(base_color, source, value):
    """Color verde/ámbar/rojo según umbrales (temp vs. porcentaje)."""
    base = _rgb_tuple(base_color)
    if "temp" in (source or ""):
        if value < 60:
            return base
        if value < 80:
            return (255, 204, 0)
        return (255, 50, 50)
    if value < 70:
        return base
    if value < 90:
        return (255, 204, 0)
    return (255, 50, 50)


def format_value(value, source, temp_hide_unit=False):
    """Valor formateado con su unidad (``68%``, ``72°C``, ``45W``...)."""
    info = SOURCE_UNITS.get(source, {"symbol": "%", "type": "percent"})
    symbol = info.get("symbol", "%")
    unit = info.get("type", "percent")
    if unit == "temp" and temp_hide_unit:
        return f"{value:.0f}°"
    if unit in ("size", "speed", "energy"):
        return f"{value:.1f}{symbol}"
    return f"{value:.0f}{symbol}"


# ---------------------------------------------------------------------------
# Fuentes (resolución propia para no depender del hilo GUI de Qt)
# ---------------------------------------------------------------------------
_FONT_DIRS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts"),
    os.path.expanduser("~/.local/share/fonts"),
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "/Library/Fonts",
    os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
]

# Familias comunes sin fichero homónimo en Linux -> candidatos por nombre.
_FAMILY_ALIASES = {
    "arial": ["liberationsans", "notosans", "freesans", "dejavusans"],
    "helvetica": ["liberationsans", "notosans", "dejavusans"],
    "segoeui": ["notosans", "liberationsans", "dejavusans"],
    "tahoma": ["liberationsans", "notosans", "dejavusans"],
    "verdana": ["liberationsans", "notosans", "dejavusans"],
    "timesnewroman": ["liberationserif", "notoserif", "dejavuserif"],
    "couriernew": ["liberationmono", "notosansmono", "dejavusansmono"],
}

_FONT_FILES = None
_FONT_PATH_CACHE: dict = {}
_FONT_CACHE: dict = {}


def _all_font_files():
    global _FONT_FILES
    if _FONT_FILES is None:
        files = []
        for directory in _FONT_DIRS:
            if not os.path.isdir(directory):
                continue
            for root, _dirs, names in os.walk(directory):
                for name in names:
                    if name.lower().endswith((".ttf", ".otf", ".ttc")):
                        files.append(os.path.join(root, name))
        _FONT_FILES = files
    return _FONT_FILES


def _alnum(text):
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _stem_matches(font_file, token):
    return token in _alnum(os.path.basename(font_file))


def _pick_font_file(token, bold, italic):
    """Devuelve el fichero de fuente más adecuado para un token de familia."""
    if not token:
        return None
    files = _all_font_files()
    bold_opts = [True, False] if bold else [False]
    italic_opts = [True, False] if italic else [False]
    for want_bold in bold_opts:
        for want_italic in italic_opts:
            for font_file in files:
                stem = os.path.basename(font_file).lower()
                if not _stem_matches(font_file, token):
                    continue
                has_bold = "bold" in stem or "black" in stem or "heavy" in stem
                has_italic = "italic" in stem or "oblique" in stem
                if want_bold != has_bold:
                    continue
                if want_italic != has_italic:
                    continue
                return font_file
    # Segundo intento relajado (ignora peso/estilo).
    for font_file in files:
        if _stem_matches(font_file, token):
            return font_file
    return None


def _font_path(family, bold=False, italic=False):
    key = (str(family or ""), bool(bold), bool(italic))
    if key in _FONT_PATH_CACHE:
        return _FONT_PATH_CACHE[key]
    token = _alnum(str(family or ""))
    path = _pick_font_file(token, bold, italic)
    if path is None:
        for alias in _FAMILY_ALIASES.get(token, []):
            path = _pick_font_file(alias, bold, italic)
            if path:
                break
    if path is None:
        for fallback in ("liberationsans", "notosans", "freesans", "dejavusans"):
            path = _pick_font_file(fallback, bold, italic)
            if path:
                break
    _FONT_PATH_CACHE[key] = path
    return path


def _font(family, size, bold=False, italic=False):
    size = max(1, int(round(size)))
    key = (str(family or ""), bool(bold), bool(italic), size)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    path = _font_path(family, bold, italic)
    try:
        font = ImageFont.truetype(path, size) if path else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


# Aliases públicos (los usan el panel de widgets y las previews).
def get_font(family, size, bold=False, italic=False):
    """Fuente PIL cacheada para la familia/tamaño dados."""
    return _font(family, size, bold, italic)


def to_rgba(color, opacity=100):
    """Convierte un color a RGBA con opacidad 0-100."""
    return _rgba(color, opacity)


# ---------------------------------------------------------------------------
# Historial de muestras (sparkline / column chart)
# ---------------------------------------------------------------------------
_HISTORY: dict = {}
_LAST_PUSH: dict = {}
_SEED_PROFILE = (0.22, 0.48, 0.85, 0.60, 0.33, 0.95, 0.72, 0.50,
                 0.28, 0.88, 0.66, 0.40, 0.55, 0.78, 0.30, 0.70)


def history_for(element, value, length=64, key=None):
    """Muestras por elemento/métrica (limitadas en frecuencia), sembradas con
    el valor. ``key`` permite mantener historiales separados por métrica (p. ej.
    READ vs WRITE en el Disk Element)."""
    base_key = getattr(element, "name", id(element))
    storage_key = f"{base_key}:{key}" if key else base_key
    now = time.time()
    samples = _HISTORY.get(storage_key)
    if samples is None:
        base = float(value)
        samples = [base * _SEED_PROFILE[i % len(_SEED_PROFILE)] for i in range(length)]
        _HISTORY[storage_key] = samples
    if now - _LAST_PUSH.get(storage_key, 0.0) >= 0.05:
        samples.append(float(value))
        del samples[:-length]
        _LAST_PUSH[storage_key] = now
    return samples


# ---------------------------------------------------------------------------
# Contexto
# ---------------------------------------------------------------------------
class Ctx:
    """Todo lo que un elemento necesita, resuelto desde el elemento y su caja."""

    def __init__(self, element, w, h):
        self.el = element
        self.w = w
        self.h = h
        self.s = SS
        self.color = _rgb_tuple(getattr(element, "color", "#00ff96"))
        self.bg = _rgba(getattr(element, "background_color", "#0d1117"),
                        getattr(element, "background_color_opacity", 100))
        self.empty = _rgba(getattr(element, "color_empty", "#1a1a2e"), 100)
        self.text_rgba = _rgba(getattr(element, "text_color", getattr(element, "color", "#00ff96")),
                               getattr(element, "text_color_opacity", 100))
        self.label_rgba = _rgba(getattr(element, "label_text_color", getattr(element, "color", "#00ff96")),
                                getattr(element, "text_color_opacity", 100))
        self.value = float(getattr(element, "_animated_display_value",
                                   getattr(element, "value", 0)) or 0)
        self.max_value = max(float(getattr(element, "max_value", 100) or 100), 0.0001)
        self.ratio = max(0.0, min(1.0, self.value / self.max_value))
        self.label = getattr(element, "text", "") or ""
        self.source = getattr(element, "source", "static")
        self.sources = list(getattr(element, "sources", []) or [])
        self.panel_values = dict(getattr(element, "panel_values", {}) or {})
        self.bar_mode = getattr(element, "bar_mode", "free") or "free"
        self.show_sparklines = bool(getattr(element, "show_sparklines", True))
        self.target = float(getattr(element, "target", 0) or 0)
        self.segments = max(1, int(getattr(element, "segments", 8) or 8))
        self.gap = max(0.0, float(getattr(element, "gap", 1) or 0))
        self.line_w = max(1.0, float(getattr(element, "line_width", 4) or 4))
        self.arc_span = float(getattr(element, "arc_span", 270) or 270)
        self.start_angle = float(getattr(element, "start_angle", -135) or 0)
        self.show_ticks = bool(getattr(element, "show_ticks", False))
        self.orientation = getattr(element, "orientation", "horizontal") or "horizontal"
        raw_thresholds = getattr(element, "thresholds", [70, 90]) or []
        self.thresholds = [float(t) for t in raw_thresholds]
        self.gradient_stops = list(getattr(element, "gradient_stops",
                                           [(0.0, "#00ff96"), (1.0, "#ff4444")]) or [])
        self.show_gradient = bool(getattr(element, "show_gradient", False))
        self.rounded = bool(getattr(element, "rounded_corners", False)
                            or getattr(element, "gauge_rounded_ends", False))
        self.line_thickness = max(1.0, float(getattr(element, "line_thickness", 2) or 2))
        self.smooth = bool(getattr(element, "smooth", False))
        self.show_background = bool(getattr(element, "show_background", True))
        self.auto_color = bool(getattr(element, "auto_color_change", False))
        self.temp_hide_unit = bool(getattr(element, "temp_hide_unit", False))
        self.border_radius = float(getattr(element, "border_radius", 0) or 0)
        self.font_family = getattr(element, "font_family", "Arial") or "Arial"
        self.font_size = max(1.0, float(getattr(element, "font_size", 24) or 24))
        self.font_bold = bool(getattr(element, "font_bold", False))
        self.font_italic = bool(getattr(element, "font_italic", False))
        self.label_font_family = getattr(element, "label_font_family", self.font_family) or self.font_family
        self.label_font_size = max(1.0, float(getattr(element, "label_font_size",
                                                     max(10.0, self.font_size * 0.5)) or 10))
        self.value_font = _font(self.font_family, self.font_size * self.s,
                                self.font_bold, self.font_italic)
        self.label_font = _font(self.label_font_family, self.label_font_size * self.s,
                                getattr(element, "label_font_bold", False),
                                getattr(element, "label_font_italic", False))
        self.small_font = _font(self.font_family, max(8.0, self.font_size * 0.42) * self.s,
                                self.font_bold, self.font_italic)

    def fill_color(self):
        """Color de relleno de un gauge (auto-color o base)."""
        if self.auto_color:
            return _auto_color(self.color, self.source, self.value)
        return self.color


# ---------------------------------------------------------------------------
# Helpers de dibujo (coordenadas lógicas -> dispositivo)
# ---------------------------------------------------------------------------
def _rounded_gradient(img, box, radius, stops, alpha=255, limit_x=None):
    """Rellena un rectángulo redondeado con un gradiente horizontal."""
    x0, y0, x1, y1 = (int(round(v)) for v in box)
    width = x1 - x0
    height = y1 - y0
    if width <= 0 or height <= 0:
        return
    grad = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for dx in range(width):
        t = dx / max(1, width - 1)
        gd.line([(dx, 0), (dx, height)], fill=_grad(stops, t) + (alpha,))
    mask = Image.new("L", (width, height), 0)
    _rrect(ImageDraw.Draw(mask), 0, 0, width - 1, height - 1, radius, fill=255)
    if limit_x is not None:
        cut = int(round(limit_x)) - x0
        cut = max(0, min(width, cut))
        ImageDraw.Draw(mask).rectangle([cut, 0, width, height], fill=0)
    img.paste(grad, (x0, y0), mask)


def _arc_point(cx, cy, radius, angle_deg):
    """Punto sobre un arco (grados estilo PIL: 0 = 3 en punto, horario)."""
    return (cx + radius * math.cos(math.radians(angle_deg)),
            cy + radius * math.sin(math.radians(angle_deg)))


def _rrect(d, x0, y0, x1, y1, radius, fill=None, outline=None, width=1):
    """``rounded_rectangle`` tolerante a cajas degeneradas (tamaños mínimos)."""
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if x1 <= x0 or y1 <= y0:
        return
    radius = max(0, int(radius))
    radius = min(radius, (x1 - x0) // 2, (y1 - y0) // 2)
    d.rounded_rectangle([x0, y0, x1, y1], radius=radius,
                        fill=fill, outline=outline, width=width)


def _area_gradient(img, origin, size, polygon, color, top_alpha=160):
    """Rellena un polígono con un gradiente vertical del color a transparente."""
    ox, oy = int(round(origin[0])), int(round(origin[1]))
    width, height = int(round(size[0])), int(round(size[1]))
    if width <= 0 or height <= 0:
        return
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).polygon(polygon, fill=255)
    grad = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    r, g, b = color
    for dy in range(height):
        alpha = int(top_alpha * (1 - dy / max(1, height - 1)))
        gd.line([(0, dy), (width, dy)], fill=(r, g, b, alpha))
    img.paste(grad, (ox, oy), mask)


# ---------------------------------------------------------------------------
# Elementos
# ---------------------------------------------------------------------------
def draw_ring_gauge(img, d, c):
    s = c.s
    w, h = c.w, c.h
    lw = c.line_w
    radius = max(lw / 2 + 1, min(w, h) / 2 - lw / 2 - 1)
    cx, cy = w / 2, h / 2
    box = [(cx - radius) * s, (cy - radius) * s, (cx + radius) * s, (cy + radius) * s]
    dwidth = max(1, int(round(lw * s)))
    span = max(1.0, min(360.0, c.arc_span))
    a0 = (270.0 + c.start_angle) % 360.0

    # Pista de fondo.
    if span >= 359.5:
        d.ellipse(box, outline=c.bg, width=dwidth)
    else:
        d.arc(box, a0, a0 + span, fill=c.bg, width=dwidth)

    value_span = c.ratio * span
    fill = c.fill_color()
    if c.show_gradient and value_span > 0.5:
        steps = max(16, int(value_span * 2))
        for i in range(steps):
            t0 = value_span * i / steps
            t1 = value_span * (i + 1) / steps
            col = _grad(c.gradient_stops, (i + 0.5) / steps)
            d.arc(box, a0 + t0, a0 + t1 + 0.6, fill=col, width=dwidth)
        if c.rounded:
            for frac, ang in ((0.0, a0), (1.0, a0 + value_span)):
                col = _grad(c.gradient_stops, frac)
                px, py = _arc_point(cx, cy, radius, ang)
                d.ellipse([(px - lw / 2) * s, (py - lw / 2) * s,
                           (px + lw / 2) * s, (py + lw / 2) * s], fill=col)
    elif value_span > 0:
        d.arc(box, a0, a0 + value_span, fill=fill, width=dwidth)
        if c.rounded:
            for ang in (a0, a0 + value_span):
                px, py = _arc_point(cx, cy, radius, ang)
                d.ellipse([(px - lw / 2) * s, (py - lw / 2) * s,
                           (px + lw / 2) * s, (py + lw / 2) * s], fill=fill)

    if c.show_ticks:
        ticks = 11
        for i in range(ticks):
            ang = a0 + span * i / (ticks - 1)
            r0 = radius + lw / 2 + 2
            r1 = r0 + 6
            d.line([((cx + r0 * math.cos(math.radians(ang))) * s,
                     (cy + r0 * math.sin(math.radians(ang))) * s),
                    ((cx + r1 * math.cos(math.radians(ang))) * s,
                     (cy + r1 * math.sin(math.radians(ang))) * s)],
                   fill=c.empty, width=max(1, int(s)))

    # Valor y etiqueta en el centro.
    vtext = format_value(c.value, c.source, c.temp_hide_unit)
    d.text((cx * s, (cy - h * 0.05) * s), vtext, font=c.value_font,
           fill=c.text_rgba, anchor="mm")
    if c.label:
        d.text((cx * s, (cy + h * 0.20) * s), c.label, font=c.label_font,
               fill=c.label_rgba, anchor="mm")


def draw_segment_bar(img, d, c):
    s = c.s
    w, h = c.w, c.h
    segments = c.segments
    gap = c.gap
    horizontal = c.orientation != "vertical"
    if horizontal:
        seg_len = max(0.5, (w - gap * (segments - 1)) / segments)
        seg_thick = h
    else:
        seg_len = max(0.5, (h - gap * (segments - 1)) / segments)
        seg_thick = w
    filled = c.ratio * segments
    for i in range(segments):
        if horizontal:
            x0, y0, x1, y1 = i * (seg_len + gap), 0, i * (seg_len + gap) + seg_len, seg_thick
        else:
            x0, y0, x1, y1 = 0, i * (seg_len + gap), seg_thick, i * (seg_len + gap) + seg_len
        reached = (i + 0.5) <= filled
        if reached:
            col = _grad(c.gradient_stops, i / max(1, segments - 1)) if c.show_gradient else c.color
        else:
            col = c.empty
        box = [x0 * s, y0 * s, x1 * s, y1 * s]
        if c.rounded:
            _rrect(d, box[0], box[1], box[2], box[3], min(seg_len, seg_thick) / 2 * s, fill=col)
        else:
            d.rectangle(box, fill=col)


def draw_zone_bar(img, d, c):
    s = c.s
    w, h = c.w, c.h
    radius = c.border_radius or (h / 2 if c.rounded else 0)
    _rrect(d, 0, 0, w * s, h * s, radius * s, fill=c.bg)
    if c.ratio > 0:
        _rounded_gradient(img, (0, 0, w * s, h * s), radius * s, c.gradient_stops,
                          limit_x=w * c.ratio * s)
    # Divisiones de zona.
    for threshold in c.thresholds:
        frac = max(0.0, min(1.0, threshold / c.max_value))
        tx = frac * w * s
        d.line([(tx, 0), (tx, h * s)], fill=(0, 0, 0, 120), width=max(1, int(s)))
    # Marcador de valor.
    mx = c.ratio * w * s
    d.line([(mx, 0), (mx, h * s)], fill=(255, 255, 255, 235), width=max(1, int(round(s * 1.5))))
    if c.target:
        fx = max(0.0, min(1.0, c.target / c.max_value)) * w * s
        for ty in range(0, int(h * s), max(2, int(3 * s))):
            d.line([(fx, ty), (fx, ty + s)], fill=(255, 255, 255, 180), width=max(1, int(s)))


def draw_stat_tile(img, d, c):
    s = c.s
    w, h = c.w, c.h
    radius = c.border_radius or h * 0.14
    _rrect(d, 0, 0, w * s, h * s, radius * s, fill=c.bg)
    pad = max(6.0, h * 0.10)
    accent_w = max(3.0, w * 0.018)
    _rrect(d, pad * s, pad * s, (pad + accent_w) * s, (h - pad) * s, accent_w / 2 * s, fill=c.fill_color())
    text_x = pad + accent_w + max(6.0, w * 0.03)
    if c.label:
        d.text((text_x * s, (pad + h * 0.06) * s), c.label.upper(), font=c.small_font,
               fill=c.label_rgba, anchor="lm")
    vtext = format_value(c.value, c.source, c.temp_hide_unit)
    d.text((text_x * s, (h * 0.56) * s), vtext, font=c.value_font,
           fill=c.text_rgba, anchor="lm")
    # Barra de progreso inferior.
    bar_h = max(3.0, h * 0.05)
    bar_y = h - pad - bar_h
    bar_w = w - text_x - pad
    if bar_w > 4:
        _rrect(d, text_x * s, bar_y * s, (text_x + bar_w) * s, (bar_y + bar_h) * s, bar_h / 2 * s, fill=c.empty)
        fill_w = bar_w * c.ratio
        if fill_w > 1:
            _rrect(d, text_x * s, bar_y * s, (text_x + fill_w) * s, (bar_y + bar_h) * s, bar_h / 2 * s, fill=c.fill_color())
def draw_sparkline(img, d, c):
    s = c.s
    w, h = c.w, c.h
    radius = c.border_radius or h * 0.15
    if c.show_background:
        _rrect(d, 0, 0, w * s, h * s, radius * s, fill=c.bg)
    pad = max(3.0, h * 0.10)
    inner_w = w - 2 * pad
    inner_h = h - 2 * pad
    if inner_w <= 2 or inner_h <= 2:
        return
    samples = history_for(c.el, c.value, max(16, int(inner_w)))
    n = len(samples)
    points = []
    for i, sample in enumerate(samples):
        r = max(0.0, min(1.0, float(sample) / c.max_value))
        px = pad + inner_w * (i / max(1, n - 1))
        py = pad + inner_h * (1 - r)
        points.append((px, py))
    dev_points = [(px * s, py * s) for px, py in points]
    base_y = pad + inner_h
    # Relleno degradado bajo la curva.
    if c.show_gradient:
        polygon = [(0, inner_h * s)] + [(px - pad, py - pad) for px, py in dev_points] \
            + [(inner_w * s, inner_h * s)]
        _area_gradient(img, (pad * s, pad * s), (inner_w * s, inner_h * s),
                       polygon, c.fill_color())
    line_w = max(1, int(round(c.line_thickness * s)))
    d.line(dev_points, fill=c.fill_color(), width=line_w, joint="curve")
    if c.target:
        ty = pad + inner_h * (1 - max(0.0, min(1.0, c.target / c.max_value)))
        for tx in range(int(pad * s), int((pad + inner_w) * s), max(2, int(4 * s))):
            d.line([(tx, ty * s), (tx + s, ty * s)], fill=(255, 255, 255, 170), width=1)


def draw_level_bar(img, d, c):
    s = c.s
    w, h = c.w, c.h
    horizontal = c.orientation != "vertical"
    radius = c.border_radius or (min(w, h) / 2 if c.rounded else min(6.0, min(w, h) * 0.15))
    _rrect(d, 0, 0, w * s, h * s, radius * s, fill=c.bg)
    inset = max(1.0, min(w, h) * 0.06)
    inner_radius = max(0.0, radius - inset)
    if horizontal:
        fill_x1 = (inset + (w - 2 * inset) * c.ratio)
        if c.ratio > 0.01:
            if c.show_gradient:
                _rounded_gradient(img, (inset * s, inset * s, (w - inset) * s, (h - inset) * s),
                                  inner_radius * s, c.gradient_stops, limit_x=fill_x1 * s)
            else:
                _rrect(d, inset * s, inset * s, fill_x1 * s, (h - inset) * s, inner_radius * s, fill=c.fill_color())
    else:
        fill_y0 = (h - inset - (h - 2 * inset) * c.ratio)
        if c.ratio > 0.01:
            _rrect(d, inset * s, fill_y0 * s, (w - inset) * s, (h - inset) * s, inner_radius * s, fill=c.fill_color())
    vtext = format_value(c.value, c.source, c.temp_hide_unit)
    d.text((w / 2 * s, h / 2 * s), vtext, font=c.small_font, fill=c.text_rgba, anchor="mm")


def draw_column_chart(img, d, c):
    s = c.s
    w, h = c.w, c.h
    radius = c.border_radius or h * 0.12
    if c.show_background:
        _rrect(d, 0, 0, w * s, h * s, radius * s, fill=c.bg)
    bars = c.segments if c.segments > 1 else max(1, int(w // 8))
    gap = c.gap
    bar_w = max(1.0, (w - gap * (bars - 1)) / bars)
    samples = history_for(c.el, c.value, bars)[-bars:]
    if len(samples) < bars:
        samples = [0.0] * (bars - len(samples)) + samples
    for i, sample in enumerate(samples):
        r = max(0.0, min(1.0, float(sample) / c.max_value))
        bar_h = max(1.0, r * (h - 2))
        bx = i * (bar_w + gap)
        by = h - bar_h
        col = _grad(c.gradient_stops, 1 - r) if c.show_gradient else c.fill_color()
        _rrect(d, bx * s, by * s, (bx + bar_w) * s, h * s,
               min(bar_w, bar_h) / 2 * s, fill=col)
    if c.target:
        ty = h - max(0.0, min(1.0, c.target / c.max_value)) * (h - 2)
        for tx in range(0, int(w * s), max(2, int(4 * s))):
            d.line([(tx, ty * s), (tx + s, ty * s)], fill=(255, 255, 255, 150), width=1)


# Etiquetas cortas por métrica del Disk Element.
_DISK_LABELS = {
    "used": "USED", "free": "FREE", "total": "TOTAL",
    "read": "READ", "write": "WRITE", "percent": "%",
}


def _draw_db_icon(d, s, x, y, size, color, dim):
    """Icono minimalista de almacenamiento: 3 cilindros apilados (base de datos)."""
    cx = x + size / 2.0
    rx = size * 0.32
    ry = size * 0.10
    layer_h = size * 0.19
    top_y = y + size * 0.26
    width = max(1, int(round(1.6 * s)))
    # De abajo hacia arriba para que las tapas queden por encima.
    for i in range(2, -1, -1):
        cy = top_y + i * layer_h
        left, right = cx - rx, cx + rx
        # Cuerpo con relleno tenue.
        d.rectangle([left * s, cy * s, right * s, (cy + layer_h) * s], fill=dim)
        # Caras laterales.
        d.line([(left * s, cy * s), (left * s, (cy + layer_h) * s)],
               fill=color, width=width)
        d.line([(right * s, cy * s), (right * s, (cy + layer_h) * s)],
               fill=color, width=width)
        # Base curva (media elipse inferior).
        d.arc([left * s, (cy + layer_h - ry) * s,
               right * s, (cy + layer_h + ry) * s],
              0, 180, fill=color, width=width)
        # Tapa superior.
        d.ellipse([left * s, (cy - ry) * s, right * s, (cy + ry) * s],
                  fill=dim, outline=color, width=width)


def _draw_mini_sparkline(d, s, x0, y0, x1, y1, samples, color, max_value):
    """Sparkline compacta dentro de una fila (sin fondo)."""
    if x1 <= x0 or y1 <= y0 or not samples:
        return
    n = len(samples)
    step = (x1 - x0) / max(1, n - 1)
    prev = None
    for i, sample in enumerate(samples):
        r = max(0.0, min(1.0, float(sample) / max(1e-6, max_value)))
        px = x0 + i * step
        py = y1 - r * (y1 - y0)
        if prev is not None:
            d.line([(prev[0] * s, prev[1] * s), (px * s, py * s)],
                   fill=color, width=max(1, int(s)))
        prev = (px, py)


def draw_disk_element(img, d, c):
    s = c.s
    w, h = c.w, c.h
    radius = c.border_radius or h * 0.10
    _rrect(d, 0, 0, (w - 1) * s, (h - 1) * s, radius * s, fill=c.bg)

    pad = max(4.0, h * 0.08)
    icon_size = max(16.0, h - 2 * pad)
    bar_w = max(8.0, w * 0.045)
    bar_x = w - pad - bar_w
    text_x = pad + icon_size + max(6.0, w * 0.03)
    text_w = max(10.0, bar_x - text_x - max(4.0, w * 0.02))

    dim = (max(0, c.color[0] // 3), max(0, c.color[1] // 3), max(0, c.color[2] // 3))
    _draw_db_icon(d, s, pad, pad, icon_size, c.color, dim)

    sources = c.sources or ["disk_used", "disk_free", "disk_total",
                            "disk_read", "disk_write"]
    n = max(1, len(sources))
    row_h = (h - 2 * pad) / n
    label_font = _font(c.font_family, max(8.0, row_h * 0.42) * s, True, False)
    value_font = _font(c.font_family, max(9.0, row_h * 0.50) * s, c.font_bold, c.font_italic)
    for i, source in enumerate(sources):
        y0 = pad + i * row_h
        cy = y0 + row_h / 2
        label = _DISK_LABELS.get(str(source).split(".")[-1], str(source).upper()[:6])
        value = float(c.panel_values.get(source, 0) or 0)
        d.text((text_x * s, cy * s), label, font=label_font, fill=c.label_rgba, anchor="lm")
        # La fila READ/WRITE deja hueco a la derecha para la sparkline.
        is_io = source in ("disk_read", "disk_write") and c.show_sparklines
        value_anchor_x = text_x + text_w * (0.45 if is_io else 0.60)
        d.text((value_anchor_x * s, cy * s), format_value(value, source),
               font=value_font, fill=c.text_rgba, anchor="lm")
        if is_io:
            samples = history_for(c.el, value, length=max(8, int(text_w * 0.4)),
                                  key=source)
            _draw_mini_sparkline(
                d, s, value_anchor_x + text_w * 0.28, y0 + row_h * 0.22,
                text_x + text_w, y0 + row_h * 0.78, samples, c.color,
                max(1.0, max(samples) if samples else 1.0))

    # Barra vertical de espacio (libre/uso).
    if c.bar_mode != "none":
        used_ratio = max(0.0, min(1.0, c.value / c.max_value))
        fill_ratio = (1.0 - used_ratio) if c.bar_mode == "free" else used_ratio
        _rrect(d, bar_x * s, pad * s, (bar_x + bar_w) * s, (h - pad) * s,
               bar_w / 2 * s, fill=c.empty)
        if fill_ratio > 0.01:
            top = (h - pad) - (h - 2 * pad) * fill_ratio
            _rrect(d, bar_x * s, top * s, (bar_x + bar_w) * s, (h - pad) * s,
                   bar_w / 2 * s, fill=c.fill_color())
        _rrect(d, bar_x * s, pad * s, (bar_x + bar_w) * s, (h - pad) * s,
               bar_w / 2 * s, outline=dim, width=max(1, int(s)))


ELEMENTS = {
    "ring_gauge": draw_ring_gauge,
    "segment_bar": draw_segment_bar,
    "zone_bar": draw_zone_bar,
    "stat_tile": draw_stat_tile,
    "sparkline": draw_sparkline,
    "level_bar": draw_level_bar,
    "column_chart": draw_column_chart,
    "disk_element": draw_disk_element,
}


def render_element(element_type, element, out_w, out_h):
    """Renderiza un elemento LCD a un array RGBA ``(out_h, out_w, 4)``."""
    out_w = max(1, int(round(out_w)))
    out_h = max(1, int(round(out_h)))
    draw = ELEMENTS.get(element_type)
    if draw is None:
        return np.zeros((out_h, out_w, 4), dtype=np.uint8)
    big = Image.new("RGBA", (out_w * SS, out_h * SS), (0, 0, 0, 0))
    painter = ImageDraw.Draw(big)
    ctx = Ctx(element, out_w, out_h)
    try:
        draw(big, painter, ctx)
    except Exception as exc:  # pragma: no cover - defensivo ante props inválidas
        print(f"LCD widget render error ({element_type}): {exc}")
    small = big.resize((out_w, out_h), Image.LANCZOS)
    return np.asarray(small, dtype=np.uint8)
