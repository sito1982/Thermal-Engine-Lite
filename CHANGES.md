# Changelog

## 0.10.0

El tema recibido por push se persiste como predeterminado.

### Añadido
- `runtime.persist_theme()`: guarda el tema (JSON tal cual) en `theme_path` de
  forma **atomica** (`*.tmp` + `os.replace`). Si no hay `theme_path` o falla la
  escritura, el tema sigue aplicado y se registra un aviso.
- `load_theme_dict(..., source="push")` persiste automaticamente; el watcher no
  recarga por nuestro propio guardado (`_theme_mtime` actualizado).
- `POST /theme` devuelve `persisted` (y `persist_error` si fallo).

### Efecto
- Un diseno publicado desde Studio queda como predeterminado: al reiniciar el
  servicio o el contenedor, Lite carga ese tema desde `theme_path`.

## 0.9.0

Calidad del preview Web y `tap_screen` con "next"/"prev".

### Cambiado
- JPEG del webserver/preview a **calidad 90** y **4:4:4** (`subsampling=0`) en
  Studio y Lite (antes 80), para que el preview se vea mas nitido. Coste marginal
  (`optimize=False`, sin renders extra).

### Añadido
- `ThemeElement.tap_screen` admite `"next"`/`"prev"` ademas de un indice entero
  (navegacion por transiciones en HDMI; en Lite solo se conserva, sin tactil).

## 0.8.0

Fuentes portables (empaquetadas) y arreglo de orientacion.

### Añadido
- `assets/fonts/ttf`: **Liberation Mono** y **Liberation Sans** (Regular/Bold/
  Italic/BoldItalic), ademas de las ya presentes (Matrix Sans, Tiny5, Pixel
  Operator...). Lite ya no depende de las fuentes del sistema.
- `constants.PORTABLE_FONT_FAMILIES`, `DEFAULT_FONT_FAMILY` y
  `DMD_DEFAULT_FONT_FAMILY`.
- `ThemeRenderer`: resolucion por mapa familia -> TTF empaquetado + alias
  (`Arial`->Liberation Sans, `Courier New`->Liberation Mono, ...) y
  `assets/fonts` en la busqueda; registro en Qt de **todas** las fuentes
  empaquetadas al arrancar (`_load_dmd_fonts`).

### Corregido
- Fuentes del editor que no se cargaban en Lite (p. ej. **Liberation Mono** y
  **Press Start 2P**): ahora se resuelven desde `assets/fonts`.
- Orientacion: al cargar un tema cuadrado tras uno vertical, se resetea la
  orientacion (antes el guard `disp_w != disp_h` lo impedia).

## 0.7.0

Nuevo elemento **Icon** (iconos de hardware empaquetados).

### Añadido
- Tipo de elemento `icon` (LCD/HDMI/Custom): iconos de `icons/` (CPU/GPU/RAM/
  HDD/SSD/fan/motherboard/network/psu/usb/monitor/keyboard/mouse, en 2 variantes).
- `constants.resolve_icon_path()`: resolucion segura dentro de `icons/` (sin
  selector de fichero).
- Campos `ThemeElement`: `icon_name` y `tint` (recolorea el icono con `color`).
- Render en el renderer PIL (`render_icon_rgba`) y en el canvas Qt (`draw_icon`).

## 0.6.0

Nuevo elemento **Disk Element** para LCD/HDMI/Custom.

### Añadido
- `disk_element` en `LCD_WIDGET_TYPES` (render por `lcd_widgets.render_element`):
  panel de disco con barra (libre/usado/ninguna) y sparklines de lectura/escritura,
  alimentado por `sources`/`panel_values`.
- Campos de `ThemeElement`: `bar_mode` ("free"/"used"/"none") y
  `show_sparklines` (+ `to_dict`).
- `lcd_widgets.history_for(..., key=)`: historiales separados por metrica (READ vs
  WRITE) y `Ctx` con `sources`/`panel_values`/`bar_mode`/`show_sparklines`.
- `runtime.sync_lcd_sensor_values()` resuelve tambien `panel_values` de los
  elementos con `sources` (necesario para el Disk Element).

## 0.5.0

Sensores de discos (HDD/SSD/NVMe) como fuentes por defecto.

### Añadido
- `disks.py`: espacio (usado/total/libre/%) y E/S (lectura/escritura MB/s) por
  punto de montaje, con tipo de disco (NVMe/SSD/HDD) y agregado `disk.all.*`.
  Claves `disk.<slug>.<metric>`, sin configuracion (sensor por defecto).
- Lite expone las claves de disco en `/sensors` y registra sus unidades
  (`size`→GB, `speed`→MB/s) para el formateo.

### Corregido
- Lite resuelve el prefijo `lite.` de las fuentes de proyectos Lite
  (`lite.cpu_temp` → `cpu_temp`), de modo que los temas publicados desde un
  proyecto Lite (CPU/GPU y ahora discos) muestran valores reales.

## 0.4.0

Arreglo del canvas de resolucion libre (solo-Web) y del canvas Custom.

### Corregido
- Lite ignoraba `web.width`/`web.height`, por lo que un proyecto solo-Web (o el
  lienzo de resolucion libre del wizard) se renderizaba a la resolucion del LCD
  (1920x480). Ahora el canvas LCD/Web usa `web.width/height` cuando existe.
- El bloque `custom` no se renderizaba: ahora se parsea (pantallas/transiciones y
  tamano de `custom_config`) y se sirve como fuente Web.

### Añadido
- `runtime.render_custom_image()` y `_effective_web_source()` con `custom`
  (auto → hdmi → custom → lcd).
- `theme.custom_*`, `theme.web_width/height`; `to_dict` re-emite el bloque
  `custom` completo y `web.width/height`.

## 0.3.0

Paridad de render con Thermal Engine Studio (esquema B: Lite acepta y renderiza
el tema completo).

### Añadido
- 7 elementos LCD de alta resolución (`ring_gauge`, `segment_bar`, `zone_bar`,
  `stat_tile`, `sparkline`, `level_bar`, `column_chart`) y `touch_nav` (solo
  render, sin interacción). Copiados de Studio (`lcd_widgets.py`, `touch_nav.py`).
- Dispatch en el renderer PIL (`render_lcd_widget`, `render_touch_nav_rgba`) y en
  el canvas Qt (`draw_lcd_widget`, `draw_touch_nav`).
- 8 campos nuevos de `ThemeElement` (`arc_span`, `start_angle`, `show_ticks`,
  `thresholds`, `orientation`, `tap_screen`, `nav_position`, `nav_items`).
- Pantallas/transiciones HDMI: `screens.py` (común a DMD/HDMI), `hdmi.screens` y
  transiciones en `outputs/output_hdmi.py`.
- `web.source` (auto/lcd/hdmi) y `render_web_source_image()`; `/image.jpg` sirve
  la fuente efectiva.
- Esquema: `allowed_keys` acepta `web`, `custom`, `custom_config`; `tap_action`
  admite `transition`.
- Unidades `energy`/`digital` en el formateo de valores.

### Notas
- El canvas **Custom** se acepta en el tema pero **no se renderiza** en Lite.
- El formato de tema mantiene compatibilidad (migración de `hdmi.elements` a una
  pantalla; bloques `lcd`/`dmd`/`hdmi` legacy).

## 0.2.0

Soporte para proyectos **Thermal Engine Lite** en Studio y API de sensores.

### Añadido
- `GET /sensors`: devuelve los valores de sensores del equipo (protegido con
  `X-Token` si hay token configurado).
- `GET /info`: metadatos del dispositivo (hostname, versión, tema, targets,
  dimensiones, modelo LCD) para el wizard de creación de proyectos de Studio.
- `runtime.info()` y `version.py` (versión central).
- El esquema de tema acepta el bloque opcional `lite` (metadato de proyecto Lite
  que Lite ignora).

## 0.1.0

Primera version de ThermalEngineLite: runtime de monitorizacion headless, hermano de
Thermal Engine Studio, reutilizando su nucleo de render y drivers.

### Añadido
- `main.py`: entrada CLI + `QApplication` en modo offscreen automatico cuando no hay
  servidor grafico.
- `runtime.py` (`ThemeRuntime`): carga de temas, orquestacion de salidas, cache JPEG y
  vigilancia del archivo de tema.
- `theme.py`: modelo y carga/validacion del formato de tema de Studio (dual LCD/DMD/HDMI
  y formato legacy).
- `renderer.py` (`ThemeRenderer`): render LCD con Pillow extraido de `main_window.py`
  (gauges, barras, texto, DMD widgets, video, fuentes, correccion de color y vertical).
- `sensor_hub.py`: hilo psutil + `get_sensor_data` (psutil + HWiNFO/linux_sensors).
- Salidas en `outputs/`: LCD (LY/HID USB), DMD (TCP RGB565 con transiciones), HDMI
  (fullscreen) y Web (Flask).
- API de push en `webserver.py`: `POST /theme` autenticado con token, `GET /theme`,
  `GET /status` y `GET /healthz`.
- `tools/push_theme.py`: CLI para enviar un tema a Lite.
- `lite_config.py`: configuracion por archivo, variables de entorno (`TE_*`) y CLI.
- Docker: `Dockerfile`, `docker-compose.yml`, `.dockerignore`; scripts de instalacion
  y arranque, unidad systemd y reglas udev.
- Tests portados del nucleo (DMD, HDMI, sensores, elementos) y nuevos para el modelo de
  tema.

### Notas
- Los modulos de canvas, transiciones DMD, drivers, sensores y constantes se copian tal
  cual de Thermal-Engine-Studio para preservar la paridad visual con el editor.
