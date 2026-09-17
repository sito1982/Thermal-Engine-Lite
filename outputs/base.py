"""Interfaz comun de las salidas (outputs) de ThermalEngineLite."""


class OutputBase:
    """Salida de un destino (LCD/DMD/HDMI/Web).

    Las subclases implementan ``_start()``/``_stop()`` y ``status()``. El ciclo
    de vida publico (``start``/``stop``) es idempotente.
    """

    name = "base"

    def __init__(self, runtime):
        self.runtime = runtime
        self.enabled = False
        self.last_error = None
        self.config = {}

    # ------------------------------------------------------------- config --
    def configure(self, config):
        """Aplica configuracion (dict) antes de arrancar."""
        self.config = config or {}

    # -------------------------------------------------------------- ciclo --
    def start(self):
        if self.enabled:
            return True
        try:
            self._start()
            self.enabled = True
            self.last_error = None
            return True
        except Exception as e:  # pragma: no cover - defensivo
            self.last_error = str(e)
            print(f"[{self.name.upper()}] Error al arrancar: {e}")
            return False

    def stop(self):
        if not self.enabled:
            return
        try:
            self._stop()
        except Exception as e:  # pragma: no cover - defensivo
            print(f"[{self.name.upper()}] Error al parar: {e}")
        finally:
            self.enabled = False

    def _start(self):
        raise NotImplementedError

    def _stop(self):
        raise NotImplementedError

    # ------------------------------------------------------------- estado --
    def status(self):
        return {
            "name": self.name,
            "enabled": self.enabled,
            "error": self.last_error,
        }
