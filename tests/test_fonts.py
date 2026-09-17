"""Resolucion de fuentes portables en ThermalEngineLite."""

from constants import DEFAULT_FONT_FAMILY, PORTABLE_FONT_FAMILIES
from element import ThemeElement
from renderer import ThemeRenderer, _resolve_bundled_font


def test_default_font_family_matches_studio():
    assert DEFAULT_FONT_FAMILY == "Liberation Mono"
    assert ThemeElement("text").font_family == "Liberation Mono"


def test_bundled_font_resolution():
    assert _resolve_bundled_font("Liberation Mono").endswith(
        "LiberationMono-Regular.ttf")
    assert _resolve_bundled_font("Liberation Mono", bold=True).endswith(
        "LiberationMono-Bold.ttf")
    assert _resolve_bundled_font("Press Start 2P").endswith(
        "PressStart2P-Regular.ttf")
    # Alias comunes -> Liberation.
    assert _resolve_bundled_font("Arial").endswith("LiberationSans-Regular.ttf")
    assert _resolve_bundled_font("Courier New").endswith(
        "LiberationMono-Regular.ttf")


def test_renderer_get_font_path_prefers_bundled():
    renderer = ThemeRenderer()
    assert renderer.get_font_path("Liberation Mono").endswith(
        "LiberationMono-Regular.ttf")
    assert renderer.get_font_path("Press Start 2P").endswith(
        "PressStart2P-Regular.ttf")


def test_portable_list_includes_failing_families():
    assert "Liberation Mono" in PORTABLE_FONT_FAMILIES
    assert "Press Start 2P" in PORTABLE_FONT_FAMILIES
    assert "Tiny5" in PORTABLE_FONT_FAMILIES
