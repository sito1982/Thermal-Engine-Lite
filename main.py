"""
ThermalEngineLite - runtime de monitorizacion headless.

Carga un tema guardado (creado con Thermal-Engine-Studio) y lo renderiza con
datos de sensores en equipos autonomos, entregandolo a LCD USB, paneles DMD
(TCP), monitores HDMI y/o un servidor web. Los temas pueden actualizarse en
caliente por push (POST /theme) sin reiniciar el servicio.

No incorpora editor: esta pensado para desplegarse en Docker sobre terminales.
"""

import argparse
import json
import logging
import os
import signal
import sys

# Qt en modo offscreen cuando no hay servidor grafico: permite renderizar DMD
# (QPainter) en contenedores sin display. Debe fijarse antes de crear QApplication.
if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from app_path import get_resource_path  # noqa: E402
from lite_config import load_config  # noqa: E402
from theme import ThemeError  # noqa: E402
from version import __version__  # noqa: E402


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="thermalenginelite",
        description="Runtime de monitorizacion ThermalEngineLite (sin editor)")
    parser.add_argument("--version", action="version",
                        version=f"ThermalEngineLite {__version__}")
    parser.add_argument("--config", default=None,
                        help="Ruta al config.json (por defecto TE_CONFIG o ./config.json)")
    parser.add_argument("--theme", default=None,
                        help="Ruta al tema JSON a cargar al arrancar")
    parser.add_argument("--targets", default=None,
                        help="Destinos activos separados por comas: web,lcd,dmd,hdmi")

    for name in ("web", "lcd", "dmd", "hdmi"):
        parser.add_argument(f"--enable-{name}", dest=f"enable_{name}",
                            action=argparse.BooleanOptionalAction, default=None,
                            help=f"Forzar {'activar' if name != 'lcd' else 'activar'} {name}")

    parser.add_argument("--port", dest="config_port", type=int, default=None,
                        help="Puerto del webserver")
    parser.add_argument("--token", default=None,
                        help="Token para POST /theme (vacio = sin autenticacion)")
    parser.add_argument("--fps", type=int, default=None,
                        help="FPS objetivo para LCD")
    parser.add_argument("--lcd-model", default=None,
                        help="Modelo de panel LCD del catalogo")
    parser.add_argument("--dmd-ip", default=None, help="IP del panel DMD")
    parser.add_argument("--dmd-size", default=None,
                        help="Resolucion DMD WxH (p.ej. 128x32)")
    parser.add_argument("--hdmi-screen", default=None,
                        help="Conector/id del monitor HDMI")
    parser.add_argument("--log-level", default=None,
                        help="DEBUG, INFO, WARNING, ERROR")
    return parser.parse_args(argv)


def setup_logging(level_name):
    level = getattr(logging, str(level_name or "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _load_initial_theme(runtime, theme_path):
    """Carga el tema inicial; si no existe, usa el preset Default incluido."""
    if theme_path and os.path.exists(theme_path):
        try:
            runtime.load_theme_path(theme_path)
            return True
        except ThemeError as e:
            logging.error("Tema inicial invalido (%s): %s", theme_path, e)
        except Exception as e:
            logging.error("No se pudo cargar el tema inicial %s: %s", theme_path, e)

    default_path = get_resource_path(os.path.join("presets", "Default.json"))
    if os.path.exists(default_path):
        try:
            with open(default_path, "r", encoding="utf-8") as f:
                runtime.load_theme_dict(json.load(f), source="default")
            logging.info("Cargado preset Default incluido")
            return False  # no hay archivo vigilado
        except Exception as e:
            logging.error("No se pudo cargar el preset Default: %s", e)

    # Sin tema: arrancar salidas igualmente y esperar un push.
    runtime.apply_targets(runtime.config.get("targets", {}))
    logging.warning("Sin tema cargado; esperando push en POST /theme")
    return False


def main(argv=None):
    args = parse_args(argv)
    config = load_config(args.config, args)
    setup_logging(config.get("log_level"))

    logging.info("ThermalEngineLite %s", __version__)
    logging.info("Plataforma Qt: %s", os.environ.get("QT_QPA_PLATFORM", "(nativa)"))

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("ThermalEngineLite")

    from runtime import ThemeRuntime

    runtime = ThemeRuntime(config)
    watched = _load_initial_theme(runtime, config.get("theme_path"))
    if watched:
        runtime.start_theme_watch()

    def _shutdown(signum=None, frame=None):
        logging.info("Deteniendo ThermalEngineLite...")
        runtime.stop()
        app.quit()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        return app.exec()
    finally:
        runtime.stop()


if __name__ == "__main__":
    sys.exit(main())
