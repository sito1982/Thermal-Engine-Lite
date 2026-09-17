"""Tests del elemento Icon en ThermalEngineLite."""

from constants import DMD_ELEMENT_TYPES, ELEMENT_TYPES, resolve_icon_path
from element import ThemeElement


def test_icon_registered_and_not_dmd():
    assert "icon" in ELEMENT_TYPES
    assert "icon" not in DMD_ELEMENT_TYPES


def test_resolve_icon_path_is_safe():
    assert resolve_icon_path("cpu1.png") is not None
    assert resolve_icon_path("../element.py") is None
    assert resolve_icon_path("does_not_exist.png") is None


def test_icon_fields_round_trip():
    element = ThemeElement("icon", icon_name="gpu2.png", tint=True)
    clone = ThemeElement.from_dict(element.to_dict())
    assert clone.icon_name == "gpu2.png"
    assert clone.tint is True


def test_canvas_draws_icon(qapp):
    from PySide6.QtGui import QImage, QPainter

    from canvas import HDMICanvas

    canvas = HDMICanvas(200, 200)
    canvas.scale = 1.0
    image = QImage(200, 200, QImage.Format.Format_RGBA8888)
    image.fill(0)
    painter = QPainter(image)
    element = ThemeElement("icon", icon_name="cpu1.png", x=0, y=0,
                           width=140, height=140)
    canvas.draw_element(painter, element, selected=False)
    painter.end()
    assert image.pixelColor(70, 70).alpha() > 0
