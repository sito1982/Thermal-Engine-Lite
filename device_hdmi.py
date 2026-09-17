"""Ventana de salida para un monitor externo (HDMI) a pantalla completa.

El target HDMI reutiliza el renderizado del editor (``HDMICanvas``) y lo
muestra en una ventana Qt sin bordes, a pantalla completa, sobre el monitor
seleccionado. Si el tamaño del frame no coincide con la resolución del monitor
(por ejemplo tras cambiar de pantalla) se aplica letterbox centrado con fondo
negro, preservando la proporción.

Además, si el monitor es táctil, la ventana acepta eventos de toque y emite la
señal ``tapped`` con las coordenadas del canvas (píxeles de la imagen), para
que la ventana principal resuelva el elemento y ejecute su acción. Un toque
válido muestra un flash breve como feedback.

Se integra en la misma ``QApplication`` que el editor (sin proceso aparte).
"""

import time

from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QWidget

# Umbrales de un toque válido (evita zooms/paneos/arrastres accidentales).
TAP_MAX_DURATION_S = 0.4
TAP_MAX_MOVEMENT_PX = 20.0
FLASH_DURATION_MS = 150


class HDMIOutputWindow(QWidget):
    """Ventana fullscreen frameless que pinta un ``QImage`` (letterbox)."""

    # Coordenadas del canvas (píxeles de la imagen renderizada).
    tapped = Signal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = None
        self._monitor = None
        self._active = False
        self._touch_start = None
        self._touch_start_time = 0.0
        self._flash = None
        self._flash_timer = None
        self._debug_text = ""
        self._debug_until = 0.0
        self._debug_timer = None

        self.setWindowTitle("Thermal Engine Studio HDMI")
        # Sin WindowDoesNotAcceptFocus: en Wayland KWin entrega el toque a la
        # ventana bajo el dedo, pero algunas configuraciones no lo hacen si la
        # ventana declara que no acepta foco. WA_ShowWithoutActivating evita
        # robar el foco al mostrarse.
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        # Necesario para recibir eventos de toque en el monitor táctil.
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.setAutoFillBackground(True)
        self.setStyleSheet("background-color: #000000;")

    # ------------------------------------------------------------------ API --
    @property
    def is_active(self):
        return self._active

    @property
    def monitor(self):
        return self._monitor

    def show_on_monitor(self, monitor):
        """Muestra la ventana a pantalla completa en el monitor indicado.

        ``monitor`` es una entrada de ``monitors.list_monitors()``.
        """
        self._monitor = monitor
        screen = self._resolve_screen(monitor)
        if screen is not None:
            self._apply_screen(self, screen)
        self.showFullScreen()
        self._active = True

    def set_monitor(self, monitor):
        """Cambia de monitor en caliente (oculta, recoloca y vuelve a fullscreen)."""
        was_visible = self.isVisible()
        self._monitor = monitor
        screen = self._resolve_screen(monitor)
        if screen is None:
            return
        if was_visible:
            self.hide()
        self._apply_screen(self, screen)
        if was_visible:
            self.showFullScreen()
        self._active = was_visible

    def render_frame(self, image: QImage):
        """Guarda el frame actual y solicita repintado."""
        if image is None or image.isNull():
            return
        self._image = image
        if self.isVisible():
            self.update()

    def clear_frame(self):
        self._image = None
        if self.isVisible():
            self.update()

    def flash_element(self, x, y, w, h, duration_ms=FLASH_DURATION_MS):
        """Flash breve sobre un rectángulo del canvas (coords lógicas)."""
        self._flash = (float(x), float(y), float(w), float(h))
        if self._flash_timer is None:
            self._flash_timer = QTimer(self)
            self._flash_timer.setSingleShot(True)
            self._flash_timer.timeout.connect(self._clear_flash)
        self._flash_timer.start(int(duration_ms))
        if self.isVisible():
            self.update()

    def _clear_flash(self):
        self._flash = None
        if self.isVisible():
            self.update()

    def close_output(self):
        self._active = False
        self._image = None
        self._clear_flash()
        if self._flash_timer is not None:
            self._flash_timer.stop()
        self.hide()
        self.close()

    # -------------------------------------------------------------- internos --
    @staticmethod
    def _apply_screen(widget, screen):
        # Qt6 permite fijar la pantalla de la ventana; en X11/XWayland además
        # movemos al topLeft para garantizar la posición.
        try:
            widget.setScreen(screen)
        except (AttributeError, TypeError):
            handle = widget.windowHandle()
            if handle is not None:
                handle.setScreen(screen)
        try:
            widget.move(screen.geometry().topLeft())
        except Exception:
            pass

    def _resolve_screen(self, monitor):
        if monitor is None:
            return None
        app = QGuiApplication.instance()
        if app is None:
            return None
        screens = app.screens()
        index = monitor.get("index", -1)
        if 0 <= index < len(screens):
            return screens[index]
        for screen in screens:
            if (screen.name() or "") == monitor.get("name"):
                return screen
        return None

    # ----------------------------------------------------------------- touch --
    def _register_debug(self, text):
        """Muestra un texto temporal en pantalla y lo imprime en consola."""
        self._debug_text = text
        self._debug_until = time.monotonic() + 2.0
        print(f"[HDMI][Touch] {text}")
        if self._debug_timer is None:
            self._debug_timer = QTimer(self)
            self._debug_timer.setSingleShot(True)
            self._debug_timer.timeout.connect(self._clear_debug)
        self._debug_timer.start(2000)
        if self.isVisible():
            self.update()

    def _clear_debug(self):
        self._debug_text = ""
        if self.isVisible():
            self.update()

    def _handle_tap(self, wx, wy, source):
        """Mapea a coordenadas de canvas, emite ``tapped`` y muestra feedback."""
        canvas = self.widget_to_canvas(wx, wy)
        if canvas is None:
            self._register_debug(f"{source} ({wx:.0f},{wy:.0f}) fuera del frame")
            return
        self._register_debug(
            f"{source} ({wx:.0f},{wy:.0f}) -> ({canvas[0]:.0f},{canvas[1]:.0f})")
        self.tapped.emit(canvas[0], canvas[1])

    def event(self, event):
        # Traza de eventos de entrada para diagnóstico.
        if event.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchEnd,
                            QEvent.Type.TouchCancel):
            print(f"[HDMI][Touch] event {event.type()}")
        return super().event(event)

    def touchEvent(self, event):
        """Gestiona toques. El tap se emite en TouchBegin (toque simple).

        Emitir en ``TouchBegin`` es más fiable entre compositores/paneles que
        esperar a ``TouchEnd`` (que a veces llega sin puntos o no llega).
        """
        points = event.points()
        event_type = event.type()
        if not points:
            event.ignore()
            return
        position = points[0].position()

        if event_type == QEvent.Type.TouchBegin:
            self._touch_start = (position.x(), position.y())
            self._touch_start_time = time.monotonic()
            self._handle_tap(position.x(), position.y(), "touch")
            event.accept()
            return

        if event_type == QEvent.Type.TouchEnd:
            self._touch_start = None
            event.accept()
            return

        if event_type == QEvent.Type.TouchCancel:
            self._touch_start = None
        event.accept()

    def mousePressEvent(self, event):
        """Fallback: algunos paneles/compositors entregan el toque como ratón."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._handle_tap(event.position().x(), event.position().y(), "mouse")
        event.accept()

    # ---------------------------------------------------------------- mapeo --
    @staticmethod
    def canvas_point(wx, wy, container_w, container_h, image_w, image_h):
        """Inverso de ``letterbox_rect``: punto de widget → píxeles de imagen.

        Devuelve ``(x, y)`` en coordenadas del canvas o None si el punto cae
        fuera del frame (barras negras).
        """
        x, y, w, h = HDMIOutputWindow.letterbox_rect(
            container_w, container_h, image_w, image_h)
        if w <= 0 or h <= 0:
            return None
        if not (x <= wx <= x + w and y <= wy <= y + h):
            return None
        return ((wx - x) / w * image_w, (wy - y) / h * image_h)

    def widget_to_canvas(self, wx, wy):
        image = self._image
        if image is None or image.isNull():
            return None
        return self.canvas_point(wx, wy, self.width(), self.height(),
                                 image.width(), image.height())

    # ---------------------------------------------------------------- paint --
    @staticmethod
    def letterbox_rect(container_w, container_h, image_w, image_h):
        """Devuelve ``(x, y, w, h)`` del frame ajustado manteniendo proporción."""
        if image_w <= 0 or image_h <= 0 or container_w <= 0 or container_h <= 0:
            return (0.0, 0.0, 0.0, 0.0)
        scale = min(container_w / image_w, container_h / image_h)
        draw_w = image_w * scale
        draw_h = image_h * scale
        x = (container_w - draw_w) / 2.0
        y = (container_h - draw_h) / 2.0
        return (x, y, draw_w, draw_h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        image = self._image
        if image is None or image.isNull() or self.width() <= 0 or self.height() <= 0:
            painter.end()
            return

        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        x, y, draw_w, draw_h = self.letterbox_rect(
            self.width(), self.height(), image.width(), image.height())
        painter.drawImage(QRectF(x, y, draw_w, draw_h), image)

        # Flash de feedback al tocar un elemento.
        flash = self._flash
        if flash is not None and draw_w > 0 and draw_h > 0:
            fx, fy, fw, fh = flash
            sx = draw_w / image.width()
            sy = draw_h / image.height()
            rect = QRectF(x + fx * sx, y + fy * sy, fw * sx, fh * sy)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.fillRect(rect, QColor(255, 255, 255, 55))
            pen = painter.pen()
            pen.setColor(QColor(255, 255, 255, 140))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

        # Diagnóstico temporal visible en pantalla.
        if self._debug_text and time.monotonic() < self._debug_until:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            box = QRectF(8, 8, min(self.width() - 16, 520), 34)
            painter.fillRect(box, QColor(0, 0, 0, 190))
            pen = painter.pen()
            pen.setColor(QColor(255, 255, 0, 230))
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(box)
            painter.drawText(box.adjusted(8, 0, -8, 0),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             self._debug_text)
        painter.end()
