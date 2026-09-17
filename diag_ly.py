try:
    from device_ly import LYDevice
    print("[DIAG] Importación de device_ly: OK")
    ly = LYDevice()
    if ly.is_available():
        print("[DIAG] Dispositivo 0416:5408 detectado!")
        try:
            ly.open()
            print("[DIAG] Conexión abierta con éxito")
            ly.close()
        except Exception as e:
            print(f"[DIAG] Error al abrir: {e}")
    else:
        print("[DIAG] Dispositivo no encontrado. Verifica lsusb.")
except Exception as e:
    print(f"[DIAG] Fallo crítico: {e}")
    import traceback
    traceback.print_exc()
