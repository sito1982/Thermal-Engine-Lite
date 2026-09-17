"""
ThemeRuntime - nucleo de ejecucion de ThermalEngineLite.

Carga un tema, mantiene el renderer y gestiona las salidas (LCD/DMD/HDMI/Web).
No contiene interfaz de edicion: es el objeto que el webserver consulta para
servir los frames y el que aplica los temas recibidos por push.
"""

import json
import os
import socket
import time

from PySide6.QtCore import QObject, QTimer

import sensors
from outputs import OutputDMD, OutputHDMI, OutputLCD, OutputWeb
from renderer import ThemeRenderer
from sensor_hub import (
    get_sensor_data,
    resolve_sensor_value,
    start_psutil_thread,
    stop_psutil_thread,
)
from theme import Theme
from version import __version__ as LITE_VERSION

# Claves de sensores incluidas en /status (observabilidad del equipo).
_STATUS_SENSOR_KEYS = (
    "cpu_percent", "cpu_temp", "cpu_clock", "cpu_power",
    "ram_percent", "ram_used", "ram_available",
    "net_upload", "net_download", "disk_read", "disk_write",
    "nvme_temp", "mainboard_temp", "uptime",
)


class ThemeRuntime(QObject):
    """Runtime headless: tema + renderer + salidas."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self.theme = Theme()

        self.renderer = ThemeRenderer(
            vertical_mode=bool(config.get("vertical_mode", False)),
            brightness=float(config.get("lcd_brightness", 1.0)),
            contrast=float(config.get("lcd_contrast", 1.0)),
            saturation=float(config.get("lcd_saturation", 1.0)),
        )
        # Interfaz que consume webserver.py.
        self._vertical_mode = self.renderer._vertical_mode
        self._last_jpeg_data = None
        self._web_hdmi_canvas = None

        self._outputs = {
            "web": OutputWeb(self),
            "lcd": OutputLCD(self),
            "dmd": OutputDMD(self),
            "hdmi": OutputHDMI(self),
        }
        self._active_targets = {}
        self._jpeg_cache_timer = None
        self._watch_timer = None
        self._theme_mtime = None
        self._last_persist = (None, None)
        self._closing = False

        start_psutil_thread()
        # Arranca el backend de sensores de la plataforma (linux_sensors/HWiNFO).
        # Sin esto, las temperaturas/consumo se quedan a 0.
        try:
            sensors.init_sensors()
        except Exception as e:
            print(f"[Runtime] No se pudo inicializar sensores: {e}")

        # Registrar en Qt las fuentes empaquetadas (assets/fonts/ttf) para que
        # el canvas HDMI/custom/DMD las use igual que Studio.
        try:
            self.renderer._load_dmd_fonts()
        except Exception as e:
            print(f"[Runtime] No se pudieron cargar las fuentes: {e}")

    # ---------------------------------------------------------- sensores --
    def get_sensor_data(self):
        return get_sensor_data()

    def sync_lcd_sensor_values(self):
        sensor_data = self.get_sensor_data()
        for element in self.renderer.lcd_elements:
            source = getattr(element, "source", "static")
            if source != "static":
                value = resolve_sensor_value(sensor_data, source)
                if value is not None:
                    element.value = value
            sources = getattr(element, "sources", None)
            if sources:
                current = getattr(element, "panel_values", None) or {}
                resolved = {}
                for s in sources:
                    value = resolve_sensor_value(sensor_data, s)
                    resolved[s] = value if value is not None else current.get(s, 0)
                element.panel_values = resolved

    # ------------------------------------------------------------ render --
    def render_theme_image(self):
        """Renderiza la pestana LCD sincronizando antes los valores de sensores."""
        self.sync_lcd_sensor_values()
        return self.renderer.render_theme_image()

    # --------------------------------------------------- fuente Web ------
    def _has_hdmi_screens(self):
        screens = getattr(self.theme, "hdmi_screens", None) or []
        return bool(screens and any(getattr(s, "elements", None) for s in screens))

    def _has_custom_canvas(self):
        theme = self.theme
        if isinstance(getattr(theme, "custom_config", None), dict):
            return True
        if getattr(theme, "targets", {}).get("custom"):
            return True
        screens = getattr(theme, "custom_screens", None) or []
        return bool(screens and any(getattr(s, "elements", None) for s in screens))

    def _effective_web_source(self):
        """Fuente efectiva del webserver: "lcd", "hdmi" o "custom"."""
        source = getattr(self.theme, "web_source", "auto") or "auto"
        has_hdmi = bool(self._active_targets.get("hdmi")) or self._has_hdmi_screens()
        has_custom = self._has_custom_canvas()
        if source == "hdmi":
            return "hdmi" if has_hdmi else ("custom" if has_custom else "lcd")
        if source == "custom":
            return "custom" if has_custom else "lcd"
        if source == "lcd":
            return "lcd"
        # auto
        if has_hdmi:
            return "hdmi"
        if has_custom:
            return "custom"
        return "lcd"

    def _render_screen_image(self, screens, width, height):
        """Frame de la primera pantalla como imagen PIL RGB (canvas offscreen)."""
        from PIL import Image

        from canvas import HDMICanvas
        from dmd_screens import DMDScreen
        from dmd_transitions import render_screen_rgb

        w = int(width or 0) or 1920
        h = int(height or 0) or 1080
        canvas = self._web_hdmi_canvas
        if canvas is None or canvas.dmd_width != w or canvas.dmd_height != h:
            canvas = HDMICanvas(w, h)
            self._web_hdmi_canvas = canvas
        screens = screens or [DMDScreen()]
        rgb = render_screen_rgb(canvas, screens[0], self.get_sensor_data())
        return Image.fromarray(rgb, "RGB")

    def render_hdmi_image(self):
        theme = self.theme
        return self._render_screen_image(
            getattr(theme, "hdmi_screens", None),
            theme.hdmi_width, theme.hdmi_height)

    def render_custom_image(self):
        theme = self.theme
        return self._render_screen_image(
            getattr(theme, "custom_screens", None),
            theme.custom_width, theme.custom_height)

    def render_web_source_image(self):
        """Imagen que sirve el webserver segun ``web.source``."""
        source = self._effective_web_source()
        if source == "hdmi":
            return self.render_hdmi_image()
        if source == "custom":
            return self.render_custom_image()
        return self.render_theme_image()

    def web_jpeg(self, quality=90):
        """JPEG del frame de la fuente Web efectiva (cachea en `_last_jpeg_data`).

        Calidad 90 y 4:4:4 (sin submuestreo de croma) para que el preview se vea
        nitido; no hereda el perfil de entrega del panel LCD.
        """
        source = self._effective_web_source()
        img = self.render_web_source_image()
        is_lcd = source == "lcd"
        jpeg = self.renderer.image_to_jpeg(
            img, quality=quality, subsampling=0,
            apply_rotation=is_lcd, apply_tuning=is_lcd)
        self._last_jpeg_data = jpeg
        return jpeg

    def image_to_jpeg(self, img, quality=80, subsampling=None,
                      apply_rotation=True, apply_tuning=True):
        jpeg = self.renderer.image_to_jpeg(img, quality=quality,
                                           subsampling=subsampling,
                                           apply_rotation=apply_rotation,
                                           apply_tuning=apply_tuning)
        self._last_jpeg_data = jpeg
        return jpeg

    def set_vertical_mode(self, enabled):
        self._vertical_mode = bool(enabled)
        self.renderer._vertical_mode = bool(enabled)
        self._last_jpeg_data = None

    # ------------------------------------------------------------- temas --
    def load_theme_dict(self, data, source="push", persist=None):
        """Carga un tema desde un dict y reconfigura las salidas.

        Los temas recibidos por push se persisten en ``theme_path`` para que
        sobrevivan a un reinicio (se convierten en el tema predeterminado).
        """
        theme = Theme.from_dict(data)
        self._apply_theme(theme, source=source)
        do_persist = (source == "push") if persist is None else bool(persist)
        if do_persist:
            self.persist_theme(data)
        return theme

    def persist_theme(self, data):
        """Guarda el tema (JSON tal cual) en ``theme_path`` de forma atomica.

        Devuelve ``(ok, error)``. Si no hay ``theme_path`` o falla la escritura,
        el tema sigue aplicado en memoria y solo se registra un aviso.
        """
        path = self.config.get("theme_path")
        if not path:
            self._last_persist = (False, "sin theme_path")
            print("[Runtime] Push aplicado pero no persistido: sin theme_path")
            return False, "sin theme_path"
        try:
            directory = os.path.dirname(os.path.abspath(path))
            if directory:
                os.makedirs(directory, exist_ok=True)
            tmp_path = f"{path}.tmp"
            with open(tmp_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
            try:
                self._theme_mtime = os.path.getmtime(path)
            except OSError:
                self._theme_mtime = None
            self._last_persist = (True, None)
            print(f"[Runtime] Tema persistido en {path}")
            return True, None
        except Exception as e:
            self._last_persist = (False, str(e))
            print(f"[Runtime] No se pudo persistir el tema en {path}: {e}")
            return False, str(e)

    def load_theme_path(self, path):
        """Carga un tema desde disco y reconfigura las salidas."""
        theme = Theme.load(path)
        self._apply_theme(theme, source=path)
        try:
            self._theme_mtime = os.path.getmtime(path)
        except OSError:
            self._theme_mtime = None
        return theme

    # Alias de compatibilidad con webserver.py (POST /apply_preset).
    def load_preset(self, data):
        return self.load_theme_dict(data, source="preset")

    def _apply_theme(self, theme, source="push"):
        self.theme = theme
        self.renderer.lcd_elements = theme.lcd_elements
        self.renderer.lcd_background_color = theme.lcd_background_color
        # Tamano del canvas LCD/Web: `web.width/height` (lienzo de resolucion
        # libre, p. ej. proyecto solo-Web) manda si esta definido; si no, el del
        # bloque `lcd`.
        disp_w = theme.web_width or theme.lcd_width
        disp_h = theme.web_height or theme.lcd_height
        self.renderer._lcd_display_width = disp_w
        self.renderer._lcd_display_height = disp_h
        self._last_jpeg_data = None

        # Orientacion segun dimensiones efectivas (portrait si h > w). Se aplica
        # siempre (tambien en cuadrados) para no arrastrar la orientacion de un
        # tema anterior.
        if disp_w and disp_h:
            self.set_vertical_mode(disp_h > disp_w)

        self.apply_targets(self.config.get("targets", {}))
        print(f"[Runtime] Tema cargado ({source}): {theme.name}")

    # ----------------------------------------------------------- salidas --
    def apply_targets(self, targets):
        targets = {
            "web": bool(targets.get("web", False)),
            "lcd": bool(targets.get("lcd", False)),
            "dmd": bool(targets.get("dmd", False)),
            "hdmi": bool(targets.get("hdmi", False)),
        }
        self._active_targets = targets

        # Web
        self._configure_and_toggle(
            "web", targets["web"],
            {"host": self.config.get("web_host", "0.0.0.0"),
             "port": self.config.get("web_port", 4241),
             "token": self.config.get("web_token")})

        # DMD
        dmd_cfg = self._resolve_dmd_config()
        self._configure_and_toggle("dmd", targets["dmd"], dmd_cfg)

        # HDMI
        hdmi_cfg = dict(self.config.get("hdmi_config") or {})
        hdmi_cfg.setdefault("fps", self.config.get("hdmi_fps", 24))
        self._configure_and_toggle("hdmi", targets["hdmi"], hdmi_cfg)

        # LCD
        self._configure_and_toggle(
            "lcd", targets["lcd"],
            {"fps": self.config.get("target_fps", 24)})

        active = [n for n, v in targets.items() if v]
        print(f"[Runtime] Targets activos: {', '.join(active) or 'ninguno'}")

    def _configure_and_toggle(self, name, enabled, cfg):
        output = self._outputs[name]
        output.configure(cfg)
        if enabled and not output.enabled:
            output.start()
        elif not enabled and output.enabled:
            output.stop()

    def _resolve_dmd_config(self):
        cfg = dict(self.config.get("dmd_config") or {})
        theme_cfg = self.theme.dmd_config or {}
        # El tamano lo manda el tema (diseno); la conexion, la config del equipo.
        cfg.setdefault("width", theme_cfg.get("width", self.theme.dmd_width))
        cfg.setdefault("height", theme_cfg.get("height", self.theme.dmd_height))
        if not cfg.get("ip"):
            cfg["ip"] = theme_cfg.get("ip")
        if not cfg.get("port"):
            cfg["port"] = theme_cfg.get("port", 8889)
        return cfg

    # ------------------------------------------------------ cache JPEG --
    def start_jpeg_cache_timer(self, interval_ms=500):
        if self._jpeg_cache_timer is not None and self._jpeg_cache_timer.isActive():
            return
        self._jpeg_cache_timer = QTimer(self)

        def tick():
            try:
                self.web_jpeg()
            except Exception:
                pass

        self._jpeg_cache_timer.timeout.connect(tick)
        self._jpeg_cache_timer.start(interval_ms)

    def stop_jpeg_cache_timer(self):
        if self._jpeg_cache_timer is not None:
            try:
                self._jpeg_cache_timer.stop()
            except Exception:
                pass
            self._jpeg_cache_timer = None

    # ------------------------------------------------------ watch tema --
    def start_theme_watch(self):
        if not self.config.get("watch_theme"):
            return
        path = self.config.get("theme_path")
        if not path:
            return
        interval = max(0.5, float(self.config.get("watch_interval_s", 2.0)))
        self._watch_timer = QTimer(self)
        self._watch_timer.timeout.connect(lambda: self._check_theme_file(path))
        self._watch_timer.start(int(interval * 1000))

    def _check_theme_file(self, path):
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return
        if self._theme_mtime is None:
            self._theme_mtime = mtime
            return
        if mtime != self._theme_mtime:
            self._theme_mtime = mtime
            try:
                self.load_theme_path(path)
            except Exception as e:
                print(f"[Runtime] Recarga de tema fallida: {e}")

    # ------------------------------------------------------------ estado --
    def info(self):
        """Metadatos del dispositivo para el wizard de Studio.

        Incluye los destinos activos, las dimensiones/configs efectivas de cada
        salida y el modelo LCD, para que el editor pueda crear un proyecto Lite
        con las mismas caracteristicas que este equipo.
        """
        theme = self.theme
        targets = self._active_targets

        dmd_cfg = self.config.get("dmd_config") or {}
        dmd = {
            "width": theme.dmd_width or int(dmd_cfg.get("width", 128) or 128),
            "height": theme.dmd_height or int(dmd_cfg.get("height", 32) or 32),
            "ip": dmd_cfg.get("ip"),
            "port": int(dmd_cfg.get("port", 8889) or 8889),
            "fps": int(dmd_cfg.get("fps", 12) or 12),
            "model_id": dmd_cfg.get("model_id"),
        }

        hdmi_cfg = self.config.get("hdmi_config") or {}
        hdmi_w = theme.hdmi_width or int(hdmi_cfg.get("width", 0) or 0)
        hdmi_h = theme.hdmi_height or int(hdmi_cfg.get("height", 0) or 0)

        try:
            hostname = socket.gethostname()
        except Exception:
            hostname = None

        return {
            "app": "ThermalEngineLite",
            "version": LITE_VERSION,
            "hostname": hostname,
            "theme": theme.name,
            "targets": {
                "web": bool(targets.get("web")),
                "lcd": bool(targets.get("lcd")),
                "dmd": bool(targets.get("dmd")),
                "hdmi": bool(targets.get("hdmi")),
            },
            "lcd": {
                "display_width": theme.lcd_width,
                "display_height": theme.lcd_height,
                "background_color": theme.lcd_background_color,
            },
            "dmd": dmd,
            "hdmi": {"width": hdmi_w or 1920, "height": hdmi_h or 1080},
            "lcd_model": self.config.get("lcd_model"),
        }

    def status(self):
        data = self.get_sensor_data()
        return {
            "theme": self.theme.name,
            "targets": dict(self._active_targets),
            "vertical_mode": self._vertical_mode,
            "sensors": {k: data.get(k) for k in _STATUS_SENSOR_KEYS},
            "outputs": {name: out.status()
                        for name, out in self._outputs.items()
                        if out.enabled or name in ("web", "dmd", "hdmi", "lcd")},
            "time": time.time(),
        }

    def stop(self):
        self._closing = True
        self.stop_jpeg_cache_timer()
        if self._watch_timer is not None:
            self._watch_timer.stop()
            self._watch_timer = None
        for output in self._outputs.values():
            output.stop()
        try:
            sensors.stop_sensors()
        except Exception:
            pass
        try:
            stop_psutil_thread()
        except Exception:
            pass
