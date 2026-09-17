"""
Sensor hub - recoleccion de datos del sistema para ThermalEngineLite.

Extraido de Thermal-Engine-Studio (main_window.py). Mantiene un hilo en segundo
plano que consulta psutil (CPU/RAM/red/disco/uptime) y combina esos datos con el
backend de sensores de la plataforma (HWiNFO en Windows; linux_sensors en Linux)
para producir el diccionario ``sensor_data`` que consumen los elementos del tema.
"""

import threading
import time

import psutil

import disks
import sensors
from constants import SOURCE_UNITS
from sensors import get_cached_sensors

# Background psutil data collection
_psutil_data = {
    'cpu_percent': 0,
    'ram_percent': 0,
    'ram_used': 0,
    'ram_available': 0,
    'net_upload': 0,
    'net_download': 0,
    'disk_read': 0,
    'disk_write': 0,
    'uptime': 0,
}
_psutil_data_lock = threading.Lock()
_psutil_thread = None
_psutil_thread_running = False
_cpu_percent_history = []
_last_net_io = None
_last_net_time = 0
_last_disk_io = None
_last_disk_time = 0
_psutil_consecutive_errors = 0


def _psutil_polling_thread():
    """Background thread that continuously polls psutil data."""
    global _psutil_data, _psutil_thread_running, _cpu_percent_history
    global _last_net_io, _last_net_time, _psutil_consecutive_errors
    global _last_disk_io, _last_disk_time

    # Initialize CPU percent
    try:
        psutil.cpu_percent(interval=None)
    except Exception:
        pass

    while _psutil_thread_running:
        try:
            # CPU (smoothed)
            raw_cpu = psutil.cpu_percent(interval=None)
            _cpu_percent_history.append(raw_cpu)
            if len(_cpu_percent_history) > 5:
                _cpu_percent_history.pop(0)
            smoothed_cpu = sum(_cpu_percent_history) / len(_cpu_percent_history)

            # RAM
            ram = psutil.virtual_memory()

            # Network
            net_upload = 0
            net_download = 0
            try:
                net_io = psutil.net_io_counters()
                current_time = time.time()
                if _last_net_io and _last_net_time:
                    time_delta = current_time - _last_net_time
                    if time_delta > 0:
                        bytes_sent = net_io.bytes_sent - _last_net_io.bytes_sent
                        bytes_recv = net_io.bytes_recv - _last_net_io.bytes_recv
                        net_upload = (bytes_sent / time_delta) / (1024 * 1024)
                        net_download = (bytes_recv / time_delta) / (1024 * 1024)
                _last_net_io = net_io
                _last_net_time = current_time
            except Exception:
                pass

            # Disk I/O (read/write MB/s) y uptime del sistema
            disk_read = 0
            disk_write = 0
            uptime_hours = 0
            try:
                disk_io = psutil.disk_io_counters()
                current_time = time.time()
                if disk_io and _last_disk_io and _last_disk_time:
                    time_delta = current_time - _last_disk_time
                    if time_delta > 0:
                        read_bytes = disk_io.read_bytes - _last_disk_io.read_bytes
                        write_bytes = disk_io.write_bytes - _last_disk_io.write_bytes
                        disk_read = (read_bytes / time_delta) / (1024 * 1024)
                        disk_write = (write_bytes / time_delta) / (1024 * 1024)
                _last_disk_io = disk_io
                _last_disk_time = current_time
            except Exception:
                pass
            try:
                uptime_hours = (time.time() - psutil.boot_time()) / 3600.0
            except Exception:
                pass


            # Update shared data
            with _psutil_data_lock:
                _psutil_data['cpu_percent'] = round(smoothed_cpu, 1)
                _psutil_data['ram_percent'] = ram.percent
                _psutil_data['ram_used'] = round(ram.used / (1024**3), 1)
                _psutil_data['ram_available'] = round(ram.available / (1024**3), 1)
                _psutil_data['net_upload'] = round(net_upload, 2)
                _psutil_data['net_download'] = round(net_download, 2)
                _psutil_data['disk_read'] = round(disk_read, 2)
                _psutil_data['disk_write'] = round(disk_write, 2)
                _psutil_data['uptime'] = round(uptime_hours, 1)

            _psutil_consecutive_errors = 0

        except Exception as e:
            _psutil_consecutive_errors += 1
            if _psutil_consecutive_errors <= 3:  # Only log first few errors
                print(f"[Psutil] Background poll error: {e}")
            # Reset state on repeated errors (might help after sleep/wake)
            if _psutil_consecutive_errors > 10:
                _cpu_percent_history.clear()
                _psutil_consecutive_errors = 0
                try:
                    psutil.cpu_percent(interval=None)  # Re-initialize
                except Exception:
                    pass

        # Poll every 500ms - balances responsiveness with CPU usage
        time.sleep(0.5)


def start_psutil_thread():
    """Start the background psutil polling thread."""
    global _psutil_thread, _psutil_thread_running
    if _psutil_thread is None or not _psutil_thread.is_alive():
        _psutil_thread_running = True
        _psutil_thread = threading.Thread(target=_psutil_polling_thread, daemon=True)
        _psutil_thread.start()
        print("[Psutil] Background polling thread started")


def stop_psutil_thread():
    """Stop the background psutil polling thread."""
    global _psutil_thread_running, _psutil_thread
    _psutil_thread_running = False
    if _psutil_thread and _psutil_thread.is_alive():
        _psutil_thread.join(timeout=1.0)
    _psutil_thread = None


def get_psutil_data():
    """Get psutil data from background thread cache (non-blocking)."""
    global _psutil_thread
    if _psutil_thread_running and (_psutil_thread is None or not _psutil_thread.is_alive()):
        print("[Psutil] Thread died, restarting...")
        _psutil_thread = threading.Thread(target=_psutil_polling_thread, daemon=True)
        _psutil_thread.start()

    with _psutil_data_lock:
        return _psutil_data.copy()


def resolve_sensor_value(sensor_data, source):
    """Resuelve el valor de una fuente.

    Acepta el prefijo ``lite.`` que usan los proyectos Lite de Studio (sus
    fuentes se exponen como ``lite.<clave>``); al publicar el tema, Lite debe
    resolverlas contra sus propias claves.
    """
    if not isinstance(source, str):
        return None
    if source in sensor_data:
        return sensor_data[source]
    if source.startswith("lite."):
        return sensor_data.get(source[5:])
    return None


def get_sensor_data():
    """Get sensor data from background threads (non-blocking)."""
    psutil_data = get_psutil_data()

    data = {
        'static': 50,
        # CPU
        'cpu_percent': psutil_data['cpu_percent'],
        'cpu_temp': 0,
        'cpu_clock': 0,
        'cpu_power': 0,
        # GPU
        'gpu_percent': 0,
        'gpu_temp': 0,
        'gpu_clock': 0,
        'gpu_memory_percent': 0,
        'gpu_memory_clock': 0,
        'gpu_memory_used': 0,
        'gpu_power': 0,
        'gpu_fan': 0,
        'gpu_fan_percent': 0,
        # RAM
        'ram_percent': psutil_data['ram_percent'],
        'ram_used': psutil_data['ram_used'],
        'ram_available': psutil_data['ram_available'],
        # Network
        'net_upload': psutil_data['net_upload'],
        'net_download': psutil_data['net_download'],
        # Storage
        'disk_read': psutil_data['disk_read'],
        'disk_write': psutil_data['disk_write'],
        # Fans / FPS / System
        'cpu_fan': 0,
        'sys_fan': 0,
        'pump': 0,
        'game_fps': 0,
        'nvme_temp': 0,
        'mainboard_temp': 0,
        'uptime': psutil_data['uptime'],
    }

    # Extra sensors from the platform backend (HWiNFO / linux_sensors)
    if getattr(sensors, "HAS_HWINFO", False):
        try:
            hwinfo_data = get_cached_sensors()
            if hwinfo_data:
                if hwinfo_data.get('cpu_temp', 0) > 0:
                    data['cpu_temp'] = hwinfo_data['cpu_temp']
                if hwinfo_data.get('cpu_clock', 0) > 0:
                    data['cpu_clock'] = hwinfo_data['cpu_clock']
                if hwinfo_data.get('cpu_power', 0) > 0:
                    data['cpu_power'] = hwinfo_data['cpu_power']
                if hwinfo_data.get('gpu_temp', 0) > 0:
                    data['gpu_temp'] = hwinfo_data['gpu_temp']
                if hwinfo_data.get('gpu_percent', 0) > 0:
                    data['gpu_percent'] = hwinfo_data['gpu_percent']
                if hwinfo_data.get('gpu_clock', 0) > 0:
                    data['gpu_clock'] = hwinfo_data['gpu_clock']
                if hwinfo_data.get('gpu_memory_percent', 0) > 0:
                    data['gpu_memory_percent'] = hwinfo_data['gpu_memory_percent']
                if hwinfo_data.get('gpu_memory_clock', 0) > 0:
                    data['gpu_memory_clock'] = hwinfo_data['gpu_memory_clock']
                if hwinfo_data.get('gpu_power', 0) > 0:
                    data['gpu_power'] = hwinfo_data['gpu_power']
                for key in ('gpu_memory_used', 'gpu_fan', 'gpu_fan_percent',
                            'cpu_fan', 'sys_fan', 'pump', 'game_fps',
                            'nvme_temp', 'mainboard_temp'):
                    value = hwinfo_data.get(key, 0)
                    if value:
                        data[key] = value
        except Exception as e:
            print(f"Sensor read error: {e}")

    # Discos (espacio y E/S) como fuentes por defecto, sin configuracion.
    disks.register_units(SOURCE_UNITS)
    data.update(disks.disk_values())

    return data
