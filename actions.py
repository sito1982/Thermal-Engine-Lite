"""Ejecución de acciones de elementos para el target HDMI (toque).

Modelo de seguridad:
- La funcionalidad está **desactivada por defecto** (ver ``settings``).
- ``run_action`` nunca usa shell: lanza el ejecutable y sus argumentos
  directamente con ``QProcess.startDetached``.
- La ventana principal decide el gate (ajuste global) y la confirmación por
  comando antes de llamar aquí. Este módulo solo parsea, valida y ejecuta.
"""

import hashlib
import json
import os
import shlex
import sys

from PySide6.QtCore import QProcess

ALLOWED_ACTION_TYPES = ("none", "command")


class ActionError(Exception):
    """Error de parseo/validación de una acción."""


def parse_args_text(text, platform=None):
    """Convierte un texto de argumentos tipo shell en lista (OS-aware)."""
    if not text or not text.strip():
        return []
    posix = (platform or sys.platform) != "win32"
    try:
        return shlex.split(text, posix=posix)
    except ValueError as exc:
        raise ActionError(f"Argumentos inválidos: {exc}") from exc


def args_to_text(args):
    """Representación legible/editable de una lista de argumentos."""
    return " ".join(shlex.quote(str(a)) for a in (args or []))


def parse_action(element):
    """Extrae la acción de un ``ThemeElement`` o None si no hay acción válida."""
    action_type = getattr(element, "tap_action", "none") or "none"
    if action_type not in ALLOWED_ACTION_TYPES or action_type == "none":
        return None
    command = (getattr(element, "tap_command", "") or "").strip()
    if not command:
        return None
    args = list(getattr(element, "tap_args", []) or [])
    workdir = (getattr(element, "tap_workdir", "") or "").strip()
    return {"type": action_type, "command": command, "args": args, "workdir": workdir}


def validate_action(command, args, workdir):
    """Devuelve una lista de errores (vacía si la acción es válida)."""
    errors = []
    if not command or not command.strip():
        errors.append("El comando está vacío")
    elif "\x00" in command or len(command) > 1000:
        errors.append("Comando inválido")
    if args is not None:
        if not isinstance(args, (list, tuple)):
            errors.append("Los argumentos deben ser una lista")
        else:
            for arg in args:
                if not isinstance(arg, str) or "\x00" in arg or len(arg) > 500:
                    errors.append("Argumento inválido")
                    break
    if workdir:
        if not isinstance(workdir, str) or "\x00" in workdir:
            errors.append("Directorio de trabajo inválido")
        elif not os.path.isdir(os.path.expanduser(workdir)):
            errors.append(f"El directorio de trabajo no existe: {workdir}")
    return errors


def action_fingerprint(command, args):
    """Hash estable para el registro de acciones aprobadas por el usuario."""
    payload = json.dumps([command, list(args or [])], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_action(action):
    """Lanza la acción sin shell.

    Returns:
        tuple[bool, str]: (éxito, mensaje).
    """
    command = action.get("command", "")
    args = [str(a) for a in (action.get("args") or [])]
    workdir = action.get("workdir", "") or ""
    program = os.path.expanduser(command)

    # Si el comando incluye ruta, comprobar que existe antes de lanzarlo.
    if os.sep in program or (os.altsep and os.altsep in program):
        if not os.path.exists(program):
            return False, f"No existe el ejecutable: {program}"

    try:
        result = QProcess.startDetached(program, args, workdir)
    except Exception as exc:  # pragma: no cover - defensivo
        return False, f"Error lanzando la acción: {exc}"

    if isinstance(result, tuple):
        started, pid = bool(result[0]), result[1]
    else:
        started, pid = bool(result), 0
    if not started:
        return False, "No se pudo lanzar la acción"
    return True, f"Acción ejecutada (pid {pid})"
