"""
CanvasPreview - Visual preview and editing widget.
"""

import os
import time

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QScrollArea, QWidget

from constants import (
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    DMD_WIDGET_TYPES,
    LCD_WIDGET_TYPES,
    PREVIEW_SCALE,
    SOURCE_UNITS,
    resolve_icon_path,
)
from elements import get_custom_element
from ui_style import ACCENT, BORDER
from video_background import video_background

ACCENT_QCOLOR = QColor(ACCENT)
BORDER_QCOLOR = QColor(BORDER)

MIN_ZOOM_SCALE = 0.05
MAX_ZOOM_SCALE = 4.0

# Smart guides: snap tolerance in on-screen pixels (converted to scene units via /scale)
SNAP_TOLERANCE_PX = 6.0
GUIDE_COLOR = QColor(255, 46, 151)


class CanvasScrollArea(QScrollArea):
    """Scroll area that reports viewport resizes (used to keep ``Fit`` current)."""

    viewport_resized = Signal()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.viewport_resized.emit()


def apply_opacity(color, opacity):
    """Apply opacity (0-100) to a QColor and return the modified color."""
    if isinstance(color, str):
        color = QColor(color)
    else:
        color = QColor(color)  # Make a copy
    alpha = int(255 * opacity / 100)
    color.setAlpha(alpha)
    return color


def dim_color(color, factor=0.4):
    """Return a darker version of ``color`` (used for DMD empty/outline states)."""
    c = QColor(color) if isinstance(color, str) else QColor(color)
    c.setRed(int(c.red() * factor))
    c.setGreen(int(c.green() * factor))
    c.setBlue(int(c.blue() * factor))
    return c


# --- DMD bar chart history ------------------------------------------------
# The bar chart mirrors the line chart approach: it keeps a small history of
# samples so the bars show a trend instead of a single value.
_BAR_CHART_HISTORY: dict = {}
_BAR_CHART_LAST_TS: dict = {}
_BAR_CHART_MAX = 64
_BAR_CHART_MIN_INTERVAL = 0.05


def get_bar_chart_history(element):
    key = getattr(element, 'name', id(element))
    if key not in _BAR_CHART_HISTORY:
        value = float(getattr(element, 'value', 0))
        profile = (0.22, 0.48, 0.85, 0.6, 0.33, 0.95, 0.72, 0.5,
                   0.28, 0.88, 0.66, 0.4, 0.55, 0.78, 0.3, 0.7)
        seed = [value * profile[i % len(profile)] for i in range(_BAR_CHART_MAX)]
        _BAR_CHART_HISTORY[key] = seed
    return _BAR_CHART_HISTORY[key]


def add_bar_chart_value(element, value):
    import time
    key = getattr(element, 'name', id(element))
    now = time.time()
    if now - _BAR_CHART_LAST_TS.get(key, 0) < _BAR_CHART_MIN_INTERVAL:
        return False
    history = get_bar_chart_history(element)
    history.append(float(value))
    if len(history) > _BAR_CHART_MAX:
        del history[:len(history) - _BAR_CHART_MAX]
    _BAR_CHART_LAST_TS[key] = now
    return True


def get_text_color(element):
    """Get the effective text color for an element (value text), with opacity applied."""
    color = getattr(element, 'text_color', element.color)
    opacity = getattr(element, 'text_color_opacity', 100)
    return apply_opacity(color, opacity)


def get_label_text_color(element):
    """Get the label text color for an element (circle gauge labels), with opacity applied."""
    color = getattr(element, 'label_text_color', element.color)
    opacity = getattr(element, 'text_color_opacity', 100)
    return apply_opacity(color, opacity)


def interpolate_gradient_color(gradient_stops, position):
    """Interpolate color from gradient stops at a given position (0-1)."""
    if not gradient_stops:
        return QColor("#00ff96")

    sorted_stops = sorted(gradient_stops)

    # Clamp position
    position = max(0.0, min(1.0, position))

    # Find surrounding stops
    if position <= sorted_stops[0][0]:
        return QColor(sorted_stops[0][1])
    if position >= sorted_stops[-1][0]:
        return QColor(sorted_stops[-1][1])

    for i in range(len(sorted_stops) - 1):
        p1, c1 = sorted_stops[i]
        p2, c2 = sorted_stops[i + 1]
        if p1 <= position <= p2:
            # Interpolate between these two stops
            t = (position - p1) / (p2 - p1) if p2 != p1 else 0
            color1 = QColor(c1)
            color2 = QColor(c2)
            r = int(color1.red() + t * (color2.red() - color1.red()))
            g = int(color1.green() + t * (color2.green() - color1.green()))
            b = int(color1.blue() + t * (color2.blue() - color1.blue()))
            return QColor(r, g, b)

    return QColor(sorted_stops[-1][1])


def get_value_with_unit(value, source, temp_hide_unit=False):
    """Format a value with its appropriate unit symbol."""
    unit_info = SOURCE_UNITS.get(source, {"symbol": "%", "type": "percent"})
    symbol = unit_info["symbol"]
    unit_type = unit_info["type"]

    if unit_type == "clock":
        return f"{value:.0f}{symbol}"
    elif unit_type == "temp":
        if temp_hide_unit:
            return f"{value:.0f}°"
        return f"{value:.0f}{symbol}"
    elif unit_type == "power":
        return f"{value:.0f}{symbol}"
    elif unit_type in ("size", "energy", "speed"):
        return f"{value:.1f}{symbol}"
    elif unit_type == "digital":
        return f"{value:.0f}{symbol}"
    else:  # percent
        return f"{value:.0f}{symbol}"


class CanvasPreview(QWidget):
    element_selected = Signal(int)  # Single selection (for backwards compat)
    elements_selected = Signal(list)  # Multi-selection
    element_moved = Signal(int, int, int)
    element_resized = Signal(int)  # Emitted when element is resized
    drag_started = Signal()  # Emitted when drag/resize starts (for undo)

    # Resize handle positions
    HANDLE_NONE = 0
    HANDLE_TL = 1  # Top-left
    HANDLE_TR = 2  # Top-right
    HANDLE_BL = 3  # Bottom-left
    HANDLE_BR = 4  # Bottom-right

    def __init__(self):
        super().__init__()
        self.elements = []
        self.selected_indices = []  # Support multiple selection
        self.dragging = False
        self.resizing = False
        self.resize_handle = self.HANDLE_NONE
        self.drag_start_positions = {}  # Store start positions for multi-drag
        self.resize_start_pos = QPointF(0, 0)
        self.resize_start_pos_element = (0, 0)
        self.resize_start_size = (0, 0)
        self.resize_start_bounds = None  # For multi-element resize
        self._active_guides = []  # Smart guides visible during a drag: [(axis, value, a, b), ...]
        self.scale = PREVIEW_SCALE
        self.vertical_mode = False  # Rotates the preview 90 degrees to match a vertically mounted LCD
        self.background_color = QColor(15, 15, 25)
        self.handle_size = 10
        self.group_selection_mode = False  # True when a complete group is selected
        self._glass_background = None  # Cached background for glass effect
        self._glass_cache_valid = False  # Track if glass cache needs rebuild
        self._has_glass_cache = None  # Cache result of _has_glass_elements()

        self._update_fixed_size()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # Enable keyboard input

    def _update_fixed_size(self):
        """Set the widget's fixed size, swapping dimensions when in vertical mode."""
        if self.vertical_mode:
            self.setFixedSize(
                int(DISPLAY_HEIGHT * self.scale),
                int(DISPLAY_WIDTH * self.scale)
            )
        else:
            self.setFixedSize(
                int(DISPLAY_WIDTH * self.scale),
                int(DISPLAY_HEIGHT * self.scale)
            )

    def set_vertical_mode(self, enabled):
        """Enable/disable the rotated (portrait) preview to match a vertically mounted LCD."""
        self.vertical_mode = enabled
        self._glass_cache_valid = False  # Invalidate glass cache (size changed)
        self._update_fixed_size()
        self.update()

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------
    def set_zoom_scale(self, scale):
        """Set the paint scale directly (1.0 == 100%, actual LCD pixels)."""
        scale = max(MIN_ZOOM_SCALE, min(MAX_ZOOM_SCALE, scale))
        if abs(scale - self.scale) < 0.001:
            return
        self.scale = scale
        self._glass_cache_valid = False  # Glass background is rendered at this scale
        self._active_guides = []  # Guides are transient; drop them on zoom changes
        self._update_fixed_size()
        self.update()

    def fit_scale_for(self, avail_w, avail_h, margin=28):
        """Compute the largest scale that fits ``avail_w x avail_h`` (preview px)."""
        base_w = DISPLAY_HEIGHT if self.vertical_mode else DISPLAY_WIDTH
        base_h = DISPLAY_WIDTH if self.vertical_mode else DISPLAY_HEIGHT
        avail_w = max(1, avail_w - margin)
        avail_h = max(1, avail_h - margin)
        return max(MIN_ZOOM_SCALE, min(MAX_ZOOM_SCALE, min(avail_w / base_w, avail_h / base_h)))

    def zoom_percent(self):
        return int(round(self.scale * 100))

    def set_elements(self, elements):
        self.elements = elements
        # Selection indices can go stale when the element list shrinks (e.g. the
        # shared list is mutated by element deletion or a theme reload). Drop any
        # index that no longer points at an element to avoid crashes on the next
        # mouse/key event.
        count = len(elements)
        self.selected_indices = [i for i in self.selected_indices if 0 <= i < count]
        if not self.selected_indices:
            self.group_selection_mode = False
        self._glass_cache_valid = False  # Invalidate glass cache when elements change
        self._has_glass_cache = None  # Clear has_glass cache
        self._active_guides = []  # Guides belong to a drag; drop them with the element set
        self.update()

    def _valid_selected_indices(self):
        """Return the current selection filtered to indices that still exist."""
        count = len(self.elements)
        return [i for i in self.selected_indices if 0 <= i < count]

    def _reconcile_selection(self):
        """Drop stale selection indices (e.g. after the element list shrank)."""
        valid = self._valid_selected_indices()
        if valid != self.selected_indices:
            self.selected_indices = valid
            if not valid:
                self.group_selection_mode = False
        return bool(valid)

    def get_animated_value(self, element):
        """Get the display value for a gauge, handling animation if enabled.

        Stores the animated value on the element itself so display renderer can use it too.
        """
        target_value = float(element.value)

        if not getattr(element, 'animate_gauge', False):
            # Clear any stored animated value when animation is disabled
            if hasattr(element, '_animated_display_value'):
                delattr(element, '_animated_display_value')
            return target_value

        # Get current animated value from element (shared with display renderer)
        current = getattr(element, '_animated_display_value', None)

        if current is None:
            # Initialize with current value
            element._animated_display_value = target_value
            return target_value

        diff = target_value - current

        # Pixel-perfect threshold - stop when difference is negligible
        if abs(diff) < 0.001:
            element._animated_display_value = target_value
            return target_value

        # Ultra-smooth animation using ease-out cubic
        # This creates natural deceleration as it approaches target
        speed = getattr(element, 'animation_speed', 0.05)

        # Ease-out: faster at start, slower near end (feels more natural)
        # The further from target, the bigger the step
        t = min(1.0, abs(diff) / 50.0)  # Normalize distance (50% gauge = full speed)
        eased_speed = speed * (1.0 + t * 2.0)  # Speed up for large changes

        step = diff * eased_speed

        # Minimum step for pixel-by-pixel movement (prevents stalling)
        min_step = 0.05
        if abs(step) < min_step and abs(diff) >= 0.001:
            step = min_step if diff > 0 else -min_step

        new_value = current + step
        element._animated_display_value = new_value
        return new_value

    def set_selected(self, index):
        """Set single selection (backwards compatible)."""
        if index >= 0:
            self.selected_indices = [index]
        else:
            self.selected_indices = []
        self.group_selection_mode = False  # Single selection is never a group selection
        self.update()

    def set_selected_indices(self, indices, group_selection=False):
        """Set multiple selected indices.

        Args:
            indices: List of element indices to select
            group_selection: True if this selection represents a complete group
                             (from clicking on group in tree, not individual elements)
        """
        self.selected_indices = list(indices)
        self.group_selection_mode = group_selection
        self.update()

    def set_background_color(self, color):
        self.background_color = QColor(color)
        self._glass_cache_valid = False  # Invalidate glass cache
        self.update()

    def _has_glass_elements(self):
        """Check if any element has glass effect enabled (cached)."""
        if self._has_glass_cache is None:
            self._has_glass_cache = any(
                el.type == "rectangle" and getattr(el, 'glass_effect', False)
                for el in self.elements
            )
        return self._has_glass_cache

    def _render_background_for_glass(self):
        """Render everything except glass effects to a buffer for blur source."""
        buffer = QPixmap(self.size())
        buffer.fill(Qt.GlobalColor.transparent)

        painter = QPainter(buffer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw video background if enabled, otherwise solid color
        if video_background.enabled:
            pixmap = video_background.get_frame_qpixmap(self.scale)
            if pixmap:
                painter.drawPixmap(0, 0, pixmap)
            else:
                painter.fillRect(self.rect(), self.background_color)
        else:
            painter.fillRect(self.rect(), self.background_color)

        # Draw elements without glass effect and without selection boxes
        for i in range(len(self.elements) - 1, -1, -1):
            element = self.elements[i]
            # Skip glass rectangles - they'll use this buffer
            if element.type == "rectangle" and getattr(element, 'glass_effect', False):
                continue
            self.draw_element(painter, element, False)

        painter.end()
        return buffer

    def paintEvent(self, event):
        # If we have glass elements, pre-render the background for blur
        # Only rebuild if cache is invalid or video is playing (video changes every frame)
        if self._has_glass_elements():
            needs_rebuild = not self._glass_cache_valid or video_background.enabled
            if needs_rebuild or self._glass_background is None:
                self._glass_background = self._render_background_for_glass()
                self._glass_cache_valid = True
        else:
            self._glass_background = None

        # In vertical mode, the design canvas itself is logically portrait
        # (DISPLAY_HEIGHT x DISPLAY_WIDTH) - matching render_theme_image() - so we
        # draw directly at the swapped size. No post-hoc rotation of the whole
        # picture is needed; element coordinates are defined in this same space.
        if self.vertical_mode:
            canvas_w = int(DISPLAY_HEIGHT * self.scale)
            canvas_h = int(DISPLAY_WIDTH * self.scale)
        else:
            canvas_w = int(DISPLAY_WIDTH * self.scale)
            canvas_h = int(DISPLAY_HEIGHT * self.scale)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        draw_rect = QRectF(0, 0, canvas_w, canvas_h)

        # Draw video background if enabled, otherwise solid color
        if video_background.enabled:
            pixmap = video_background.get_frame_qpixmap(self.scale)
            if pixmap:
                painter.drawPixmap(0, 0, pixmap)
            else:
                painter.fillRect(draw_rect, self.background_color)
        else:
            painter.fillRect(draw_rect, self.background_color)

        pen = QPen(ACCENT_QCOLOR, 2)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(draw_rect.adjusted(1, 1, -1, -1))

        # Draw elements in reverse: last in list drawn first (back), first in list drawn last (front)
        # Tree shows first element at top, so top of tree = front of display
        for i in range(len(self.elements) - 1, -1, -1):
            # In group selection mode, don't draw individual selection boxes
            # (we'll draw only the combined box instead)
            is_selected = i in self.selected_indices
            draw_individual_selection = is_selected and not self.group_selection_mode
            self.draw_element(painter, self.elements[i], draw_individual_selection)

        # Draw combined selection box if multiple elements selected (always for groups,
        # or for multi-select of individual elements)
        if len(self.selected_indices) > 1:
            self.draw_multi_selection_box(painter)

        # Draw active smart guides on top
        if self._active_guides:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            guide_pen = QPen(GUIDE_COLOR, 1, Qt.PenStyle.DashLine)
            guide_pen.setDashPattern([4, 3])
            painter.setPen(guide_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for axis, value, extent_a, extent_b in self._active_guides:
                px = int(value * self.scale)
                a = int(extent_a * self.scale)
                b = int(extent_b * self.scale)
                if axis == 'x':
                    painter.drawLine(px, a, px, b)
                else:
                    painter.drawLine(a, px, b, px)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        painter.end()

    def draw_element(self, painter, element, selected):
        x = int(element.x * self.scale)
        y = int(element.y * self.scale)

        # Hidden elements are not drawn, but keep a selection outline so they can
        # still be moved/resized after selecting them from the element list.
        if not getattr(element, 'visible', True):
            if selected:
                self.draw_selection_box(painter, element, x, y)
            return

        # Only apply clipping for text/clock elements that have clip enabled
        needs_clip = element.clip and element.type in ["text", "clock"]
        if needs_clip:
            clip_rect = QRectF(x, y, element.width * self.scale, element.height * self.scale)
            painter.setClipRect(clip_rect)

        if element.type == "circle_gauge":
            self.draw_circle_gauge(painter, element, x, y, selected)
        elif element.type == "bar_gauge":
            self.draw_bar_gauge(painter, element, x, y, selected)
        elif element.type == "text":
            self.draw_text(painter, element, x, y, selected)
        elif element.type == "rectangle":
            self.draw_rectangle(painter, element, x, y, selected)
        elif element.type == "clock":
            self.draw_clock(painter, element, x, y, selected)
        elif element.type == "image":
            self.draw_image(painter, element, x, y, selected)
        elif element.type == "icon":
            self.draw_icon(painter, element, x, y)
        elif element.type == "video":
            self.draw_video(painter, element, x, y)
        elif element.type == "gauge_circle_dmd":
            self.draw_gauge_circle_dmd(painter, element, x, y, selected)
        elif element.type == "segmented_bar":
            self.draw_segmented_bar(painter, element, x, y, selected)
        elif element.type == "bar_chart":
            self.draw_bar_chart(painter, element, x, y, selected)
        elif element.type in LCD_WIDGET_TYPES:
            self.draw_lcd_widget(painter, element, x, y)
        elif element.type == "touch_nav":
            self.draw_touch_nav(painter, element, x, y)
        elif element.type in DMD_WIDGET_TYPES:
            self.draw_dmd_widget(painter, element, x, y)
        else:
            # Try custom element
            custom = get_custom_element(element.type)
            if custom and custom.get('draw_preview'):
                try:
                    custom['draw_preview'](painter, element, x, y, self.scale)
                except Exception as e:
                    print(f"Custom element draw error: {e}")

        if needs_clip:
            painter.setClipping(False)

        if selected:
            self.draw_selection_box(painter, element, x, y)

    def draw_circle_gauge(self, painter, element, x, y, selected):
        radius = int(element.radius * self.scale)
        bg_color = apply_opacity(element.background_color, getattr(element, 'background_color_opacity', 100))

        # Get animated display value
        display_value = self.get_animated_value(element)

        # Determine color (with auto color change support)
        use_gradient = getattr(element, 'gradient_fill', False)
        if not use_gradient:
            auto_color = getattr(element, 'auto_color_change', False)
            if auto_color:
                if "temp" in element.source:
                    if display_value < 60:
                        color_hex = element.color
                    elif display_value < 80:
                        color_hex = "#ffcc00"
                    else:
                        color_hex = "#ff3232"
                else:
                    if display_value < 70:
                        color_hex = element.color
                    elif display_value < 90:
                        color_hex = "#ffcc00"
                    else:
                        color_hex = "#ff3232"
            else:
                color_hex = element.color
            color = apply_opacity(color_hex, getattr(element, 'color_opacity', 100))
        else:
            color = apply_opacity(element.color, getattr(element, 'color_opacity', 100))

        # Check for rounded ends (pill shape)
        rounded_ends = getattr(element, 'gauge_rounded_ends', False)
        pen_width = max(1, int(getattr(element, 'line_width', 15) * self.scale))

        # Draw background arc
        bg_pen = QPen(bg_color, pen_width)
        if rounded_ends:
            bg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(bg_pen)
        painter.drawArc(
            x - radius, y - radius, radius * 2, radius * 2,
            225 * 16, -270 * 16
        )

        sweep = int(-270 * (display_value / 100) * 16)

        if use_gradient and display_value > 0:
            # Draw gradient arc using multiple small segments
            from PySide6.QtGui import QColor as QC
            gradient_stops = getattr(element, 'gradient_stops', [(0.0, "#00ff96"), (1.0, "#ff4444")])
            # Draw in small increments for smooth gradient
            num_segments = max(1, int(display_value * 2.7))  # ~2.7 segments per percent (270 degrees / 100)
            for i in range(num_segments):
                t = i / (270.0)  # Position along full arc range (0 to 1 for full 270 degrees)
                segment_color = interpolate_gradient_color(gradient_stops, t)
                segment_pen = QPen(QC(segment_color), pen_width)
                if rounded_ends:
                    segment_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(segment_pen)
                segment_start = 225 * 16 - int(i * 16)
                segment_sweep = -16  # 1 degree at a time
                painter.drawArc(
                    x - radius, y - radius, radius * 2, radius * 2,
                    segment_start, segment_sweep
                )
        else:
            fill_color = color
            fill_pen = QPen(fill_color, pen_width)
            if rounded_ends:
                fill_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(fill_pen)
            painter.drawArc(
                x - radius, y - radius, radius * 2, radius * 2,
                225 * 16, sweep
            )

        # Draw value text
        painter.setPen(QPen(get_text_color(element)))
        font = QFont(element.font_family)
        font.setPixelSize(int(element.font_size * self.scale))
        font.setBold(element.font_bold)
        font.setItalic(element.font_italic)
        painter.setFont(font)

        text = get_value_with_unit(display_value, element.source, getattr(element, 'temp_hide_unit', False))
        text_rect = QRectF(x - radius, y - radius / 2, radius * 2, radius)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, text)

        # Draw label with separate label font settings and color
        label_font = QFont(getattr(element, 'label_font_family', element.font_family))
        label_font.setPixelSize(int(getattr(element, 'label_font_size', 16) * self.scale))
        label_font.setBold(getattr(element, 'label_font_bold', False))
        label_font.setItalic(getattr(element, 'label_font_italic', False))
        painter.setFont(label_font)
        painter.setPen(QPen(get_label_text_color(element)))
        label_rect = QRectF(x - radius, y + radius / 4, radius * 2, radius / 2)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, element.text)

    def draw_bar_gauge(self, painter, element, x, y, selected):
        from PySide6.QtGui import QLinearGradient, QPainterPath

        width = int(element.width * self.scale)
        height = int(element.height * self.scale)
        bg_color = apply_opacity(element.background_color, getattr(element, 'background_color_opacity', 100))

        # Get animated display value
        display_value = self.get_animated_value(element)

        rounded = getattr(element, 'rounded_corners', False)
        use_gradient = getattr(element, 'gradient_fill', False)
        corner_radius = height // 2 if rounded else 0

        # Determine color (with auto color change support)
        if not use_gradient:
            auto_color = getattr(element, 'auto_color_change', False)
            if auto_color:
                if display_value < 70:
                    color_hex = element.color
                elif display_value < 90:
                    color_hex = "#ffcc00"
                else:
                    color_hex = "#ff3232"
            else:
                color_hex = element.color
            color = apply_opacity(color_hex, getattr(element, 'color_opacity', 100))
        else:
            color = apply_opacity(element.color, getattr(element, 'color_opacity', 100))

        # Draw background
        if rounded:
            bg_path = QPainterPath()
            bg_path.addRoundedRect(x, y, width, height, corner_radius, corner_radius)
            painter.fillPath(bg_path, bg_color)
        else:
            painter.fillRect(x, y, width, height, bg_color)

        # Draw fill
        fill_width = int(width * display_value / 100)
        if fill_width > 0:
            if use_gradient:
                # Use horizontal gradient with custom stops
                gradient_stops = getattr(element, 'gradient_stops', [(0.0, "#00ff96"), (1.0, "#ff4444")])
                grad = QLinearGradient(x, y, x + width, y)
                for pos, stop_color in gradient_stops:
                    grad.setColorAt(pos, QColor(stop_color))
                fill_brush = QBrush(grad)
            else:
                fill_brush = QBrush(color)

            if rounded:
                fill_path = QPainterPath()
                fill_path.addRoundedRect(x, y, fill_width, height, corner_radius, corner_radius)
                painter.fillPath(fill_path, fill_brush)
            else:
                painter.fillRect(x, y, fill_width, height, fill_brush)

        # Draw border if enabled
        bar_border = getattr(element, 'bar_border', False)
        if bar_border:
            border_width = int(getattr(element, 'bar_border_width', 2) * self.scale)
            border_color = getattr(element, 'bar_border_color', '#ffffff')
            border_opacity = getattr(element, 'bar_border_opacity', 100)
            border_position = getattr(element, 'bar_border_position', 'center')
            border_qcolor = apply_opacity(border_color, border_opacity)

            border_pen = QPen(border_qcolor, border_width)
            painter.setPen(border_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)

            half_border = border_width / 2

            # Calculate offset based on border position
            if border_position == "inside":
                offset = half_border
                size_adjust = -border_width
                radius_adjust = -half_border
            elif border_position == "center":
                offset = 0
                size_adjust = 0
                radius_adjust = 0
            else:  # outside
                offset = -half_border
                size_adjust = border_width
                radius_adjust = half_border

            if rounded:
                border_path = QPainterPath()
                border_path.addRoundedRect(
                    x + offset, y + offset,
                    width + size_adjust, height + size_adjust,
                    max(0, corner_radius + radius_adjust), max(0, corner_radius + radius_adjust)
                )
                painter.drawPath(border_path)
            else:
                painter.drawRect(
                    int(x + offset), int(y + offset),
                    int(width + size_adjust), int(height + size_adjust)
                )

        # Draw text based on bar_text_mode and bar_text_position
        bar_text_mode = getattr(element, 'bar_text_mode', 'full')
        bar_text_position = getattr(element, 'bar_text_position', 'inside')

        if bar_text_mode != 'none':
            # Value text font
            value_font = QFont(element.font_family)
            value_font.setPixelSize(int(element.font_size * self.scale))
            value_font.setBold(element.font_bold)
            value_font.setItalic(element.font_italic)

            # Label text font (separate styling)
            label_font = QFont(getattr(element, 'label_font_family', element.font_family))
            label_font.setPixelSize(int(getattr(element, 'label_font_size', element.font_size) * self.scale))
            label_font.setBold(getattr(element, 'label_font_bold', element.font_bold))
            label_font.setItalic(getattr(element, 'label_font_italic', element.font_italic))

            value_text = get_value_with_unit(display_value, element.source, getattr(element, 'temp_hide_unit', False))

            if bar_text_position == 'inside':
                if bar_text_mode == 'full':
                    # Draw label and value separately with their own fonts
                    painter.setFont(label_font)
                    label_metrics = painter.fontMetrics()
                    label_text = f"{element.text} "
                    label_width = label_metrics.horizontalAdvance(label_text)

                    painter.setFont(value_font)
                    value_metrics = painter.fontMetrics()
                    value_width = value_metrics.horizontalAdvance(value_text)

                    total_width = label_width + value_width
                    start_x = x + (width - total_width) / 2

                    # Draw label
                    painter.setPen(QPen(get_label_text_color(element)))
                    painter.setFont(label_font)
                    label_rect = QRectF(start_x, y, label_width, height)
                    painter.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter, label_text)

                    # Draw value
                    painter.setPen(QPen(get_text_color(element)))
                    painter.setFont(value_font)
                    value_rect = QRectF(start_x + label_width, y, value_width, height)
                    painter.drawText(value_rect, Qt.AlignmentFlag.AlignVCenter, value_text)
                elif bar_text_mode == 'value_only':
                    painter.setPen(QPen(get_text_color(element)))
                    painter.setFont(value_font)
                    text_rect = QRectF(x, y, width, height)
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, value_text)
                elif bar_text_mode == 'label_only':
                    painter.setPen(QPen(get_label_text_color(element)))
                    painter.setFont(label_font)
                    text_rect = QRectF(x, y, width, height)
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, element.text)

            elif bar_text_position == 'left':
                if bar_text_mode == 'full':
                    # Draw label and value separately, centered with bar
                    painter.setFont(label_font)
                    label_metrics = painter.fontMetrics()
                    label_text = f"{element.text} "
                    label_width = label_metrics.horizontalAdvance(label_text)

                    painter.setFont(value_font)
                    value_metrics = painter.fontMetrics()
                    value_width = value_metrics.horizontalAdvance(value_text)

                    total_width = label_width + value_width
                    start_x = x - total_width - 10 * self.scale

                    # Draw label centered with bar's vertical center
                    painter.setPen(QPen(get_label_text_color(element)))
                    painter.setFont(label_font)
                    label_rect = QRectF(start_x, y, label_width, height)
                    painter.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter, label_text)

                    # Draw value centered with bar's vertical center
                    painter.setPen(QPen(get_text_color(element)))
                    painter.setFont(value_font)
                    value_rect = QRectF(start_x + label_width, y, value_width, height)
                    painter.drawText(value_rect, Qt.AlignmentFlag.AlignVCenter, value_text)
                elif bar_text_mode == 'value_only':
                    painter.setPen(QPen(get_text_color(element)))
                    painter.setFont(value_font)
                    metrics = painter.fontMetrics()
                    text_width = metrics.horizontalAdvance(value_text)
                    text_x = x - text_width - 10 * self.scale
                    text_rect = QRectF(text_x, y, text_width, height)
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, value_text)
                elif bar_text_mode == 'label_only':
                    painter.setPen(QPen(get_label_text_color(element)))
                    painter.setFont(label_font)
                    metrics = painter.fontMetrics()
                    text_width = metrics.horizontalAdvance(element.text)
                    text_x = x - text_width - 10 * self.scale
                    text_rect = QRectF(text_x, y, text_width, height)
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, element.text)

            elif bar_text_position == 'right':
                if bar_text_mode == 'full':
                    # Draw label and value separately, centered with bar
                    painter.setFont(label_font)
                    label_metrics = painter.fontMetrics()
                    label_text = f"{element.text} "
                    label_width = label_metrics.horizontalAdvance(label_text)

                    painter.setFont(value_font)
                    value_metrics = painter.fontMetrics()
                    value_width = value_metrics.horizontalAdvance(value_text)

                    start_x = x + width + 10 * self.scale

                    # Draw label centered with bar's vertical center
                    painter.setPen(QPen(get_label_text_color(element)))
                    painter.setFont(label_font)
                    label_rect = QRectF(start_x, y, label_width, height)
                    painter.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter, label_text)

                    # Draw value centered with bar's vertical center
                    painter.setPen(QPen(get_text_color(element)))
                    painter.setFont(value_font)
                    value_rect = QRectF(start_x + label_width, y, value_width, height)
                    painter.drawText(value_rect, Qt.AlignmentFlag.AlignVCenter, value_text)
                elif bar_text_mode == 'value_only':
                    painter.setPen(QPen(get_text_color(element)))
                    painter.setFont(value_font)
                    metrics = painter.fontMetrics()
                    text_width = metrics.horizontalAdvance(value_text)
                    text_x = x + width + 10 * self.scale
                    text_rect = QRectF(text_x, y, text_width, height)
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, value_text)
                elif bar_text_mode == 'label_only':
                    painter.setPen(QPen(get_label_text_color(element)))
                    painter.setFont(label_font)
                    metrics = painter.fontMetrics()
                    text_width = metrics.horizontalAdvance(element.text)
                    text_x = x + width + 10 * self.scale
                    text_rect = QRectF(text_x, y, text_width, height)
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, element.text)

            elif bar_text_position == 'top':
                # Label and value inline above bar with 16px padding
                if bar_text_mode == 'full':
                    # Draw label and value inline above bar with vertical center alignment
                    painter.setFont(label_font)
                    label_metrics = painter.fontMetrics()
                    label_text = f"{element.text} "
                    label_width = label_metrics.horizontalAdvance(label_text)
                    label_height = label_metrics.height()

                    painter.setFont(value_font)
                    value_metrics = painter.fontMetrics()
                    value_width = value_metrics.horizontalAdvance(value_text)
                    value_height = value_metrics.height()

                    total_width = label_width + value_width
                    max_height = max(label_height, value_height)
                    start_x = x + (width - total_width) / 2
                    center_y = y - 16 * self.scale - max_height / 2

                    # Draw label centered vertically
                    painter.setPen(QPen(get_label_text_color(element)))
                    painter.setFont(label_font)
                    label_rect = QRectF(start_x, center_y - label_height / 2, label_width, label_height)
                    painter.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter, label_text)

                    # Draw value centered vertically
                    painter.setPen(QPen(get_text_color(element)))
                    painter.setFont(value_font)
                    value_rect = QRectF(start_x + label_width, center_y - value_height / 2, value_width, value_height)
                    painter.drawText(value_rect, Qt.AlignmentFlag.AlignVCenter, value_text)
                elif bar_text_mode == 'value_only':
                    # Value only above bar
                    painter.setPen(QPen(get_text_color(element)))
                    painter.setFont(value_font)
                    metrics = painter.fontMetrics()
                    text_width = metrics.horizontalAdvance(value_text)
                    text_height = metrics.height()
                    text_x = x + (width - text_width) / 2
                    text_y = y - 16 * self.scale - text_height
                    text_rect = QRectF(text_x, text_y, text_width, text_height)
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, value_text)
                elif bar_text_mode == 'label_only':
                    # Label only above bar
                    painter.setPen(QPen(get_label_text_color(element)))
                    painter.setFont(label_font)
                    metrics = painter.fontMetrics()
                    text_width = metrics.horizontalAdvance(element.text)
                    text_height = metrics.height()
                    text_x = x + (width - text_width) / 2
                    text_y = y - 16 * self.scale - text_height
                    text_rect = QRectF(text_x, text_y, text_width, text_height)
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, element.text)

            elif bar_text_position == 'bottom':
                # Label and value inline below bar with 16px padding
                if bar_text_mode == 'full':
                    # Draw label and value inline below bar with vertical center alignment
                    painter.setFont(label_font)
                    label_metrics = painter.fontMetrics()
                    label_text = f"{element.text} "
                    label_width = label_metrics.horizontalAdvance(label_text)
                    label_height = label_metrics.height()

                    painter.setFont(value_font)
                    value_metrics = painter.fontMetrics()
                    value_width = value_metrics.horizontalAdvance(value_text)
                    value_height = value_metrics.height()

                    total_width = label_width + value_width
                    max_height = max(label_height, value_height)
                    start_x = x + (width - total_width) / 2
                    center_y = y + height + 16 * self.scale + max_height / 2

                    # Draw label centered vertically
                    painter.setPen(QPen(get_label_text_color(element)))
                    painter.setFont(label_font)
                    label_rect = QRectF(start_x, center_y - label_height / 2, label_width, label_height)
                    painter.drawText(label_rect, Qt.AlignmentFlag.AlignVCenter, label_text)

                    # Draw value centered vertically
                    painter.setPen(QPen(get_text_color(element)))
                    painter.setFont(value_font)
                    value_rect = QRectF(start_x + label_width, center_y - value_height / 2, value_width, value_height)
                    painter.drawText(value_rect, Qt.AlignmentFlag.AlignVCenter, value_text)
                elif bar_text_mode == 'value_only':
                    # Value only below bar
                    painter.setPen(QPen(get_text_color(element)))
                    painter.setFont(value_font)
                    metrics = painter.fontMetrics()
                    text_width = metrics.horizontalAdvance(value_text)
                    text_height = metrics.height()
                    text_x = x + (width - text_width) / 2
                    text_y = y + height + 16 * self.scale
                    text_rect = QRectF(text_x, text_y, text_width, text_height)
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, value_text)
                elif bar_text_mode == 'label_only':
                    # Label only below bar
                    painter.setPen(QPen(get_label_text_color(element)))
                    painter.setFont(label_font)
                    metrics = painter.fontMetrics()
                    text_width = metrics.horizontalAdvance(element.text)
                    text_height = metrics.height()
                    text_x = x + (width - text_width) / 2
                    text_y = y + height + 16 * self.scale
                    text_rect = QRectF(text_x, text_y, text_width, text_height)
                    painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, element.text)

    def draw_gauge_circle_dmd(self, painter, element, x, y, selected):
        """Segmented ring gauge designed for DMD panels (128x32).

        Draws a dashed 270-degree arc (gap centred on top) plus a centred label.
        ``color`` fills the reached segments, ``background_color`` the empty ones.
        """
        radius = max(1, int(getattr(element, 'radius', 7) * self.scale))
        line_width = max(1, int(getattr(element, 'line_width', 2) * self.scale))
        max_value = max(float(getattr(element, 'max_value', 100) or 100), 0.0001)
        display_value = self.get_animated_value(element)
        ratio = max(0.0, min(1.0, display_value / max_value))

        color = apply_opacity(element.color, getattr(element, 'color_opacity', 100))
        empty_color = apply_opacity(element.background_color,
                                    getattr(element, 'background_color_opacity', 100))

        segments = max(3, int(getattr(element, 'segments', 24) or 24))
        total_deg = 270.0
        start_deg = 45.0  # gap centred on top (90 degrees)
        seg_span = total_deg / segments
        dash_ratio = 0.62
        filled = ratio * segments

        painter.setBrush(Qt.BrushStyle.NoBrush)
        for i in range(segments):
            a0 = start_deg - i * seg_span
            a1 = a0 - seg_span * dash_ratio
            reached = (i + 0.5) <= filled
            pen = QPen(color if reached else empty_color, line_width,
                       Qt.PenStyle.SolidLine, Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawArc(x - radius, y - radius, radius * 2, radius * 2,
                            int(a0 * 16), int((a1 - a0) * 16))

        text = element.text or ""
        if text:
            font = QFont(element.font_family)
            font.setPixelSize(max(1, int(getattr(element, 'font_size', 5) * self.scale)))
            font.setBold(element.font_bold)
            font.setItalic(element.font_italic)
            painter.setFont(font)
            painter.setPen(QPen(get_text_color(element)))
            painter.drawText(QRectF(x - radius, y - radius, radius * 2, radius * 2),
                             Qt.AlignmentFlag.AlignCenter, text)

    def draw_segmented_bar(self, painter, element, x, y, selected):
        """Horizontal bar split into square segments (MultiPart Bar look)."""
        width = int(element.width * self.scale)
        height = int(element.height * self.scale)
        segments = max(1, int(getattr(element, 'segments', 8) or 8))
        gap = max(0, int(getattr(element, 'gap', 1)))
        max_value = max(float(getattr(element, 'max_value', 100) or 100), 0.0001)
        display_value = self.get_animated_value(element)
        ratio = max(0.0, min(1.0, display_value / max_value))

        color = apply_opacity(element.color, getattr(element, 'color_opacity', 100))
        empty_color = apply_opacity(element.color_empty,
                                    getattr(element, 'color_empty_opacity', 100))
        outline = dim_color(color, 0.45)

        total_gap = gap * (segments - 1)
        seg_w = max(1.0, (width - total_gap) / segments)
        filled = ratio * segments

        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(segments):
            sx = x + i * (seg_w + gap)
            fill = color if (i + 0.5) <= filled else empty_color
            painter.fillRect(QRectF(sx, y, seg_w, height), fill)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(outline, 1))
        for i in range(segments):
            sx = x + i * (seg_w + gap)
            painter.drawRect(QRectF(sx, y, seg_w, height))
        painter.drawRect(QRectF(x, y, width, height))

    def draw_bar_chart(self, painter, element, x, y, selected):
        """History bar chart with scanline stripes, framed (bars-chart look)."""
        width = int(element.width * self.scale)
        height = int(element.height * self.scale)
        max_value = max(float(getattr(element, 'max_value', 100) or 100), 0.0001)
        color = apply_opacity(element.color, getattr(element, 'color_opacity', 100))
        bg = apply_opacity(element.background_color,
                           getattr(element, 'background_color_opacity', 100))
        frame = dim_color(color, 0.6)

        if getattr(element, 'show_background', True) and width > 0 and height > 0:
            painter.fillRect(QRectF(x, y, width, height), bg)

        add_bar_chart_value(element, element.value)
        history = get_bar_chart_history(element)

        bars = int(getattr(element, 'segments', 0) or 0)
        if bars <= 0:
            bars = max(1, width // 5)
        gap = max(0, int(getattr(element, 'gap', 1)))
        bar_w = max(1.0, (width - gap * (bars - 1)) / bars)

        samples = history[-bars:]
        if len(samples) < bars:
            samples = [0.0] * (bars - len(samples)) + samples

        painter.setPen(Qt.PenStyle.NoPen)
        for i, sample in enumerate(samples):
            r = max(0.0, min(1.0, float(sample) / max_value))
            bh = max(1.0, r * max(1, height - 2))
            bx = x + i * (bar_w + gap)
            by = y + height - bh
            painter.fillRect(QRectF(bx, by, bar_w, bh), color)

            stripe_pen = QPen(dim_color(color, 0.3), 1)
            painter.setPen(stripe_pen)
            stripe_y = by + 2.0
            while stripe_y < y + height:
                painter.drawLine(QPointF(bx, stripe_y), QPointF(bx + bar_w, stripe_y))
                stripe_y += 3.0
            painter.setPen(Qt.PenStyle.NoPen)

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(frame, 1))
        painter.drawRect(QRectF(x, y, width, height))

    def draw_video(self, painter, element, x, y):
        """Draw the current frame of a ``video`` element (scaled to its rect)."""
        width = int(element.width * self.scale)
        height = int(element.height * self.scale)
        path = getattr(element, "video_path", "")
        if not path or not os.path.exists(path):
            painter.fillRect(x, y, width, height, QColor(40, 40, 60))
            painter.setPen(QPen(QColor(100, 100, 120)))
            painter.drawRect(x, y, width, height)
            painter.drawText(x + 5, y + height // 2, "No Video")
            return
        from video_background import get_video_frame

        frame = get_video_frame(
            path, (max(1, int(element.width)), max(1, int(element.height))),
            getattr(element, "video_fit_mode", "fit_height"))
        if frame is None:
            return
        image = QImage(frame.tobytes(), frame.width, frame.height,
                       4 * frame.width, QImage.Format.Format_RGBA8888).copy()
        painter.drawImage(QRectF(x, y, width, height), image)

    def draw_dmd_widget(self, painter, element, x, y):
        """Render one of the HWMON·32 DMD widgets (128×32 logical, scaled)."""
        from dmd_widgets import render_widget

        width = max(1, int(element.width * self.scale))
        height = max(1, int(element.height * self.scale))
        pixels = render_widget(element.type, element, width, height)
        if pixels.size == 0:
            return
        image = QImage(pixels.tobytes(), width, height, 4 * width,
                       QImage.Format.Format_RGBA8888)
        painter.drawImage(QRectF(x, y, width, height), image)

    def draw_lcd_widget(self, painter, element, x, y):
        """Render one of the high-resolution LCD elements (antialiased, PIL path)."""
        from lcd_widgets import render_element

        width = max(1, int(element.width * self.scale))
        height = max(1, int(element.height * self.scale))
        self.get_animated_value(element)
        pixels = render_element(element.type, element, width, height)
        if pixels.size == 0:
            return
        image = QImage(pixels.tobytes(), width, height, 4 * width,
                       QImage.Format.Format_RGBA8888)
        painter.drawImage(QRectF(x, y, width, height), image)

    def draw_touch_nav(self, painter, element, x, y):
        """Render the HDMI touch-navigation widget (buttons along an edge)."""
        from touch_nav import render

        width = max(1, int(element.width * self.scale))
        height = max(1, int(element.height * self.scale))
        pixels = render(element, width, height)
        if pixels.size == 0:
            return
        image = QImage(pixels.tobytes(), width, height, 4 * width,
                       QImage.Format.Format_RGBA8888)
        painter.drawImage(QRectF(x, y, width, height), image)

    def draw_text(self, painter, element, x, y, selected):
        color = apply_opacity(element.color, getattr(element, 'color_opacity', 100))

        painter.setPen(QPen(color))
        font = QFont(element.font_family)
        font.setPixelSize(int(element.font_size * self.scale))
        font.setBold(element.font_bold)
        font.setItalic(element.font_italic)
        painter.setFont(font)

        # Determine text to display based on source
        source = getattr(element, 'source', 'static')
        if source and source != 'static':
            # Display sensor value, optionally with label
            value_text = get_value_with_unit(element.value, source, getattr(element, 'temp_hide_unit', False))
            if element.text:
                text = f"{element.text}: {value_text}"
            else:
                text = value_text
        else:
            text = element.text

        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(text)
        text_height = metrics.height()

        width = int(element.width * self.scale)
        height = int(element.height * self.scale)

        if element.text_align == "left":
            draw_x = x
        elif element.text_align == "right":
            draw_x = x + width - text_width
        else:
            draw_x = x + (width - text_width) // 2

        draw_y = y + (height + text_height) // 2 - metrics.descent()

        painter.drawText(draw_x, draw_y, text)

    def draw_rectangle(self, painter, element, x, y, selected):
        width = int(element.width * self.scale)
        height = int(element.height * self.scale)
        color = apply_opacity(element.color, getattr(element, 'color_opacity', 100))
        border_radius = int(getattr(element, 'border_radius', 0) * self.scale)
        glass_effect = getattr(element, 'glass_effect', False)

        if glass_effect:
            self.draw_glass_rectangle(painter, element, x, y, width, height, border_radius, color)
        elif border_radius > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawRoundedRect(x, y, width, height, border_radius, border_radius)
        else:
            painter.fillRect(x, y, width, height, color)

    def draw_glass_rectangle(self, painter, element, x, y, width, height, border_radius, color):
        """Draw a frosted glass effect rectangle using pre-rendered background."""
        from PySide6.QtGui import QPainterPath

        glass_blur = getattr(element, 'glass_blur', 10)
        glass_opacity = getattr(element, 'glass_opacity', 50)

        # Use the pre-rendered background (no recursive grab needed)
        if self._glass_background is not None and width > 0 and height > 0:
            # Extract the region we need to blur
            region = self._glass_background.copy(x, y, width, height)

            # Apply blur by downscaling and upscaling (fast box blur approximation)
            blur_amount = max(2, glass_blur // 2)
            small = region.scaled(
                max(1, width // blur_amount),
                max(1, height // blur_amount),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            blurred = small.scaled(
                width, height,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )

            # Draw the blurred background
            if border_radius > 0:
                path = QPainterPath()
                path.addRoundedRect(x, y, width, height, border_radius, border_radius)
                painter.setClipPath(path)
                painter.drawPixmap(x, y, blurred)
                painter.setClipping(False)
            else:
                painter.drawPixmap(x, y, blurred)

        # Draw semi-transparent tinted overlay
        tint_color = QColor(color)
        tint_color.setAlpha(int(255 * glass_opacity / 100))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(tint_color))

        if border_radius > 0:
            painter.drawRoundedRect(x, y, width, height, border_radius, border_radius)
        else:
            painter.fillRect(x, y, width, height, tint_color)

        # Draw subtle border for glass effect
        border_color = QColor(255, 255, 255, 40)
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if border_radius > 0:
            painter.drawRoundedRect(x, y, width, height, border_radius, border_radius)
        else:
            painter.drawRect(x, y, width, height)

    def draw_clock(self, painter, element, x, y, selected):
        color = apply_opacity(element.color, getattr(element, 'color_opacity', 100))

        painter.setPen(QPen(color))
        font = QFont(element.font_family)
        font.setPixelSize(int(element.font_size * self.scale))
        font.setBold(element.font_bold)
        font.setItalic(element.font_italic)
        painter.setFont(font)

        # Build time format string based on element settings
        time_format = getattr(element, 'time_format', '24h')
        show_seconds = getattr(element, 'show_seconds', True)
        show_am_pm = getattr(element, 'show_am_pm', True)
        show_leading_zero = getattr(element, 'show_leading_zero', True)

        if time_format == '12h':
            fmt = "%I:%M:%S" if show_seconds else "%I:%M"
            if show_am_pm:
                fmt += " %p"
        else:  # 24h
            fmt = "%H:%M:%S" if show_seconds else "%H:%M"

        current_time = time.strftime(fmt)

        # Remove leading zero from hour if disabled
        if not show_leading_zero and current_time[0] == '0':
            current_time = current_time[1:]

        metrics = painter.fontMetrics()
        text_width = metrics.horizontalAdvance(current_time)
        text_height = metrics.height()

        width = int(element.width * self.scale)
        height = int(element.height * self.scale)

        if element.text_align == "left":
            draw_x = x
        elif element.text_align == "right":
            draw_x = x + width - text_width
        else:
            draw_x = x + (width - text_width) // 2

        draw_y = y + (height + text_height) // 2 - metrics.descent()

        painter.drawText(draw_x, draw_y, current_time)

    def draw_image(self, painter, element, x, y, selected):
        width = int(element.width * self.scale)
        height = int(element.height * self.scale)

        if element.image_path and os.path.exists(element.image_path):
            pixmap = QPixmap(element.image_path)
            if element.scale_proportionally:
                # Maintain aspect ratio - fit within bounds
                pixmap = pixmap.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            else:
                # Stretch to fill exact dimensions
                pixmap = pixmap.scaled(width, height, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
            painter.drawPixmap(x, y, pixmap)
        else:
            painter.fillRect(x, y, width, height, QColor(40, 40, 60))
            painter.setPen(QPen(QColor(100, 100, 120)))
            painter.drawRect(x, y, width, height)
            painter.drawText(x + 5, y + height // 2, "No Image")

    def draw_icon(self, painter, element, x, y):
        """Draw an Icon element loaded from the bundled icons/ folder."""
        width = max(1, int(element.width * self.scale))
        height = max(1, int(element.height * self.scale))
        path = resolve_icon_path(getattr(element, "icon_name", ""))
        if not path:
            painter.fillRect(x, y, width, height, QColor(40, 40, 60))
            return
        image = QImage(path)
        if image.isNull():
            painter.fillRect(x, y, width, height, QColor(40, 40, 60))
            return
        if getattr(element, "tint", False):
            tinted = QImage(image.size(), QImage.Format.Format_ARGB32)
            tinted.fill(Qt.GlobalColor.transparent)
            tint_painter = QPainter(tinted)
            tint_painter.drawImage(0, 0, image)
            tint_painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceIn)
            tint_painter.fillRect(tinted.rect(), QColor(element.color))
            tint_painter.end()
            image = tinted
        pixmap = QPixmap.fromImage(image)
        ratio = (Qt.AspectRatioMode.KeepAspectRatio if element.scale_proportionally
                 else Qt.AspectRatioMode.IgnoreAspectRatio)
        pixmap = pixmap.scaled(width, height, ratio,
                               Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap(x, y, pixmap)

    def get_element_bounds(self, element):
        """Get the bounding rectangle for an element."""
        x = int(element.x * self.scale)
        y = int(element.y * self.scale)

        if element.type in ["circle_gauge", "gauge_circle_dmd"]:
            radius = int(element.radius * self.scale)
            return QRectF(x - radius, y - radius, radius * 2, radius * 2)
        elif hasattr(element, 'width') and hasattr(element, 'height') and element.width > 0 and element.height > 0:
            width = int(element.width * self.scale)
            height = int(element.height * self.scale)
            return QRectF(x, y, width, height)
        else:
            return QRectF(x, y, 100, 50)

    # ------------------------------------------------------------------
    # Smart guides
    # ------------------------------------------------------------------
    def get_element_logical_bounds(self, element):
        """Get the bounding rectangle of an element in logical (unscaled) units."""
        if element.type in ["circle_gauge", "gauge_circle_dmd"]:
            radius = int(element.radius)
            return (element.x - radius, element.y - radius,
                    element.x + radius, element.y + radius)
        elif hasattr(element, 'width') and hasattr(element, 'height') and element.width > 0 and element.height > 0:
            return (element.x, element.y,
                    element.x + element.width, element.y + element.height)
        else:
            return (element.x, element.y, element.x + 100, element.y + 50)

    def _active_canvas_bounds(self):
        """Logical canvas extent for the current orientation: (w, h)."""
        if self.vertical_mode:
            return DISPLAY_HEIGHT, DISPLAY_WIDTH
        return DISPLAY_WIDTH, DISPLAY_HEIGHT

    def _logical_bounds_from(self, element, ox, oy):
        """Logical bounds of an element anchored at origin (ox, oy)."""
        if element.type in ["circle_gauge", "gauge_circle_dmd"]:
            radius = int(element.radius)
            return (ox - radius, oy - radius, ox + radius, oy + radius)
        elif hasattr(element, 'width') and hasattr(element, 'height') and element.width > 0 and element.height > 0:
            return (ox, oy, ox + element.width, oy + element.height)
        else:
            return (ox, oy, ox + 100, oy + 50)

    def _moving_selection_bounds(self, base_x, base_y):
        """Union logical bounds of the dragged selection at a raw offset from its start."""
        min_x = min_y = None
        max_x = max_y = None
        for idx in self.selected_indices:
            if idx not in self.drag_start_positions:
                continue
            sx, sy = self.drag_start_positions[idx]
            l, t, r, b = self._logical_bounds_from(self.elements[idx], sx, sy)
            l += base_x
            r += base_x
            t += base_y
            b += base_y
            if min_x is None:
                min_x, max_x, min_y, max_y = l, r, t, b
            else:
                min_x, max_x = min(min_x, l), max(max_x, r)
                min_y, max_y = min(min_y, t), max(max_y, b)
        if min_x is None:
            return (0, 0, 0, 0)
        return (min_x, min_y, max_x, max_y)

    def _collect_guide_candidates(self, axis):
        """Reference coordinates for a guide axis: each non-moving element's
        left/center/right (x) or top/center/bottom (y), plus the canvas extent."""
        bound_w, bound_h = self._active_canvas_bounds()
        if bound_w <= 0 or bound_h <= 0:
            return []
        candidates = []
        for idx, el in enumerate(self.elements):
            if idx in self.selected_indices:
                continue
            l, t, r, b = self.get_element_logical_bounds(el)
            if axis == 'x':
                candidates.extend((l, (l + r) / 2.0, r))
            else:
                candidates.extend((t, (t + b) / 2.0, b))
        if axis == 'x':
            candidates.extend((0, bound_w / 2.0, bound_w))
        else:
            candidates.extend((0, bound_h / 2.0, bound_h))
        return candidates

    def _compute_snap(self, base_x, base_y, modifiers):
        """Resolve smart-guide snapping for the dragged selection.

        Returns (snap_dx, snap_dy, guides): the offsets to add to the raw drag
        translation and the guide lines (axis, value, extent_a, extent_b) to draw.
        """
        snap_off_x = snap_off_y = 0.0
        guides = []
        if modifiers & Qt.KeyboardModifier.AltModifier:
            return 0.0, 0.0, []

        min_x, min_y, max_x, max_y = self._moving_selection_bounds(base_x, base_y)
        tol = SNAP_TOLERANCE_PX / self.scale

        for axis, (a, b), _offset_attr in (
                ('x', (min_x, max_x), 'snap_off_x'),
                ('y', (min_y, max_y), 'snap_off_y')):
            # edges/centers of the moving selection: 0=start-edge, 1=center, 2=end-edge
            moving_vals = (a, (a + b) / 2.0, b)
            best_delta = None
            best_ref = None
            best_i = 0
            for cand in self._collect_guide_candidates(axis):
                for i, mval in enumerate(moving_vals):
                    delta = cand - mval
                    if best_delta is None or abs(delta) < abs(best_delta):
                        best_delta = delta
                        best_ref = cand
                        best_i = i
            if best_delta is not None and abs(best_delta) <= tol:
                if axis == 'x':
                    snap_off_x = best_delta
                else:
                    snap_off_y = best_delta
                bound_w, bound_h = self._active_canvas_bounds()
                if axis == 'x':
                    guides.append(('x', best_ref, 0, bound_h))
                else:
                    guides.append(('y', best_ref, 0, bound_w))

        return snap_off_x, snap_off_y, guides

    def draw_selection_box(self, painter, element, x, y):
        bounds = self.get_element_bounds(element)

        pen = QPen(ACCENT_QCOLOR, 1.6, Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 3])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(bounds)

        # Draw resize handles at corners
        hs = self.handle_size
        handles = [
            (bounds.left(), bounds.top()),      # TL
            (bounds.right(), bounds.top()),     # TR
            (bounds.left(), bounds.bottom()),   # BL
            (bounds.right(), bounds.bottom()),  # BR
        ]

        painter.setPen(Qt.PenStyle.NoPen)
        for hx, hy in handles:
            painter.setBrush(QBrush(ACCENT_QCOLOR))
            painter.drawRect(int(hx - hs / 2), int(hy - hs / 2), hs, hs)

    def get_multi_selection_bounds(self):
        """Get combined bounding rectangle for all selected elements."""
        if not self.selected_indices:
            return None

        min_x = float('inf')
        min_y = float('inf')
        max_x = float('-inf')
        max_y = float('-inf')

        for idx in self.selected_indices:
            if 0 <= idx < len(self.elements):
                bounds = self.get_element_bounds(self.elements[idx])
                min_x = min(min_x, bounds.left())
                min_y = min(min_y, bounds.top())
                max_x = max(max_x, bounds.right())
                max_y = max(max_y, bounds.bottom())

        if min_x == float('inf'):
            return None

        return QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

    def draw_multi_selection_box(self, painter):
        """Draw a combined selection box around all selected elements."""
        bounds = self.get_multi_selection_bounds()
        if bounds is None:
            return

        # Draw outer selection box
        pen = QPen(ACCENT_QCOLOR, 1.6, Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 3])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(bounds)

        # Draw resize handles at corners
        hs = self.handle_size
        handles = [
            (bounds.left(), bounds.top()),
            (bounds.right(), bounds.top()),
            (bounds.left(), bounds.bottom()),
            (bounds.right(), bounds.bottom()),
        ]

        painter.setPen(Qt.PenStyle.NoPen)
        for hx, hy in handles:
            painter.setBrush(QBrush(ACCENT_QCOLOR))
            painter.drawRect(int(hx - hs / 2), int(hy - hs / 2), hs, hs)

    def get_handle_at(self, pos, element):
        """Check if position is over a resize handle. Returns handle type or HANDLE_NONE."""
        bounds = self.get_element_bounds(element)
        hs = self.handle_size

        handles = {
            self.HANDLE_TL: (bounds.left(), bounds.top()),
            self.HANDLE_TR: (bounds.right(), bounds.top()),
            self.HANDLE_BL: (bounds.left(), bounds.bottom()),
            self.HANDLE_BR: (bounds.right(), bounds.bottom()),
        }

        for handle_type, (hx, hy) in handles.items():
            handle_rect = QRectF(hx - hs, hy - hs, hs * 2, hs * 2)
            if handle_rect.contains(pos):
                return handle_type

        return self.HANDLE_NONE

    def get_element_at(self, pos):
        # Check from index 0 first (top of tree = front of display)
        # This matches rendering order where index 0 is drawn last (on top)
        for i in range(len(self.elements)):
            element = self.elements[i]
            x = element.x * self.scale
            y = element.y * self.scale

            if element.type in ["circle_gauge", "gauge_circle_dmd"]:
                radius = element.radius * self.scale
                dist = ((pos.x() - x) ** 2 + (pos.y() - y) ** 2) ** 0.5
                if dist <= radius:
                    return i
            elif hasattr(element, 'width') and hasattr(element, 'height') and element.width > 0 and element.height > 0:
                # Any element with width/height properties
                width = element.width * self.scale
                height = element.height * self.scale
                if x <= pos.x() <= x + width and y <= pos.y() <= y + height:
                    return i

        return -1

    @staticmethod
    def hit_test_elements(elements, x, y, visible_only=False):
        """Hit-test a escala 1.0 (coordenadas lógicas del canvas).

        Recorre de frente a fondo (índice 0 = dibujado al final = encima),
        igual que ``get_element_at``. Se usa para el toque en el monitor HDMI,
        donde la salida se renderiza 1:1 con el canvas. Con ``visible_only``
        los elementos ocultos no son "tocables".
        """
        for i, element in enumerate(elements):
            if visible_only and not getattr(element, "visible", True):
                continue
            if element.type in ("circle_gauge", "gauge_circle_dmd"):
                radius = element.radius
                dist = ((x - element.x) ** 2 + (y - element.y) ** 2) ** 0.5
                if dist <= radius:
                    return i
            elif getattr(element, "width", 0) > 0 and getattr(element, "height", 0) > 0:
                if (element.x <= x <= element.x + element.width and
                        element.y <= y <= element.y + element.height):
                    return i
        return -1

    def get_multi_handle_at(self, pos):
        """Check if position is over a resize handle for multi-selection."""
        bounds = self.get_multi_selection_bounds()
        if bounds is None:
            return self.HANDLE_NONE

        hs = self.handle_size
        handles = {
            self.HANDLE_TL: (bounds.left(), bounds.top()),
            self.HANDLE_TR: (bounds.right(), bounds.top()),
            self.HANDLE_BL: (bounds.left(), bounds.bottom()),
            self.HANDLE_BR: (bounds.right(), bounds.bottom()),
        }

        for handle_type, (hx, hy) in handles.items():
            handle_rect = QRectF(hx - hs, hy - hs, hs * 2, hs * 2)
            if handle_rect.contains(pos):
                return handle_type

        return self.HANDLE_NONE

    def mousePressEvent(self, event):
        self._reconcile_selection()
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            modifiers = event.modifiers()
            ctrl_held = modifiers & Qt.KeyboardModifier.ControlModifier
            shift_held = modifiers & Qt.KeyboardModifier.ShiftModifier

            # Check if clicking on resize handle of selected element(s)
            # Don't allow resizing if any selected element is locked
            any_locked = any(self.elements[idx].locked for idx in self.selected_indices) if self.selected_indices else False

            if len(self.selected_indices) > 1 and not any_locked:
                # Multi-selection resize handle check
                handle = self.get_multi_handle_at(pos)
                if handle != self.HANDLE_NONE:
                    self.drag_started.emit()
                    self.resizing = True
                    self.resize_handle = handle
                    self.resize_start_pos = pos
                    self.resize_start_bounds = self.get_multi_selection_bounds()
                    # Store original positions and sizes for all selected elements
                    self.resize_start_elements = {}
                    for idx in self.selected_indices:
                        el = self.elements[idx]
                        if el.type in ["circle_gauge", "gauge_circle_dmd"]:
                            self.resize_start_elements[idx] = (el.x, el.y, el.radius, el.radius)
                        else:
                            self.resize_start_elements[idx] = (el.x, el.y, el.width, el.height)
                    return
            elif len(self.selected_indices) == 1 and not any_locked:
                element = self.elements[self.selected_indices[0]]
                handle = self.get_handle_at(pos, element)
                if handle != self.HANDLE_NONE:
                    self.drag_started.emit()
                    self.resizing = True
                    self.resize_handle = handle
                    self.resize_start_pos = pos
                    self.resize_start_pos_element = (element.x, element.y)
                    if element.type in ["circle_gauge", "gauge_circle_dmd"]:
                        self.resize_start_size = (element.radius, element.radius)
                    else:
                        self.resize_start_size = (element.width, element.height)
                    return

            # Check if clicking on an element
            index = self.get_element_at(pos)

            if index >= 0:
                clicked_element = self.elements[index]
                clicked_group = getattr(clicked_element, 'group', None)

                if ctrl_held:
                    # Ctrl+click: Toggle selection (respects groups)
                    if clicked_group:
                        # Get all indices in this group
                        group_indices = [i for i, el in enumerate(self.elements) if getattr(el, 'group', None) == clicked_group]
                        # Check if entire group is selected
                        all_selected = all(i in self.selected_indices for i in group_indices)
                        if all_selected:
                            # Deselect entire group
                            for i in group_indices:
                                if i in self.selected_indices:
                                    self.selected_indices.remove(i)
                        else:
                            # Select entire group
                            for i in group_indices:
                                if i not in self.selected_indices:
                                    self.selected_indices.append(i)
                    else:
                        # Ungrouped element - toggle individual
                        if index in self.selected_indices:
                            self.selected_indices.remove(index)
                        else:
                            self.selected_indices.append(index)
                elif shift_held and self.selected_indices:
                    # Shift+click: Range selection
                    last_selected = self.selected_indices[-1]
                    start, end = min(last_selected, index), max(last_selected, index)
                    for i in range(start, end + 1):
                        if i not in self.selected_indices:
                            self.selected_indices.append(i)
                else:
                    # Normal click behavior:
                    # - If element already selected (e.g., via tree), keep current selection for dragging
                    # - If element not selected, select entire group (or just element if ungrouped)
                    if index in self.selected_indices:
                        # Already selected - keep current selection (allows dragging individual from tree selection)
                        pass
                    elif clicked_group:
                        # Not selected, but in a group - select entire group
                        group_indices = [i for i, el in enumerate(self.elements) if getattr(el, 'group', None) == clicked_group]
                        self.selected_indices = group_indices
                        self.group_selection_mode = True
                    else:
                        # Ungrouped element - single selection
                        self.selected_indices = [index]
                        self.group_selection_mode = False

                # Check if any selected element is locked - don't allow dragging
                any_locked = any(self.elements[idx].locked for idx in self.selected_indices)

                # Start dragging (only if not locked)
                if not any_locked:
                    self.drag_started.emit()
                    self.dragging = True
                    self._active_guides.clear()
                    # Store start positions for all selected elements
                    self.drag_start_positions = {}
                    for idx in self.selected_indices:
                        el = self.elements[idx]
                        self.drag_start_positions[idx] = (el.x, el.y)
                    self.drag_start_mouse = pos

                # Emit signals
                if len(self.selected_indices) == 1:
                    self.element_selected.emit(self.selected_indices[0])
                else:
                    self.element_selected.emit(-1)  # -1 indicates multi-select
                self.elements_selected.emit(self.selected_indices.copy())
            else:
                # Clicked on empty space
                if not ctrl_held and not shift_held:
                    self.selected_indices = []
                    self.element_selected.emit(-1)
                    self.elements_selected.emit([])

            self.update()

    def mouseMoveEvent(self, event):
        self._reconcile_selection()
        pos = event.position()

        # Handle multi-element resizing
        if self.resizing and len(self.selected_indices) > 1 and self.resize_start_bounds:
            dx = (pos.x() - self.resize_start_pos.x()) / self.scale
            dy = (pos.y() - self.resize_start_pos.y()) / self.scale

            orig_bounds = self.resize_start_bounds
            orig_w = orig_bounds.width() / self.scale
            orig_h = orig_bounds.height() / self.scale

            # Calculate scale factors
            if self.resize_handle in [self.HANDLE_TR, self.HANDLE_BR]:
                scale_x = (orig_w + dx) / orig_w if orig_w > 0 else 1
            elif self.resize_handle in [self.HANDLE_TL, self.HANDLE_BL]:
                scale_x = (orig_w - dx) / orig_w if orig_w > 0 else 1
            else:
                scale_x = 1

            if self.resize_handle in [self.HANDLE_BL, self.HANDLE_BR]:
                scale_y = (orig_h + dy) / orig_h if orig_h > 0 else 1
            elif self.resize_handle in [self.HANDLE_TL, self.HANDLE_TR]:
                scale_y = (orig_h - dy) / orig_h if orig_h > 0 else 1
            else:
                scale_y = 1

            scale_x = max(0.1, scale_x)
            scale_y = max(0.1, scale_y)

            # Apply scale to all selected elements
            anchor_x = orig_bounds.right() / self.scale if self.resize_handle in [self.HANDLE_TL, self.HANDLE_BL] else orig_bounds.left() / self.scale
            anchor_y = orig_bounds.bottom() / self.scale if self.resize_handle in [self.HANDLE_TL, self.HANDLE_TR] else orig_bounds.top() / self.scale

            for idx, (ox, oy, ow, oh) in self.resize_start_elements.items():
                el = self.elements[idx]
                if el.type in ["circle_gauge", "gauge_circle_dmd"]:
                    new_radius = max(30, int(ow * (scale_x + scale_y) / 2))
                    el.radius = new_radius
                    el.x = int(anchor_x + (ox - anchor_x) * scale_x)
                    el.y = int(anchor_y + (oy - anchor_y) * scale_y)
                else:
                    el.width = max(20, int(ow * scale_x))
                    el.height = max(20, int(oh * scale_y))
                    el.x = int(anchor_x + (ox - anchor_x) * scale_x)
                    el.y = int(anchor_y + (oy - anchor_y) * scale_y)

            self.element_resized.emit(-1)
            self.update()
            return

        # Handle single element resizing
        if self.resizing and len(self.selected_indices) == 1:
            element = self.elements[self.selected_indices[0]]
            dx = (pos.x() - self.resize_start_pos.x()) / self.scale
            dy = (pos.y() - self.resize_start_pos.y()) / self.scale

            if element.type in ["circle_gauge", "gauge_circle_dmd"]:
                if self.resize_handle in [self.HANDLE_BR, self.HANDLE_TR]:
                    new_radius = max(30, int(self.resize_start_size[0] + (dx + dy) / 2))
                else:
                    new_radius = max(30, int(self.resize_start_size[0] - (dx + dy) / 2))
                element.radius = new_radius
            else:
                new_width, new_height = self.resize_start_size

                if self.resize_handle in [self.HANDLE_TR, self.HANDLE_BR]:
                    new_width = max(20, int(self.resize_start_size[0] + dx))
                elif self.resize_handle in [self.HANDLE_TL, self.HANDLE_BL]:
                    new_width = max(20, int(self.resize_start_size[0] - dx))
                    element.x = int(self.resize_start_pos_element[0] + dx)

                if self.resize_handle in [self.HANDLE_BL, self.HANDLE_BR]:
                    new_height = max(20, int(self.resize_start_size[1] + dy))
                elif self.resize_handle in [self.HANDLE_TL, self.HANDLE_TR]:
                    new_height = max(20, int(self.resize_start_size[1] - dy))
                    element.y = int(self.resize_start_pos_element[1] + dy)

                if element.type == "image" and element.scale_proportionally and element.aspect_ratio > 0:
                    width_ratio = new_width / self.resize_start_size[0] if self.resize_start_size[0] > 0 else 1
                    height_ratio = new_height / self.resize_start_size[1] if self.resize_start_size[1] > 0 else 1

                    if abs(width_ratio - 1) > abs(height_ratio - 1):
                        new_height = max(20, int(new_width / element.aspect_ratio))
                    else:
                        new_width = max(20, int(new_height * element.aspect_ratio))

                    if self.resize_handle == self.HANDLE_TL:
                        element.x = int(self.resize_start_pos_element[0] + self.resize_start_size[0] - new_width)
                        element.y = int(self.resize_start_pos_element[1] + self.resize_start_size[1] - new_height)
                    elif self.resize_handle == self.HANDLE_TR:
                        element.y = int(self.resize_start_pos_element[1] + self.resize_start_size[1] - new_height)
                    elif self.resize_handle == self.HANDLE_BL:
                        element.x = int(self.resize_start_pos_element[0] + self.resize_start_size[0] - new_width)

                element.width = new_width
                element.height = new_height

            self.element_resized.emit(self.selected_indices[0])
            self.update()
            return

        # Handle dragging (single or multiple elements)
        if self.dragging and self.selected_indices:
            dx = (pos.x() - self.drag_start_mouse.x()) / self.scale
            dy = (pos.y() - self.drag_start_mouse.y()) / self.scale

            # Snap to smart guides and update the temporary alignment lines
            snap_dx, snap_dy, self._active_guides = self._compute_snap(dx, dy, event.modifiers())
            dx += snap_dx
            dy += snap_dy

            # Clamp against the active canvas bounds - swapped when vertical mode
            # is enabled, since the logical design space is then DISPLAY_HEIGHT x
            # DISPLAY_WIDTH instead of DISPLAY_WIDTH x DISPLAY_HEIGHT.
            if self.vertical_mode:
                bound_w, bound_h = DISPLAY_HEIGHT, DISPLAY_WIDTH
            else:
                bound_w, bound_h = DISPLAY_WIDTH, DISPLAY_HEIGHT

            for idx in self.selected_indices:
                if idx in self.drag_start_positions:
                    start_x, start_y = self.drag_start_positions[idx]
                    new_x = int(start_x + dx)
                    new_y = int(start_y + dy)
                    new_x = max(0, min(new_x, bound_w - 50))
                    new_y = max(0, min(new_y, bound_h - 50))
                    self.elements[idx].x = new_x
                    self.elements[idx].y = new_y

            if len(self.selected_indices) == 1:
                el = self.elements[self.selected_indices[0]]
                self.element_moved.emit(self.selected_indices[0], el.x, el.y)
            self.update()
            return

        # Update cursor based on hover
        if len(self.selected_indices) > 1:
            # Multi-selection - check for multi-selection resize handles
            handle = self.get_multi_handle_at(pos)
            if handle in [self.HANDLE_TL, self.HANDLE_BR]:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif handle in [self.HANDLE_TR, self.HANDLE_BL]:
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        elif len(self.selected_indices) == 1:
            element = self.elements[self.selected_indices[0]]
            handle = self.get_handle_at(pos, element)
            if handle in [self.HANDLE_TL, self.HANDLE_BR]:
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif handle in [self.HANDLE_TR, self.HANDLE_BL]:
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = False
            self.resizing = False
            self.resize_handle = self.HANDLE_NONE
            self._active_guides = []

    def keyPressEvent(self, event):
        """Handle arrow key nudging for selected elements."""
        if not self._reconcile_selection():
            return

        # Check if any selected element is locked
        any_locked = any(self.elements[idx].locked for idx in self.selected_indices)
        if any_locked:
            return

        key = event.key()
        shift_held = event.modifiers() & Qt.KeyboardModifier.ShiftModifier

        # Determine nudge amount: 10px with Shift, 1px without
        nudge = 10 if shift_held else 1

        dx, dy = 0, 0
        if key == Qt.Key.Key_Left:
            dx = -nudge
        elif key == Qt.Key.Key_Right:
            dx = nudge
        elif key == Qt.Key.Key_Up:
            dy = -nudge
        elif key == Qt.Key.Key_Down:
            dy = nudge
        else:
            # Not an arrow key, pass to parent
            super().keyPressEvent(event)
            return

        # Emit drag_started for undo state
        self.drag_started.emit()

        # Move all selected elements
        for idx in self.selected_indices:
            element = self.elements[idx]
            element.x += dx
            element.y += dy
            self.element_moved.emit(idx, element.x, element.y)

        self.update()


class DMDCanvas(CanvasPreview):
    """Canvas adaptado a resolución DMD (128×32 nativo).

    Hereda de CanvasPreview para reutilizar los draw_* existentes.
    Produces RGB565 bytes para enviar por TCP al ESP32.
    """

    def __init__(self, width=128, height=32):
        self.dmd_width = width
        self.dmd_height = height
        super().__init__()
        self.scale = 1.0
        self.vertical_mode = False
        self.background_color = QColor(0, 0, 0)
        self._preview_image = None  # QImage superpuesta (preview de transiciones)
        self._update_fixed_size()

    def set_preview_image(self, image):
        """Overlay a QImage (or None to clear) on top of the canvas.

        Se usa para previsualizar el ciclo de pantallas con transiciones sin
        alterar los elementos en edición.
        """
        self._preview_image = image
        self.update()

    def _update_fixed_size(self):
        self.setFixedSize(
            int(self.dmd_width * self.scale),
            int(self.dmd_height * self.scale),
        )

    def fit_scale_for(self, avail_w, avail_h, margin=28):
        avail_w = max(1, avail_w - margin)
        avail_h = max(1, avail_h - margin)
        return max(1.0, min(8.0, min(avail_w / self.dmd_width,
                                     avail_h / self.dmd_height)))

    def set_zoom_scale(self, scale):
        scale = max(1.0, min(8.0, scale))
        if abs(scale - self.scale) < 0.001:
            return
        self.scale = scale
        self._active_guides = []
        self._update_fixed_size()
        self.update()

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        cw = int(self.dmd_width * self.scale)
        ch = int(self.dmd_height * self.scale)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Fondo del viewport (área fuera del canvas nativo)
        painter.fillRect(0, 0, self.width(), self.height(), QColor("#08090b"))

        # Canvas nativo (negro) con borde sutil
        draw_rect = QRectF(0, 0, cw, ch)
        painter.fillRect(draw_rect, self.background_color)
        pen = QPen(BORDER_QCOLOR, 1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(draw_rect.adjusted(0, 0, -1, -1))

        # Elementos en orden inverso (último en lista = fondo)
        for i in range(len(self.elements) - 1, -1, -1):
            is_selected = i in self.selected_indices
            draw_individual = is_selected and not self.group_selection_mode
            self.draw_element(painter, self.elements[i], draw_individual)

        # Preview del ciclo de pantallas (transiciones): se pinta encima.
        if self._preview_image is not None:
            painter.drawImage(QRectF(0, 0, cw, ch), self._preview_image)

        if len(self.selected_indices) > 1:
            self.draw_multi_selection_box(painter)

        if self._active_guides:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            guide_pen = QPen(GUIDE_COLOR, 1, Qt.PenStyle.DashLine)
            guide_pen.setDashPattern([4, 3])
            painter.setPen(guide_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for axis, value, extent_a, extent_b in self._active_guides:
                px = int(value * self.scale)
                a = int(extent_a * self.scale)
                b = int(extent_b * self.scale)
                if axis == 'x':
                    painter.drawLine(px, a, px, b)
                else:
                    painter.drawLine(a, px, b, px)

        painter.end()

    # ------------------------------------------------------------------
    # RGB565 frame generation
    # ------------------------------------------------------------------
    def get_frame_rgb565(self):
        """Renderiza los elementos a un buffer RGB565 (bytes) del tamaño nativo DMD.

        Returns:
            bytes: payload de 8192 bytes (128×32×2) listo para enviar por TCP.
        """
        img = QImage(self.dmd_width, self.dmd_height,
                     QImage.Format.Format_RGB16)
        img.fill(self.background_color)

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # Temporarily set scale=1 for 1:1 rendering
        old_scale = self.scale
        self.scale = 1.0

        for i in range(len(self.elements) - 1, -1, -1):
            self.draw_element(painter, self.elements[i], False)

        self.scale = old_scale
        painter.end()

        return img.bits().tobytes()

    def get_frame_rgb888(self):
        """Renderiza los elementos a un ``QImage`` RGB888 (sin antialiasing).

        Se usa para componer las transiciones entre pantallas DMD.
        """
        img = QImage(self.dmd_width, self.dmd_height,
                     QImage.Format.Format_RGB888)
        img.fill(self.background_color)

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        old_scale = self.scale
        self.scale = 1.0
        try:
            for i in range(len(self.elements) - 1, -1, -1):
                self.draw_element(painter, self.elements[i], False)
        finally:
            self.scale = old_scale
            painter.end()

        return img

    def set_dmd_size(self, width, height):
        self.dmd_width = width
        self.dmd_height = height
        self._update_fixed_size()
        self.update()


class HDMICanvas(DMDCanvas):
    """Canvas de edición para una salida en monitor (HDMI), a resolución nativa.

    Reutiliza de ``DMDCanvas`` el zoom, el tamaño fijo y los ``draw_*`` de
    ``CanvasPreview``, pero trabaja en color completo (RGB888) y con
    antialiasing, que es lo que espera la ventana fullscreen de salida.
    El tamaño del canvas es la resolución física del monitor seleccionado.
    """

    def __init__(self, width=1920, height=1080):
        super().__init__(width, height)

    @property
    def hdmi_width(self):
        return self.dmd_width

    @property
    def hdmi_height(self):
        return self.dmd_height

    def set_hdmi_size(self, width, height):
        self.set_dmd_size(int(width), int(height))

    def fit_scale_for(self, avail_w, avail_h, margin=28):
        # Límite de zoom más laxo que DMD: los monitores tienen mucha más
        # resolución, así que el rango útil (fracciones) empieza por debajo de 1.
        avail_w = max(1, avail_w - margin)
        avail_h = max(1, avail_h - margin)
        return max(0.05, min(4.0, min(avail_w / self.dmd_width,
                                       avail_h / self.dmd_height)))

    def set_zoom_scale(self, scale):
        scale = max(0.05, min(4.0, scale))
        if abs(scale - self.scale) < 0.001:
            return
        self.scale = scale
        self._active_guides = []
        self._update_fixed_size()
        self.update()

    def paintEvent(self, event):
        cw = int(self.dmd_width * self.scale)
        ch = int(self.dmd_height * self.scale)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        painter.fillRect(0, 0, self.width(), self.height(), QColor("#08090b"))

        draw_rect = QRectF(0, 0, cw, ch)
        painter.fillRect(draw_rect, self.background_color)
        pen = QPen(BORDER_QCOLOR, 1)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(draw_rect.adjusted(0, 0, -1, -1))

        for i in range(len(self.elements) - 1, -1, -1):
            is_selected = i in self.selected_indices
            draw_individual = is_selected and not self.group_selection_mode
            self.draw_element(painter, self.elements[i], draw_individual)

        if len(self.selected_indices) > 1:
            self.draw_multi_selection_box(painter)

        if self._active_guides:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            guide_pen = QPen(GUIDE_COLOR, 1, Qt.PenStyle.DashLine)
            guide_pen.setDashPattern([4, 3])
            painter.setPen(guide_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for axis, value, extent_a, extent_b in self._active_guides:
                px = int(value * self.scale)
                a = int(extent_a * self.scale)
                b = int(extent_b * self.scale)
                if axis == 'x':
                    painter.drawLine(px, a, px, b)
                else:
                    painter.drawLine(a, px, b, px)

        painter.end()

    def get_frame_rgb888(self):
        """Renderiza los elementos a un ``QImage`` RGB888 a resolución nativa.

        Se usa directamente como frame de la ventana HDMI (sin pasar por JPEG).
        """
        img = QImage(self.dmd_width, self.dmd_height,
                     QImage.Format.Format_RGB888)
        img.fill(self.background_color)

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        old_scale = self.scale
        self.scale = 1.0
        try:
            for i in range(len(self.elements) - 1, -1, -1):
                self.draw_element(painter, self.elements[i], False)
        finally:
            self.scale = old_scale
            painter.end()

        return img
