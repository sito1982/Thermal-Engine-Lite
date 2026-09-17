"""
Thermal Engine Studio - UI design system.

Central dark theme (matches the approved LCDForge Figma mock):
design tokens + one global QSS stylesheet + small styled helper widgets.

All panels/widgets in the app should pick up the look from this single source;
widgets that need a custom look just set an objectName the stylesheet targets
(e.g. 'appLogo', 'statusMetric', 'propertySection').
"""

import os
import tempfile

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap, QPolygonF
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QLabel, QToolButton

# ---------------------------------------------------------------------------
# Design tokens
# ---------------------------------------------------------------------------
APP_BG      = "#0c0d0f"   # window / canvas viewport background
PANEL_BG    = "#13141a"   # side panels, menubar, toolbar
CARD_BG     = "#1a1c24"   # cards, rows, sections
CARD_BG_HI  = "#21242e"   # hover state
BORDER      = "#2a2d37"   # default borders
ACCENT      = "#00c896"   # brand / selection
ACCENT_DIM  = "#0f6b57"
TEXT        = "#e8e9ef"   # primary text
TEXT_DIM    = "#a0a2af"   # secondary text
TEXT_FAINT  = "#5c6070"   # placeholders / disabled
ROW_SEL     = "rgba(0, 200, 150, 0.13)"   # selected row overlay
ERROR       = "#f25c54"
WARN        = "#ffbf69"
BLUE        = "#58a6ff"

DOT_OFF     = "#3a3e4c"   # device status dot, disconnected
DOT_ON      = "#00c896"   # device status dot, connected

# Figma prototype tokens (LCDForge) — usados por el asistente New Project
BG_HOVER         = "#22252f"
BG_SELECTED      = "#1e2a24"
BORDER_LIGHT     = "#2c3040"
ACCENT_GLOW      = "rgba(0, 200, 150, 0.18)"
ACCENT_BORDER    = "rgba(0, 200, 150, 0.35)"
TEXT_SECONDARY   = "#8a909f"
TEXT_MUTED       = "#484d5c"

MONO_FAMILIES = "'DejaVu Sans Mono', 'JetBrains Mono', 'Liberation Mono', monospace"


# ---------------------------------------------------------------------------
# Inline SVG icon set (stroke uses a placeholder color that we inject)
# ---------------------------------------------------------------------------
def _svg(name, color):
    stroke = color
    if name == "eye":
        body = ('<path d="M1 8s3-5.5 8-5.5S17 8 17 8s-3 5.5-8 5.5S1 8 1 8z"/>'
                '<circle cx="9" cy="8" r="2.6"/>')
    elif name == "eye_off":
        body = ('<path d="M1 1l16 14"/>'
                '<path d="M6.8 5.7A5.6 5.6 0 0 1 9 5.2c3.6 0 6 2.8 6 2.8s-.9 1.4-2.5 2.5"/>'
                '<path d="M5.1 6.9C3.6 8 2.3 9.6 1.5 10.8S3.4 15.5 9 15.5a5.7 5.7 0 0 0 3.2-.9"/>'
                '<path d="M9 13.3a2.6 2.6 0 0 1-2.5-2.6"/>')
    elif name == "lock":
        body = ('<rect x="4.5" y="8.5" width="9" height="7" rx="1.5"/>'
                '<path d="M6.5 8.5v-2a2.5 2.5 0 0 1 5 0v2"/>')
    elif name == "lock_open":
        body = ('<rect x="4.5" y="8.5" width="9" height="7" rx="1.5"/>'
                '<path d="M6.5 8.5v-2a2.5 2.5 0 0 1 4.8-1.1"/>')
    elif name == "plus":
        body = ('<path d="M9 3v12M3 9h12"/>')
    elif name == "trash":
        body = ('<path d="M3 4.5h12"/>'
                '<path d="M6.5 4V3a1 1 0 0 1 1-1h2.5a1 1 0 0 1 1 1v1"/>'
                '<path d="M5 4.5l.6 9.2A1.7 1.7 0 0 0 7.3 15.3h3.4a1.7 1.7 0 0 0 1.7-1.6L13 4.5"/>'
                '<path d="M7.7 7.5v4.3M10.3 7.5v4.3"/>')
    elif name == "star":
        body = ('<path d="M9 1.8l2.2 4.4 4.9.7-3.5 3.4.8 4.9-4.4-2.3-4.4 2.3.8-4.9L1.9 6.9l4.9-.7z"/>')
    elif name == "check":
        body = ('<path d="M2.5 8.5l3.6 3.6L15 4"/>')
    elif name == "xmark":
        body = ('<path d="M3 3l12 12M15 3L3 15"/>')
    elif name == "collapse":
        body = ('<path d="M14 5l-6 6L2 5"/>')
    elif name == "expand":
        body = ('<path d="M2 5l6 6 6-6"/>')
    elif name == "swap":
        body = ('<path d="M13 5H4M4 11h9" fill="none"/>'
                '<path d="M13 3.5L16 5l-3 1.5M5 8.5L3 10.5l3 1.5"/>'
                '<path d="M10 13.5L8 15.5l2 2"/>')
    elif name == "chevron_down":
        body = '<path d="M2 4l6 6 6-6"/>'
    elif name == "device":
        body = ('<rect x="2" y="4.5" width="14" height="9" rx="1.5"/>'
                '<path d="M6 17h6"/>')
    else:
        body = '<circle cx="9" cy="9" r="7"/>'
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" '
        'viewBox="0 0 18 18" fill="none">'
        f'<g stroke="{stroke}" stroke-width="1.6" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</g></svg>'
    )


def make_icon(name, color, size=18):
    """Build a QIcon from an inline SVG icon, tinted with `color`."""
    svg = _svg(name, color).replace('width="18" height="18"',
                                    f'width="{size}" height="{size}"')
    renderer = QSvgRenderer(svg.encode("utf-8"))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


def render_svg(svg, width, height):
    """Render an SVG string to a transparent QPixmap at the given size."""
    renderer = QSvgRenderer(svg.encode("utf-8"))
    pixmap = QPixmap(width, height)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


class IconButton(QToolButton):
    """Flat icon button with hover/active tint and optional checkable accent."""

    def __init__(self, name, color=TEXT_DIM, hover_color=ACCENT, size=18,
                 parent=None, checkable=False, check_color=ACCENT, tooltip=None):
        super().__init__(parent)
        self._name = name
        self._color = color
        self._hover_color = hover_color
        self._check_color = check_color
        self._hovered = False
        self.setCheckable(checkable)
        self.setIconSize(QSize(size, size))
        self.setFixedSize(size + 14, size + 8)
        self.setObjectName("iconButton")
        self._apply_icon()
        if tooltip:
            self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _current_color(self):
        if self.isChecked():
            return self._check_color
        if self._hovered:
            return self._hover_color
        return self._color

    def _apply_icon(self):
        color = self._current_color()
        size = self.iconSize().width()
        self.setIcon(make_icon(self._name, color, size))

    def enterEvent(self, event):
        self._hovered = True
        if not self.isChecked():
            self._apply_icon()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        if not self.isChecked():
            self._apply_icon()
        super().leaveEvent(event)

    def setChecked(self, checked):
        super().setChecked(checked)
        self._apply_icon()


class SectionLabel(QLabel):
    """Uppercase dim label used as a column/section header."""

    def __init__(self, text, parent=None):
        super().__init__(text.upper(), parent)
        self.setObjectName("sectionLabel")


class LogoLabel(QLabel):
    """App title in the menu bar ('THERMAL ENGINE STUDIO')."""

    def __init__(self, text, parent=None):
        super().__init__(text.upper(), parent)
        self.setObjectName("appLogo")


class SwitchButton(QAbstractButton):
    """Pill-shaped On/Off switch (checkable).

    Draws a rounded track, a sliding knob and the state text ("On"/"Off").
    """

    def __init__(self, checked=True, parent=None, tooltip=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(bool(checked))
        self.setFixedSize(60, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if tooltip:
            self.setToolTip(tooltip)
        self.toggled.connect(lambda _checked: self.update())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        width, height = self.width(), self.height()
        radius = height / 2.0
        on = self.isChecked()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ACCENT if on else DOT_OFF))
        painter.drawRoundedRect(QRectF(0, 0, width, height), radius, radius)

        knob_radius = radius - 3
        cx = (width - radius) if on else radius
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(QPointF(cx, height / 2.0), knob_radius, knob_radius)

        font = painter.font()
        font.setPointSizeF(7.5)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#0c0d0f" if on else TEXT))
        if on:
            text_rect = QRectF(4, 0, width - radius - 4, height)
        else:
            text_rect = QRectF(2 * radius, 0, width - radius - 4, height)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter,
                         "On" if on else "Off")


_spinbox_arrows_cache = {}


def _spinbox_arrow_paths():
    """Render small PNG arrow icons for QSpinBox::up-arrow / down-arrow.

    El truco CSS de triángulos con bordes ("border-left/right: transparent")
    no se dibuja correctamente en los sub-controls de los spinbox en Qt y
    deja cuadrados; por eso se generan iconos reales y se referencian con
    `image: url(...)`. Se reutilizan entre llamadas (misma ruta de cache).
    """
    global _spinbox_arrows_cache
    if _spinbox_arrows_cache:
        return _spinbox_arrows_cache

    tmp = tempfile.gettempdir()
    cache_key = None
    for name, path in (("up", "te_spin_up.png"),
                       ("down", "te_spin_down.png")):
        fp = os.path.join(tmp, path)
        if os.path.exists(fp):
            try:
                os.remove(fp)
            except OSError:
                pass
        pm = QPixmap(9, 9)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(TEXT_DIM))
        if name == "up":
            pts = QPolygonF(
                [QPointF(1.0, 6.5), QPointF(8.0, 6.5), QPointF(4.5, 2.0)])
        else:
            pts = QPolygonF(
                [QPointF(1.0, 2.5), QPointF(8.0, 2.5), QPointF(4.5, 7.0)])
        p.drawPolygon(pts)
        p.end()
        pm.save(fp, "PNG")
        _spinbox_arrows_cache[name] = fp
    return _spinbox_arrows_cache


def build_stylesheet():
    """Global QSS for the whole application."""
    arrows = _spinbox_arrow_paths()
    return f"""
    /* ---------- global ---------- */
    QMainWindow, QDialog, QWidget#centralRoot {{
        background-color: {APP_BG};
        color: {TEXT};
    }}
    QWidget {{
        background-color: transparent;
        color: {TEXT};
        font-size: 12px;
    }}
    QToolTip {{
        background-color: {CARD_BG};
        color: {TEXT};
        border: 1px solid {BORDER};
        padding: 4px 8px;
    }}

    /* ---------- menu bar ---------- */
    QMenuBar {{
        background-color: {PANEL_BG};
        color: {TEXT_DIM};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 0 4px;
        min-height: 30px;
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 6px 10px;
        border-radius: 5px;
        color: {TEXT_DIM};
    }}
    QMenuBar::item:selected, QMenuBar::item:pressed {{
        background-color: {CARD_BG_HI};
        color: {TEXT};
    }}
    QMenu {{
        background-color: {CARD_BG};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 6px 24px 6px 12px;
        border-radius: 5px;
        color: {TEXT};
    }}
    QMenu::item:selected {{
        background-color: {ROW_SEL};
        color: {ACCENT};
    }}
    QMenu::item:disabled {{ color: {TEXT_FAINT}; }}
    QMenu::separator {{
        height: 1px;
        background: {BORDER};
        margin: 5px 8px;
    }}

    /* ---------- toolbar ---------- */
    QToolBar#mainToolbar {{
        background-color: {PANEL_BG};
        border: none;
        border-bottom: 1px solid {BORDER};
        spacing: 8px;
        padding: 4px 10px;
    }}
    QToolBar#mainToolbar QLabel {{
        color: {TEXT_DIM};
        padding: 0 2px;
    }}
    QToolBar#mainToolbar QLineEdit#themeNameEdit {{
        background-color: {APP_BG};
        border: 1px solid {BORDER};
        border-radius: 5px;
        padding: 5px 8px;
    }}
    QToolBar#mainToolbar QLineEdit#themeNameEdit:focus {{
        border-color: {ACCENT};
    }}

    /* ---------- buttons ---------- */
    QPushButton {{
        background-color: {CARD_BG};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 5px;
        padding: 5px 10px;
    }}
    QPushButton:hover {{ background-color: {CARD_BG_HI}; border-color: #3a3e4c; }}
    QPushButton:pressed {{ background-color: {PANEL_BG}; }}
    QPushButton:disabled {{ color: {TEXT_FAINT}; border-color: {BORDER}; }}
    QPushButton#accentButton {{
        background-color: {ACCENT_DIM};
        color: #ffffff;
        border-color: {ACCENT};
        padding: 5px 14px;
    }}
    QPushButton#accentButton:hover {{ background-color: {ACCENT}; color: #00241c; }}

    QToolButton#iconButton {{
        background: transparent;
        border: none;
        border-radius: 5px;
    }}
    QToolButton#iconButton:checked {{ background-color: {ROW_SEL}; }}
    QToolButton#iconButton:hover:!checked {{ background-color: {CARD_BG_HI}; }}

    /* ---------- side panels ---------- */
    QTabWidget#sidePanel::pane {{
        border: none;
        background-color: {PANEL_BG};
    }}
    QTabBar {{
        background-color: {PANEL_BG};
        qproperty-drawBase: 0;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {TEXT_DIM};
        padding: 9px 14px;
        margin: 0 2px;
        border: none;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{
        color: {TEXT};
        border-bottom: 2px solid {ACCENT};
    }}
    QTabBar::tab:hover:!selected {{ color: {TEXT}; }}

    QTreeWidget, QListWidget {{
        background-color: {PANEL_BG};
        border: none;
        outline: none;
        padding: 4px;
    }}
    QTreeWidget::item, QListWidget::item {{
        min-height: 32px;
        border-radius: 6px;
        padding: 0 4px;
    }}
    QTreeWidget::item:hover {{ background-color: {CARD_BG_HI}; }}
    QTreeWidget::item:selected, QListWidget::item:selected {{
        background-color: {ROW_SEL};
        color: {TEXT};
        border-left: 2px solid {ACCENT};
    }}
    QTreeWidget::branch {{
        background: transparent;
    }}
    QHeaderView::section {{
        background-color: {PANEL_BG};
        color: {TEXT_DIM};
        border: none;
        border-bottom: 1px solid {BORDER};
        padding: 5px;
    }}

    /* ---------- property sections ---------- */
    QFrame#propertySection {{
        background-color: {CARD_BG};
        border: 1px solid {BORDER};
        border-radius: 8px;
    }}
    QLabel#sectionLabel {{
        color: {TEXT_DIM};
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 1px;
    }}
    QLabel#sectionTitle {{
        color: {TEXT};
        font-size: 11px;
        font-weight: 600;
    }}

    /* ---------- inputs ---------- */
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {APP_BG};
        border: 1px solid {BORDER};
        border-radius: 5px;
        padding: 4px 8px;
        selection-background-color: {ACCENT_DIM};
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border-color: {ACCENT};
    }}
    QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
        color: {TEXT_FAINT};
    }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        background-color: {CARD_BG};
        border: none;
        border-left: 1px solid {BORDER};
        width: 14px;
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        background-color: {CARD_BG};
        border: none;
        border-left: 1px solid {BORDER};
        border-top: 1px solid {BORDER};
        width: 14px;
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url("{arrows['up']}");
        width: 9px; height: 9px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url("{arrows['down']}");
        width: 9px; height: 9px;
    }}
    QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled,
    QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {{
        image: none;
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        border: none;
        width: 20px;
    }}
    QComboBox::drop-down:hover {{
        background-color: {CARD_BG};
    }}
    QComboBox::down-arrow {{
        image: url("{arrows['down']}");
        width: 10px; height: 10px;
    }}
    QComboBox::down-arrow:disabled {{
        image: none;
    }}
    QComboBox QAbstractItemView {{
        background-color: {CARD_BG};
        border: 1px solid {BORDER};
        selection-background-color: {ROW_SEL};
        selection-color: {TEXT};
        outline: none;
    }}

    QCheckBox {{
        spacing: 6px;
        color: {TEXT};
    }}
    QCheckBox::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {BORDER};
        border-radius: 4px;
        background: {APP_BG};
    }}
    QCheckBox::indicator:checked {{
        background-color: {ACCENT};
        border-color: {ACCENT};
    }}
    QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}

    /* ---------- slider ---------- */
    QSlider::groove:horizontal {{
        height: 4px;
        background: {BORDER};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {ACCENT};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 12px;
        margin: -4px 0;
        border-radius: 6px;
        background: {TEXT};
    }}

    /* ---------- canvas / scroll ---------- */
    QScrollArea#canvasScroll {{ background-color: {APP_BG}; border: none; }}
    QScrollArea#canvasScroll > QWidget > QWidget {{ background-color: {APP_BG}; }}
    QWidget#canvasViewport, QWidget#canvasHost {{ background-color: {APP_BG}; }}
    QScrollBar:vertical {{
        background: {APP_BG};
        width: 10px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: {BORDER};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{ background: #3a3e4c; }}
    QScrollBar:horizontal {{
        background: {APP_BG};
        height: 10px;
    }}
    QScrollBar::handle:horizontal {{
        background: {BORDER};
        border-radius: 5px;
        min-width: 30px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        width: 0; height: 0;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* ---------- canvas sub-toolbar ---------- */
    QWidget#canvasBar {{
        background-color: {PANEL_BG};
        border: none;
        border-bottom: 1px solid {BORDER};
    }}
    QWidget#canvasBar QLabel {{ color: {TEXT_DIM}; }}
    QToolButton#zoomButton {{
        background: transparent;
        border: 1px solid {BORDER};
        border-radius: 5px;
        color: {TEXT};
        padding: 3px 9px;
        min-width: 20px;
    }}
    QToolButton#zoomButton:hover {{ border-color: {ACCENT}; color: {ACCENT}; }}
    QLabel#deviceStatusDot {{ border-radius: 5px; }}

    /* ---------- canvas toolbar fit/zoom ---------- */
    QLabel#zoomValue {{
        color: {TEXT};
        min-width: 40px;
        text-align: center;
    }}

    /* ---------- status bar ---------- */
    QStatusBar {{
        background-color: {PANEL_BG};
        border-top: 1px solid {BORDER};
    }}
    QStatusBar::item {{ border: none; }}
    QLabel#statusMetric {{
        padding: 2px 8px;
    }}
    QLabel#statusMetricDim {{
        color: {TEXT_DIM};
        padding: 2px 8px;
    }}
    QLabel#perfIndicator {{
        border-radius: 4px;
        min-height: 16px;
    }}

    /* ---------- dialogs ---------- */
    QDialog QLabel {{ color: {TEXT}; }}
    QDialogButtonBox QPushButton {{ min-width: 80px; }}
    """


def apply_dark_theme(app):
    """Apply the design system to a QApplication."""
    app.setStyle("Fusion")
    app.setStyleSheet(build_stylesheet())
