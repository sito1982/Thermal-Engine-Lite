"""Salidas de ThermalEngineLite (LCD, DMD, HDMI, Web)."""

from outputs.base import OutputBase
from outputs.output_dmd import OutputDMD
from outputs.output_hdmi import OutputHDMI
from outputs.output_lcd import OutputLCD
from outputs.output_web import OutputWeb

__all__ = ["OutputBase", "OutputDMD", "OutputHDMI", "OutputLCD", "OutputWeb"]
