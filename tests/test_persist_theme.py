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
