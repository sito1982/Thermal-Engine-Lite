"""Pantallas y transiciones reutilizables (DMD y HDMI).

Un proyecto puede tener varias **pantallas** (cada una con su fondo y su lista
de elementos). Se muestran en bucle, con una **transición** configurable entre
pantalla y pantalla; en HDMI además se puede saltar a una pantalla por toque.

Este módulo es agnóstico del dispositivo: lo usan tanto el DMD (`dmd_screens`)
como el HDMI (`main_window`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from constants import DMD_DEFAULT_TRANSITION, DMD_DEFAULT_TRANSITION_MS
from element import ThemeElement

# Máximo de pantallas por target (mismo límite para DMD y HDMI).
MAX_SCREENS = 8


@dataclass
class Screen:
    """Una pantalla: fondo + elementos + tiempo/transición de salida."""

    name: str = "Screen 1"
    elements: list = field(default_factory=list)
    background_color: str = "#000000"
    duration_s: float = 5.0
    transition: str = DMD_DEFAULT_TRANSITION
    transition_ms: int = DMD_DEFAULT_TRANSITION_MS

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "background_color": self.background_color,
            "duration_s": float(self.duration_s),
            "transition": self.transition,
            "transition_ms": int(self.transition_ms),
            "elements": [e.to_dict() for e in self.elements],
        }

    @classmethod
    def from_dict(cls, data, index=0) -> "Screen":
        data = data or {}
        return cls(
            name=data.get("name") or f"Screen {index + 1}",
            elements=[ThemeElement.from_dict(e) for e in data.get("elements", [])],
            background_color=data.get("background_color", "#000000"),
            duration_s=float(data.get("duration_s", 5.0) or 5.0),
            transition=data.get("transition", DMD_DEFAULT_TRANSITION),
            transition_ms=int(data.get("transition_ms", DMD_DEFAULT_TRANSITION_MS) or 0),
        )


def new_screen(name="Screen 1") -> Screen:
    return Screen(name=name)


def screens_from_block(block) -> list:
    """Build the screen list from a target block (``dmd``/``hdmi``).

    Supports the new ``screens`` list and migrates the legacy single
    ``elements``/``background_color`` format into one screen.
    """
    block = block or {}
    raw_screens = block.get("screens")
    if isinstance(raw_screens, list) and raw_screens:
        return [Screen.from_dict(item, i) for i, item in enumerate(raw_screens)]
    return [Screen(
        name="Screen 1",
        elements=[ThemeElement.from_dict(e) for e in block.get("elements", [])],
        background_color=block.get("background_color", "#000000"),
    )]
