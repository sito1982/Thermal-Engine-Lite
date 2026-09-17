"""Salida Web: servidor Flask con preview y endpoints de gestion."""

from outputs.base import OutputBase


class OutputWeb(OutputBase):
    name = "web"

    def _start(self):
        from webserver import is_running, start_server

        host = self.config.get("host", "0.0.0.0")
        port = int(self.config.get("port", 4241))
        token = self.config.get("token")
        if not is_running():
            start_server(self.runtime, host=host, port=port, token=token)
        # Cache JPEG periodico para servir /image.jpg sin bloquear bajo demanda.
        self.runtime.start_jpeg_cache_timer(500)
        print(f"[WEB] Servidor escuchando en http://{host}:{port}")

    def _stop(self):
        from webserver import is_running, stop_server

        self.runtime.stop_jpeg_cache_timer()
        if is_running():
            stop_server()
        print("[WEB] Servidor detenido")

    def status(self):
        from webserver import is_running

        data = super().status()
        data["running"] = is_running()
        data["port"] = int(self.config.get("port", 4241))
        return data
