#!/usr/bin/env bash
# Arranca ThermalEngineLite desde el entorno virtual local.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$DIR/.venv/bin/python"

if [ ! -x "$PY" ]; then
    echo "No existe el entorno virtual. Ejecuta primero scripts/install-linux.sh" >&2
    exit 1
fi

# Sin servidor grafico -> Qt offscreen (DMD/Web siguen funcionando).
if [ -z "${DISPLAY:-}" ] && [ -z "${WAYLAND_DISPLAY:-}" ]; then
    export QT_QPA_PLATFORM=offscreen
fi

exec "$PY" "$DIR/main.py" "$@"
