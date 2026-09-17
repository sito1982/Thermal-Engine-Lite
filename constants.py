"""
Constants and configuration for Thermal Engine Studio.
"""

import os

# Carpeta de iconos empaquetados (elemento `icon`).
ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")


def resolve_icon_path(name):
    """Ruta segura de un icono dentro de ``icons/`` (o ``None``)."""
    if not name:
        return None
    candidate = os.path.normpath(os.path.join(ICONS_DIR, name))
    if not candidate.startswith(ICONS_DIR + os.sep):
        return None
    return candidate if os.path.exists(candidate) else None

# Display dimensions
DISPLAY_WIDTH = 1920
DISPLAY_HEIGHT = 480
PREVIEW_SCALE = 0.5

# Rotation applied when "vertical_mode" is enabled (physical panel mounted vertically).
# The design canvas stays at DISPLAY_WIDTH x DISPLAY_HEIGHT; the rotation is applied
# only to the final rendered preview / JPEG frame sent to the LCD.
VERTICAL_MODE_ROTATION = 90

# HID Device settings
VENDOR_ID = 0x35CC
PRODUCT_ID = 0x0104

# Fuente por defecto de los elementos (empaquetada en assets/fonts para que Lite
# no dependa de las fuentes del sistema).
DEFAULT_FONT_FAMILY = "Liberation Mono"
DMD_DEFAULT_FONT_FAMILY = "Tiny5"

# Familias "portables": las empaquetadas en assets/fonts/ttf. Studio ofrece solo
# estas en LCD/HDMI/custom para garantizar que Lite las renderiza igual.
PORTABLE_FONT_FAMILIES = [
    "Liberation Mono",
    "Liberation Sans",
    "Matrix Sans Print",
    "Matrix Sans Screen",
    "Matrix Sans",
    "Matrix Sans Raster",
    "Matrix Sans Video",
    "Pixel Operator",
    "Tiny5",
    "Silkscreen",
    "Press Start 2P",
    "Micro 5",
    "VT323",
]

# Elementos de alta resolución para canvas normal (LCD/HDMI). No se usan en DMD:
# son el bloque de construcción de los widgets de resumen (CPU, GPU, RAM...).
LCD_WIDGET_TYPES = [
    "ring_gauge",
    "segment_bar",
    "zone_bar",
    "stat_tile",
    "sparkline",
    "level_bar",
    "column_chart",
    "disk_element",
]

# Elementos disponibles solo en el target HDMI táctil.
HDMI_ONLY_TYPES = ("touch_nav",)

# Base element types available in the editor
_BASE_ELEMENT_TYPES = [
    "circle_gauge",
    "bar_gauge",
    "text",
    "rectangle",
    "clock",
    "image",
    "video",
    "icon",
    *LCD_WIDGET_TYPES,
    *HDMI_ONLY_TYPES,
]

# This will be populated with custom elements after they are loaded
ELEMENT_TYPES = _BASE_ELEMENT_TYPES.copy()

# --- DMD (Dot Matrix Display) ---
# Tipos de elemento disponibles en una pantalla DMD 128×32.
# circle_gauge se incluye (ver cómo queda), los demás ilegibles se descartan.
DMD_WIDGET_TYPES = [
    "dmd_bar", "dmd_value_bar", "dmd_blocks", "dmd_zones", "dmd_big_number",
    "dmd_giant_number", "dmd_sparkline", "dmd_histogram", "dmd_strip",
    "dmd_arc", "dmd_ring", "dmd_fan", "dmd_panel",
]
DMD_ELEMENT_TYPES = ["text", "bar_gauge", "rectangle", "image", "circle_gauge",
                     "line_chart", "gauge_circle_dmd", "segmented_bar", "bar_chart",
                     *DMD_WIDGET_TYPES]
DMD_SIZES = [(128, 32), (128, 64), (192, 64), (256, 64), (320, 132)]
DMD_DEFAULT_PORT = 8889

# Transiciones entre pantallas DMD (id, etiqueta para la UI).
DMD_TRANSITIONS = [
    ("cut", "Cut"),
    ("fade", "Fade"),
    ("slide_left", "Slide Left"),
    ("slide_right", "Slide Right"),
    ("slide_up", "Slide Up"),
    ("slide_down", "Slide Down"),
    ("wipe", "Wipe"),
    ("dissolve", "Dissolve"),
]
DMD_DEFAULT_TRANSITION = "fade"
DMD_DEFAULT_TRANSITION_MS = 250
DMD_DEFAULT_DURATION_S = 5.0


def register_custom_element_types(custom_types):
    """Register custom element types from the elements folder."""
    global ELEMENT_TYPES
    ELEMENT_TYPES = _BASE_ELEMENT_TYPES + list(custom_types)

# Categorized data sources for UI display
# Format: (source_id, display_name, unit, unit_symbol)
DATA_SOURCES_CATEGORIZED = {
    "Static": [
        ("static", "Static Value", "percent", "%"),
    ],
    "CPU": [
        ("cpu_percent", "CPU Utilization", "percent", "%"),
        ("cpu_temp", "CPU Temperature", "temp", "°C"),
        ("cpu_clock", "CPU Clock Speed", "clock", "MHz"),
        ("cpu_power", "CPU Power", "power", "W"),
    ],
    "GPU": [
        ("gpu_percent", "GPU Utilization", "percent", "%"),
        ("gpu_temp", "GPU Temperature", "temp", "°C"),
        ("gpu_clock", "GPU Clock Speed", "clock", "MHz"),
        ("gpu_memory_percent", "GPU Memory", "percent", "%"),
        ("gpu_memory_clock", "GPU Memory Clock", "clock", "MHz"),
        ("gpu_power", "GPU Power", "power", "W"),
    ],
    "Memory": [
        ("ram_percent", "RAM Usage", "percent", "%"),
        ("ram_used", "RAM Used", "size", "GB"),
        ("ram_available", "RAM Available", "size", "GB"),
    ],
    "Network": [
        ("net_upload", "Upload Speed", "speed", "MB/s"),
        ("net_download", "Download Speed", "speed", "MB/s"),
    ],
    "Fans": [
        ("cpu_fan", "CPU Fan", "clock", "RPM"),
        ("gpu_fan", "GPU Fan", "clock", "RPM"),
        ("gpu_fan_percent", "GPU Fan", "percent", "%"),
        ("sys_fan", "System Fan", "clock", "RPM"),
        ("pump", "Pump", "clock", "RPM"),
    ],
    "Performance": [
        ("game_fps", "Game FPS", "clock", "FPS"),
    ],
    "Storage": [
        ("disk_read", "Disk Read", "speed", "MB/s"),
        ("disk_write", "Disk Write", "speed", "MB/s"),
    ],
    "System": [
        ("uptime", "Uptime", "size", "h"),
        ("gpu_memory_used", "GPU Memory Used", "size", "GB"),
        ("nvme_temp", "NVMe Temperature", "temp", "°C"),
        ("mainboard_temp", "Mainboard Temperature", "temp", "°C"),
    ],
}

# Lookup for source units
SOURCE_UNITS = {}
for category, sources in DATA_SOURCES_CATEGORIZED.items():
    for source_info in sources:
        source_id, name, unit_type, unit_symbol = source_info
        SOURCE_UNITS[source_id] = {
            "name": name,
            "type": unit_type,
            "symbol": unit_symbol
        }

# Per-element-type field visibility, shared by the Qt properties panel so all
# UI surfaces agree on which controls apply to which element type.
ELEMENT_FIELD_VISIBILITY = {
    "circle_gauge": {
        "width": False, "height": False, "radius": True,
        "color": True, "bg_color": True, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": True, "label_text_group": True,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "line_width": True,
        "auto_color_change": True, "animate_gauge": True, "gauge_rounded_ends": True
    },
    "text": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": False, "text": True,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": True, "label_text_group": False,
        "align": True, "clip": True, "source": True, "value": True, "image": False
    },
    "clock": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": False, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": True, "label_text_group": False,
        "align": True, "clip": True, "source": False, "value": False, "image": False,
        "time_format": True, "show_am_pm": True, "show_seconds": True, "show_leading_zero": True
    },
    "rectangle": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": False, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "align": False, "clip": False, "source": False, "value": False, "image": False,
        "border_radius": True, "glass_effect": True
    },
    "image": {
        "width": True, "height": True, "radius": False,
        "color": False, "bg_color": False, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "align": False, "clip": False, "source": False, "value": False, "image": True
    },
    "video": {
        "width": True, "height": True, "radius": False,
        "color": False, "bg_color": False, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "align": False, "clip": False, "source": False, "value": False, "image": False,
        "video": True, "video_fit": True
    },
    "gif": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": False, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "align": False, "clip": False, "source": False, "value": False, "image": False,
        "gif": True, "scale_mode": True
    },
    "bar_gauge": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": True, "label_text_group": True,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "show_background": False, "show_label": False, "show_gradient": False,
        "rounded_corners": True,
        "auto_color_change": True, "animate_gauge": True,
        "bar_text_mode": True, "bar_text_position": True,
        "bar_border": True
    },
    "gauge_circle_dmd": {
        "width": False, "height": False, "radius": True,
        "color": True, "bg_color": True, "text": True,
        "font": True, "font_size": True, "font_style": True,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "segments": True, "line_width": True
    },
    "segmented_bar": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "segments": True, "gap": True, "color_empty": True
    },
    "bar_chart": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": False,
        "font": False, "font_size": False, "font_style": False,
        "value_text_group": False, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "show_background": True, "segments": True, "gap": True
    },
    "line_chart": {
        "width": True, "height": True, "radius": False,
        "color": True, "bg_color": True, "text": True,
        "font": True, "font_size": True, "font_style": True,
        "value_text_group": True, "label_text_group": False,
        "align": False, "clip": False, "source": True, "value": True, "image": False,
        "show_background": True, "show_label": True, "show_gradient": True,
        "line_thickness": True, "smooth": True
    }
}

# Los 13 widgets DMD comparten el mismo conjunto de campos visibles.
DMD_WIDGET_VISIBILITY = {
    "width": True, "height": True, "radius": False,
    "color": True, "bg_color": True, "text": True,
    "font": False, "font_size": False, "font_style": False,
    "value_text_group": False, "label_text_group": False,
    "align": False, "clip": False, "source": True, "value": True, "image": False,
    "segments": True, "gap": True, "color_empty": True, "line_width": True,
    "max_value": True, "target": True, "sources": True,
}
for _widget_type in DMD_WIDGET_TYPES:
    ELEMENT_FIELD_VISIBILITY[_widget_type] = dict(DMD_WIDGET_VISIBILITY)

# Default element properties by type
DEFAULT_ELEMENT_PROPS = {
    "circle_gauge": {"radius": 120, "x": 200, "y": 240, "text": "GAUGE", "line_width": 15},
    "bar_gauge": {"width": 300, "height": 30, "x": 100, "y": 100, "text": "BAR"},
    "text": {"x": 100, "y": 100, "text": "Text Label", "font_size": 36, "width": 200, "height": 50},
    "rectangle": {"width": 200, "height": 100, "x": 100, "y": 100, "border_radius": 0, "glass_effect": False, "glass_blur": 10, "glass_opacity": 50},
    "clock": {"x": 100, "y": 100, "font_size": 48, "width": 200, "height": 60},
    "image": {"width": 200, "height": 200, "x": 100, "y": 100},
    "video": {"width": 1920, "height": 480, "x": 0, "y": 0,
              "video_path": "", "video_fit_mode": "fit_height"}
}

# Valores por defecto para elementos en modo DMD (128×32 nativo).
# Todos los tamaños y posiciones están acordes a la resolución real.
DMD_DEFAULT_ELEMENT_PROPS = {
    "text": {"x": 2, "y": 2, "text": "TXT", "font_size": 8,
             "width": 60, "height": 12},
    "bar_gauge": {"x": 2, "y": 18, "text": "BAR",
                  "width": 124, "height": 8},
    "rectangle": {"x": 64, "y": 2, "width": 62, "height": 14,
                  "border_radius": 0, "glass_effect": False,
                  "glass_blur": 0, "glass_opacity": 50},
    "image": {"x": 0, "y": 0, "width": 128, "height": 32},
    "circle_gauge": {"x": 64, "y": 16, "radius": 14, "text": "G", "max_value": 100,
                  "color": "#00ff96", "background_color": "#1a1a2e", "line_width": 2,
                  "font_size": 5, "value": 50, "source": "cpu_percent"},
    "line_chart": {"x": 2, "y": 2, "width": 124, "height": 28,
                   "text": "CPU", "font_size": 5,
                   "show_background": True, "show_label": False, "show_gradient": False,
                   "line_thickness": 1, "smooth": False, "max_value": 100,
                   "source": "cpu_percent", "value": 50},
    "gauge_circle_dmd": {"x": 64, "y": 16, "radius": 12, "text": "CPU",
                        "max_value": 100, "color": "#00ff96",
                        "background_color": "#0d3b26", "line_width": 2,
                        "segments": 24, "font_size": 7, "font_family": "Matrix Sans",
                        "value": 50, "source": "cpu_percent"},
    "segmented_bar": {"x": 2, "y": 13, "width": 124, "height": 6,
                      "segments": 10, "gap": 1, "max_value": 100,
                      "color": "#00d0ff", "color_empty": "#12303a",
                      "value": 50, "source": "cpu_percent"},
    "bar_chart": {"x": 2, "y": 2, "width": 124, "height": 28,
                  "color": "#00ff96", "background_color": "#08090b",
                  "show_background": True, "gap": 1,
                  "segments": 0, "max_value": 100,
                  "value": 50, "source": "cpu_percent"},
}

# Widgets HWMON·32 (128×32). Cada uno es un elemento DMD-only a pantalla
# completa que se escala al tamaño del lienzo.
_DMD_WIDGET_DEFAULTS = {
    "dmd_bar": {"text": "CPU", "source": "cpu_percent", "value": 68},
    "dmd_value_bar": {"text": "GPU", "source": "gpu_percent", "value": 74},
    "dmd_blocks": {"text": "TEMP", "source": "cpu_temp", "value": 72},
    "dmd_zones": {"text": "TEMP", "source": "cpu_temp", "value": 72},
    "dmd_big_number": {"text": "CPU", "source": "cpu_percent", "value": 68},
    "dmd_giant_number": {"text": "FPS", "source": "game_fps", "value": 60,
                         "max_value": 240},
    "dmd_sparkline": {"text": "CPU", "source": "cpu_percent", "value": 55},
    "dmd_histogram": {"text": "FPS", "source": "game_fps", "value": 60,
                      "max_value": 120, "target": 60},
    "dmd_strip": {"text": "PWR", "source": "cpu_power", "value": 45,
                  "max_value": 150},
    "dmd_arc": {"text": "GPU", "source": "gpu_percent", "value": 62},
    "dmd_ring": {"text": "RAM", "source": "ram_percent", "value": 48},
    "dmd_fan": {"text": "FAN", "source": "cpu_fan", "value": 1800,
                "max_value": 3000},
    "dmd_panel": {
        "text": "PANEL", "source": "cpu_percent", "value": 0,
        "sources": ["cpu_percent", "cpu_temp", "gpu_percent", "gpu_temp",
                    "game_fps", "cpu_fan"],
    },
}
for _widget_type, _widget_props in _DMD_WIDGET_DEFAULTS.items():
    DMD_DEFAULT_ELEMENT_PROPS[_widget_type] = {
        "x": 0, "y": 0, "width": 128, "height": 32,
        "color": "#00ff96", "color_empty": "#12303a", "background_color": "#08090b",
        "max_value": 100, "segments": 8, "gap": 1, "line_width": 2,
        "target": 0,
        **_widget_props,
    }
