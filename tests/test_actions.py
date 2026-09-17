"""Tests para la ejecución de acciones de elementos (toque HDMI)."""

import actions
from element import ThemeElement


def test_parse_action_none_by_default():
    assert actions.parse_action(ThemeElement("text")) is None


def test_parse_action_command():
    element = ThemeElement(
        "text", tap_action="command", tap_command="/bin/echo",
        tap_args=["hi"], tap_workdir="/tmp",
    )
    assert actions.parse_action(element) == {
        "type": "command", "command": "/bin/echo",
        "args": ["hi"], "workdir": "/tmp",
    }


def test_parse_action_requires_command():
    element = ThemeElement("text", tap_action="command", tap_command="   ")
    assert actions.parse_action(element) is None


def test_validate_action():
    assert actions.validate_action("", [], "")  # comando vacío -> error
    assert actions.validate_action("/bin/echo", ["ok"], "") == []
    assert actions.validate_action("/bin/echo", "not-a-list", "") != []
    assert actions.validate_action("/bin/echo", [], "/no/such/dir") != []
    assert actions.validate_action("/bin/echo", ["a\x00b"], "") != []


def test_args_text_roundtrip():
    args = actions.parse_args_text('--foo "bar baz"')
    assert args == ["--foo", "bar baz"]
    assert actions.parse_args_text(actions.args_to_text(args)) == args


def test_fingerprint_stable_and_distinct():
    same_a = actions.action_fingerprint("/bin/echo", ["x"])
    same_b = actions.action_fingerprint("/bin/echo", ["x"])
    different = actions.action_fingerprint("/bin/echo", ["y"])
    assert same_a == same_b
    assert same_a != different


class _FakeQProcess:
    calls = []

    @staticmethod
    def startDetached(program, args, workdir):
        _FakeQProcess.calls.append((program, list(args), workdir))
        return (True, 1234)


def test_run_action_uses_start_detached(monkeypatch):
    _FakeQProcess.calls = []
    monkeypatch.setattr(actions, "QProcess", _FakeQProcess)
    ok, message = actions.run_action(
        {"command": "/bin/echo", "args": ["hi"], "workdir": "/tmp"})
    assert ok
    assert _FakeQProcess.calls == [("/bin/echo", ["hi"], "/tmp")]
    assert "1234" in message


def test_run_action_missing_path_does_not_launch(monkeypatch):
    monkeypatch.setattr(actions, "QProcess", _FakeQProcess)
    _FakeQProcess.calls = []
    ok, _ = actions.run_action(
        {"command": "/no/such/binary", "args": [], "workdir": ""})
    assert not ok
    assert _FakeQProcess.calls == []
