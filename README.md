# ThermalEngineLite

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-0.10.0-blue.svg)](CHANGES.md)
[![Python](https://img.shields.io/badge/python-%3E%3D3.10-blue.svg)](pyproject.toml)

**🇪🇸 Español** · [🇬🇧 English](#english)

Runtime de monitorización **headless** hermano de [Thermal Engine Studio](../Thermal-Engine-Linux).
No incluye editor: carga un **tema guardado** (diseñado con Studio) y lo renderiza en
vivo con datos de sensores del equipo donde corre, entregándolo a **LCD USB, paneles
DMD (TCP), monitores HDMI y/o un servidor web**. Pensado para desplegarse en
**Docker sobre terminales y equipos autónomos** (servidores, kioscos, HTPC) y para
recibir temas en caliente por **push**.

---

## Español

### ¿Qué es?

ThermalEngineLite es el **runtime** de un tema. Mientras Studio es el editor visual
(Python + Qt/PySide6) que se ejecuta en tu portátil, Lite es el reproductor que vive
en la máquina monitorizada. Reutiliza el núcleo de render y los drivers de
Thermal-Engine-Studio, pero elimina toda la interfaz de edición.

| Destino | Salida |
|---|---|
| **LCD** | Pantalla LCD por USB (driver LY *bulk* o HID), p. ej. Thermalright Trofeo Vision. |
| **DMD** | Panel LED *Dot Matrix* ESP32 por TCP (frames RGB565). |
| **HDMI** | Monitor externo a pantalla completa, a su resolución nativa. |
| **Web** | Servidor Flask con la imagen renderizada, panel de control, estado y push de temas. |

### Flujo de trabajo remoto (push)

```
┌──────────────────────────┐        POST /theme (JSON)        ┌────────────────────────┐
│  Portátil: Studio + tema │  ──────────────────────────────▶ │  Terminal: Lite        │
│  (diseño en vivo)        │                                  │  LCD / DMD / HDMI / Web│
└──────────────────────────┘                                  └────────────────────────┘
```

1. En el portátil diseñas el tema con Studio.
2. Envíalo al equipo remoto, de una de estas dos formas:
   - Desde **Studio: `File → Publish to ThermalEngineLite...`** (introduces URL y token; se recuerdan).
   - Por CLI:

   ```bash
   python tools/push_theme.py --url http://terminal:4241 \
       --token TU_TOKEN --theme "/ruta/al/Theme.json"
   ```

3. Lite valida el JSON y lo aplica **en caliente** (sin reiniciar): reconstruye los
   elementos y reconfigura las salidas. El preview web muestra el cambio al instante.

También puedes montar el tema como archivo (`theme_path`) y Lite lo recarga solo
cuando cambia (`watch_theme: true`).

### Uso

```bash
# Instalación local (Linux)
scripts/install-linux.sh
scripts/run-linux.sh --config config.json

# Directo
python main.py --config config.json
python main.py --theme /data/theme.json --targets web,dmd --dmd-ip 192.168.1.66
```

Argumentos útiles: `--theme`, `--targets web,lcd,dmd,hdmi`, `--enable-dmd/--no-dmd`,
`--port`, `--token`, `--dmd-ip`, `--dmd-size 128x32`, `--hdmi-screen`, `--fps`, `--log-level`.

Sin servidor gráfico, Lite arranca Qt en modo **offscreen** automáticamente (DMD y Web
funcionan; HDMI solo con display).

### Docker

```bash
cp config.json.example config.json   # edita DMD/token/targets
docker compose up -d --build
```

`docker-compose.yml` incluye ejemplos comentados para pasar sensores del host
(`/sys/class/hwmon`, `/sys/class/powercap`, `/proc`), el LCD USB y el display HDMI.

> **Sensores en contenedor.** `psutil` y `linux_sensors` leen CPU/RAM/red/disco del
> host, pero temperaturas, RAPL y GPU necesitan acceso a `/sys`, `/proc` y NVML.
> Descomenta `privileged: true` y los volúmenes según tu caso.

### Configuración (`config.json`)

Precedencia: por defecto `< config.json < variables de entorno (`TE_*`) < argumentos CLI`.

| Clave | Descripción |
|---|---|
| `theme_path` | Ruta del tema inicial (por defecto `/data/theme.json`). |
| `watch_theme` / `watch_interval_s` | Recargar el archivo cuando cambia. |
| `targets` | `{web, lcd, dmd, hdmi}`: salidas activas en este equipo. |
| `web_host`, `web_port`, `web_token` | Servidor web y token de `POST /theme`. |
| `target_fps` | FPS objetivo (LCD y caché del preview). |
| `vertical_mode`, `lcd_brightness/contrast/saturation` | Orientación y ajuste de imagen. |
| `lcd_model` | Modelo del panel LCD del catálogo. |
| `dmd_config` | `{ip, port, width, height, fps}` del panel DMD. |
| `hdmi_config` | `{screen_id}` del monitor HDMI (vacío = primer HDMI). |
| `log_level` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |

Variables de entorno: `TE_CONFIG`, `TE_THEME`, `TE_TARGETS`, `TE_WEB_PORT`, `TE_WEB_TOKEN`,
`TE_DMD_IP`, `TE_DMD_PORT`, `TE_DMD_SIZE`, `TE_DMD_FPS`, `TE_HDMI_SCREEN`, `TE_TARGET_FPS`,
`TE_LCD_MODEL`, `TE_WATCH`, `TE_LOG_LEVEL`.

### API HTTP

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/` | Imagen renderizada a pantalla completa. |
| `GET` | `/image.jpg` | Frame JPEG actual (`?w=`/`?h=` para escalar). |
| `GET` | `/theme` | JSON del tema activo. |
| `POST` | `/theme` | Aplica un tema nuevo (**push**). Requiere `X-Token` si hay token. |
| `GET` | `/info` | Metadatos para el wizard de Studio (host, versión, targets, dimensiones, modelo LCD). |
| `GET` | `/sensors` | Valores de sensores del equipo. Requiere `X-Token` si hay token. |
| `GET` | `/status` | Estado de las salidas y del tema. |
| `GET` | `/healthz` | Sonda de salud. |
| `GET` | `/config` | Panel de control. |

Ejemplo con `curl`:

```bash
curl -X POST http://terminal:4241/theme \
  -H "X-Token: TU_TOKEN" -H "Content-Type: application/json" \
  --data-binary @Theme.json
```

### Arquitectura

```
main.py ──▶ ThemeRuntime ──▶ renderer.ThemeRenderer   (PIL: LCD/Web)
                     │      sensor_hub                  (psutil + HWiNFO/linux_sensors)
                     └──▶ outputs/
                            output_lcd.py   (LY/HID USB)
                            output_dmd.py   (DMDCanvas offscreen + RGB565 TCP)
                            output_hdmi.py  (HDMICanvas + ventana fullscreen)
                            output_web.py   (Flask)
```

Los módulos de render, canvas, transiciones DMD, drivers y sensores se copian tal cual
de Thermal-Engine-Studio para garantizar la **paridad visual** con el editor. Lo nuevo
es el runtime sin UI (`runtime.py`, `theme.py`, `renderer.py`, `sensor_hub.py`,
`outputs/`) y la API de push en `webserver.py`.

### Tests y lint

```bash
python -m pytest -q
python -m ruff check .
```

---

<a id="english"></a>

## English

**Headless** monitoring runtime, sibling of [Thermal Engine Studio](../Thermal-Engine-Linux).
No editor: it loads a **saved theme** (designed with Studio) and renders it live with
the host's sensor data, delivering it to **USB LCD, DMD panels (TCP), HDMI monitors
and/or a web server**. Built to run in **Docker on terminals and autonomous machines**
(servers, kiosks, HTPCs) and to receive themes over **HTTP push**.

### Remote workflow (push)

1. Design the theme with Studio on your laptop.
2. Push it to the remote device with **Studio: `File → Publish to ThermalEngineLite...`**
   or the CLI:
   ```bash
   python tools/push_theme.py --url http://device:4241 --token TOKEN --theme Theme.json
   ```
3. Lite validates the JSON and applies it **live** (no restart), reconfiguring outputs.
   Or mount the theme as a file (`theme_path`) and let Lite reload it on change.

### Usage

```bash
scripts/install-linux.sh
scripts/run-linux.sh --config config.json      # local
docker compose up -d --build                    # Docker
python main.py --theme /data/theme.json --targets web,dmd --dmd-ip 192.168.1.66
```

Without a display server, Qt starts in **offscreen** mode automatically (DMD and Web
work; HDMI needs a display).

### HTTP API

`GET /`, `GET /image.jpg`, `GET /theme`, `POST /theme` (push, `X-Token`), `GET /info`,
`GET /sensors` (`X-Token`), `GET /status`, `GET /healthz`, `GET /config`, plus local
presets (`GET /presets`, `POST /apply_preset`).

### Configuration

Defaults `< config.json < environment (TE_*) < CLI args. See the Spanish section for the
full key list; `config.json.example` is a ready-to-edit template.

### Tests

```bash
python -m pytest -q
python -m ruff check .
```

### Créditos / Credits

Núcleo reutilizado de [Thermal Engine Studio / Thermal-Engine-Linux](../Thermal-Engine-Linux).
Protocolo LY de referencia: [Lexonight1/thermalright-trcc-linux](https://github.com/Lexonight1/thermalright-trcc-linux).
Firmware DMD: [sito1982/RetroPixelLED-ThermalEngine](https://github.com/sito1982/RetroPixelLED-ThermalEngine).
