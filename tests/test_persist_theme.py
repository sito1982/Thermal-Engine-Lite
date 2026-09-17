"""Persistencia del tema recibido por push (predeterminado tras reinicio)."""

import copy
import json
import os

from lite_config import DEFAULT_CONFIG
from runtime import ThemeRuntime

THEME = {
    "name": "Pushed",
    "targets": {"web": False},
    "lcd": {"display_width": 800, "display_height": 480, "elements": []},
}


def _runtime(path):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["targets"] = {"web": False, "lcd": False, "dmd": False, "hdmi": False}
    cfg["watch_theme"] = False
    cfg["theme_path"] = path
    return ThemeRuntime(cfg)


def test_push_persists_raw_json(qapp, tmp_path):
    path = str(tmp_path / "theme.json")
    runtime = _runtime(path)
    try:
        runtime.load_theme_dict(THEME, source="push")
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as handle:
            assert json.load(handle) == THEME
        assert runtime._last_persist[0] is True
        assert runtime._theme_mtime == os.path.getmtime(path)
    finally:
        runtime.stop()


def test_preset_does_not_persist(qapp, tmp_path):
    path = str(tmp_path / "theme.json")
    runtime = _runtime(path)
    try:
        runtime.load_theme_dict(THEME, source="preset")
        assert not os.path.exists(path)
    finally:
        runtime.stop()


def test_persist_without_theme_path(qapp):
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    cfg["targets"] = {"web": False}
    cfg["watch_theme"] = False
    cfg["theme_path"] = ""
    runtime = ThemeRuntime(cfg)
    try:
        ok, error = runtime.persist_theme(THEME)
        assert ok is False
        assert error
    finally:
        runtime.stop()


def test_backup_created_and_rotated(qapp, tmp_path):
    path = tmp_path / "theme.json"
    runtime = _runtime(str(path))
    try:
        runtime.config["theme_backups"] = 2
        for i in range(4):
            theme = dict(THEME, name=f"T{i}")
            runtime.load_theme_dict(theme, source="push")
        bak = tmp_path / "theme.bak"
        backups = sorted(bak.glob("*.json"))
        # 4 pushes -> se respalda antes de cada uno menos el primero; rota a 2.
        assert len(backups) == 2
    finally:
        runtime.stop()


def test_persist_false_does_not_write(qapp, tmp_path):
    path = str(tmp_path / "theme.json")
    runtime = _runtime(path)
    try:
        runtime.load_theme_dict(THEME, source="push", persist=False)
        assert not os.path.exists(path)
    finally:
        runtime.stop()
