"""
Theme - modelo de tema de ThermalEngineLite.

Carga y representa el mismo formato JSON que Thermal-Engine-Studio:
``{name, targets, lcd_model, dmd_config, hdmi_config, lcd:{...}, dmd:{...},
hdmi:{...}}``. Tambien acepta el formato "legacy" (elementos en la raiz, -> LCD).

No hay logica de edicion: solo lectura, validacion y (de)serializacion.
"""

import json
import os

from constants import (
    DISPLAY_HEIGHT,
    DISPLAY_WIDTH,
    DMD_DEFAULT_DURATION_S,
    DMD_DEFAULT_TRANSITION,
    DMD_DEFAULT_TRANSITION_MS,
)
from dmd_screens import DMDScreen, screens_from_block, screens_from_dmd
from element import ThemeElement
from security import validate_preset_schema


class ThemeError(Exception):
    """Error de carga o validacion de un tema."""


def _normalize_targets(raw):
    if isinstance(raw, dict):
        return {
            "web": bool(raw.get("web", True)),
            "lcd": bool(raw.get("lcd", True)),
            "dmd": bool(raw.get("dmd", False)),
            "hdmi": bool(raw.get("hdmi", False)),
            "custom": bool(raw.get("custom", False)),
        }
    if isinstance(raw, list):
        return {
            "web": "web" in raw,
            "lcd": "lcd" in raw,
            "dmd": "dmd" in raw,
            "hdmi": "hdmi" in raw,
            "custom": "custom" in raw,
        }
    return {"web": True, "lcd": True, "dmd": False, "hdmi": False,
            "custom": False}


class Theme:
    """Tema cargado en memoria, listo para renderizar."""

    def __init__(self):
        self.name = "Untitled"
        self.targets = {"web": True, "lcd": True, "dmd": False, "hdmi": False}
        self.lcd_model = None
        self.dmd_config = None
        self.hdmi_config = None

        # LCD
        self.lcd_background_color = "#0f0f19"
        self.lcd_elements: list[ThemeElement] = []
        self.lcd_width = DISPLAY_WIDTH
        self.lcd_height = DISPLAY_HEIGHT

        # DMD
        self.dmd_background_color = "#000000"
        self.dmd_screens: list[DMDScreen] = [DMDScreen(name="Screen 1")]
        self.dmd_transitions_enabled = True
        self.dmd_default_duration_s = DMD_DEFAULT_DURATION_S
        self.dmd_default_transition = DMD_DEFAULT_TRANSITION
        self.dmd_default_transition_ms = DMD_DEFAULT_TRANSITION_MS
        self.dmd_width = 128
        self.dmd_height = 32

        # HDMI (varias pantallas con transiciones, como el DMD)
        self.hdmi_background_color = "#000000"
        self.hdmi_screens: list = [DMDScreen(name="Screen 1")]
        self.hdmi_elements: list[ThemeElement] = self.hdmi_screens[0].elements
        self.hdmi_transitions_enabled = True
        self.hdmi_default_duration_s = DMD_DEFAULT_DURATION_S
        self.hdmi_default_transition = DMD_DEFAULT_TRANSITION
        self.hdmi_default_transition_ms = DMD_DEFAULT_TRANSITION_MS
        self.hdmi_width = 0
        self.hdmi_height = 0

        # Fuente del webserver y resolucion del lienzo solo-Web
        self.web_source = "auto"
        self.web_width = 0
        self.web_height = 0

        # Canvas Custom (lienzo libre; se sirve como fuente Web en Lite)
        self.custom = None
        self.custom_config = None
        self.custom_background_color = "#000000"
        self.custom_screens: list = [DMDScreen(name="Screen 1")]
        self.custom_elements: list[ThemeElement] = self.custom_screens[0].elements
        self.custom_transitions_enabled = True
        self.custom_default_duration_s = DMD_DEFAULT_DURATION_S
        self.custom_default_transition = DMD_DEFAULT_TRANSITION
        self.custom_default_transition_ms = DMD_DEFAULT_TRANSITION_MS
        self.custom_width = 1280
        self.custom_height = 800

    # ------------------------------------------------------------- carga --
    @classmethod
    def from_dict(cls, data: dict) -> "Theme":
        if not isinstance(data, dict):
            raise ThemeError("El tema debe ser un objeto JSON")

        is_valid, errors = validate_preset_schema(data)
        if not is_valid:
            raise ThemeError("; ".join(errors[:5]))

        theme = cls()
        theme.name = data.get("name", "Untitled")

        # Formato dual (lcd/dmd/hdmi) vs legacy (raiz -> LCD).
        if "lcd" in data or "dmd" in data or "hdmi" in data:
            lcd_dat = data.get("lcd", {}) or {}
            dmd_dat = data.get("dmd", {}) or {}
            hdmi_dat = data.get("hdmi", {}) or {}
        else:
            lcd_dat, dmd_dat, hdmi_dat = data, {}, {}

        theme.lcd_background_color = lcd_dat.get("background_color", "#0f0f19")
        theme.lcd_elements = [ThemeElement.from_dict(e)
                              for e in lcd_dat.get("elements", [])]
        theme.lcd_width = int(lcd_dat.get("display_width", DISPLAY_WIDTH)
                              or DISPLAY_WIDTH)
        theme.lcd_height = int(lcd_dat.get("display_height", DISPLAY_HEIGHT)
                               or DISPLAY_HEIGHT)

        theme.dmd_screens = screens_from_dmd(dmd_dat)
        theme.dmd_transitions_enabled = bool(
            dmd_dat.get("transitions_enabled", True))
        defaults = dmd_dat.get("defaults") or {}
        theme.dmd_default_duration_s = float(
            defaults.get("duration_s", DMD_DEFAULT_DURATION_S)
            or DMD_DEFAULT_DURATION_S)
        theme.dmd_default_transition = defaults.get(
            "transition", DMD_DEFAULT_TRANSITION)
        theme.dmd_default_transition_ms = int(
            defaults.get("transition_ms", DMD_DEFAULT_TRANSITION_MS) or 0)
        theme.dmd_background_color = theme.dmd_screens[0].background_color
        theme.dmd_width = int(dmd_dat.get("width", 128) or 128)
        theme.dmd_height = int(dmd_dat.get("height", 32) or 32)

        theme.hdmi_screens = screens_from_block(hdmi_dat)
        theme.hdmi_elements = theme.hdmi_screens[0].elements
        theme.hdmi_background_color = theme.hdmi_screens[0].background_color
        theme.hdmi_transitions_enabled = bool(
            hdmi_dat.get("transitions_enabled", True))
        hdmi_defaults = hdmi_dat.get("defaults") or {}
        theme.hdmi_default_duration_s = float(
            hdmi_defaults.get("duration_s", DMD_DEFAULT_DURATION_S)
            or DMD_DEFAULT_DURATION_S)
        theme.hdmi_default_transition = hdmi_defaults.get(
            "transition", DMD_DEFAULT_TRANSITION)
        theme.hdmi_default_transition_ms = int(
            hdmi_defaults.get("transition_ms", DMD_DEFAULT_TRANSITION_MS) or 0)
        theme.hdmi_width = int(hdmi_dat.get("width", 0) or 0)
        theme.hdmi_height = int(hdmi_dat.get("height", 0) or 0)

        # Fuente del webserver y resolucion del lienzo solo-Web (web.width/height).
        web_dat = data.get("web")
        if isinstance(web_dat, dict):
            theme.web_source = web_dat.get("source") or "auto"
            theme.web_width = int(web_dat.get("width", 0) or 0)
            theme.web_height = int(web_dat.get("height", 0) or 0)

        # Canvas Custom: pantallas/transiciones + tamano (custom_config o custom).
        custom_dat = data.get("custom")
        theme.custom = custom_dat if isinstance(custom_dat, dict) else None
        theme.custom_config = data.get("custom_config")
        if isinstance(custom_dat, dict):
            theme.custom_screens = screens_from_block(custom_dat)
            theme.custom_elements = theme.custom_screens[0].elements
            theme.custom_background_color = theme.custom_screens[0].background_color
            theme.custom_transitions_enabled = bool(
                custom_dat.get("transitions_enabled", True))
            custom_defaults = custom_dat.get("defaults") or {}
            theme.custom_default_duration_s = float(
                custom_defaults.get("duration_s", DMD_DEFAULT_DURATION_S)
                or DMD_DEFAULT_DURATION_S)
            theme.custom_default_transition = custom_defaults.get(
                "transition", DMD_DEFAULT_TRANSITION)
            theme.custom_default_transition_ms = int(
                custom_defaults.get("transition_ms", DMD_DEFAULT_TRANSITION_MS) or 0)
        cfg = theme.custom_config if isinstance(theme.custom_config, dict) else {}
        cw = int(cfg.get("width") or 0) or (
            int(custom_dat.get("width", 0) or 0) if isinstance(custom_dat, dict) else 0)
        ch = int(cfg.get("height") or 0) or (
            int(custom_dat.get("height", 0) or 0) if isinstance(custom_dat, dict) else 0)
        theme.custom_width = cw or 1280
        theme.custom_height = ch or 800

        theme.targets = _normalize_targets(data.get("targets"))
        theme.lcd_model = data.get("lcd_model")
        theme.dmd_config = data.get("dmd_config")
        theme.hdmi_config = data.get("hdmi_config")
        return theme

    @classmethod
    def loads(cls, text: str) -> "Theme":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ThemeError(f"JSON invalido: {e}") from e
        return cls.from_dict(data)

    @classmethod
    def load(cls, path: str) -> "Theme":
        if not path or not os.path.exists(path):
            raise ThemeError(f"Tema no encontrado: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return cls.loads(f.read())

    # ------------------------------------------------------------ salida --
    def to_dict(self) -> dict:
        dmd_dat = {
            "width": self.dmd_width,
            "height": self.dmd_height,
            "background_color": self.dmd_background_color,
            "transitions_enabled": self.dmd_transitions_enabled,
            "downsample": False,
            "defaults": {
                "duration_s": self.dmd_default_duration_s,
                "transition": self.dmd_default_transition,
                "transition_ms": self.dmd_default_transition_ms,
            },
        }
        if len(self.dmd_screens) > 1 or self.dmd_screens[0].name != "Screen 1":
            dmd_dat["screens"] = [s.to_dict() for s in self.dmd_screens]
        else:
            dmd_dat["elements"] = [e.to_dict() for e in self.dmd_screens[0].elements]

        return {
            "name": self.name,
            "targets": dict(self.targets),
            "lcd_model": self.lcd_model,
            "dmd_config": self.dmd_config,
            "hdmi_config": self.hdmi_config,
            "lcd": {
                "background_color": self.lcd_background_color,
                "display_width": self.lcd_width,
                "display_height": self.lcd_height,
                "elements": [e.to_dict() for e in self.lcd_elements],
            },
            "dmd": dmd_dat,
            "hdmi": {
                "background_color": self.hdmi_background_color,
                "width": self.hdmi_width,
                "height": self.hdmi_height,
                "transitions_enabled": self.hdmi_transitions_enabled,
                "defaults": {
                    "duration_s": self.hdmi_default_duration_s,
                    "transition": self.hdmi_default_transition,
                    "transition_ms": self.hdmi_default_transition_ms,
                },
                "screens": [s.to_dict() for s in self.hdmi_screens],
                # Compatibilidad: elementos de la pantalla activa.
                "elements": [e.to_dict() for e in self.hdmi_elements],
            },
            "web": {
                "source": self.web_source,
                **({"width": self.web_width, "height": self.web_height}
                   if self.web_width and self.web_height else {}),
            },
            "custom": {
                "background_color": self.custom_background_color,
                "width": self.custom_width,
                "height": self.custom_height,
                "transitions_enabled": self.custom_transitions_enabled,
                "defaults": {
                    "duration_s": self.custom_default_duration_s,
                    "transition": self.custom_default_transition,
                    "transition_ms": self.custom_default_transition_ms,
                },
                "screens": [s.to_dict() for s in self.custom_screens],
                "elements": [e.to_dict() for e in self.custom_elements],
            },
            "custom_config": self.custom_config,
        }
