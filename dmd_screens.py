"""Compatibilidad: pantallas y transiciones del target DMD.

El modelo de pantallas es comun a DMD y HDMI, asi que ahora vive en
``screens.py``. Este modulo mantiene los nombres historicos (``DMDScreen``,
``screens_from_dmd``) usados por el resto del codigo.
"""

from __future__ import annotations

from screens import MAX_SCREENS, Screen, new_screen, screens_from_block

DMDScreen = Screen
screens_from_dmd = screens_from_block

__all__ = [
    "MAX_SCREENS",
    "Screen",
    "DMDScreen",
    "new_screen",
    "screens_from_block",
    "screens_from_dmd",
]
