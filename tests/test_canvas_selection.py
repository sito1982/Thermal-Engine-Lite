"""Regression tests for stale canvas selection handling."""

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent

from canvas import DMDCanvas
from element import ThemeElement


def _canvas(count):
    canvas = DMDCanvas(128, 32)
    canvas.set_elements([ThemeElement("text", x=i * 4, y=0) for i in range(count)])
    return canvas


def test_set_elements_drops_stale_selection(qapp):
    canvas = _canvas(3)
    canvas.set_selected_indices([2])
    canvas.set_elements([ThemeElement("text")])
    assert canvas.selected_indices == []


def test_set_elements_keeps_valid_selection(qapp):
    canvas = _canvas(3)
    canvas.set_selected_indices([0, 2])
    canvas.set_elements([ThemeElement("text")] * 3)
    assert canvas.selected_indices == [0, 2]


def test_mouse_move_with_stale_selection_does_not_crash(qapp):
    canvas = _canvas(1)
    canvas.selected_indices = [5]
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(4, 4),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mouseMoveEvent(event)
    assert canvas.selected_indices == []


def test_mouse_move_after_shared_list_shrinks(qapp):
    """Reproduce the reported crash: the shared element list is mutated by the
    element list panel and the canvas selection points past the end."""
    canvas = _canvas(3)
    shared = canvas.elements
    canvas.set_selected_indices([2])
    del shared[2]
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        QPointF(4, 4),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    canvas.mouseMoveEvent(event)
    assert canvas.selected_indices == []


def test_reconcile_filters_partial_selection(qapp):
    canvas = _canvas(2)
    canvas.selected_indices = [0, 5]
    assert canvas._reconcile_selection() is True
    assert canvas.selected_indices == [0]
