"""Tests del emisor DMD: keepalive continuo y backoff ante caídas."""

import socket
import threading
import time

from device_dmd import DMDSenderThread


class _Server:
    def __init__(self, mode="read"):
        self.mode = mode
        self.connections = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(2)
        self.port = self.sock.getsockname()[1]
        self._stop = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while not self._stop:
            try:
                self.sock.settimeout(0.2)
                client, _ = self.sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.connections += 1
            if self.mode == "drop":
                client.close()
                continue
            try:
                client.settimeout(0.3)
                while not self._stop:
                    try:
                        if not client.recv(65536):
                            break
                    except socket.timeout:
                        continue
            finally:
                client.close()

    def stop(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass


def test_keepalive_resends_last_frame():
    server = _Server("read")
    sender = DMDSenderThread("127.0.0.1", server.port, 128, 32, 12)
    sender.start()
    try:
        sender.push(bytes(8192))  # un solo frame...
        time.sleep(0.6)           # ...pero el worker lo reenvía a ~12 FPS
        assert sender.stats()["send_count"] >= 4
    finally:
        sender.stop()
        server.stop()


def test_backoff_on_dropping_peer():
    server = _Server("drop")
    sender = DMDSenderThread("127.0.0.1", server.port, 128, 32, 12)
    sender.start()
    try:
        end = time.time() + 1.5
        while time.time() < end:
            sender.push(bytes(8192))
            time.sleep(1 / 12)
        # Con backoff exponencial no debe reconectar decenas de veces.
        assert server.connections <= 5
    finally:
        sender.stop()
        server.stop()


def test_pause_stops_sending():
    server = _Server("read")
    sender = DMDSenderThread("127.0.0.1", server.port, 128, 32, 12)
    sender.start()
    try:
        sender.push(bytes(8192))
        time.sleep(0.5)
        sent_before = sender.stats()["send_count"]
        assert sent_before >= 3
        sender.set_paused(True)
        time.sleep(0.4)
        paused_count = sender.stats()["send_count"]
        # En pausa el worker no debe seguir enviando (keepalive incluido).
        assert paused_count - sent_before <= 1
        sender.set_paused(False)
        time.sleep(0.4)
        assert sender.stats()["send_count"] > paused_count
    finally:
        sender.stop()
        server.stop()

