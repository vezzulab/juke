## Security update

What changed for you:

- **Updates are checked.** Juke only installs an update if its file is exactly the one we published. If not, it refuses it.
- **Safer server addresses.** If you type a server address without `http://` or `https://`, Juke now uses a secure connection (unless the server is on your own network).
- **Your server password stays protected.** Juke no longer sends it unprotected over plain `http` to a server on the internet.
- **Stricter sync.** It refuses damaged or oversized copies.

> **Downloaded Juke 1.0.4 for Mac or Linux on 27 October before 11:41 (New York time), and it does not open?** Download it again from this page. Android is not affected.

Also: a faster Android app, and when the check for updates cannot be done, Juke tries again within minutes instead of half an hour later.

## What's new in 1.0.4

- **YouTube, audio only.** Search a song and Juke shows exactly what you asked for (search *Juan Luis Guerra* and you get Juan Luis Guerra), plays just the audio, with no video and no ads, and never downloads anything. **Search an artist and you get the whole repertoire**, most watched first. Add songs to a playlist and play it later without searching again. Mixes, covers, karaoke and live recordings stay out unless you ask for them. On the computer it is the *YouTube* section under *Online*; on Android, the new *YouTube* tab.
- **Playlists on Android.** The phone now has playlists (a new *Playlists* tab, with a search box and a choice of order: by name, most recent, most songs), with songs from your music, your server and YouTube. Songs the phone does not have show greyed.
- **Everything follows you, by itself.** Playlists, radio stations, favorites and a few settings sync between your Linux, Mac and Android: when Juke opens, a few seconds after you change something and every few minutes, deletions included. Menu ▸ *Backup & sync…* (Android: *Settings ▸ Backup & sync*) sets it up with a code only you have; the copy is encrypted, so the server cannot read it. A copy in a file is there too.
- **Updates inside every app.** On a **Mac**, *Update now* downloads the disk image, checks it and puts the new Juke in place of the old one by itself (before, it only opened the page). On Linux and Android it already did. The YouTube part on the computer updates itself too, so YouTube changes do not break Juke while you wait for a new version.
- A *What's new* window shows once the first time you open this version.

## Downloads

- **Mac:** the Dock icon now has the same size as the other apps. Download `Juke-macos-arm64.dmg` (Apple chips, macOS 15 or newer); the first time, macOS asks you to confirm it in *System Settings ▸ Privacy & Security ▸ Open Anyway*.
- **Linux:** download `Juke-x86_64.AppImage`. **Android:** download `Juke-1.0.4.apk` (Android 8 or newer).

---

## Actualización de seguridad

Qué cambia para ti:

- **Las actualizaciones se comprueban.** Juke solo instala una actualización si su archivo es exactamente el que publicamos. Si no, la rechaza.
- **Direcciones de servidor más seguras.** Si escribes la dirección de un servidor sin `http://` ni `https://`, Juke ahora usa una conexión segura (salvo que el servidor esté en tu propia red).
- **La contraseña de tu servidor sigue protegida.** Juke ya no la envía sin protección por `http` a un servidor de internet.
- **Sincronización más estricta.** Rechaza copias dañadas o demasiado grandes.

> **¿Descargaste Juke 1.0.4 para Mac o Linux el 27 de octubre antes de las 11:41 (hora de Nueva York) y no abre?** Vuelve a descargarlo desde esta página. Android no está afectado.

Además: una app de Android más rápida, y cuando no se puede hacer la búsqueda de actualizaciones, Juke lo intenta de nuevo en pocos minutos y no media hora después.

## Novedades de la 1.0.4

- **YouTube, solo audio.** Busca una canción y Juke muestra exactamente lo que pediste (si buscas *Juan Luis Guerra*, salen canciones de Juan Luis Guerra), reproduce solo el audio, sin video y sin anuncios, y no descarga nada. **Si buscas un artista sale todo su repertorio**, lo más visto primero. Añade canciones a una playlist y tócala después sin volver a buscar. Los mixes, covers, karaoke y grabaciones en vivo quedan fuera a menos que los pidas. En la computadora es la sección *YouTube* bajo *En línea*; en Android, la pestaña nueva *YouTube*.
- **Playlists en Android.** El teléfono ya tiene playlists (una pestaña nueva, *Listas*, con caja de búsqueda y orden a elegir: por nombre, más recientes, más canciones), con canciones de tu música, de tu servidor y de YouTube. Las canciones que el teléfono no tiene salen en gris.
- **Todo te sigue, solo.** Playlists, emisoras de radio, favoritos y algunos ajustes se sincronizan entre tu Linux, tu Mac y tu Android: al abrir Juke, unos segundos después de que cambies algo y cada pocos minutos, borrados incluidos. Menú ▸ *Copia y sincronización…* (Android: *Ajustes ▸ Copia y sincronización*) lo prepara con un código que solo tú tienes; la copia va cifrada, así que el servidor no puede leerla. También hay una copia en un archivo.
- **Actualizaciones dentro de cada app.** En una **Mac**, *Actualizar ahora* descarga la imagen de disco, la comprueba y pone la Juke nueva en lugar de la vieja por sí sola (antes solo abría la página). En Linux y Android ya lo hacía. La parte de YouTube en la computadora también se actualiza sola, así que los cambios de YouTube no rompen Juke mientras esperas una versión nueva.
- Una ventana de *Novedades* aparece una sola vez, la primera vez que abres esta versión.

## Descargas

- **Mac:** el icono del Dock ahora tiene el mismo tamaño que el de las otras apps. Descarga `Juke-macos-arm64.dmg` (chips de Apple, macOS 15 o más nuevo); la primera vez, macOS pide confirmarlo en *Ajustes del Sistema ▸ Privacidad y seguridad ▸ Abrir de todos modos*.
- **Linux:** descarga `Juke-x86_64.AppImage`. **Android:** descarga `Juke-1.0.4.apk` (Android 8 o más nuevo).

<!-- juke-build:mac=1793115353 -->
