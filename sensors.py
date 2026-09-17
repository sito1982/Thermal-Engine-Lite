"""
Monitorización de sensores multiplataforma.

- En Windows: usa la memoria compartida de HWiNFO (hwinfo_reader).
- En Linux (p. ej. Bazzite): lee los sensores del sistema (linux_sensors):
  psutil + RAPL para la CPU y NVML/nvidia-smi para la GPU NVIDIA.

El resto de la aplicación usa siempre las mismas funciones
(`is_hwinfo_available`, `get_hwinfo_sensors`, `HAS_HWINFO`, ...), sin importar
el sistema operativo, por lo que este módulo elige el backend adecuado.
"""

import sys
import threading
import time

IS_WINDOWS = sys.platform == "win32"

# Selección del backend de sensores según el sistema operativo.
if IS_WINDOWS:
    from hwinfo_reader import (
        get_hwinfo_reader as _get_reader,
    )
    from hwinfo_reader import (
        get_hwinfo_sensors as _backend_sensors,
    )
    from hwinfo_reader import (
        is_hwinfo_available as _backend_available,
    )
    SENSOR_BACKEND_NAME = "HWiNFO"
else:
    from linux_sensors import (
        get_linux_reader as _get_reader,
    )
    from linux_sensors import (
        get_linux_sensors as _backend_sensors,
    )
    from linux_sensors import (
        is_linux_sensors_available as _backend_available,
    )
    SENSOR_BACKEND_NAME = "Sensores de Linux"


# Alias retrocompatibles usados en el resto del código base.
def is_hwinfo_available():
    """Indica si el backend de sensores está disponible/conectado."""
    return _backend_available()


def get_hwinfo_sensors():
    """Obtiene las lecturas de sensores del backend activo."""
    return _backend_sensors()


def get_hwinfo_reader():
    """Devuelve la instancia del lector del backend activo."""
    return _get_reader()


# Configuration
_SENSOR_UPDATE_INTERVAL = 0.5

# Track initialization state
# NOTA: HAS_HWINFO conserva su nombre por retrocompatibilidad, pero en Linux
# significa "el backend de sensores nativo está conectado".
HAS_HWINFO = False
HWINFO_ERROR = None

# Background sensor thread
_sensor_thread = None
_sensor_thread_running = False
_sensor_data_lock = threading.Lock()
_latest_sensor_data = {
    "cpu_temp": 0,
    "cpu_clock": 0,
    "cpu_power": 0,
    "gpu_temp": 0,
    "gpu_percent": 0,
    "gpu_clock": 0,
    "gpu_memory_clock": 0,
    "gpu_memory_percent": 0,
    "gpu_power": 0,
}

# Smoothing configuration
# Lower factor = smoother but slower response, higher = faster but jumpier
_SMOOTHING_FACTOR = 0.15  # 15% new value, 85% previous (smooth transitions)
_smoothed_values = {}

# All sensors get smoothed for consistent visual appearance
_SMOOTHED_SENSORS = {
    "cpu_temp", "cpu_clock", "cpu_power", "cpu_percent",
    "gpu_temp", "gpu_clock", "gpu_power", "gpu_percent",
    "gpu_memory_clock", "gpu_memory_percent",
}


def _apply_smoothing(raw_data):
    """Apply exponential smoothing to sensor values that fluctuate rapidly."""
    global _smoothed_values

    smoothed = raw_data.copy()

    for key in _SMOOTHED_SENSORS:
        if key in raw_data:
            raw_value = raw_data[key]
            if key in _smoothed_values and _smoothed_values[key] > 0:
                smoothed[key] = _smoothed_values[key] * (1 - _SMOOTHING_FACTOR) + raw_value * _SMOOTHING_FACTOR
            else:
                smoothed[key] = raw_value
            _smoothed_values[key] = smoothed[key]

    return smoothed


def _sensor_polling_thread():
    """Background thread that continuously polls sensors from HWiNFO."""
    global _latest_sensor_data, _sensor_thread_running, HAS_HWINFO

    while _sensor_thread_running:
        try:
            if is_hwinfo_available():
                if not HAS_HWINFO:
                    HAS_HWINFO = True
                    print(f"[Sensors] Connected to {SENSOR_BACKEND_NAME}")

                data = get_hwinfo_sensors()
                if data and any(v > 0 for v in data.values()):
                    smoothed_data = _apply_smoothing(data)
                    with _sensor_data_lock:
                        _latest_sensor_data = smoothed_data
            else:
                if HAS_HWINFO:
                    HAS_HWINFO = False
                    print(f"[Sensors] Lost connection to {SENSOR_BACKEND_NAME}")

        except Exception as e:
            print(f"[Sensors] Poll error: {e}")

        time.sleep(_SENSOR_UPDATE_INTERVAL)


def init_sensors(app_dir=None):
    """Initialize the sensor system using HWiNFO shared memory."""
    global HAS_HWINFO, HWINFO_ERROR
    global _sensor_thread, _sensor_thread_running, _latest_sensor_data

    # Stop any existing thread first
    if _sensor_thread_running:
        stop_sensors()

    # Check if the sensor backend is available
    if is_hwinfo_available():
        HAS_HWINFO = True
        print(f"[Sensors] {SENSOR_BACKEND_NAME} detected")

        # Do initial read
        initial_data = get_hwinfo_sensors()
        if initial_data:
            with _sensor_data_lock:
                _latest_sensor_data = initial_data.copy()
    else:
        HAS_HWINFO = False
        if IS_WINDOWS:
            HWINFO_ERROR = "HWiNFO not running or shared memory not enabled"
            print("[Sensors] HWiNFO not available")
            print("[Sensors] Please start HWiNFO with 'Shared Memory Support' enabled")
        else:
            HWINFO_ERROR = "No se pudieron leer los sensores del sistema (¿falta psutil?)"
            print("[Sensors] Backend de sensores de Linux no disponible")
            print("[Sensors] Instala las dependencias: pip install psutil nvidia-ml-py")

    # Start background polling thread (will keep trying if backend appears later)
    _sensor_thread_running = True
    _sensor_thread = threading.Thread(target=_sensor_polling_thread, daemon=True)
    _sensor_thread.start()

    if HAS_HWINFO:
        print("[Sensors] Background polling started")
    else:
        print(f"[Sensors] Background polling started (waiting for {SENSOR_BACKEND_NAME})")

    return HAS_HWINFO


def get_cached_sensors():
    """Get sensor data from background thread cache (non-blocking)."""
    with _sensor_data_lock:
        return _latest_sensor_data.copy()


def get_sensors_sync():
    """Get sensor data synchronously from HWiNFO."""
    if is_hwinfo_available():
        return get_hwinfo_sensors()
    return None


# Aliases for backwards compatibility
get_lhm_sensors = get_cached_sensors
get_lhm_sensors_sync = get_sensors_sync


def stop_sensors():
    """Stop the sensor background thread."""
    global _sensor_thread_running, _sensor_thread, HAS_HWINFO

    print("[Sensors] Stopping sensor monitoring...")

    _sensor_thread_running = False
    if _sensor_thread and _sensor_thread.is_alive():
        _sensor_thread.join(timeout=3.0)
    _sensor_thread = None

    # Disconnect HWiNFO
    try:
        reader = get_hwinfo_reader()
        reader.disconnect()
    except:
        pass

    HAS_HWINFO = False
    print("[Sensors] Sensor monitoring stopped")


def get_sensor_source():
    """Get the current sensor source name."""
    return ("hwinfo" if IS_WINDOWS else "linux") if HAS_HWINFO else None


def get_sensor_source_display():
    """Get a user-friendly sensor source name."""
    if HAS_HWINFO:
        return SENSOR_BACKEND_NAME
    else:
        return "Not connected"
