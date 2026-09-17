FROM python:3.12-slim

# Qt funciona en modo offscreen (sin servidor grafico) para renderizar DMD y
# servir el preview web. Estas librerias cubren Qt/PySide6 y OpenCV.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    QT_QPA_PLATFORM=offscreen \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libegl1 \
        libxkbcommon0 \
        libdbus-1-3 \
        libfontconfig1 \
        libfreetype6 \
        libharfbuzz0b \
        libsm6 \
        libxext6 \
        libxrender1 \
        libgomp1 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Volumen para el tema activo y la configuracion.
VOLUME ["/data"]
EXPOSE 4241

ENTRYPOINT ["python", "main.py"]
CMD ["--config", "/data/config.json"]
