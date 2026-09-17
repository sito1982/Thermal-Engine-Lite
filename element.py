"""
ThemeElement - Data model for theme elements.
"""

from constants import DEFAULT_FONT_FAMILY


# Los temas creados por Thermal Engine Studio pueden usar los ids del plugin
# Lite ("lite.cpu_temp"); este equipo resuelve las fuentes con los ids base
# ("cpu_temp"), así que se normaliza al cargar.
_LITE_SOURCE_PREFIX = "lite."


def _strip_lite_prefix(value):
    if isinstance(value, str) and value.startswith(_LITE_SOURCE_PREFIX):
        return value[len(_LITE_SOURCE_PREFIX):]
    return value


class ThemeElement:
    def __init__(self, element_type="text", **kwargs):
        self.type = element_type
        self.x = kwargs.get("x", 100)
        self.y = kwargs.get("y", 100)
        self.width = kwargs.get("width", 200)
        self.height = kwargs.get("height", 50)
        self.radius = kwargs.get("radius", 100)
        self.border_radius = kwargs.get("border_radius", 0)
        self.glass_effect = kwargs.get("glass_effect", False)
        self.glass_blur = kwargs.get("glass_blur", 10)
        self.glass_opacity = kwargs.get("glass_opacity", 50)
        self.color = kwargs.get("color", "#00ff96")
        self.color_opacity = kwargs.get("color_opacity", 100)  # 0-100
        self.background_color = kwargs.get("background_color", "#1a1a2e")
        self.background_color_opacity = kwargs.get("background_color_opacity", 100)  # 0-100
        self.use_custom_text_color = kwargs.get("use_custom_text_color", False)
        # Default text color: white for gauges, element color for others
        default_text_color = "#ffffff" if element_type in ["circle_gauge", "bar_gauge"] else self.color
        self.text_color = kwargs.get("text_color", default_text_color)
        self.text_color_opacity = kwargs.get("text_color_opacity", 100)  # 0-100
        self.text = kwargs.get("text", "Label")
        self.font_size = kwargs.get("font_size", 32)
        self.font_family = kwargs.get("font_family", DEFAULT_FONT_FAMILY)
        self.font_bold = kwargs.get("font_bold", False)
        self.font_italic = kwargs.get("font_italic", False)
        self.text_align = kwargs.get("text_align", "center")
        self.clip = kwargs.get("clip", False)
        self.source = _strip_lite_prefix(kwargs.get("source", "static"))
        self.value = kwargs.get("value", 50)
        self.max_value = max(float(kwargs.get("max_value", 100)), 0.0001)
        # Default arc thickness: 15 keeps the classic circle gauge look for themes
        # saved before line_width existed; the DMD components pass their own value.
        default_line_width = 15 if element_type == "circle_gauge" else 2
        self.line_width = kwargs.get("line_width", default_line_width)
        self.segments = kwargs.get("segments", 8)
        self.gap = kwargs.get("gap", 1)
        self.color_empty = kwargs.get("color_empty", "#1a1a2e")
        self.target = float(kwargs.get("target", 0) or 0)
        self.sources = [_strip_lite_prefix(s)
                        for s in (kwargs.get("sources", []) or [])]
        # Runtime values for the DMD combined panel (source id -> value); not
        # persisted, refreshed from sensors on every DMD tick.
        self.panel_values = dict(kwargs.get("panel_values", {}) or {})
        self.image_path = kwargs.get("image_path", "")
        self.scale_proportionally = kwargs.get("scale_proportionally", True)
        self.aspect_ratio = kwargs.get("aspect_ratio", 1.0)
        # Elemento Icon: se carga de la carpeta icons/ (sin selector de fichero).
        self.icon_name = kwargs.get("icon_name", "")
        self.tint = kwargs.get("tint", False)  # Recolorea el icono con `color`
        self.name = kwargs.get("name", f"{element_type}_{id(self)}")

        # Visibility: hidden elements are not rendered to the LCD/preview but can
        # still be selected and edited from the element list. Defaults to True so
        # themes saved before this field existed keep working unchanged.
        self.visible = kwargs.get("visible", True)

        # Line chart options
        self.show_background = kwargs.get("show_background", True)
        self.show_label = kwargs.get("show_label", True)
        self.show_gradient = kwargs.get("show_gradient", True)
        self.line_thickness = kwargs.get("line_thickness", 2)
        self.smooth = kwargs.get("smooth", False)

        # Bar gauge options
        self.rounded_corners = kwargs.get("rounded_corners", False)
        self.gradient_fill = kwargs.get("gradient_fill", False)
        self.gradient_stops = kwargs.get("gradient_stops", [(0.0, "#00ff96"), (1.0, "#ff4444")])  # Gradient color stops
        self.bar_text_mode = kwargs.get("bar_text_mode", "full")  # "full", "value_only", "none"
        # Default text position: "top" for bar gauge, "inside" for others
        default_bar_text_position = "top" if element_type == "bar_gauge" else "inside"
        self.bar_text_position = kwargs.get("bar_text_position", default_bar_text_position)
        # Bar gauge border options
        self.bar_border = kwargs.get("bar_border", False)  # Show border around bar
        self.bar_border_width = kwargs.get("bar_border_width", 2)  # Border stroke width
        self.bar_border_color = kwargs.get("bar_border_color", "#ffffff")  # Border color
        self.bar_border_opacity = kwargs.get("bar_border_opacity", 100)  # Border opacity 0-100
        self.bar_border_position = kwargs.get("bar_border_position", "center")  # "inside", "center", "outside"

        # Gauge options
        self.auto_color_change = kwargs.get("auto_color_change", False)  # Change color at thresholds
        self.animate_gauge = kwargs.get("animate_gauge", False)  # Animate value changes
        self.animation_speed = kwargs.get("animation_speed", 0.05)  # Animation interpolation speed (0.02-0.15, lower=smoother)
        self.gauge_rounded_ends = kwargs.get("gauge_rounded_ends", False)  # Circle gauge: pill-shaped arc ends

        # High-resolution LCD elements (ring_gauge, zone_bar, segment_bar...)
        self.arc_span = float(kwargs.get("arc_span", 270) or 270)  # ring_gauge: degrees drawn
        self.start_angle = float(kwargs.get("start_angle", -135) or 0)  # ring_gauge: 0 = top, clockwise
        self.show_ticks = kwargs.get("show_ticks", False)  # ring_gauge: radial tick marks
        self.thresholds = list(kwargs.get("thresholds", [70, 90]) or [])  # zone_bar: warn/crit
        self.orientation = kwargs.get("orientation", "horizontal")  # "horizontal" | "vertical"
        # Disk element (LCD/HDMI/Custom): barra vertical y sparklines opcionales.
        self.bar_mode = kwargs.get("bar_mode", "free")  # "free" | "used" | "none"
        self.show_sparklines = kwargs.get("show_sparklines", True)

        # Gauge label options (separate from value text)
        # Default label size: 24 for gauges, 16 for others
        default_label_font_size = 24 if element_type in ["circle_gauge", "bar_gauge"] else 16
        self.label_font_size = kwargs.get("label_font_size", default_label_font_size)
        self.label_font_family = kwargs.get("label_font_family", DEFAULT_FONT_FAMILY)
        self.label_font_bold = kwargs.get("label_font_bold", False)
        self.label_font_italic = kwargs.get("label_font_italic", False)
        self.label_text_color = kwargs.get("label_text_color", self.color)  # Label text color

        # GIF options
        self.gif_path = kwargs.get("gif_path", "")
        self.scale_mode = kwargs.get("scale_mode", "fit")  # fit, fill, stretch

        # Video element options
        self.video_path = kwargs.get("video_path", "")
        self.video_fit_mode = kwargs.get("video_fit_mode", "fit_height")

        # Clock time format options (for digital clock)
        self.time_format = kwargs.get("time_format", "24h")  # "24h", "12h"
        self.show_am_pm = kwargs.get("show_am_pm", True)  # Show AM/PM indicator
        self.show_seconds = kwargs.get("show_seconds", True)  # Show seconds
        self.show_leading_zero = kwargs.get("show_leading_zero", True)  # Show leading zero (09 vs 9)

        # Grouping
        self.group = kwargs.get("group", None)  # Group name, None if ungrouped

        # Locking
        self.locked = kwargs.get("locked", False)  # Prevent editing/dragging when True

        # Temperature display option
        self.temp_hide_unit = kwargs.get("temp_hide_unit", False)  # Show only ° instead of °C

        # Interaction (HDMI touch): action executed when this element is tapped
        # on the HDMI output window. Off by default and validated/approved by the
        # app before running anything (see actions.py / security.py).
        self.tap_action = kwargs.get("tap_action", "none")  # "none" | "command" | "transition"
        self.tap_command = kwargs.get("tap_command", "")
        self.tap_args = list(kwargs.get("tap_args", []) or [])
        self.tap_workdir = kwargs.get("tap_workdir", "")
        # Interacción "screen transition": índice de pantalla destino o
        # "next"/"prev".
        tap_screen = kwargs.get("tap_screen", 0)
        if isinstance(tap_screen, str) and tap_screen in ("next", "prev"):
            self.tap_screen = tap_screen
        else:
            self.tap_screen = int(tap_screen or 0)

        # Widget de navegación táctil (HDMI): barra anclada a un borde con items.
        self.nav_position = kwargs.get("nav_position", "bottom")  # bottom|top|left|right
        self.nav_items = list(kwargs.get("nav_items", []) or [])

    def to_dict(self):
        return {
            "type": self.type,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "radius": self.radius,
            "border_radius": self.border_radius,
            "glass_effect": self.glass_effect,
            "glass_blur": self.glass_blur,
            "glass_opacity": self.glass_opacity,
            "color": self.color,
            "color_opacity": self.color_opacity,
            "background_color": self.background_color,
            "background_color_opacity": self.background_color_opacity,
            "use_custom_text_color": self.use_custom_text_color,
            "text_color": self.text_color,
            "text_color_opacity": self.text_color_opacity,
            "text": self.text,
            "font_size": self.font_size,
            "font_family": self.font_family,
            "font_bold": self.font_bold,
            "font_italic": self.font_italic,
            "text_align": self.text_align,
            "clip": self.clip,
            "source": self.source,
            "value": self.value,
            "max_value": self.max_value,
            "line_width": self.line_width,
            "segments": self.segments,
            "gap": self.gap,
            "color_empty": self.color_empty,
            "target": self.target,
            "sources": self.sources,
            "image_path": self.image_path,
            "scale_proportionally": self.scale_proportionally,
            "aspect_ratio": self.aspect_ratio,
            "icon_name": self.icon_name,
            "tint": self.tint,
            "show_background": self.show_background,
            "show_label": self.show_label,
            "show_gradient": self.show_gradient,
            "line_thickness": self.line_thickness,
            "smooth": self.smooth,
            "rounded_corners": self.rounded_corners,
            "gradient_fill": self.gradient_fill,
            "gradient_stops": self.gradient_stops,
            "bar_text_mode": self.bar_text_mode,
            "bar_text_position": self.bar_text_position,
            "bar_border": self.bar_border,
            "bar_border_width": self.bar_border_width,
            "bar_border_color": self.bar_border_color,
            "bar_border_opacity": self.bar_border_opacity,
            "bar_border_position": self.bar_border_position,
            "auto_color_change": self.auto_color_change,
            "animate_gauge": self.animate_gauge,
            "animation_speed": self.animation_speed,
            "gauge_rounded_ends": self.gauge_rounded_ends,
            "arc_span": self.arc_span,
            "start_angle": self.start_angle,
            "show_ticks": self.show_ticks,
            "thresholds": self.thresholds,
            "orientation": self.orientation,
            "bar_mode": self.bar_mode,
            "show_sparklines": self.show_sparklines,
            "label_font_size": self.label_font_size,
            "label_font_family": self.label_font_family,
            "label_font_bold": self.label_font_bold,
            "label_font_italic": self.label_font_italic,
            "label_text_color": self.label_text_color,
            "gif_path": self.gif_path,
            "scale_mode": self.scale_mode,
            "video_path": self.video_path,
            "video_fit_mode": self.video_fit_mode,
            "time_format": self.time_format,
            "show_am_pm": self.show_am_pm,
            "show_seconds": self.show_seconds,
            "show_leading_zero": self.show_leading_zero,
            "group": self.group,
            "locked": self.locked,
            "visible": self.visible,
            "temp_hide_unit": self.temp_hide_unit,
            "tap_action": self.tap_action,
            "tap_command": self.tap_command,
            "tap_args": self.tap_args,
            "tap_workdir": self.tap_workdir,
            "tap_screen": self.tap_screen,
            "nav_position": self.nav_position,
            "nav_items": self.nav_items,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            element_type=data.get("type", "text"),
            **{k: v for k, v in data.items() if k != "type"}
        )
