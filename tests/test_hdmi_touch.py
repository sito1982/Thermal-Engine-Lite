"""Tests para el toque en la salida HDMI (mapeo, hit-test, flash)."""

from PySide6.QtGui import QImage

from canvas import CanvasPreview
from device_hdmi import HDMIOutputWindow
from element import ThemeElement


def test_canvas_point_full_frame():
    assert HDMIOutputWindow.canvas_point(50, 50, 100, 100, 1000, 1000) == (500.0, 500.0)
    assert HDMIOutputWindow.canvas_point(0, 0, 100, 100, 1000, 1000) == (0.0, 0.0)


def test_canvas_point_pillarbox_and_outside():
    # Contenedor 200x100, imagen 100x100 -> se dibuja a 100x100 centrada en x=50.
    assert HDMIOutputWindow.canvas_point(100, 50, 200, 100, 100, 100) == (50.0, 50.0)
    # Barra negra a la izquierda -> fuera
    assert HDMIOutputWindow.canvas_point(10, 50, 200, 100, 100, 100) is None
    # Fuera verticalmente
    assert HDMIOutputWindow.canvas_point(100, 150, 200, 100, 100, 100) is None


def test_hit_test_front_to_back_scale_one():
    front = ThemeElement("rectangle", name="front", x=10, y=10, width=100, height=50)
    back = ThemeElement("rectangle", name="back", x=0, y=0, width=200, height=100)
    elements = [front, back]
    assert CanvasPreview.hit_test_elements(elements, 50, 30) == 0
    assert CanvasPreview.hit_test_elements(elements, 5, 5) == 1
    assert CanvasPreview.hit_test_elements(elements, 500, 500) == -1


def test_hit_test_circle_gauge():
    gauge = ThemeElement("circle_gauge", name="g", x=100, y=100, radius=50)
    assert CanvasPreview.hit_test_elements([gauge], 100, 100) == 0
    assert CanvasPreview.hit_test_elements([gauge], 100, 100 + 60) == -1


def test_hit_test_visible_only():
    hidden = ThemeElement("rectangle", name="h", x=0, y=0, width=100, height=100,
                          visible=False)
    assert CanvasPreview.hit_test_elements([hidden], 50, 50) == 0
    assert CanvasPreview.hit_test_elements([hidden], 50, 50, visible_only=True) == -1


def test_flash_state(qapp):
    window = HDMIOutputWindow()
    window.flash_element(1, 2, 30, 40)
    assert window._flash == (1.0, 2.0, 30.0, 40.0)
    window._clear_flash()
    assert window._flash is None
    window.close_output()


def test_widget_to_canvas_mapping(qapp):
    window = HDMIOutputWindow()
    window._image = QImage(100, 100, QImage.Format.Format_RGB888)
    window.resize(200, 100)
    assert window.widget_to_canvas(100, 50) == (50.0, 50.0)
    window.close_output()
