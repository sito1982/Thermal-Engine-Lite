"""Datos de discos (espacio y E/S) como fuentes de datos por defecto.

Expone, por cada punto de montaje/particion, un conjunto de claves estables:

    disk.<slug>.used     espacio usado (GB)
    disk.<slug>.total    espacio total (GB)
    disk.<slug>.free     espacio libre (GB)
    disk.<slug>.percent  uso (%)
    disk.<slug>.read     lectura (MB/s)
    disk.<slug>.write    escritura (MB/s)

y un agregado de todos los discos en ``disk.all.*``.

No depende de ``constants`` (para evitar ciclos): es autonoma y cachea el sondeo
para no penalizar el render. Solo usa ``psutil``.
"""

from __future__ import annotations

import os
import re
import time

import psutil

# Tiempo de cache del sondeo (espacio + tasas de E/S).
_TTL = 2.0

# Sistemas de ficheros que no representan un disco real.
_PSEUDO_FS = {
    "tmpfs", "devtmpfs", "devfs", "squashfs", "overlay", "aufs", "ramfs",
    "proc", "procfs", "sysfs", "cgroup", "cgroup2", "debugfs", "tracefs",
    "securityfs", "pstore", "bpf", "configfs", "nsfs", "mqueue",
    "hugetlbfs", "fusectl", "autofs", "efivarfs", "binfmt_misc",
}

_METRICS = (
    ("used", "used", "size", "GB"),
    ("total", "total", "size", "GB"),
    ("free", "free", "size", "GB"),
    ("percent", "usage", "percent", "%"),
    ("read", "read", "speed", "MB/s"),
    ("write", "write", "speed", "MB/s"),
)

_cache = {"ts": 0.0, "mounts": [], "values": {}}
_io_prev = {"ts": 0.0, "dev": {}}


def _slug(mount):
    """Slug estable y legible para un punto de montaje."""
    m = (mount or "").strip()
    if len(m) == 3 and m[1] == ":":  # Windows: C:\ -> c
        return m[0].lower()
    m = m.strip("/\\")
    if not m:
        return "root"
    m = re.sub(r"[^A-Za-z0-9]+", "_", m).strip("_").lower()
    return m or "root"


def _base_device(device):
    """Dispositivo base de una particion (nvme0n1p2 -> nvme0n1, sda2 -> sda)."""
    dev = os.path.basename(device or "")
    if not dev:
        return ""
    m = re.match(r"^(nvme\d+n\d+|mmcblk\d+)p\d+$", dev)
    if m:
        return m.group(1)
    m = re.match(r"^([a-z]+)(\d+)$", dev)
    if m and not dev.startswith("nvme"):
        return m.group(1)
    return dev


def _kind(device, base):
    """Tipo de disco: NVMe / SSD / HDD / Disk."""
    if "nvme" in (device or "").lower():
        return "NVMe"
    try:
        with open(f"/sys/block/{base}/queue/rotational") as handle:
            return "HDD" if handle.read().strip() == "1" else "SSD"
    except OSError:
        return "Disk"


def _is_real(device, fstype):
    if (fstype or "").lower() in _PSEUDO_FS:
        return False
    if os.name == "nt":
        return bool(device)
    return (device or "").startswith("/dev/")


def _io_rates():
    """Tasas de E/S (MB/s) por dispositivo base, calculadas por diferencias."""
    now = time.monotonic()
    rates = {}
    try:
        counters = psutil.disk_io_counters(perdisk=True) or {}
    except Exception:
        counters = {}
    prev_ts = _io_prev["ts"]
    dt = now - prev_ts if prev_ts else 0.0
    for name, c in counters.items():
        prev = _io_prev["dev"].get(name)
        if prev and dt > 0:
            rates[name] = {
                "read": max(0.0, (c.read_bytes - prev[0]) / dt / 1e6),
                "write": max(0.0, (c.write_bytes - prev[1]) / dt / 1e6),
            }
    _io_prev["ts"] = now
    _io_prev["dev"] = {n: (c.read_bytes, c.write_bytes) for n, c in counters.items()}
    return rates


def _refresh(force=False):
    now = time.monotonic()
    if not force and _cache["mounts"] and (now - _cache["ts"]) < _TTL:
        return

    mounts = []
    seen = set()
    try:
        partitions = psutil.disk_partitions(all=False)
    except Exception:
        partitions = []
    for p in partitions:
        device = getattr(p, "device", "")
        mount = getattr(p, "mountpoint", "")
        fstype = getattr(p, "fstype", "")
        if not _is_real(device, fstype):
            continue
        slug = _slug(mount)
        if slug in seen:
            continue
        try:
            usage = psutil.disk_usage(mount)
        except Exception:
            continue
        seen.add(slug)
        base = _base_device(device)
        mounts.append({
            "slug": slug,
            "mount": mount,
            "device": device,
            "base": base,
            "kind": _kind(device, base),
            "total": usage.total / 1e9,
            "used": usage.used / 1e9,
            "free": usage.free / 1e9,
            "percent": float(usage.percent),
        })

    rates = _io_rates()

    values = {}
    sum_total = sum_used = sum_free = 0.0
    for m in mounts:
        s = m["slug"]
        values[f"disk.{s}.used"] = round(m["used"], 1)
        values[f"disk.{s}.total"] = round(m["total"], 1)
        values[f"disk.{s}.free"] = round(m["free"], 1)
        values[f"disk.{s}.percent"] = round(m["percent"], 1)
        rate = rates.get(m["base"], {})
        values[f"disk.{s}.read"] = round(rate.get("read", 0.0), 2)
        values[f"disk.{s}.write"] = round(rate.get("write", 0.0), 2)
        sum_total += m["total"]
        sum_used += m["used"]
        sum_free += m["free"]

    values["disk.all.total"] = round(sum_total, 1)
    values["disk.all.used"] = round(sum_used, 1)
    values["disk.all.free"] = round(sum_free, 1)
    values["disk.all.percent"] = (
        round(sum_used / sum_total * 100, 1) if sum_total else 0.0)
    values["disk.all.read"] = round(sum(r.get("read", 0.0) for r in rates.values()), 2)
    values["disk.all.write"] = round(sum(r.get("write", 0.0) for r in rates.values()), 2)

    _cache.update({"ts": now, "mounts": mounts, "values": values})


def enumerate_disks():
    """Lista (cacheada) de montajes con sus datos."""
    _refresh()
    return list(_cache["mounts"])


def disk_values():
    """Valores actuales ``{source_id: float}`` (cacheado)."""
    _refresh()
    return dict(_cache["values"])


def disk_sources():
    """Fuentes para el selector: ``[(id, name, unit_type, symbol)]``."""
    _refresh()
    out = []
    for m in _cache["mounts"]:
        label = f"{m['kind']} {m['mount']}"
        for key, name, unit, sym in _METRICS:
            out.append((f"disk.{m['slug']}.{key}", f"{label} {name}", unit, sym))
    for key, name, unit, sym in _METRICS:
        out.append((f"disk.all.{key}", f"ALL disks {name}", unit, sym))
    return out


def register_units(units):
    """Registra las unidades de los discos en un dict tipo ``SOURCE_UNITS``."""
    for source_id, name, unit, symbol in disk_sources():
        units[source_id] = {"name": name, "type": unit, "symbol": symbol}
