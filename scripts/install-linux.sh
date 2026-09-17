#!/usr/bin/env bash
# Instalacion de ThermalEngineLite en Linux (Bazzite/Fedora/Debian/Arch).
# Crea un entorno virtual, instala dependencias y (opcional) reglas udev para
# el panel LCD USB Thermalright.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Comprobando Python"
PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null; then
    echo "Python 3 no encontrado" >&2
    exit 1
fi
"$PYTHON" - <<'EOF'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Se requiere Python >= 3.10")
EOF

echo "==> Creando entorno virtual en .venv"
"$PYTHON" -m venv "$DIR/.venv"

echo "==> Instalando dependencias"
"$DIR/.venv/bin/python" -m pip install --upgrade pip
"$DIR/.venv/bin/python" -m pip install -r "$DIR/requirements.txt"

echo "==> Reglas udev para el LCD Thermalright (requiere sudo)"
if command -v udevadm >/dev/null; then
    sudo cp "$DIR/scripts/99-thermalright-trofeo.rules" /etc/udev/rules.d/
    sudo udevadm control --reload-rules && sudo udevadm trigger || true
    if getent group plugdev >/dev/null; then
        sudo usermod -aG plugdev "$USER" || true
        echo "   Usuario añadido a 'plugdev' (reconecta la sesion)."
    fi
else
    echo "   udev no disponible; omitiendo."
fi

echo "==> Configuracion"
if [ ! -f "$DIR/config.json" ]; then
    cp "$DIR/config.json.example" "$DIR/config.json"
    echo "   Creado config.json (revisa IP del DMD y el token)."
fi

echo
echo "Listo. Arranca con:"
echo "    scripts/run-linux.sh --config config.json"
