"""Tests de la API HTTP de ThermalEngineLite (/info, /sensors)."""

import pytest

import webserver


class _FakeRuntime:
    def info(self):
        return {"app": "ThermalEngineLite", "version": "0.2.0",
                "hostname": "pve", "targets": {"web": True, "dmd": True}}

    def get_sensor_data(self):
        return {"static": 50, "cpu_temp": 42.5, "cpu_percent": 5.0,
                "ram_percent": 70.0}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(webserver, "_RUNTIME", _FakeRuntime())
    monkeypatch.setattr(webserver, "_TOKEN", "tok")
    webserver.app.config["TESTING"] = True
    return webserver.app.test_client()


def test_info(client):
    resp = client.get("/info")
    assert resp.status_code == 200
    assert resp.get_json()["hostname"] == "pve"


def test_sensors_requires_token(client):
    resp = client.get("/sensors")
    assert resp.status_code == 401


def test_sensors_rejects_bad_token(client):
    resp = client.get("/sensors", headers={"X-Token": "nope"})
    assert resp.status_code == 401


def test_sensors_with_token(client):
    resp = client.get("/sensors", headers={"X-Token": "tok"})
    assert resp.status_code == 200
    assert resp.get_json()["cpu_temp"] == 42.5


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json()["ready"] is True


def _push(client, monkeypatch, persist_state, persist_param=None):
    seen = {}

    class _Runtime:
        _last_persist = persist_state

        def load_theme_dict(self, data, source="push", persist=None):
            seen["persist"] = persist

            class _Theme:
                name = "x"
            return _Theme()

    monkeypatch.setattr(webserver, "_RUNTIME", _Runtime())
    monkeypatch.setattr(webserver, "run_on_qt_and_wait",
                        lambda fn, timeout=5.0: (fn(), None))
    url = "/theme"
    if persist_param is not None:
        url += f"?persist={persist_param}"
    return client.post(url, json={"name": "x"}, headers={"X-Token": "tok"}), seen


def test_push_theme_reports_persisted(client, monkeypatch):
    resp, seen = _push(client, monkeypatch, (True, None))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["persisted"] is True
    assert seen["persist"] is True


def test_push_theme_reports_persist_failure(client, monkeypatch):
    resp, _ = _push(client, monkeypatch, (False, "read-only"))
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["persisted"] is False
    assert body["persist_error"] == "read-only"


def test_push_theme_persist_zero_applies_without_saving(client, monkeypatch):
    resp, seen = _push(client, monkeypatch, (True, None), persist_param="0")
    assert resp.status_code == 200
    assert seen["persist"] is False
