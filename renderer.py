"""
ThemeRenderer - nucleo de renderizado de temas (sin UI).

Extraido de Thermal-Engine-Studio (main_window.py). Renderiza los elementos de
la pestana LCD con Pillow y produce la imagen/JPEG que alimenta al target Web y
al driver LCD. Para cargar las fuentes bitmap DMD usa QFontDatabase (Qt), por lo
que requiere una QGuiApplication inicializada (aunque sea en modo offscreen).

No contiene ninguna dependencia del editor: el estado (elementos, fondo,
modo vertical, correccion de color) se expone como atributos publicos.
"""

import io
import math
import os
import sys
import threading
import time

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFont

from canvas import add_bar_chart_value, get_bar_chart_history, interpolate_gradient_color
from constants import (
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    DMD_WIDGET_TYPES,
    LCD_WIDGET_TYPES,
    SOURCE_UNITS,
    resolve_icon_path,
)
from element import ThemeElement
from elements import get_custom_element
from security import is_safe_path

# Nombres de las fuentes bitmap DMD que se registran en Qt (antes en
# properties.py, que es exclusivo del editor).
DMD_FONT_NAMES = ["Matrix Sans Print", "Matrix Sans Screen", "Matrix Sans",
                  "Pixel Operator", "Tiny5", "Silkscreen", "Press Start 2P",
                  "Micro 5", "VT323"]

# Cache global de fuentes PIL (compartida entre instancias).
_pil_font_cache = {}
_pil_font_cache_lock = threading.Lock()

# Cache de gradientes (rendimiento).
_gradient_cache = {}
_gradient_cache_max_size = 20


def get_value_with_unit(value, source, temp_hide_unit=False):
    """Format a value with its appropriate unit symbol."""
    unit_info = SOURCE_UNITS.get(source, {"symbol": "%", "type": "percent"})
    symbol = unit_info["symbol"]
    unit_type = unit_info["type"]

    if unit_type == "clock":
        return f"{value:.0f}{symbol}"
    elif unit_type == "temp":
        # Option to show only degrees instead of degrees C
        if temp_hide_unit:
            return f"{value:.0f}\u00b0"
        return f"{value:.0f}{symbol}"
    elif unit_type == "power":
        return f"{value:.0f}{symbol}"
    elif unit_type in ("size", "energy", "speed"):
        return f"{value:.1f}{symbol}"
    elif unit_type == "digital":
        return f"{value:.0f}{symbol}"
    else:  # percent
        return f"{value:.0f}{symbol}"


def hex_to_rgba(hex_color, opacity=100):
    """Convert hex color and opacity (0-100) to RGBA tuple."""
    if hex_color.startswith('#'):
        hex_color = hex_color[1:]
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    a = int(255 * opacity / 100)
    return (r, g, b, a)


_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "assets", "fonts", "ttf")


def _bundled_font_files():
    """Todos los TTF empaquetados en ``assets/fonts/ttf``."""
    try:
        return sorted(os.path.join(_FONT_DIR, name)
                      for name in os.listdir(_FONT_DIR)
                      if name.lower().endswith(".ttf"))
    except OSError:
        return []


def _dmd_font_paths():
    return _bundled_font_files()


# Familias empaquetadas: familia (minusculas) -> (regular, bold, italic, bi).
_BUNDLED_FAMILIES = {
    "liberation mono": ("LiberationMono-Regular.ttf", "LiberationMono-Bold.ttf",
                        "LiberationMono-Italic.ttf", "LiberationMono-BoldItalic.ttf"),
    "liberation sans": ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf",
                        "LiberationSans-Italic.ttf", "LiberationSans-BoldItalic.ttf"),
    "matrix sans print": ("MatrixSansPrint-Regular.ttf", None, None, None),
    "matrix sans screen": ("MatrixSansScreen-Regular.ttf", None, None, None),
    "matrix sans": ("MatrixSans-Regular.ttf", None, None, None),
    "matrix sans raster": ("MatrixSansRaster-Regular.ttf", None, None, None),
    "matrix sans video": ("MatrixSansVideo-Regular.ttf", None, None, None),
    "pixel operator": ("PixelOperator.ttf", None, None, None),
    "tiny5": ("Tiny5-Regular.ttf", None, None, None),
    "silkscreen": ("Silkscreen-Regular.ttf", None, None, None),
    "press start 2p": ("PressStart2P-Regular.ttf", None, None, None),
    "micro 5": ("Micro5-Regular.ttf", None, None, None),
    "vt323": ("VT323-Regular.ttf", None, None, None),
}

# Alias de familias comunes -> familia empaquetada equivalente.
_FAMILY_ALIASES = {
    "arial": "liberation sans",
    "helvetica": "liberation sans",
    "segoeui": "liberation sans",
    "tahoma": "liberation sans",
    "verdana": "liberation sans",
    "calibri": "liberation sans",
    "freesans": "liberation sans",
    "couriernew": "liberation mono",
    "consolas": "liberation mono",
    "monospace": "liberation mono",
    "notosansmono": "liberation mono",
    "dejavusansmono": "liberation mono",
}


def _resolve_bundled_font(font_family, bold=False, italic=False):
    """Ruta TTF empaquetada para una familia (o ``None``)."""
    name = (font_family or "").strip().lower()
    if not name:
        return None
    key = name
    if key not in _BUNDLED_FAMILIES:
        collapsed = {k.replace(" ", ""): k for k in _BUNDLED_FAMILIES}
        key = collapsed.get(name.replace(" ", ""))
    if key is None:
        key = _FAMILY_ALIASES.get(name.replace(" ", "")) or _FAMILY_ALIASES.get(name)
    if key is None:
        return None
    variants = _BUNDLED_FAMILIES.get(key)
    if not variants:
        return None
    regular, bold_f, italic_f, bold_italic_f = variants
    if bold and italic:
        chosen = bold_italic_f or bold_f or italic_f or regular
    elif bold:
        chosen = bold_f or regular
    elif italic:
        chosen = italic_f or regular
    else:
        chosen = regular
    path = os.path.join(_FONT_DIR, chosen)
    return path if os.path.exists(path) else None


class ThemeRenderer:
    """Dibuja los elementos de un tema LCD a una imagen PIL."""

    DMD_FONT_PATHS = _dmd_font_paths()

    _font_cache = None

    def __init__(self, vertical_mode=False, brightness=1.0, contrast=1.0,
                 saturation=1.0):
        self.lcd_elements = []
        self.lcd_background_color = "#0f0f19"
        self._vertical_mode = bool(vertical_mode)
        self._lcd_brightness = float(brightness)
        self._lcd_contrast = float(contrast)
        self._lcd_saturation = float(saturation)
        # Submuestreo JPEG del perfil de entrega del device LCD conectado.
        self._delivery_subsampling = 0
        # Dimensiones logicas del panel LCD (por defecto, el Trofeo 1920x480).
        self._lcd_display_width = DISPLAY_WIDTH
        self._lcd_display_height = DISPLAY_HEIGHT

    # Alias del helper de canvas (antes se invocaba como self.interpolate...).
    interpolate_gradient_color = staticmethod(interpolate_gradient_color)

    def _load_dmd_fonts(self):
        from PySide6.QtGui import QFontDatabase
        loaded = []
        for path in self.DMD_FONT_PATHS:
            if not os.path.exists(path):
                print(f"[DMD] Fuente no encontrada: {path}")
                continue
            fid = QFontDatabase.addApplicationFont(path)
            if fid >= 0:
                families = QFontDatabase.applicationFontFamilies(fid)
                loaded.extend(families)
            else:
                print(f"[DMD] Error al cargar fuente: {path}")
        if loaded:
            missing = [n for n in DMD_FONT_NAMES if n not in loaded]
            if missing:
                print(f"[DMD] Fuentes no registradas: {missing}")
        else:
            print("[DMD] Ninguna fuente DMD cargada")

    _font_cache = None

    def _get_font_dirs(self):
        """Get platform-specific font directories."""
        if sys.platform == "win32":
            return [os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')]
        elif sys.platform == "darwin":
            return [
                '/System/Library/Fonts',
                '/Library/Fonts',
                os.path.expanduser('~/Library/Fonts'),
            ]
        else:  # Linux
            return [
                _FONT_DIR,                     # fuentes empaquetadas (Lite)
                '/usr/share/fonts',            # Fedora/Bazzite: fuentes en subcarpetas
                '/usr/share/fonts/truetype',   # Debian/Ubuntu
                '/usr/share/fonts/TTF',        # Arch
                '/usr/local/share/fonts',
                os.path.expanduser('~/.fonts'),
                os.path.expanduser('~/.local/share/fonts'),
            ]

    def _build_font_cache(self):
        """Build a cache of font family names to file paths."""
        if self._font_cache is not None:
            return self._font_cache

        self._font_cache = {}

        # Windows: use registry for accurate font names
        if sys.platform == "win32":
            font_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
            try:
                import winreg
                reg_paths = [
                    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                    (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                ]

                for hkey, subkey in reg_paths:
                    try:
                        with winreg.OpenKey(hkey, subkey) as key:
                            i = 0
                            while True:
                                try:
                                    name, value, _ = winreg.EnumValue(key, i)
                                    font_name = name.replace(" (TrueType)", "").replace(" (OpenType)", "")

                                    if not os.path.isabs(value):
                                        value = os.path.join(font_dir, value)

                                    if os.path.exists(value):
                                        self._font_cache[font_name.lower()] = value

                                    i += 1
                                except OSError:
                                    break
                    except OSError:
                        pass
            except ImportError:
                pass
        else:
            # Non-Windows: scan font directories
            for font_dir in self._get_font_dirs():
                if not os.path.exists(font_dir):
                    continue
                try:
                    for root, dirs, files in os.walk(font_dir):
                        for filename in files:
                            if filename.lower().endswith(('.ttf', '.otf', '.ttc')):
                                font_path = os.path.join(root, filename)
                                # Use filename without extension as font name
                                font_name = os.path.splitext(filename)[0].lower()
                                self._font_cache[font_name] = font_path
                except Exception:
                    pass

        return self._font_cache

    def _get_default_font_path(self):
        """Get a default fallback font path for the current platform."""
        # Preferir las fuentes empaquetadas (portables).
        for name in ("LiberationMono-Regular.ttf", "LiberationSans-Regular.ttf"):
            candidate = os.path.join(_FONT_DIR, name)
            if os.path.exists(candidate):
                return candidate
        if sys.platform == "win32":
            font_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
            for name in ['arial.ttf', 'segoeui.ttf', 'tahoma.ttf']:
                path = os.path.join(font_dir, name)
                if os.path.exists(path):
                    return path
        elif sys.platform == "darwin":
            for path in ['/System/Library/Fonts/Helvetica.ttc', '/Library/Fonts/Arial.ttf']:
                if os.path.exists(path):
                    return path
        else:  # Linux
            for path in [
                # Fedora / Bazzite
                '/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf',
                '/usr/share/fonts/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf',
                '/usr/share/fonts/google-noto/NotoSans-Regular.ttf',
                '/usr/share/fonts/abattis-cantarell-fonts/Cantarell-Regular.otf',
                # Debian / Ubuntu / Arch
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
                '/usr/share/fonts/TTF/DejaVuSans.ttf',
                '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            ]:
                if os.path.exists(path):
                    return path
        return None

    def get_font_path(self, font_family, bold=False, italic=False):
        # 1) Fuentes empaquetadas (portables): mapa familia -> TTF.
        bundled = _resolve_bundled_font(font_family, bold, italic)
        if bundled:
            return bundled
        # 2) Fuentes del sistema (con alias).
        font_dirs = self._get_font_dirs()
        font_cache = self._build_font_cache()
        font_family = _FAMILY_ALIASES.get(
            (font_family or "").strip().lower().replace(" ", ""), font_family)

        if bold and italic:
            variants = [
                f"{font_family} Bold Italic",
                f"{font_family} Bold Oblique",
                f"{font_family}",
            ]
        elif bold:
            variants = [
                f"{font_family} Bold",
                f"{font_family}",
            ]
        elif italic:
            variants = [
                f"{font_family} Italic",
                f"{font_family} Oblique",
                f"{font_family}",
            ]
        else:
            variants = [
                f"{font_family}",
                f"{font_family} Regular",
            ]

        for variant in variants:
            if variant.lower() in font_cache:
                return font_cache[variant.lower()]

        font_name_lower = font_family.lower()
        for cached_name, cached_path in font_cache.items():
            if font_name_lower in cached_name or cached_name.startswith(font_name_lower):
                return cached_path

        # Try to find font by filename in font directories
        try:
            font_name_clean = font_family.lower().replace(' ', '')
            for font_dir in font_dirs:
                if not os.path.exists(font_dir):
                    continue
                for filename in os.listdir(font_dir):
                    if filename.lower().endswith(('.ttf', '.otf', '.ttc')):
                        if font_name_clean in filename.lower().replace(' ', ''):
                            return os.path.join(font_dir, filename)
        except Exception:
            pass

        # Return platform-appropriate default font
        default_font = self._get_default_font_path()
        if default_font:
            return default_font

        # Last resort fallback
        if sys.platform == "win32":
            return os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'arial.ttf')
        return None

    def get_pil_font(self, element, size_override=None):
        """Get a PIL font with caching for performance."""
        size = size_override or element.font_size
        return self.get_pil_font_custom(element.font_family, element.font_bold, element.font_italic, size)

    def get_pil_font_custom(self, font_family, font_bold, font_italic, font_size):
        """Get a PIL font with explicit parameters and caching."""
        cache_key = (font_family, font_bold, font_italic, font_size)

        with _pil_font_cache_lock:
            if cache_key in _pil_font_cache:
                return _pil_font_cache[cache_key]

        try:
            font_path = self.get_font_path(font_family, font_bold, font_italic)
            if font_path and os.path.exists(font_path):
                font = ImageFont.truetype(font_path, font_size)
            else:
                font = ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        with _pil_font_cache_lock:
            # Limit cache size to prevent memory bloat (hard limit of 50)
            while len(_pil_font_cache) >= 50:
                # Remove oldest entry (FIFO)
                oldest_key = next(iter(_pil_font_cache))
                del _pil_font_cache[oldest_key]
            _pil_font_cache[cache_key] = font

        return font

    def _compute_frame_signature(self, sensor_data):
        """Build a lightweight signature representing everything that affects the
        rendered frame's pixels. If the signature is unchanged since the last frame,
        we can skip re-rendering and re-encoding the JPEG entirely, which is the main
        source of avoidable CPU usage when sensor values are not actively changing."""
        parts = [self._vertical_mode,
                 self._lcd_brightness, self._lcd_contrast, self._lcd_saturation]
        has_video = False
        for element in self.lcd_elements:
            value = element.value
            # Round floats to 1 decimal so tiny sensor jitter doesn't force re-renders
            if isinstance(value, float):
                value = round(value, 1)
            parts.append((element.source, value, getattr(element, "x", None),
                          getattr(element, "y", None), getattr(element, "visible", True)))
            if element.type == "video":
                has_video = True
        # A video element changes every frame by nature, so never cache while present
        if has_video:
            parts.append(time.perf_counter())
        return tuple(parts)

    def render_theme_image(self):
        # When vertical mode is enabled, the design is laid out on a logical
        # portrait canvas (DISPLAY_HEIGHT x DISPLAY_WIDTH, e.g. 480x1920) matching
        # how the physically-rotated panel will be viewed. This canvas is rotated
        # back to the panel's fixed physical buffer size in image_to_jpeg().
        disp_w = getattr(self, "_lcd_display_width", DISPLAY_WIDTH)
        disp_h = getattr(self, "_lcd_display_height", DISPLAY_HEIGHT)
        if getattr(self, "_vertical_mode", False):
            canvas_w, canvas_h = disp_h, disp_w
        else:
            canvas_w, canvas_h = disp_w, disp_h

        img = Image.new('RGBA', (canvas_w, canvas_h), color=self.lcd_background_color)

        # Render in reverse order so elements at top of list appear in front
        for element in reversed(self.lcd_elements):
            self.render_element_with_opacity(img, element)

        # Convert back to RGB for output
        return img.convert('RGB')

    def render_element_with_opacity(self, img, element):
        """Render an element with opacity support using alpha compositing."""
        if not getattr(element, 'visible', True):
            return
        font = self.get_pil_font(element)
        font_small = self.get_pil_font(element, int(element.font_size * 0.6))

        # Get opacity values
        color_opacity = getattr(element, 'color_opacity', 100)
        bg_opacity = getattr(element, 'background_color_opacity', 100)

        if element.type == "circle_gauge":
            self.render_circle_gauge_rgba(img, element, font, font_small, color_opacity, bg_opacity)
        elif element.type == "bar_gauge":
            self.render_bar_gauge_rgba(img, element, font, color_opacity, bg_opacity)
        elif element.type == "text":
            self.render_text_rgba(img, element, font, color_opacity)
        elif element.type == "rectangle":
            self.render_rectangle_rgba(img, element, color_opacity)
        elif element.type == "clock":
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
            temp_element = ThemeElement(
                text=current_time, x=element.x, y=element.y,
                font_family=element.font_family, font_size=element.font_size,
                font_bold=element.font_bold, font_italic=element.font_italic,
                text_align=element.text_align, color=element.color,
                color_opacity=color_opacity,
                width=element.width, height=element.height, clip=element.clip
            )
            self.render_text_rgba(img, temp_element, font, color_opacity)
        elif element.type == "gauge_circle_dmd":
            self.render_gauge_circle_dmd_rgba(img, element, font, color_opacity, bg_opacity)
        elif element.type == "segmented_bar":
            self.render_segmented_bar_rgba(img, element, color_opacity, bg_opacity)
        elif element.type == "bar_chart":
            self.render_bar_chart_rgba(img, element, color_opacity, bg_opacity)
        elif element.type in LCD_WIDGET_TYPES:
            self.render_lcd_widget(img, element, color_opacity)
        elif element.type == "touch_nav":
            self.render_touch_nav_rgba(img, element, color_opacity)
        elif element.type in DMD_WIDGET_TYPES:
            self.render_dmd_widget(img, element, color_opacity)
        elif element.type == "video":
            self.render_video_rgba(img, element)
        elif element.type == "icon":
            self.render_icon_rgba(img, element, color_opacity)
        elif element.type == "image":
            if element.image_path:
                # Validate image path is safe
                safe, resolved_path, err = is_safe_path(element.image_path, allow_absolute=True)
                if not safe or not os.path.exists(element.image_path):
                    if not safe:
                        print(f"Unsafe image path blocked: {element.image_path} - {err}")
                    return
                try:
                    # Open image via context manager to ensure file descriptor is closed
                    with open(element.image_path, 'rb') as _f:
                        with Image.open(_f) as _im:
                            overlay = _im.convert('RGBA').copy()

                    if element.scale_proportionally:
                        overlay.thumbnail((element.width, element.height), Image.Resampling.LANCZOS)
                    else:
                        overlay = overlay.resize((element.width, element.height), Image.Resampling.LANCZOS)
                    # Apply opacity to image
                    if color_opacity < 100:
                        alpha = overlay.split()[3]
                        alpha = alpha.point(lambda x: int(x * color_opacity / 100))
                        overlay.putalpha(alpha)
                    img.paste(overlay, (element.x, element.y), overlay)
                except Exception as e:
                    print(f"Image load error: {e}")
        else:
            custom = get_custom_element(element.type)
            if custom and custom.get('render_image'):
                try:
                    draw = ImageDraw.Draw(img)
                    custom['render_image'](draw, img, element)
                except Exception as e:
                    print(f"Custom element render error: {e}")

    def render_rectangle_rgba(self, img, element, opacity):
        """Render a rectangle with opacity, optional border radius, and glass effect."""
        from PIL import ImageFilter

        border_radius = getattr(element, 'border_radius', 0)
        glass_effect = getattr(element, 'glass_effect', False)
        coords = [element.x, element.y, element.x + element.width, element.y + element.height]

        if glass_effect:
            # Frosted glass effect
            glass_blur = getattr(element, 'glass_blur', 10)
            glass_opacity = getattr(element, 'glass_opacity', 50)

            x, y, w, h = element.x, element.y, element.width, element.height

            # Extract region to blur
            region = img.crop((x, y, x + w, y + h))

            # Apply gaussian blur
            blurred = region.filter(ImageFilter.GaussianBlur(radius=glass_blur))

            # If border radius, we need to mask the blurred region
            if border_radius > 0:
                # Create a mask for rounded corners
                mask = Image.new('L', (w, h), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle([0, 0, w, h], radius=border_radius, fill=255)

                # Create a temp image and paste blurred with mask
                temp = img.crop((x, y, x + w, y + h))
                temp.paste(blurred, mask=mask)
                img.paste(temp, (x, y))
            else:
                img.paste(blurred, (x, y))

            # Draw tinted overlay
            overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            tint_rgba = hex_to_rgba(element.color, glass_opacity)

            if border_radius > 0:
                overlay_draw.rounded_rectangle(coords, radius=border_radius, fill=tint_rgba)
            else:
                overlay_draw.rectangle(coords, fill=tint_rgba)

            # Add subtle white border
            border_rgba = (255, 255, 255, 40)
            if border_radius > 0:
                overlay_draw.rounded_rectangle(coords, radius=border_radius, outline=border_rgba, width=1)
            else:
                overlay_draw.rectangle(coords, outline=border_rgba, width=1)

            img.alpha_composite(overlay)

        elif opacity >= 100:
            draw = ImageDraw.Draw(img)
            if border_radius > 0:
                draw.rounded_rectangle(coords, radius=border_radius, fill=element.color)
            else:
                draw.rectangle(coords, fill=element.color)
        else:
            # Create overlay with alpha
            overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            rgba = hex_to_rgba(element.color, opacity)
            if border_radius > 0:
                overlay_draw.rounded_rectangle(coords, radius=border_radius, fill=rgba)
            else:
                overlay_draw.rectangle(coords, fill=rgba)
            img.alpha_composite(overlay)

    def render_text_rgba(self, img, element, font, opacity):
        """Render text with opacity."""
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

        # Create a temporary draw to measure text
        temp_draw = ImageDraw.Draw(img)
        bbox = temp_draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        if element.text_align == "left":
            x = element.x
        elif element.text_align == "right":
            x = element.x + element.width - text_width
        else:
            x = element.x + (element.width - text_width) // 2

        y = element.y + (element.height - text_height) // 2

        if opacity >= 100 and not element.clip:
            temp_draw.text((x, y), text, fill=element.color, font=font)
        else:
            # Create overlay with alpha
            overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            rgba = hex_to_rgba(element.color, opacity)
            overlay_draw.text((x, y), text, fill=rgba, font=font)

            if element.clip:
                # Create mask for clipping
                mask = Image.new('L', img.size, 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rectangle([element.x, element.y, element.x + element.width, element.y + element.height], fill=255)
                # Apply mask to overlay
                overlay_alpha = overlay.split()[3]
                overlay_alpha = Image.composite(overlay_alpha, Image.new('L', img.size, 0), mask)
                overlay.putalpha(overlay_alpha)

            img.alpha_composite(overlay)

    def render_circle_gauge_rgba(self, img, element, font, font_small, color_opacity, bg_opacity):
        """Render circle gauge with opacity support."""
        x, y = element.x, element.y
        radius = element.radius
        # Use animated value if available (from canvas animation), otherwise use raw value
        value = getattr(element, '_animated_display_value', element.value)

        # Check for gradient fill
        use_gradient = getattr(element, 'gradient_fill', False)
        if use_gradient:
            # Interpolate color from gradient stops based on value
            gradient_stops = getattr(element, 'gradient_stops', [(0.0, "#00ff96"), (1.0, "#ff4444")])
            color = self.interpolate_gradient_color(gradient_stops, value / 100.0)
        else:
            # Determine color based on value thresholds (if enabled)
            auto_color = getattr(element, 'auto_color_change', True)
            if auto_color:
                if "temp" in element.source:
                    if value < 60:
                        color = element.color
                    elif value < 80:
                        color = "#ffcc00"
                    else:
                        color = "#ff3232"
                else:
                    if value < 70:
                        color = element.color
                    elif value < 90:
                        color = "#ffcc00"
                    else:
                        color = "#ff3232"
            else:
                color = element.color

        # Create overlay for drawing with transparency
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Check for rounded ends (pill shape)
        rounded_ends = getattr(element, 'gauge_rounded_ends', False)

        # Draw background arc on separate layer for proper opacity handling
        arc_width = max(1, int(getattr(element, 'line_width', 15)))  # Match canvas pen width
        arc_radius = radius - arc_width // 2
        bg_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg_layer)

        # Draw at full opacity
        bg_rgb = hex_to_rgba(element.background_color, 100)
        bg_draw.arc(
            [x - arc_radius, y - arc_radius, x + arc_radius, y + arc_radius],
            start=135, end=405,
            fill=bg_rgb, width=arc_width
        )

        # Draw rounded end caps for background arc
        if rounded_ends:
            cap_radius = arc_width // 2
            # Radial offset to push caps inward along the radius direction
            radial_offset = -(arc_width // 2)
            # Start cap at 135° (bottom-left)
            start_angle = 135
            start_x = x + (arc_radius + radial_offset) * math.cos(math.radians(start_angle))
            start_y = y + (arc_radius + radial_offset) * math.sin(math.radians(start_angle))
            bg_draw.ellipse(
                [start_x - cap_radius, start_y - cap_radius,
                 start_x + cap_radius, start_y + cap_radius],
                fill=bg_rgb
            )
            # End cap at 45° (bottom-right)
            end_angle_bg = 45
            end_x = x + (arc_radius + radial_offset) * math.cos(math.radians(end_angle_bg))
            end_y = y + (arc_radius + radial_offset) * math.sin(math.radians(end_angle_bg))
            bg_draw.ellipse(
                [end_x - cap_radius, end_y - cap_radius,
                 end_x + cap_radius, end_y + cap_radius],
                fill=bg_rgb
            )

        # Apply bg_opacity to the background layer by scaling the alpha channel
        if bg_opacity < 100:
            r, g, b, a = bg_layer.split()
            a = a.point(lambda x: int(x * bg_opacity / 100))
            bg_layer = Image.merge('RGBA', (r, g, b, a))

        # Composite background layer onto the main overlay
        overlay.alpha_composite(bg_layer)

        # Draw value arc - use float for smoother animation
        sweep = 270 * min(value, 100) / 100
        end_angle = 135 + sweep

        if sweep > 0:
            # Create separate layer for value arc to properly handle opacity
            value_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
            value_draw = ImageDraw.Draw(value_layer)

            if use_gradient:
                # Draw gradient arc using multiple small segments
                gradient_stops = getattr(element, 'gradient_stops', [(0.0, "#00ff96"), (1.0, "#ff4444")])
                # Draw in 2-degree increments for smooth gradient
                step = 2
                for i in range(0, int(sweep), step):
                    segment_start = 135 + i
                    segment_end = min(135 + i + step, end_angle)
                    # Calculate gradient position (0 to 1) based on arc position
                    t = i / 270.0  # Position along full arc range
                    grad_color = self.interpolate_gradient_color(gradient_stops, t)
                    # Draw at full opacity, we'll apply color_opacity to the layer
                    segment_rgb = hex_to_rgba(grad_color, 100)
                    value_draw.arc(
                        [x - arc_radius, y - arc_radius, x + arc_radius, y + arc_radius],
                        start=segment_start, end=segment_end,
                        fill=segment_rgb, width=arc_width
                    )
                # Draw rounded end caps for gradient arc
                if rounded_ends:
                    cap_radius = arc_width // 2
                    radial_offset = -(arc_width // 2)
                    # Start cap (use start color)
                    start_color = self.interpolate_gradient_color(gradient_stops, 0)
                    start_rgb = hex_to_rgba(start_color, 100)
                    start_x = x + (arc_radius + radial_offset) * math.cos(math.radians(135))
                    start_y = y + (arc_radius + radial_offset) * math.sin(math.radians(135))
                    value_draw.ellipse(
                        [start_x - cap_radius, start_y - cap_radius,
                         start_x + cap_radius, start_y + cap_radius],
                        fill=start_rgb
                    )
                    # End cap (use color at current position)
                    end_t = sweep / 270.0
                    end_color = self.interpolate_gradient_color(gradient_stops, end_t)
                    end_rgb = hex_to_rgba(end_color, 100)
                    end_x = x + (arc_radius + radial_offset) * math.cos(math.radians(end_angle))
                    end_y = y + (arc_radius + radial_offset) * math.sin(math.radians(end_angle))
                    value_draw.ellipse(
                        [end_x - cap_radius, end_y - cap_radius,
                         end_x + cap_radius, end_y + cap_radius],
                        fill=end_rgb
                    )
            else:
                # Draw at full opacity
                color_rgb = hex_to_rgba(color, 100)
                value_draw.arc(
                    [x - arc_radius, y - arc_radius, x + arc_radius, y + arc_radius],
                    start=135, end=end_angle,
                    fill=color_rgb, width=arc_width
                )
                # Draw rounded end caps for solid color arc
                if rounded_ends:
                    cap_radius = arc_width // 2
                    radial_offset = -(arc_width // 2)
                    # Start cap
                    start_x = x + (arc_radius + radial_offset) * math.cos(math.radians(135))
                    start_y = y + (arc_radius + radial_offset) * math.sin(math.radians(135))
                    value_draw.ellipse(
                        [start_x - cap_radius, start_y - cap_radius,
                         start_x + cap_radius, start_y + cap_radius],
                        fill=color_rgb
                    )
                    # End cap
                    end_x = x + (arc_radius + radial_offset) * math.cos(math.radians(end_angle))
                    end_y = y + (arc_radius + radial_offset) * math.sin(math.radians(end_angle))
                    value_draw.ellipse(
                        [end_x - cap_radius, end_y - cap_radius,
                         end_x + cap_radius, end_y + cap_radius],
                        fill=color_rgb
                    )

            # Apply color_opacity to the value layer by scaling the alpha channel
            if color_opacity < 100:
                r, g, b, a = value_layer.split()
                a = a.point(lambda x: int(x * color_opacity / 100))
                value_layer = Image.merge('RGBA', (r, g, b, a))

            # Composite value layer onto the main overlay
            overlay.alpha_composite(value_layer)

        # Draw value text
        value_text = get_value_with_unit(value, element.source, getattr(element, 'temp_hide_unit', False))
        bbox = draw.textbbox((0, 0), value_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        # Get value text color
        value_text_color = getattr(element, 'text_color', element.color)
        value_text_opacity = getattr(element, 'text_color_opacity', 100)
        value_text_rgba = hex_to_rgba(value_text_color, value_text_opacity)
        draw.text(
            (x - text_width // 2, y - text_height // 2 - 10),
            value_text, fill=value_text_rgba, font=font
        )

        # Draw label text with separate label font settings and color
        label_font = self.get_pil_font_custom(
            getattr(element, 'label_font_family', element.font_family),
            getattr(element, 'label_font_bold', False),
            getattr(element, 'label_font_italic', False),
            getattr(element, 'label_font_size', 16)
        )
        label_text_color = getattr(element, 'label_text_color', element.color)
        label_rgba = hex_to_rgba(label_text_color, getattr(element, 'text_color_opacity', 100))
        bbox = draw.textbbox((0, 0), element.text, font=label_font)
        text_width = bbox[2] - bbox[0]
        draw.text(
            (x - text_width // 2, y + radius // 3),
            element.text, fill=label_rgba, font=label_font
        )

        # Composite onto main image
        img.alpha_composite(overlay)

    def render_bar_gauge_rgba(self, img, element, font, color_opacity, bg_opacity):
        """Render bar gauge with opacity support."""
        x, y = element.x, element.y
        # Use animated value if available (from canvas animation), otherwise use raw value
        value = getattr(element, '_animated_display_value', element.value)
        width, height = element.width, element.height

        # Check for gradient fill
        use_gradient = getattr(element, 'gradient_fill', False)

        if not use_gradient:
            # Determine color based on value (if auto color enabled)
            auto_color = getattr(element, 'auto_color_change', True)
            if auto_color:
                if value < 70:
                    color = element.color
                elif value < 90:
                    color = "#ffcc00"
                else:
                    color = "#ff3232"
            else:
                color = element.color

        rounded = getattr(element, 'rounded_corners', False)
        corner_radius = height // 2 if rounded else 0

        # Create overlay for final compositing
        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))

        # Draw background on separate layer for proper opacity handling
        bg_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
        bg_draw = ImageDraw.Draw(bg_layer)
        bg_rgb = hex_to_rgba(element.background_color, 100)  # Full opacity for drawing
        if rounded:
            bg_draw.rounded_rectangle(
                [x, y, x + width, y + height],
                radius=corner_radius,
                fill=bg_rgb
            )
        else:
            bg_draw.rectangle(
                [x, y, x + width, y + height],
                fill=bg_rgb
            )

        # Apply bg_opacity by scaling alpha channel
        if bg_opacity < 100:
            r, g, b, a = bg_layer.split()
            a = a.point(lambda px: int(px * bg_opacity / 100))
            bg_layer = Image.merge('RGBA', (r, g, b, a))

        # Composite background layer onto overlay
        overlay.alpha_composite(bg_layer)

        # Draw fill on separate layer
        fill_width = int(width * min(value, 100) / 100)
        if fill_width > 0:
            fill_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
            fill_draw = ImageDraw.Draw(fill_layer)

            if use_gradient:
                # Draw horizontal gradient using lines at full opacity
                gradient_stops = getattr(element, 'gradient_stops', [(0.0, "#00ff96"), (1.0, "#ff4444")])

                if rounded and fill_width > 0:
                    # Create gradient on temporary image, then mask with rounded rect
                    gradient_layer = Image.new('RGBA', (fill_width, height), (0, 0, 0, 0))
                    gradient_draw = ImageDraw.Draw(gradient_layer)

                    for i in range(fill_width):
                        t = i / (width - 1) if width > 1 else 0
                        grad_color = self.interpolate_gradient_color(gradient_stops, t)
                        r = int(grad_color[1:3], 16)
                        g = int(grad_color[3:5], 16)
                        b = int(grad_color[5:7], 16)
                        gradient_draw.line([(i, 0), (i, height - 1)], fill=(r, g, b, 255))

                    # Create rounded rectangle mask
                    mask = Image.new('L', (fill_width, height), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.rounded_rectangle([0, 0, fill_width, height], radius=corner_radius, fill=255)

                    # Apply mask to gradient
                    gradient_layer.putalpha(ImageChops.multiply(gradient_layer.split()[3], mask))

                    # Paste onto fill layer
                    fill_layer.paste(gradient_layer, (x, y), gradient_layer)
                else:
                    # No rounded corners, draw lines directly
                    for i in range(fill_width):
                        t = i / (width - 1) if width > 1 else 0
                        grad_color = self.interpolate_gradient_color(gradient_stops, t)
                        r = int(grad_color[1:3], 16)
                        g = int(grad_color[3:5], 16)
                        b = int(grad_color[5:7], 16)
                        fill_draw.line([(x + i, y), (x + i, y + height - 1)], fill=(r, g, b, 255))
            else:
                fill_rgb = hex_to_rgba(color, 100)  # Full opacity for drawing
                if rounded:
                    fill_draw.rounded_rectangle(
                        [x, y, x + fill_width, y + height],
                        radius=corner_radius,
                        fill=fill_rgb
                    )
                else:
                    fill_draw.rectangle(
                        [x, y, x + fill_width, y + height],
                        fill=fill_rgb
                    )

            # Apply color_opacity by scaling alpha channel
            if color_opacity < 100:
                r, g, b, a = fill_layer.split()
                a = a.point(lambda px: int(px * color_opacity / 100))
                fill_layer = Image.merge('RGBA', (r, g, b, a))

            # Composite fill layer onto overlay
            overlay.alpha_composite(fill_layer)

        # Draw border if enabled
        bar_border = getattr(element, 'bar_border', False)
        if bar_border:
            border_width = getattr(element, 'bar_border_width', 2)
            border_color = getattr(element, 'bar_border_color', '#ffffff')
            border_opacity = getattr(element, 'bar_border_opacity', 100)
            border_position = getattr(element, 'bar_border_position', 'center')

            # Create border layer for proper opacity handling
            border_layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
            border_draw = ImageDraw.Draw(border_layer)
            border_rgb = hex_to_rgba(border_color, 100)  # Full opacity for drawing

            half_border = border_width / 2

            # Calculate offset based on border position
            # PIL draws stroke INSIDE the bounding box (not centered like Qt)
            if border_position == "inside":
                # Stroke entirely inside element - box at element boundary
                bx1, by1 = int(x), int(y)
                bx2, by2 = int(x + width), int(y + height)
                bradius = corner_radius
            elif border_position == "center":
                # Stroke centered on element boundary - expand box by half_border
                bx1, by1 = int(x - half_border), int(y - half_border)
                bx2, by2 = int(x + width + half_border), int(y + height + half_border)
                bradius = int(corner_radius + half_border)
            else:  # outside
                # Stroke entirely outside element - expand box by full border_width
                bx1, by1 = int(x - border_width), int(y - border_width)
                bx2, by2 = int(x + width + border_width), int(y + height + border_width)
                bradius = int(corner_radius + border_width)

            # Draw border (outline only)
            if rounded:
                border_draw.rounded_rectangle(
                    [bx1, by1, bx2, by2],
                    radius=bradius,
                    outline=border_rgb,
                    width=border_width
                )
            else:
                border_draw.rectangle(
                    [bx1, by1, bx2, by2],
                    outline=border_rgb,
                    width=border_width
                )

            # Apply border opacity
            if border_opacity < 100:
                r, g, b, a = border_layer.split()
                a = a.point(lambda px: int(px * border_opacity / 100))
                border_layer = Image.merge('RGBA', (r, g, b, a))

            # Composite border layer onto overlay
            overlay.alpha_composite(border_layer)

        # Now use overlay's draw for text (text doesn't need the layer approach)
        draw = ImageDraw.Draw(overlay)

        # Draw text based on bar_text_mode and bar_text_position
        bar_text_mode = getattr(element, 'bar_text_mode', 'full')
        bar_text_position = getattr(element, 'bar_text_position', 'inside')

        if bar_text_mode != 'none':
            value_text = get_value_with_unit(value, element.source, getattr(element, 'temp_hide_unit', False))

            # Value font
            value_font = self.get_pil_font(element, element.font_size)
            # Label font (separate styling)
            label_font = self.get_pil_font_custom(
                getattr(element, 'label_font_family', element.font_family),
                getattr(element, 'label_font_bold', element.font_bold),
                getattr(element, 'label_font_italic', element.font_italic),
                getattr(element, 'label_font_size', element.font_size)
            )

            # Text colors
            value_text_color = getattr(element, 'text_color', element.color)
            value_text_opacity = getattr(element, 'text_color_opacity', 100)
            value_rgba = hex_to_rgba(value_text_color, value_text_opacity)

            label_text_color = getattr(element, 'label_text_color', element.color)
            label_rgba = hex_to_rgba(label_text_color, value_text_opacity)

            if bar_text_position == 'inside':
                if bar_text_mode == 'full':
                    # Draw label and value separately, centered with bar
                    label_text = f"{element.text} "
                    bbox_label = draw.textbbox((0, 0), label_text, font=label_font)
                    label_width = bbox_label[2] - bbox_label[0]

                    bbox_value = draw.textbbox((0, 0), value_text, font=value_font)
                    value_width = bbox_value[2] - bbox_value[0]

                    total_width = label_width + value_width
                    start_x = x + (width - total_width) // 2
                    center_y = y + height // 2

                    draw.text((start_x, center_y), label_text, fill=label_rgba, font=label_font, anchor="lm")
                    draw.text((start_x + label_width, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'value_only':
                    bbox = draw.textbbox((0, 0), value_text, font=value_font)
                    text_width = bbox[2] - bbox[0]
                    text_x = x + (width - text_width) // 2
                    center_y = y + height // 2
                    draw.text((text_x, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'label_only':
                    bbox = draw.textbbox((0, 0), element.text, font=label_font)
                    text_width = bbox[2] - bbox[0]
                    text_x = x + (width - text_width) // 2
                    center_y = y + height // 2
                    draw.text((text_x, center_y), element.text, fill=label_rgba, font=label_font, anchor="lm")

            elif bar_text_position == 'left':
                if bar_text_mode == 'full':
                    # Draw label and value separately, centered with bar
                    label_text = f"{element.text} "
                    bbox_label = draw.textbbox((0, 0), label_text, font=label_font)
                    label_width = bbox_label[2] - bbox_label[0]

                    bbox_value = draw.textbbox((0, 0), value_text, font=value_font)
                    value_width = bbox_value[2] - bbox_value[0]

                    total_width = label_width + value_width
                    start_x = x - total_width - 10
                    center_y = y + height // 2

                    draw.text((start_x, center_y), label_text, fill=label_rgba, font=label_font, anchor="lm")
                    draw.text((start_x + label_width, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'value_only':
                    bbox = draw.textbbox((0, 0), value_text, font=value_font)
                    text_width = bbox[2] - bbox[0]
                    text_x = x - text_width - 10
                    center_y = y + height // 2
                    draw.text((text_x, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'label_only':
                    bbox = draw.textbbox((0, 0), element.text, font=label_font)
                    text_width = bbox[2] - bbox[0]
                    text_x = x - text_width - 10
                    center_y = y + height // 2
                    draw.text((text_x, center_y), element.text, fill=label_rgba, font=label_font, anchor="lm")

            elif bar_text_position == 'right':
                if bar_text_mode == 'full':
                    # Draw label and value separately, centered with bar
                    label_text = f"{element.text} "
                    bbox_label = draw.textbbox((0, 0), label_text, font=label_font)
                    label_width = bbox_label[2] - bbox_label[0]

                    start_x = x + width + 10
                    center_y = y + height // 2

                    draw.text((start_x, center_y), label_text, fill=label_rgba, font=label_font, anchor="lm")
                    draw.text((start_x + label_width, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'value_only':
                    text_x = x + width + 10
                    center_y = y + height // 2
                    draw.text((text_x, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'label_only':
                    text_x = x + width + 10
                    center_y = y + height // 2
                    draw.text((text_x, center_y), element.text, fill=label_rgba, font=label_font, anchor="lm")

            elif bar_text_position == 'top':
                # Label and value inline above bar with 16px padding
                if bar_text_mode == 'full':
                    label_text = f"{element.text} "
                    bbox_label = draw.textbbox((0, 0), label_text, font=label_font)
                    label_width = bbox_label[2] - bbox_label[0]
                    label_height = bbox_label[3] - bbox_label[1]

                    bbox_value = draw.textbbox((0, 0), value_text, font=value_font)
                    value_width = bbox_value[2] - bbox_value[0]
                    value_height = bbox_value[3] - bbox_value[1]

                    total_width = label_width + value_width
                    max_height = max(label_height, value_height)
                    start_x = x + (width - total_width) // 2
                    center_y = y - 16 - max_height // 2

                    draw.text((start_x, center_y), label_text, fill=label_rgba, font=label_font, anchor="lm")
                    draw.text((start_x + label_width, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'value_only':
                    bbox = draw.textbbox((0, 0), value_text, font=value_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    text_x = x + (width - text_width) // 2
                    center_y = y - 16 - text_height // 2
                    draw.text((text_x, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'label_only':
                    bbox = draw.textbbox((0, 0), element.text, font=label_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    text_x = x + (width - text_width) // 2
                    center_y = y - 16 - text_height // 2
                    draw.text((text_x, center_y), element.text, fill=label_rgba, font=label_font, anchor="lm")

            elif bar_text_position == 'bottom':
                # Label and value inline below bar with 16px padding
                if bar_text_mode == 'full':
                    label_text = f"{element.text} "
                    bbox_label = draw.textbbox((0, 0), label_text, font=label_font)
                    label_width = bbox_label[2] - bbox_label[0]
                    label_height = bbox_label[3] - bbox_label[1]

                    bbox_value = draw.textbbox((0, 0), value_text, font=value_font)
                    value_width = bbox_value[2] - bbox_value[0]
                    value_height = bbox_value[3] - bbox_value[1]

                    total_width = label_width + value_width
                    max_height = max(label_height, value_height)
                    start_x = x + (width - total_width) // 2
                    center_y = y + height + 16 + max_height // 2

                    draw.text((start_x, center_y), label_text, fill=label_rgba, font=label_font, anchor="lm")
                    draw.text((start_x + label_width, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'value_only':
                    bbox = draw.textbbox((0, 0), value_text, font=value_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    text_x = x + (width - text_width) // 2
                    center_y = y + height + 16 + text_height // 2
                    draw.text((text_x, center_y), value_text, fill=value_rgba, font=value_font, anchor="lm")
                elif bar_text_mode == 'label_only':
                    bbox = draw.textbbox((0, 0), element.text, font=label_font)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                    text_x = x + (width - text_width) // 2
                    center_y = y + height + 16 + text_height // 2
                    draw.text((text_x, center_y), element.text, fill=label_rgba, font=label_font, anchor="lm")

        # Composite onto main image
        img.alpha_composite(overlay)

    def render_gauge_circle_dmd_rgba(self, img, element, font, color_opacity, bg_opacity):
        """Segmented ring gauge (DMD) rendered with PIL, mirroring draw_gauge_circle_dmd."""
        x, y = element.x, element.y
        radius = max(1, int(getattr(element, 'radius', 7)))
        line_width = max(1, int(getattr(element, 'line_width', 2)))
        max_value = max(float(getattr(element, 'max_value', 100) or 100), 0.0001)
        ratio = max(0.0, min(1.0, float(getattr(element, 'value', 50)) / max_value))
        segments = max(3, int(getattr(element, 'segments', 24) or 24))

        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        color = hex_to_rgba(element.color, color_opacity)
        empty = hex_to_rgba(element.background_color, bg_opacity)

        seg_span = 270.0 / segments
        dash = 0.62
        filled = ratio * segments
        box = [x - radius, y - radius, x + radius, y + radius]
        for i in range(segments):
            a0 = -45.0 + i * seg_span
            a1 = a0 + seg_span * dash
            fill = color if (i + 0.5) <= filled else empty
            draw.arc(box, start=a0, end=a1, fill=fill, width=line_width)

        text = element.text or ""
        if text:
            text_color = hex_to_rgba(getattr(element, 'text_color', element.color),
                                     getattr(element, 'text_color_opacity', 100))
            bbox = draw.textbbox((0, 0), text, font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            draw.text((x - tw / 2 - bbox[0], y - th / 2 - bbox[1]),
                      text, font=font, fill=text_color)

        img.alpha_composite(overlay)

    def render_segmented_bar_rgba(self, img, element, color_opacity, bg_opacity):
        """Horizontal segmented bar (DMD) rendered with PIL."""
        x, y = element.x, element.y
        width = int(element.width)
        height = int(element.height)
        segments = max(1, int(getattr(element, 'segments', 8) or 8))
        gap = max(0, int(getattr(element, 'gap', 1)))
        max_value = max(float(getattr(element, 'max_value', 100) or 100), 0.0001)
        ratio = max(0.0, min(1.0, float(getattr(element, 'value', 0)) / max_value))

        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        color = hex_to_rgba(element.color, color_opacity)
        empty = hex_to_rgba(element.color_empty, getattr(element, 'color_empty_opacity', 100))
        outline = hex_to_rgba(element.color, max(0, color_opacity * 45 // 100))

        total_gap = gap * (segments - 1)
        seg_w = max(1.0, (width - total_gap) / segments)
        filled = ratio * segments
        for i in range(segments):
            sx = x + i * (seg_w + gap)
            fill = color if (i + 0.5) <= filled else empty
            draw.rectangle([sx, y, sx + seg_w, y + height], fill=fill, outline=outline)
        draw.rectangle([x, y, x + width, y + height], outline=outline)

        img.alpha_composite(overlay)

    def render_bar_chart_rgba(self, img, element, color_opacity, bg_opacity):
        """History bar chart with scanline stripes (DMD) rendered with PIL."""

        x, y = element.x, element.y
        width = int(element.width)
        height = int(element.height)
        max_value = max(float(getattr(element, 'max_value', 100) or 100), 0.0001)
        color = hex_to_rgba(element.color, color_opacity)
        bg = hex_to_rgba(element.background_color, bg_opacity)
        frame = hex_to_rgba(element.color, max(0, color_opacity * 60 // 100))

        overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        if getattr(element, 'show_background', True):
            draw.rectangle([x, y, x + width, y + height], fill=bg)

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

        stripe = (int(color[0] * 0.3), int(color[1] * 0.3), int(color[2] * 0.3), color[3])
        for i, sample in enumerate(samples):
            r = max(0.0, min(1.0, float(sample) / max_value))
            bh = max(1.0, r * max(1, height - 2))
            bx = x + i * (bar_w + gap)
            by = y + height - bh
            draw.rectangle([bx, by, bx + bar_w, y + height], fill=color)
            stripe_y = by + 2
            while stripe_y < y + height:
                draw.line([bx, stripe_y, bx + bar_w, stripe_y], fill=stripe, width=1)
                stripe_y += 3

        draw.rectangle([x, y, x + width, y + height], outline=frame)

        img.alpha_composite(overlay)

    def render_dmd_widget(self, img, element, color_opacity):
        """Render one of the HWMON·32 DMD widgets (PIL path)."""
        from dmd_widgets import render_widget

        width = max(1, int(element.width))
        height = max(1, int(element.height))
        pixels = render_widget(element.type, element, width, height)
        if pixels.size == 0:
            return
        overlay = Image.fromarray(pixels, "RGBA")
        if color_opacity < 100:
            alpha = overlay.split()[3].point(lambda a: int(a * color_opacity / 100))
            overlay.putalpha(alpha)
        img.alpha_composite(overlay, (int(element.x), int(element.y)))

    def render_lcd_widget(self, img, element, color_opacity):
        """Render one of the high-resolution LCD elements (PIL path)."""
        from lcd_widgets import render_element

        width = max(1, int(element.width))
        height = max(1, int(element.height))
        pixels = render_element(element.type, element, width, height)
        if pixels.size == 0:
            return
        overlay = Image.fromarray(pixels, "RGBA")
        if color_opacity < 100:
            alpha = overlay.split()[3].point(lambda a: int(a * color_opacity / 100))
            overlay.putalpha(alpha)
        img.alpha_composite(overlay, (int(element.x), int(element.y)))

    def render_touch_nav_rgba(self, img, element, color_opacity):
        """Render the HDMI touch-navigation widget (PIL path, no interaction)."""
        from touch_nav import render

        width = max(1, int(element.width))
        height = max(1, int(element.height))
        pixels = render(element, width, height)
        if pixels.size == 0:
            return
        overlay = Image.fromarray(pixels, "RGBA")
        if color_opacity < 100:
            alpha = overlay.split()[3].point(lambda a: int(a * color_opacity / 100))
            overlay.putalpha(alpha)
        img.alpha_composite(overlay, (int(element.x), int(element.y)))

    def render_icon_rgba(self, img, element, color_opacity):
        """Render an Icon element loaded from the bundled icons/ folder."""
        path = resolve_icon_path(getattr(element, "icon_name", ""))
        if not path:
            return
        try:
            with open(path, "rb") as handle:
                with Image.open(handle) as opened:
                    overlay = opened.convert("RGBA").copy()
            if getattr(element, "tint", False):
                r, g, b, _a = hex_to_rgba(element.color, 100)
                solid = Image.new("RGBA", overlay.size, (r, g, b, 0))
                solid.putalpha(overlay.split()[3])
                overlay = solid
            width = max(1, int(element.width))
            height = max(1, int(element.height))
            if element.scale_proportionally:
                overlay.thumbnail((width, height), Image.Resampling.LANCZOS)
            else:
                overlay = overlay.resize((width, height), Image.Resampling.LANCZOS)
            if color_opacity < 100:
                alpha = overlay.split()[3].point(lambda a: int(a * color_opacity / 100))
                overlay.putalpha(alpha)
            img.alpha_composite(overlay, (int(element.x), int(element.y)))
        except Exception as e:  # noqa: BLE001
            print(f"Icon load error: {e}")

    def render_video_rgba(self, img, element):
        """Render a ``video`` element frame fitted to its rectangle."""
        from video_background import get_video_frame

        path = getattr(element, "video_path", "")
        if not path or not os.path.exists(path):
            return
        frame = get_video_frame(
            path, (max(1, int(element.width)), max(1, int(element.height))),
            getattr(element, "video_fit_mode", "fit_height"))
        if frame is None:
            return
        img.paste(frame, (int(element.x), int(element.y)), frame)

    def image_to_jpeg(self, img, quality=80, subsampling=None,
                      apply_rotation=True, apply_tuning=True):
        """Convert image to JPEG bytes with optimized settings.

        ``apply_rotation``/``apply_tuning`` permiten saltarse el giro de modo
        vertical y la correccion de color del panel LCD cuando la imagen no va
        destinada al panel (p. ej. la fuente HDMI del webserver).
        """
        # Si vertical mode está activo, img se renderiza en espacio lógico
        # retrato (DISPLAY_HEIGHT x DISPLAY_WIDTH). Rótalo 90 grados para que el
        # buffer físico enviado al panel sea SIEMPRE exactamente
        # DISPLAY_WIDTH x DISPLAY_HEIGHT (resolución nativa fija del panel) - nunca
        # otro tamaño, o el firmware estira/comprime el frame y distorsiona.
        if apply_rotation and getattr(self, "_vertical_mode", False):
            disp_w = getattr(self, "_lcd_display_width", DISPLAY_WIDTH)
            disp_h = getattr(self, "_lcd_display_height", DISPLAY_HEIGHT)
            img = img.transpose(Image.ROTATE_270)
            if img.size != (disp_w, disp_h):
                img = img.resize((disp_w, disp_h))

        # Color correction (brightness/contrast/saturation) to compensate for LCD
        # panels that render colors washed-out/dim compared to the design preview.
        # Values of 1.0 are a no-op, so this is skipped entirely when unused.
        brightness = getattr(self, "_lcd_brightness", 1.0) if apply_tuning else 1.0
        contrast = getattr(self, "_lcd_contrast", 1.0) if apply_tuning else 1.0
        saturation = getattr(self, "_lcd_saturation", 1.0) if apply_tuning else 1.0
        if brightness != 1.0:
            img = ImageEnhance.Brightness(img).enhance(brightness)
        if contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(contrast)
        if saturation != 1.0:
            img = ImageEnhance.Color(img).enhance(saturation)

        # Subsampling seleccionado por el perfil de entrega del device conectado:
        #  - Low/legado: 0 (4:4:4, croma completa) como siempre.
        #  - High (24fps en LY): 1 (4:2:2, mitad de croma) para duplicar el ritmo
        #    de decodificación del panel (~12 -> ~24fps).
        # Si el device no declara perfil, subsampling=0 (comportamiento original).
        if subsampling is None:
            subsampling = getattr(self, "_delivery_subsampling", 0)

        buffer = io.BytesIO()
        # Use quality=80 and optimize=False for faster encoding
        # The LCD display doesn't need highest quality
        img.save(buffer, format='JPEG', quality=quality, optimize=False, subsampling=subsampling)
        return buffer.getvalue()
