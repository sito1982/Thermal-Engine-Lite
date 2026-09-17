"""Tests del lector best-effort de FPS de juego (MangoHud)."""

from linux_sensors import _read_game_fps


def test_reads_plain_number(tmp_path):
    path = tmp_path / "fps.txt"
    path.write_text("143.5\n")
    assert _read_game_fps(str(path)) == 143.5


def test_reads_mangohud_csv_last_row(tmp_path):
    path = tmp_path / "log.csv"
    path.write_text(
        "fps,frametime,cpu_load\n"
        "60,16.6,10\n"
        "144,6.9,22\n"
    )
    assert _read_game_fps(str(path)) == 144.0


def test_missing_fps_column_returns_none(tmp_path):
    path = tmp_path / "log.csv"
    path.write_text("frametime,cpu_load\n16.6,10\n")
    assert _read_game_fps(str(path)) is None
