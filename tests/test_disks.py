"""Sensores de discos (espacio/E-S) y resolucion del prefijo `lite.`."""

import disks
from sensor_hub import resolve_sensor_value


class _Part:
    def __init__(self, device, mountpoint, fstype):
        self.device = device
        self.mountpoint = mountpoint
        self.fstype = fstype


class _Usage:
    def __init__(self, total, used, free, percent):
        self.total = total
        self.used = used
        self.free = free
        self.percent = percent


def _reset():
    disks._cache.update({"ts": 0.0, "mounts": [], "values": {}})
    disks._io_prev.update({"ts": 0.0, "dev": {}})


def _mock(monkeypatch):
    _reset()
    parts = [
        _Part("/dev/nvme0n1p2", "/", "ext4"),
        _Part("/dev/nvme0n1p1", "/boot/efi", "vfat"),
        _Part("tmpfs", "/run", "tmpfs"),
        _Part("overlay", "/var/lib/docker", "overlay"),
    ]
    usage = {
        "/": _Usage(1000e9, 400e9, 600e9, 40.0),
        "/boot/efi": _Usage(500e6, 100e6, 400e6, 20.0),
    }
    monkeypatch.setattr(disks.psutil, "disk_partitions", lambda all=False: parts)
    monkeypatch.setattr(disks.psutil, "disk_usage", lambda mp: usage[mp])
    monkeypatch.setattr(disks.psutil, "disk_io_counters", lambda perdisk=True: {})
    disks._refresh(force=True)


def test_slug():
    assert disks._slug("/") == "root"
    assert disks._slug("/home") == "home"
    assert disks._slug("/var/lib/vz") == "var_lib_vz"
    assert disks._slug("C:\\") == "c"


def test_values_and_filtering(monkeypatch):
    _mock(monkeypatch)
    values = disks.disk_values()
    assert values["disk.root.total"] == 1000.0
    assert values["disk.root.used"] == 400.0
    assert values["disk.root.free"] == 600.0
    assert values["disk.root.percent"] == 40.0
    assert "disk.run.total" not in values        # tmpfs filtrado
    assert "disk.var_lib_docker.total" not in values  # overlay filtrado
    # agregado = 1000 + 0.5 GB total, 400 + 0.1 GB usado
    assert values["disk.all.total"] == 1000.5
    assert round(values["disk.all.used"], 2) == 400.1
    assert values["disk.all.percent"] == 40.0


def test_sources_units(monkeypatch):
    _mock(monkeypatch)
    sources = {s[0]: s for s in disks.disk_sources()}
    assert sources["disk.root.total"][2] == "size"
    assert sources["disk.root.total"][3] == "GB"
    assert sources["disk.root.percent"][2] == "percent"
    assert sources["disk.all.read"][2] == "speed"
    assert "NVMe /" in sources["disk.root.total"][1]


def test_register_units(monkeypatch):
    _mock(monkeypatch)
    units = {}
    disks.register_units(units)
    assert units["disk.root.total"] == {
        "name": units["disk.root.total"]["name"], "type": "size", "symbol": "GB"}


def test_resolve_lite_prefix():
    data = {"cpu_temp": 50.0, "disk.root.used": 400.0}
    assert resolve_sensor_value(data, "cpu_temp") == 50.0
    assert resolve_sensor_value(data, "disk.root.used") == 400.0
    assert resolve_sensor_value(data, "lite.cpu_temp") == 50.0
    assert resolve_sensor_value(data, "lite.disk.root.used") == 400.0
    assert resolve_sensor_value(data, "nope") is None
