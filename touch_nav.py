"""Widget de navegación táctil para HDMI.

Una barra de botones anclada a un borde de la pantalla (``bottom``/``top``/
``left``/``right``). Cada item salta a una pantalla (o *Next*/*Prev*) mediante
la interacción de transición. El widget expone:

- :func:`item_rects` / :func:`item_at` para el *hit-test* por sub-item en el
  toque del monitor HDMI.
- :func:`render` que devuelve una imagen RGBA (numpy) para el canvas y el
  render final.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from lcd_widgets import get_font, to_rgba

POSITIONS = ("bottom", "top", "left", "right")


def _items(element):
    return list(getattr(element, "nav_items", []) or [])


def item_rects(element):
    """Rectángulos lógicos ``(x0, y0, x1, y1)`` de cada item dentro del widget."""
    width = max(1.0, float(getattr(element, "width", 1) or 1))
    height = max(1.0, float(getattr(element, "height", 1) or 1))
    count = len(_items(element))
    if count == 0:
        return []
    position = getattr(element, "nav_position", "bottom") or "bottom"
    rects = []
    if position in ("bottom", "top"):
        seg = width / count
        for i in range(count):
            rects.append((i * seg, 0.0, (i + 1) * seg, height))
    else:
        seg = height / count
        for i in range(count):
            rects.append((0.0, i * seg, width, (i + 1) * seg))
    return rects


def item_at(element, x, y):
    """Índice del item tocado en coordenadas del canvas, o ``None``."""
    width = float(getattr(element, "width", 0) or 0)
    height = float(getattr(element, "height", 0) or 0)
    if width <= 0 or height <= 0:
        return None
    local_x = x - float(getattr(element, "x", 0))
    local_y = y - float(getattr(element, "y", 0))
    if not (0 <= local_x <= width and 0 <= local_y <= height):
        return None
    items = _items(element)
    if not items:
        return None
    position = getattr(element, "nav_position", "bottom") or "bottom"
    count = len(items)
    if position in ("bottom", "top"):
        index = int(local_x / (width / count))
    else:
        index = int(local_y / (height / count))
    return max(0, min(count - 1, index))


def render(element, out_w, out_h):
    """Renderiza el widget a un array RGBA ``(out_h, out_w, 4)``."""
    out_w = max(1, int(out_w))
    out_h = max(1, int(out_h))
    image = Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    radius = int(getattr(element, "border_radius", 0) or 0)
    bg = to_rgba(getattr(element, "background_color", "#12141c"),
                 getattr(element, "background_color_opacity", 100))
    if radius > 0:
        draw.rounded_rectangle([0, 0, out_w - 1, out_h - 1],
                               radius=min(radius, out_w // 2, out_h // 2), fill=bg)
    else:
        draw.rectangle([0, 0, out_w - 1, out_h - 1], fill=bg)

    color = to_rgba(getattr(element, "color", "#00ff96"),
                    getattr(element, "color_opacity", 100))
    font = get_font(getattr(element, "font_family", "Arial"),
                    getattr(element, "font_size", 18),
                    getattr(element, "font_bold", False),
                    getattr(element, "font_italic", False))

    items = _items(element)
    rects = item_rects(element)
    scale_x = out_w / max(1e-6, float(getattr(element, "width", 1) or 1))
    scale_y = out_h / max(1e-6, float(getattr(element, "height", 1) or 1))
    pad = max(2, int(min(out_w, out_h) * 0.07))
    outline_w = max(1, int(min(out_w, out_h) * 0.02))
    for item, (rx0, ry0, rx1, ry1) in zip(items, rects):
        bx0, by0 = rx0 * scale_x + pad, ry0 * scale_y + pad
        bx1, by1 = rx1 * scale_x - pad, ry1 * scale_y - pad
        if bx1 <= bx0 or by1 <= by0:
            continue
        btn_radius = max(2, int(min(bx1 - bx0, by1 - by0) / 2))
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=btn_radius,
                               fill=(color[0], color[1], color[2], 60))
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=btn_radius,
                               outline=color, width=outline_w)
        label = str(item.get("label") or "")
        if label:
            draw.text(((bx0 + bx1) / 2, (by0 + by1) / 2), label, font=font,
                      fill=color, anchor="mm")
    return np.asarray(image, dtype=np.uint8)
