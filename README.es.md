<div align="center">

<img src="assets/hero-es.png" alt="Juke — un reproductor de música moderno para Linux" width="100%">

<br>

**Un reproductor de música moderno de 3 paneles para Linux.**<br>
Tu biblioteca local, tu servidor Airsonic / Subsonic y un ecualizador de 10 bandas — y sigue siendo instantáneo con más de 50.000 pistas.

<br>

[English](README.md) · **Español**

<br>

![Linux](https://img.shields.io/badge/plataforma-Linux-7aa2f7?style=for-the-badge&logo=linux&logoColor=white)
![AppImage](https://img.shields.io/badge/paquete-AppImage-cba6f7?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3.10+-7aa2f7?style=for-the-badge&logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/Qt-6%20·%20PySide6-cba6f7?style=for-the-badge&logo=qt&logoColor=white)
![Motor](https://img.shields.io/badge/audio-libVLC-7aa2f7?style=for-the-badge&logo=vlcmediaplayer&logoColor=white)

[**Descargar**](https://github.com/vezzulab/juke/releases/latest) &nbsp;·&nbsp; [**Sitio web**](https://vezzulab.github.io/juke/) &nbsp;·&nbsp; [Reportar un problema](https://github.com/vezzulab/juke/issues)

</div>

<br>

## Por qué Juke

El clásico diseño de iTunes 4 — fuentes a la izquierda, canciones en el centro, el reproductor arriba — reconstruido para hoy: una interfaz oscura, redondeada y con aire Libadwaita, una tubería de audio de verdad y una biblioteca que no se traba cuando crece.

<table>
<tr>
<td width="50%" valign="top">

### Instantáneo, sin importar el tamaño
La tabla de canciones nunca carga tu biblioteca en memoria. Guarda una lista ordenada de ids y trae las filas de SQLite página a página mientras haces scroll. Buscar, ordenar y filtrar ocurre en la base de datos, sobre columnas indexadas.

</td>
<td width="50%" valign="top">

### Airsonic, como lo tienes organizado
Recorre tu servidor **por carpetas**, tal como están en disco, o por artista / álbum / género. Las canciones se reproducen en streaming directo por HTTP(S); no se descarga nada antes. La autenticación usa el token con sal de Subsonic: tu contraseña nunca se envía.

</td>
</tr>
<tr>
<td valign="top">

### Ecualizador de 10 bandas
Diez bandas (60 Hz – 16 kHz), preamp de ±20 dB, diez presets incluidos y los tuyos guardados. Usa el ecualizador nativo de libVLC sobre un único reproductor de larga vida, así que cambiar de canción nunca lo reinicia.

</td>
<td valign="top">

### Una cola de verdad, y tus propias listas
**Reproducir a continuación** inserta justo después de la canción actual; **Añadir a la cola** va al final. La cola es temporal e independiente de la lista desde la que empezaste, que continúa cuando la cola se vacía. Crea listas con el **+** junto a *Listas*.

</td>
</tr>
<tr>
<td valign="top">

### Local y remoto, una sola biblioteca
Los archivos del disco y las canciones de tu servidor comparten el mismo modelo de metadatos. Juke solo pide la URL reproducible — `file:///…` o `https://…/stream.view` — en el momento en que pulsas Play.

</td>
<td valign="top">

### Bilingüe y listo para Wayland
Inglés y español, con cambio en vivo. Escalado HiDPI de Qt 6 (también fraccionario), Wayland primero con X11 como respaldo, y todos los iconos son SVG dibujados a la escala exacta de tu pantalla: nada borroso.

</td>
</tr>
</table>

## Capturas

<div align="center">
<img src="assets/screenshot-main-es.png" alt="Vista de biblioteca con la pantalla LCD, el panel lateral y la tabla de canciones" width="100%">
</div>

<table>
<tr>
<td width="50%"><img src="assets/screenshot-folders.png" alt="Airsonic recorrido por las carpetas del servidor"><br><sub><b>Airsonic por carpetas</b> — la jerarquía del servidor, desplegable en el panel lateral.</sub></td>
<td width="50%"><img src="assets/screenshot-queue.png" alt="La cola actual con elementos de Reproducir a continuación y Añadir a la cola"><br><sub><b>Cola actual</b> — a continuación, añadidas a la cola y luego la lista de origen.</sub></td>
</tr>
<tr>
<td><img src="assets/screenshot-equalizer.png" alt="Ecualizador de diez bandas con curva de respuesta en vivo"><br><sub><b>Ecualizador</b> — curva de respuesta en vivo, presets, velocidad y balance estéreo.</sub></td>
<td><img src="assets/screenshot-settings.png" alt="Ajustes de Airsonic"><br><sub><b>Ajustes</b> — idioma, carpetas de música y tu servidor Airsonic / Subsonic.</sub></td>
</tr>
</table>

> Las capturas de arriba están en inglés salvo la principal; la interfaz completa cambia de idioma en vivo desde *Ajustes*.

## Instalación

### AppImage (recomendado)

1. Descarga `Juke-x86_64.AppImage` de la [última versión](https://github.com/vezzulab/juke/releases/latest).
2. Hazlo ejecutable y ábrelo:

   ```sh
   chmod +x Juke-x86_64.AppImage
   ./Juke-x86_64.AppImage
   ```

3. En el primer arranque Juke se ofrece a añadirse a tu **menú de aplicaciones con su icono**. Solo toca tu propia cuenta de usuario (`~/.local/share/applications` y `~/.local/share/icons`) y puedes deshacerlo cuando quieras en *Ajustes*.

Todo lo que Juke necesita — Python, Qt y libVLC — va dentro del archivo. Solo necesitas:

- Linux x86_64 con **glibc 2.35 o superior** (Ubuntu 22.04, Debian 12, Fedora 36 o más reciente)
- PulseAudio o PipeWire para el sonido (presentes en prácticamente todo escritorio)
- FUSE 2 (`libfuse2`) — o ejecútalo con `--appimage-extract-and-run`

### Desde el código fuente

Juke necesita libVLC instalado en el sistema:

| Distribución | libVLC |
| --- | --- |
| Fedora | `sudo dnf install vlc-libs` (RPM Fusion) |
| Debian / Ubuntu | `sudo apt install libvlc5 vlc-plugin-base` |
| Arch | `sudo pacman -S vlc` |

```sh
git clone https://github.com/vezzulab/juke.git
cd juke
python -m venv .venv && . .venv/bin/activate
pip install -e .
juke                 # o: python -m juke
```

Para añadir al menú el lanzador y el icono de una instalación desde fuente: `juke --install-desktop` (y `--uninstall-desktop` para quitarlo). Los archivos pasados por la línea de comandos se reproducen: `juke cancion.flac`.

## Uso

| | |
| --- | --- |
| **Biblioteca** | Añade tus carpetas de música en *Ajustes ▸ Biblioteca*. Juke las indexa en un hilo en segundo plano y solo relee los archivos que cambiaron. |
| **Airsonic** | Pulsa **Ajustes** al final del panel lateral (o el botón *Configurar Airsonic…* de la vista vacía de Airsonic) ▸ pestaña *Airsonic*: dirección del servidor (p. ej. `http://tu-servidor:4040`), usuario y contraseña, luego *Probar conexión*. *Sincronizar Airsonic* importa el servidor una vez; recórrelo en **Servidores**. Las canciones terminadas se registran (scrobble) en el servidor. |
| **Cola** | Clic derecho ▸ **Reproducir a continuación** / **Añadir a la cola**. La lista *Cola actual* muestra lo que suena, lo que encolaste y lo que sigue. |
| **Listas** | Pulsa el **+** junto a *Listas* (o `Ctrl` + `N`) para crear una. Clic derecho en canciones ▸ *Añadir a la lista*; clic derecho en una lista para renombrarla o eliminarla. Las listas sobreviven a los reescaneos y a las resincronizaciones de Airsonic. |
| **Favoritos** | Clic derecho ▸ *Marcar como favorita*. |
| **Etiquetas** | Clic derecho ▸ *Editar metadatos…* escribe en el archivo (canciones locales). |

| Atajo | Acción |
| --- | --- |
| `Espacio` | Reproducir / pausar |
| `Enter` o doble clic | Reproducir la canción seleccionada |
| `Ctrl` + `→` / `←` | Siguiente / anterior |
| `Ctrl` + `F` | Buscar |
| `Ctrl` + `N` | Nueva lista |
| `Ctrl` + `E` | Ecualizador |
| `Ctrl` + `,` | Ajustes |
| `Ctrl` + `Q` | Salir |

## Cómo se mantiene rápido

- **SQLite con índices explícitos** en `artist`, `album`, `title`, `genre`, `source_type` (y `folder`), más un índice compuesto para el orden por defecto.
- **El escaneo corre en un `QThread`** y avisa por señales; la interfaz nunca espera a `mutagen`.
- **Un `QAbstractTableModel` virtual y perezoso**: ids en memoria, filas leídas de 256 en 256, como máximo 48 páginas en caché.
- **Una sola tubería de audio**: un único reproductor libVLC para toda la sesión.

Medido en una laptop AMD Ryzen 7 2700U con 60.000 pistas (`tests/test_core.py`): orden por defecto en ~25 ms, una búsqueda de texto en ~100–140 ms y una página de filas en ~2 ms.

## Estructura del proyecto

```
juke/
├── main.py             punto de entrada (Wayland/HiDPI, CLI)
├── config.py           rutas XDG, persistencia de ajustes
├── i18n.py, locales/   inglés / español, cambio en vivo
├── integration.py      entrada del menú de aplicaciones + iconos (AppImage)
├── audio/              motor (libVLC), ecualizador, cola, balance, resolución de fuentes
├── api/airsonic.py     cliente REST Subsonic asíncrono (httpx)
├── db/                 biblioteca SQLite e indexador en segundo plano
└── gui/                ventana principal, barra superior, panel lateral, tabla, ecualizador, diálogos, tema QSS, iconos SVG
packaging/              construcción del AppImage (AppRun, entrada .desktop, scripts)
docs/                   el sitio web del proyecto (GitHub Pages)
tests/                  pruebas unitarias y de interfaz sin pantalla
```

## Construir el AppImage

```sh
packaging/build-appimage.sh     # escribe dist/Juke-x86_64.AppImage
```

Constrúyelo en la distribución **más antigua** que quieras soportar: un AppImage necesita al menos la glibc con la que se construyó. El [workflow de publicación](.github/workflows/appimage.yml) construye en Ubuntu 22.04. Las variables de entorno (`PYTHON_PREFIX`, `APPIMAGETOOL`, `RUNTIME_FROM`) están documentadas al inicio del script.

## Desarrollo

```sh
pip install -e .
python -m unittest discover -s tests -t .
QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2 python tools/make_assets.py assets   # regenerar capturas
```

Las pruebas incluyen reproducción real con libVLC (se omite si libVLC no está).

## Límites conocidos

- El espectro de la pantalla LCD es un **medidor animado, no un analizador** — libVLC no expone datos FFT.
- El **balance** estéreo necesita PulseAudio o PipeWire (`pactl`) y un flujo estéreo; si no, se desactiva.
- Aún no hay MPRIS / teclas multimedia globales, ni reproducción sin pausas (gapless), ni reordenar canciones arrastrando dentro de las listas, y solo un servidor Airsonic a la vez.
- La navegación por carpetas está disponible para Airsonic; la biblioteca local se recorre por artista, álbum y género.
