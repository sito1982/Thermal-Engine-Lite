"""Salida LCD USB (Thermalright Trofeo u otros compatibles).

Reutiliza el driver LY (bulk USB) y, como alternativa, el protocolo HID legacy.
Renderiza el tema con Pillow y envia el JPEG al panel a la tasa objetivo. Ante
un error de escritura se desconecta y reintenta con backoff exponencial.

En contenedores requiere pasar el dispositivo USB y reglas udev en el host.
"""

import threading

from PySide6.QtCore import QTimer

from outputs.base import OutputBase

try:
    import hid
    HAS_HID = True
except ImportError:
    HAS_HID = False


class OutputLCD(OutputBase):
    name = "lcd"

    def __init__(self, runtime):
        super().__init__(runtime)
        self.device = None
        self._ly_device = None
        self.timer = None
        self._reconnect_timer = None
        self._reconnect_attempts = 0
        self._sending = threading.Lock()

    # -------------------------------------------------------------- ciclo --
    def _start(self):
        fps = max(1, int((self.config or {}).get("fps", 25)))
        self._connect()
        if self.device is None:
            # Sin panel: se sigue intentando reconectar en segundo plano.
            self._schedule_reconnect()
        self.timer = QTimer()
        self.timer.timeout.connect(self.tick)
        self.timer.start(int(1000 / fps))

    def _stop(self):
        if self.timer is not None:
            self.timer.stop()
            self.timer = None
        if self._reconnect_timer is not None:
            self._reconnect_timer.stop()
            self._reconnect_timer = None
        self._disconnect()

    # ------------------------------------------------------------ conexion --
    def _connect(self):
        # 1) LY bulk USB (0416:5408 - Thermalright Trofeo)
        try:
            from device_ly import LYDevice

            ly = LYDevice()
            if ly.is_available():
                ly.open()
                self.device = ly
                self._ly_device = ly
                self._reconnect_attempts = 0
                print("[LCD] Conectado al panel LY (0416:5408)")
                return True
        except ImportError:
            print("[LCD] device_ly no disponible")
        except Exception as e:
            print(f"[LCD] Conexion LY fallida: {e}")

        # 2) HID legacy (0416:5302 / 35CC:0104)
        if not HAS_HID:
            return False
        try:
            dev = hid.device()
            dev.open(0x0416, 0x5302)
            init = bytearray(512)
            init[0:4] = bytes([0xDA, 0xDB, 0xDC, 0xDD])
            init[4] = 0x00
            init[12] = 0x01
            dev.write(bytes([0x00]) + bytes(init))
            self.device = dev
            self._reconnect_attempts = 0
            print("[LCD] Conectado al panel HID (0416:5302)")
            return True
        except Exception as e:
            print(f"[LCD] Conexion HID fallida: {e}")
            return False

    def _disconnect(self):
        if self._ly_device is not None:
            try:
                self._ly_device.close()
            except Exception:
                pass
            self._ly_device = None
        if self.device is not None:
            try:
                self.device.close()
            except Exception:
                pass
            self.device = None

    def _schedule_reconnect(self):
        if self._reconnect_timer is None:
            self._reconnect_timer = QTimer()
            self._reconnect_timer.setSingleShot(True)
            self._reconnect_timer.timeout.connect(self._attempt_reconnect)
        delay = min(30000, 1000 * (2 ** min(self._reconnect_attempts, 5)))
        self._reconnect_timer.start(delay)

    def _attempt_reconnect(self):
        if self.enabled is False:
            return
        self._reconnect_attempts += 1
        if not self._connect():
            self._schedule_reconnect()

    # --------------------------------------------------------------- envio --
    def tick(self):
        if self.device is None:
            return
        if not self._sending.acquire(blocking=False):
            return
        try:
            img = self.runtime.render_theme_image()
            jpeg = self.runtime.image_to_jpeg(img, quality=80)
            self._send_jpeg_frame(jpeg)
        except Exception as e:
            print(f"[LCD] Error de envio: {e}")
            self._disconnect()
            if self.enabled:
                self._schedule_reconnect()
        finally:
            self._sending.release()

    def _send_jpeg_frame(self, jpeg_data):
        from device_ly import LYDevice

        if isinstance(self.device, LYDevice):
            if not self.device.send_frame(jpeg_data):
                raise IOError("LY send_frame devolvio False")
            return

        # Protocolo HID legacy.
        MAGIC = bytes([0xDA, 0xDB, 0xDC, 0xDD])
        header = bytearray(512)
        header[0:4] = MAGIC
        header[4] = 0x02
        header[8:12] = bytes([0x00, 0x05, 0xE0, 0x01])
        header[12] = 0x02
        jpeg_len = len(jpeg_data)
        header[16] = jpeg_len & 0xFF
        header[17] = (jpeg_len >> 8) & 0xFF
        header[18] = (jpeg_len >> 16) & 0xFF
        header[19] = (jpeg_len >> 24) & 0xFF
        first_chunk = min(len(jpeg_data), 492)
        header[20:20 + first_chunk] = jpeg_data[:first_chunk]
        self.device.write(bytes([0x00]) + bytes(header))
        offset = first_chunk
        while offset < len(jpeg_data):
            chunk = jpeg_data[offset:offset + 512]
            if len(chunk) < 512:
                chunk = chunk + bytes(512 - len(chunk))
            self.device.write(bytes([0x00]) + chunk)
            offset += 512

    def status(self):
        data = super().status()
        data["connected"] = self.device is not None
        data["transport"] = ("ly" if self._ly_device is not None
                             else ("hid" if self.device is not None else None))
        return data
