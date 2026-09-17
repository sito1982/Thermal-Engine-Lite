"""Tests para las nuevas estadísticas (ventiladores, FPS, disco, sistema)."""

from constants import DATA_SOURCES_CATEGORIZED, SOURCE_UNITS

NEW_CATEGORIES = ("Fans", "Performance", "Storage", "System")
NEW_SOURCES = (
    "cpu_fan", "gpu_fan", "gpu_fan_percent", "sys_fan", "pump",
    "game_fps", "disk_read", "disk_write",
    "uptime", "gpu_memory_used", "nvme_temp", "mainboard_temp",
)


def test_new_categories_present():
    for category in NEW_CATEGORIES:
        assert category in DATA_SOURCES_CATEGORIZED
        assert DATA_SOURCES_CATEGORIZED[category]


def test_new_sources_have_units():
    for source in NEW_SOURCES:
        assert source in SOURCE_UNITS
        info = SOURCE_UNITS[source]
        assert info["name"]
        assert info["symbol"]
        assert info["type"]


def test_fan_and_fps_units():
    assert SOURCE_UNITS["cpu_fan"]["symbol"] == "RPM"
    assert SOURCE_UNITS["gpu_fan_percent"]["symbol"] == "%"
    assert SOURCE_UNITS["game_fps"]["symbol"] == "FPS"
    assert SOURCE_UNITS["disk_read"]["symbol"] == "MB/s"
