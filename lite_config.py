"""
Configuracion de ThermalEngineLite.

Precedencia (de menor a mayor): valores por defecto < config.json < variables de
entorno < argumentos de linea de comandos.
"""

import copy
import json
import os

DEFAULT_CONFIG = {
    # Tema inicial (volumen montado en Docker). Si no existe, arranca vacio y
    # espera un push por el webserver.
    "theme_path": "/data/theme.json",
    "watch_theme": True,          # recargar si cambia el mtime del archivo
    "watch_interval_s": 2.0,

    # Destinos activos
    "targets": {"web": True, "lcd": False, "dmd": True, "hdmi": False},

    # Web
    "web_host": "0.0.0.0",
    "web_port": 4241,
    "web_token": None,            # requerido para POST /theme si no es null

    # Rendimiento
    "target_fps": 24,
    "overdrive_mode": False,

    # Ajuste de imagen / orientacion (LCD y Web)
    "vertical_mode": False,
    "lcd_brightness": 1.0,
    "lcd_contrast": 1.2,
    "lcd_saturation": 1.25,

    # LCD USB
    "lcd_model": "trofeo_9_16",

    # DMD (TCP)
    "dmd_config": {
        "ip": "192.168.1.66",
        "port": 8889,
        "width": 128,
        "height": 32,
        "fps": 12,
        "model_id": "dmd_128_32",
    },

    # HDMI (monitor por nombre de conector o id persistido). None = primer HDMI.
    "hdmi_config": None,
    "hdmi_fps": 24,
    "hdmi_scale_mode": "letterbox",

    "log_level": "INFO",
}


def _deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _env_overrides(env):
    out = {}
    if env.get("TE_THEME"):
        out["theme_path"] = env["TE_THEME"]
    if env.get("TE_TARGETS"):
        out["targets"] = {
            "web": "web" in env["TE_TARGETS"],
            "lcd": "lcd" in env["TE_TARGETS"],
            "dmd": "dmd" in env["TE_TARGETS"],
            "hdmi": "hdmi" in env["TE_TARGETS"],
        }
    if env.get("TE_WEB_PORT"):
        out["web_port"] = int(env["TE_WEB_PORT"])
    if env.get("TE_WEB_HOST"):
        out["web_host"] = env["TE_WEB_HOST"]
    if env.get("TE_WEB_TOKEN"):
        out["web_token"] = env["TE_WEB_TOKEN"]
    if env.get("TE_TARGET_FPS"):
        out["target_fps"] = int(env["TE_TARGET_FPS"])
    if env.get("TE_LCD_MODEL"):
        out["lcd_model"] = env["TE_LCD_MODEL"]
    if env.get("TE_WATCH") is not None:
        out["watch_theme"] = env["TE_WATCH"].lower() not in ("0", "false", "no")

    dmd = {}
    if env.get("TE_DMD_IP"):
        dmd["ip"] = env["TE_DMD_IP"]
    if env.get("TE_DMD_PORT"):
        dmd["port"] = int(env["TE_DMD_PORT"])
    if env.get("TE_DMD_SIZE"):
        try:
            w, h = env["TE_DMD_SIZE"].lower().split("x")
            dmd["width"], dmd["height"] = int(w), int(h)
        except ValueError:
            pass
    if env.get("TE_DMD_FPS"):
        dmd["fps"] = int(env["TE_DMD_FPS"])
    if dmd:
        out["dmd_config"] = dmd

    if env.get("TE_HDMI_SCREEN"):
        out["hdmi_config"] = {"screen_id": env["TE_HDMI_SCREEN"]}
    if env.get("TE_HDMI_FPS"):
        out["hdmi_fps"] = int(env["TE_HDMI_FPS"])

    if env.get("TE_LOG_LEVEL"):
        out["log_level"] = env["TE_LOG_LEVEL"]
    return out


def _cli_overrides(args):
    out = {}
    if args is None:
        return out
    targets = {}
    if getattr(args, "targets", None):
        csv = args.targets
        targets = {
            "web": "web" in csv,
            "lcd": "lcd" in csv,
            "dmd": "dmd" in csv,
            "hdmi": "hdmi" in csv,
        }
    for name in ("web", "lcd", "dmd", "hdmi"):
        enabled = getattr(args, f"enable_{name}", None)
        if enabled is not None:
            targets[name] = bool(enabled)
    if targets:
        out["targets"] = targets

    if getattr(args, "theme", None):
        out["theme_path"] = args.theme
    if getattr(args, "config_port", None):
        out["web_port"] = args.config_port
    if getattr(args, "token", None) is not None:
        out["web_token"] = args.token
    if getattr(args, "fps", None):
        out["target_fps"] = args.fps
    if getattr(args, "lcd_model", None):
        out["lcd_model"] = args.lcd_model
    if getattr(args, "dmd_ip", None):
        out.setdefault("dmd_config", {})["ip"] = args.dmd_ip
    if getattr(args, "dmd_size", None):
        try:
            w, h = args.dmd_size.lower().split("x")
            out.setdefault("dmd_config", {})["width"] = int(w)
            out.setdefault("dmd_config", {})["height"] = int(h)
        except ValueError:
            pass
    if getattr(args, "hdmi_screen", None):
        out["hdmi_config"] = {"screen_id": args.hdmi_screen}
    if getattr(args, "log_level", None):
        out["log_level"] = args.log_level
    return out


def load_config(path=None, args=None, env=None):
    """Devuelve el diccionario de configuracion efectivo."""
    env = os.environ if env is None else env
    config = copy.deepcopy(DEFAULT_CONFIG)

    config_path = path or env.get("TE_CONFIG") or "config.json"
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = _deep_merge(config, json.load(f))
        except Exception as e:
            print(f"[Config] No se pudo leer {config_path}: {e}")

    config = _deep_merge(config, _env_overrides(env))
    config = _deep_merge(config, _cli_overrides(args))
    return config
