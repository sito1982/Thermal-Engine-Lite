"""Detección de monitores conectados para el target HDMI.

Usa la API de Qt (``QGuiApplication.screens()``) para enumerar las pantallas
conectadas y sus datos relevantes (conector, resolución, refresco, DPI y
fabricante/modelo). En Linux, el nombre que reporta Qt es el conector DRM
(``HDMI-A-1``, ``DP-1``, ``eDP-1``...), lo que permite distinguir un monitor
HDMI del resto.

No crea ninguna ``QApplication``: reutiliza la instancia existente para poder
usarse tanto desde el editor como desde el asistente New Project.
"""

from PySide6.QtGui import QGuiApplication

# Tipos de conector conocidos, por orden de comprobación (el prefijo del
# nombre DRM suele ser exactamente uno de estos).
_CONNECTOR_PREFIXES = ("HDMI", "DP", "eDP", "DVI", "VGA", "USB-C", "DSI", "LVDS")


def connector_type(name):
    """Devuelve el tipo de conector a partir del nombre DRM de la pantalla."""
    upper = (name or "").upper()
    for prefix in _CONNECTOR_PREFIXES:
        if upper.startswith(prefix.upper()):
            return prefix
    return "OTHER"


def is_hdmi(name):
    """True si el nombre de la pantalla corresponde a un conector HDMI."""
    return connector_type(name) == "HDMI"


def monitor_id(monitor):
    """Identificador persistente de un monitor.

    Combina conector, modelo y número de serie para sobrevivir a reconexiones
    aunque cambie el índice de Qt. Si el serial está vacío se usa el nombre.
    """
    name = monitor.get("name") or ""
    model = (monitor.get("model") or "").replace(" ", "_")
    serial = (monitor.get("serial") or "").replace(" ", "_")
    return f"{name}|{model}|{serial}"


def display_label(monitor):
    """Etiqueta legible para combos/avisos."""
    name = monitor.get("name") or "?"
    w = monitor.get("width")
    h = monitor.get("height")
    hz = monitor.get("refresh") or 0
    connector = monitor.get("connector") or connector_type(name)
    maker = " ".join(x for x in (monitor.get("manufacturer"), monitor.get("model")) if x)
    parts = [f"{name} · {w}×{h}"]
    if hz:
        parts.append(f"{hz:.0f} Hz")
    parts.append(connector)
    if maker:
        parts.append(maker)
    return " · ".join(parts)


def list_monitors():
    """Enumera las pantallas conectadas.

    Returns:
        list[dict]: una entrada por pantalla con claves ``index``, ``name``,
        ``connector``, ``is_hdmi``, ``width``/``height`` (píxeles físicos),
        ``logical_width``/``logical_height``, ``dpr``, ``refresh``,
        ``manufacturer``, ``model``, ``serial``, ``primary`` e ``id``.
    """
    app = QGuiApplication.instance()
    if app is None:
        return []

    primary = app.primaryScreen()
    monitors = []
    for index, screen in enumerate(app.screens()):
        dpr = screen.devicePixelRatio() or 1.0
        logical = screen.size()
        name = screen.name() or f"screen{index}"
        monitor = {
            "index": index,
            "name": name,
            "connector": connector_type(name),
            "is_hdmi": is_hdmi(name),
            "logical_width": logical.width(),
            "logical_height": logical.height(),
            "width": int(round(logical.width() * dpr)),
            "height": int(round(logical.height() * dpr)),
            "dpr": float(dpr),
            "refresh": float(screen.refreshRate() or 0.0),
            "manufacturer": screen.manufacturer() or "",
            "model": screen.model() or "",
            "serial": screen.serialNumber() or "",
            "primary": screen is primary,
        }
        monitor["id"] = monitor_id(monitor)
        monitors.append(monitor)
    return monitors


def first_hdmi(monitors=None):
    """Primer monitor HDMI, o None."""
    monitors = list_monitors() if monitors is None else monitors
    for monitor in monitors:
        if monitor.get("is_hdmi"):
            return monitor
    return None


def resolve_monitor(screen_id, monitors=None):
    """Resuelve un identificador persistido a la entrada de monitor actual.

    Orden de coincidencia: ``id`` exacto, luego ``name`` y por último
    ``name`` + ``model``. Si ``screen_id`` es falsy devuelve el primer HDMI
    disponible, o el primario como último recurso.
    """
    monitors = list_monitors() if monitors is None else monitors
    if not monitors:
        return None
    if screen_id:
        for monitor in monitors:
            if monitor.get("id") == screen_id:
                return monitor
        for monitor in monitors:
            if monitor.get("name") == screen_id:
                return monitor
        # Último intento: comparar solo la parte del nombre del id.
        name = str(screen_id).split("|", 1)[0]
        for monitor in monitors:
            if monitor.get("name") == name:
                return monitor
        return None
    hdmi = first_hdmi(monitors)
    if hdmi is not None:
        return hdmi
    for monitor in monitors:
        if monitor.get("primary"):
            return monitor
    return monitors[0]


def find_qscreen(screen_id):
    """Devuelve el ``QScreen`` correspondiente a un id persistido (o None)."""
    app = QGuiApplication.instance()
    if app is None:
        return None
    monitors = list_monitors()
    target = resolve_monitor(screen_id, monitors)
    if target is None:
        return None
    screens = app.screens()
    index = target.get("index", -1)
    if 0 <= index < len(screens):
        return screens[index]
    for screen in screens:
        if (screen.name() or "") == target.get("name"):
            return screen
    return None
