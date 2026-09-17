"""
Servidor web de ThermalEngineLite (Flask en un hilo de fondo).

Sirve el frame renderizado, un panel de control y la API de gestion. Corre en un
hilo dentro del mismo proceso que Qt y habla con ``ThemeRuntime`` mediante
llamadas programadas en el bucle de eventos de Qt.

Endpoints:
- GET  /            -> pantalla completa con la imagen renderizada
- GET  /config      -> panel de control (presets, intervalo de refresco)
- GET  /image.jpg   -> frame JPEG actual
- GET  /theme       -> JSON del tema activo
- POST /theme       -> aplica un tema nuevo (push). Requiere token si esta configurado.
- GET  /status      -> estado de las salidas y del tema
- GET  /healthz     -> sonda de salud
- GET  /presets     -> lista de presets locales
- POST /apply_preset-> aplica un preset local

El servidor escucha en 0.0.0.0:4241 por defecto.
"""

import io
import json
import os
import threading

from flask import Flask, abort, jsonify, render_template, request
from PySide6.QtCore import QObject, Qt, Signal

# Pillow es opcional para post-proceso (resize/rotate).
try:
    from PIL import Image
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

from app_path import get_resource_path
from security import validate_preset_schema

MAX_THEME_BYTES = 8 * 1024 * 1024  # 8 MB

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
    static_folder=os.path.join(os.path.dirname(__file__), 'static'),
)

# Runtime global (asignado por start_server en el hilo de Qt).
_RUNTIME = None
_TOKEN = None


# --------------------------------------------------------------------------
# Puente hilo Flask -> bucle de eventos Qt (senal en cola).
# --------------------------------------------------------------------------
class _QtInvoker(QObject):
    _invoke = Signal(object)

    def __init__(self):
        super().__init__()
        self._invoke.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def _run(self, fn):
        fn()

    def schedule(self, fn):
        self._invoke.emit(fn)


_qt_invoker = None


def run_on_qt_and_wait(fn, timeout=5.0):
    """Ejecuta fn() en el hilo de Qt y espera el resultado.

    Devuelve (result, None) o (None, error).
    """
    if _qt_invoker is None:
        return None, "Qt event loop not ready"

    event = threading.Event()
    result = {"value": None, "error": None}

    def wrapper():
        try:
            result["value"] = fn()
        except Exception as e:
            result["error"] = str(e)
        finally:
            event.set()

    _qt_invoker.schedule(wrapper)

    if not event.wait(timeout):
        return None, "timeout"
    if result["error"]:
        return None, result["error"]
    return result["value"], None


def _check_token():
    """True si el token es valido (o no hay token configurado)."""
    if not _TOKEN:
        return True
    supplied = (request.headers.get("X-Token")
                or request.headers.get("Authorization", "").removeprefix("Bearer ").strip())
    return supplied == _TOKEN


# --------------------------------------------------------------------------
# Paginas
# --------------------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/config')
def config_page():
    return render_template('config.html')


# --------------------------------------------------------------------------
# Imagen
# --------------------------------------------------------------------------
@app.route('/image.jpg')
def image_jpeg():
    global _RUNTIME
    if _RUNTIME is None:
        abort(503)

    try:
        req_w = int(request.args.get('w')) if request.args.get('w') else None
    except Exception:
        req_w = None
    try:
        req_h = int(request.args.get('h')) if request.args.get('h') else None
    except Exception:
        req_h = None

    cached = getattr(_RUNTIME, '_last_jpeg_data', None)
    if cached and not (req_w or req_h):
        try:
            vertical = bool(getattr(_RUNTIME, '_vertical_mode', False))
        except Exception:
            vertical = False
        if vertical and PIL_AVAILABLE:
            try:
                with Image.open(io.BytesIO(cached)) as _im:
                    im = _im.rotate(90, expand=True)
                    out = io.BytesIO()
                    im.save(out, format='JPEG', quality=90)
                    return (out.getvalue(), 200, {
                        'Content-Type': 'image/jpeg',
                        'Cache-Control': 'no-cache, no-store, must-revalidate'})
            except Exception:
                pass
        return (cached, 200, {'Content-Type': 'image/jpeg',
                              'Cache-Control': 'no-cache, no-store, must-revalidate'})

    def make_jpeg():
        return _RUNTIME.web_jpeg(quality=95)

    data, err = run_on_qt_and_wait(make_jpeg, timeout=15.0)
    if err:
        fallback = getattr(_RUNTIME, '_last_jpeg_data', None)
        if fallback:
            data = fallback
        else:
            abort(500, description=f"Render error: {err}")

    def _web_source_is_lcd():
        try:
            return _RUNTIME._effective_web_source() == "lcd"
        except Exception:
            return True

    rotate = bool(getattr(_RUNTIME, '_vertical_mode', False)) and _web_source_is_lcd()
    need_post = PIL_AVAILABLE and (req_w is not None or req_h is not None or rotate)

    if need_post:
        try:
            with Image.open(io.BytesIO(data)) as _im:
                im = _im.copy()
            if rotate:
                im = im.rotate(90, expand=True)
            if req_w and not req_h:
                w = req_w
                h = int(im.height * (req_w / im.width))
            elif req_h and not req_w:
                h = req_h
                w = int(im.width * (req_h / im.height))
            elif req_w and req_h:
                w, h = req_w, req_h
            else:
                w, h = im.width, im.height
            if (w, h) != (im.width, im.height):
                im = im.resize((w, h), resample=Image.LANCZOS)
            out = io.BytesIO()
            im.save(out, format='JPEG', quality=90)
            data = out.getvalue()
        except Exception:
            pass

    return (data, 200, {'Content-Type': 'image/jpeg',
                        'Cache-Control': 'no-cache, no-store, must-revalidate'})


# --------------------------------------------------------------------------
# API de temas
# --------------------------------------------------------------------------
@app.route('/theme', methods=['GET'])
def get_theme():
    if _RUNTIME is None:
        abort(503)
    return jsonify(_RUNTIME.theme.to_dict())


@app.route('/theme', methods=['POST'])
def push_theme():
    if _RUNTIME is None:
        abort(503)
    if not _check_token():
        abort(401)

    raw = request.get_data(cache=False)
    if len(raw) > MAX_THEME_BYTES:
        abort(413, description="theme too large")
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        abort(400, description="invalid JSON")

    is_valid, errors = validate_preset_schema(data)
    if not is_valid:
        return jsonify(success=False, error="invalid theme",
                       details=errors[:10]), 422

    result, err = run_on_qt_and_wait(
        lambda: _RUNTIME.load_theme_dict(data, source="push"), timeout=15.0)
    if err:
        return jsonify(success=False, error=err), 500

    persisted, persist_error = getattr(_RUNTIME, "_last_persist", (None, None))
    body = {
        "success": True,
        "theme": getattr(result, "name", None),
        "persisted": bool(persisted),
    }
    if persist_error:
        body["persist_error"] = persist_error
    return jsonify(body)


@app.route('/status')
def status():
    if _RUNTIME is None:
        return jsonify(ready=False), 503
    return jsonify(_RUNTIME.status())


@app.route('/info')
def info():
    """Metadatos del dispositivo para el wizard de ThermalEngineStudio."""
    if _RUNTIME is None:
        abort(503)
    return jsonify(_RUNTIME.info())


@app.route('/sensors')
def sensors():
    """Valores de sensores del equipo. Requiere token si esta configurado."""
    if _RUNTIME is None:
        abort(503)
    if not _check_token():
        abort(401)
    return jsonify(_RUNTIME.get_sensor_data())


@app.route('/healthz')
def healthz():
    return jsonify(status="ok", ready=_RUNTIME is not None)


# --------------------------------------------------------------------------
# Presets locales
# --------------------------------------------------------------------------
@app.route('/presets')
def list_presets():
    presets_dir = get_resource_path('presets')
    try:
        names = [os.path.splitext(f)[0]
                 for f in sorted(os.listdir(presets_dir))
                 if f.lower().endswith('.json')]
        return jsonify(names)
    except Exception:
        return jsonify([])


@app.route('/apply_preset', methods=['POST'])
def apply_preset():
    if _RUNTIME is None:
        abort(503)
    payload = request.get_json()
    if not payload:
        abort(400, 'expected JSON body')

    if 'preset' in payload:
        preset_data = payload['preset']
    elif 'preset_name' in payload:
        preset_path = os.path.join(get_resource_path('presets'),
                                   f"{payload['preset_name']}.json")
        if not os.path.exists(preset_path):
            abort(404, 'preset not found')
        with open(preset_path, 'r', encoding='utf-8') as f:
            preset_data = json.load(f)
    else:
        abort(400, 'invalid payload')

    result, err = run_on_qt_and_wait(
        lambda: _RUNTIME.load_theme_dict(preset_data, source="preset"), timeout=15.0)
    if err:
        return jsonify(success=False, error=err), 500
    return jsonify({'status': 'ok'})


# --------------------------------------------------------------------------
# Ciclo de vida del servidor
# --------------------------------------------------------------------------
_SERVER = None
_SERVER_THREAD = None


def start_server(runtime, host='0.0.0.0', port=4241, token=None):
    """Arranca el servidor Flask en un hilo daemon y asocia el runtime."""
    global _RUNTIME, _qt_invoker, _SERVER, _SERVER_THREAD, _TOKEN

    if is_running():
        return _SERVER_THREAD

    _RUNTIME = runtime
    _TOKEN = token
    if not _TOKEN:
        print("[WEB] Aviso: sin web_token; POST /theme acepta cualquier origen")

    if _qt_invoker is None:
        _qt_invoker = _QtInvoker()

    from werkzeug.serving import make_server
    server = make_server(host, port, app, threaded=True)

    def _run():
        import logging
        logging.getLogger('werkzeug').setLevel(logging.ERROR)
        server.serve_forever()

    _SERVER = server
    t = threading.Thread(target=_run, daemon=True, name='Thermal-LiteWebServer')
    t.start()
    _SERVER_THREAD = t
    return t


def is_running():
    return _SERVER is not None


def stop_server():
    global _SERVER, _SERVER_THREAD
    if _SERVER is None:
        return
    server = _SERVER
    _SERVER = None
    _SERVER_THREAD = None
    try:
        server.shutdown()
        server.server_close()
    except Exception as e:
        print(f"[WEB] stop_server warning: {e}")
