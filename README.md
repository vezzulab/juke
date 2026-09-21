<div align="center">

<img src="assets/hero.png" alt="Juke — a modern music player for Linux" width="100%">

<br>

**A modern 3-pane music player for Linux.**<br>
Your own files, your Airsonic / Subsonic server, internet radio and a 10-band equalizer. It stays quick with big libraries and light on the battery.

<br>

**English** · [Español](README.es.md)

<br>

![Linux](https://img.shields.io/badge/platform-Linux-7aa2f7?style=for-the-badge&logo=linux&logoColor=white)
![AppImage](https://img.shields.io/badge/package-AppImage-cba6f7?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3.10+-7aa2f7?style=for-the-badge&logo=python&logoColor=white)
![Qt](https://img.shields.io/badge/Qt-6%20·%20PySide6-cba6f7?style=for-the-badge&logo=qt&logoColor=white)
![Engine](https://img.shields.io/badge/audio-libVLC-7aa2f7?style=for-the-badge&logo=vlcmediaplayer&logoColor=white)

[**Download**](https://github.com/vezzulab/juke/releases/latest) &nbsp;·&nbsp; [**Website**](https://vezzulab.github.io/juke/) &nbsp;·&nbsp; [Report a problem](https://github.com/vezzulab/juke/issues)

</div>

<br>

## Why Juke

The layout is the classic one: sources on the left, songs in the middle, the player on top. Dark or light theme, libVLC underneath, and a song list that stays quick as the library grows.

<table>
<tr>
<td width="50%" valign="top">

### Quick with big libraries
The song table never loads your library into memory. It keeps an ordered list of ids and pulls rows from SQLite one page at a time while you scroll. Search, sort and filter happen in the database, over indexed columns.

</td>
<td width="50%" valign="top">

### Airsonic, the way you keep it
Browse your server **by folders**, exactly as it shows them, or by artist / album / genre. Sync uses the server's bulk search — a 6,000-song library in about 8 seconds — retries slow requests and never deletes songs it could not reach. Songs stream directly; nothing is downloaded first.

</td>
</tr>
<tr>
<td valign="top">

### Internet radio
**My Stations**, **Explore Radio** (the community directory radio-browser.info) and **Add station by URL**: paste a web page, a stream or a `.pls` / `.m3u` and Juke finds the audio. The LCD shows **LIVE**, the station and the song on air. Stations keep changing their stream address, so Juke follows them when they move.

</td>
<td valign="top">

### Light on resources
An idle Juke makes **no wake-ups at all**. Playing on battery it uses about **1 %** of one core. libVLC, the network stack and the tag reader are loaded only when needed, and the level meter stays still on battery. Measured numbers below.

</td>
</tr>
<tr>
<td valign="top">

### 10-band equalizer
Ten bands (60 Hz – 16 kHz), ±20 dB preamp, fifteen built-in presets (including **Dembow, Reggaeton, Salsa, Merengue and Bachata**) and your own. Every preset is played with its own headroom, so a bass boost never makes the sound break up. It runs through libVLC's native equalizer on one long-lived player, so switching songs — or tuning in a radio station — never resets it.

</td>
<td valign="top">

### A real queue, and your own playlists
**Play next** inserts right after the current song; **Add to queue** goes to the end. The queue is temporary and independent of the list you started from, which resumes when it is empty. Make playlists with the **+** next to *Playlists*.

</td>
</tr>
<tr>
<td valign="top">

### Dark and light
Pick a theme, or let Juke match your desktop. Both palettes are checked for legibility (WCAG contrast), and the switch is instant — `Ctrl` + `T`.

</td>
<td valign="top">

### Updates on your terms
When it opens, and every 30 minutes while it is open (switchable), Juke asks GitHub whether a newer release exists. If so it shows what changed and **you** choose *Update now*, *Later* or *Skip this version*. Downloads are verified against their SHA-256 before anything is replaced. **The Android app does the same**: it shows what changed, downloads the APK, checks it and hands it to Android's installer (you allow *Install unknown apps* for Juke once). A fix published under the same version number is recognised by its SHA-256 too.

</td>
</tr>
<tr>
<td valign="top">

### Local and remote, one library
Files on disk and songs on your server share the same metadata model. Juke only asks for the playable URL — `file:///…` or `https://…/stream.view` — at the moment you press Play.

</td>
<td valign="top">

### Bilingual, Wayland-ready
English and Spanish, switchable live. Qt 6 HiDPI scaling (fractional too), Wayland first with X11 fallback, and every icon is an SVG rendered at your screen's exact scale — nothing blurry.

</td>
</tr>
</table>

## Your music, in your folders

Under **Folders** in the sidebar Juke keeps your music the way you arrange it. There is no import step: whatever you do, it just happens.

- **Music.juke** sits in your Music folder like a library. Open it and you find `folders.db` (how things are organized), a `Folders` directory with the same tree as shortcuts to your songs, and a short README. Your files stay where they are: Juke never moves, renames or deletes them.
- Make folders, put folders inside folders, drag songs into them from the list, or drop files and whole folders from your file manager onto the sidebar. Dropped folders keep their layout.
- Right-click a folder to rename, duplicate or delete it, sort what is inside (A→Z, Z→A, by number, newest, oldest), play it, shuffle it or add it to the queue.
- Deleting a folder takes its songs out of Juke; the files stay on disk. If you delete or move a folder in your file manager, Juke notices as soon as you come back to it.
- **Find duplicates** is in the ⋯ menu, next to *Show* for Favorites, Recently played and the queue.
- **Edit metadata** works on one song or many. Select with `Ctrl` + `A`, `Ctrl` + click or `Shift` + click, right-click ▸ *Edit metadata…*, and only the fields you change are written. Add, replace or remove the cover, or just drop an image on the window; it is stored in the file itself.
- The update window says which version you are on, which one is out and what changed, and you accept or cancel.
- **Send feedback…** and **View log…** are in the ⋯ menu. A report opens as a new issue on GitHub for you to review. Your home folder, passwords and server address are hidden first.
- The AppImage adds itself to your applications menu the first time it runs.
- **Twenty colour themes**, ten light and ten dark, one click away from the palette button next to the ⋯ menu. Soft pastels (Rose, Lavender, Mint, Sky, Peach, Sand, Lagoon, Coral, Sage, Lemon) and deeper looks (Deep Forest, Ocean, Sunset, Neon, Ember, Arctic, Twilight, Amber, Rosewood, Graphite), all checked for legibility.
- **Lyrics.** Right-click a song ▸ *Add lyrics…* (paste them or import a `.lrc` file) or *Find lyrics…*, which searches [LRCLIB](https://lrclib.net), a free lyrics service, by the song's name. A column on the right opens by itself when the playing song has lyrics, and stays shut when it has none. Synced lyrics light up the line being sung. Juke also reads a `.lrc` file beside the song and the lyrics inside its tags.

## Screenshots

<div align="center">
<img src="assets/screenshot-main.png" alt="Library view with the LCD display, sidebar and song table" width="100%">
</div>

<table>
<tr>
<td width="50%"><img src="assets/screenshot-radio.png" alt="Internet radio: My Stations with a station on air"><br><sub><b>Internet radio</b> — saved stations, the <b>LIVE</b> badge and the song on air.</sub></td>
<td width="50%"><img src="assets/screenshot-light.png" alt="The light theme"><br><sub><b>Light theme</b> — or match your desktop automatically.</sub></td>
</tr>
<tr>
<td><img src="assets/screenshot-folders.png" alt="Airsonic browsed by the server's folders"><br><sub><b>Airsonic by folders</b> — the server's hierarchy, expandable in the sidebar.</sub></td>
<td><img src="assets/screenshot-queue.png" alt="The current queue with Play next and Add to queue items"><br><sub><b>Current queue</b> — Play next, Add to queue, then the list you started from.</sub></td>
</tr>
<tr>
<td><img src="assets/screenshot-equalizer.png" alt="Ten-band equalizer with live response curve"><br><sub><b>Equalizer</b> — live response curve, presets, playback speed and stereo balance.</sub></td>
<td><img src="assets/screenshot-settings.png" alt="Airsonic settings"><br><sub><b>Settings</b> — language, theme, folders, updates and your Airsonic / Subsonic server.</sub></td>
</tr>
</table>

## Juke for Android

<div align="center">
<img src="assets/android-player.png" alt="The player on Android" width="30%">
<img src="assets/android-library.png" alt="Music folders on the card" width="30%">
<img src="assets/android-radio.png" alt="The radio directory on Android" width="30%">
</div>

Juke also runs on a phone or a tablet. It is in [`android/`](android), written in Kotlin with Jetpack
Compose and Media3.

- Your music on the card or in the phone's storage, listed by folders. There is no card in some
  phones, and then it just shows the internal storage.
- Your Airsonic / Subsonic server on its own tab, also by folders.
- Radio: the directory, or paste an address. If a page has several stations, it offers all of them.
- Keeps playing with the screen off, with the usual controls in the notification.
- 10-band equalizer, English and Spanish, dark and light.
- *Settings ▸ Help* has **Send feedback** and the app's **log**, with private details hidden, and a **Support on Ko-fi** button.
- The same twenty colour themes, in *Settings ▸ Colors*.
- **Lyrics and karaoke.** Find lyrics by the song's name or paste them, see them follow the song, and switch to **Karaoke**: big lines, and a countdown into each phrase.
- **Sort** folders and songs A → Z or Z → A, in the library and on the server.
- Better on the lock screen: the player card, the notification and headset or Bluetooth buttons work, tapping the notification opens Juke, and the system can resume what was playing. The time bar follows your finger and shows where you jump at once.

Get `Juke-<version>.apk` from the [latest release](https://github.com/vezzulab/juke/releases/latest).
It needs Android 8 or newer and weighs about 3 MB. To build it you need the Android SDK and JDK 17:

```sh
cd android
./gradlew :app:assembleDebug
```

## Install

### AppImage (recommended)

1. Download `Juke-x86_64.AppImage` (about 190 MB) from the [latest release](https://github.com/vezzulab/juke/releases/latest).
2. Make it executable and run it:

   ```sh
   chmod +x Juke-x86_64.AppImage
   ./Juke-x86_64.AppImage
   ```

3. That is all. The first time it runs, Juke adds itself to your **applications menu with its icon**. It only touches your own user account (`~/.local/share/applications` and `~/.local/share/icons`) and you can undo it any time in *Settings*.

Or in one line, which downloads it, makes it executable and starts it:

```sh
curl -fsSL https://vezzulab.github.io/juke/install.sh | sh
```

Everything Juke needs — Python, Qt, libVLC and yt-dlp — is inside the file; there is nothing else to install. It expects:

- x86_64 Linux with **glibc 2.35 or newer** (Ubuntu 22.04, Debian 12, Fedora 36 or newer)
- PulseAudio or PipeWire for sound (present on practically every desktop)
- FUSE 2 (`libfuse2`) — or run it with `--appimage-extract-and-run`

**Updating:** Juke tells you when a new release is out (or use *menu ▸ Check for updates…*). If the AppImage sits in a folder you can write to, *Update now* replaces it in place and offers to restart.

### From source

Juke needs libVLC installed on the system:

| Distribution | libVLC |
| --- | --- |
| Fedora | `sudo dnf install vlc-libs` (RPM Fusion) |
| Debian / Ubuntu | `sudo apt install libvlc5 vlc-plugin-base` |
| Arch | `sudo pacman -S vlc` |

```sh
git clone https://github.com/vezzulab/juke.git
cd juke
python -m venv .venv && . .venv/bin/activate
pip install -e .
juke                 # or: python -m juke
```

To add the launcher and icon of a source install to your menu: `juke --install-desktop` (and `--uninstall-desktop` to remove it). Files given on the command line are played: `juke song.flac`.

## Using it

| | |
| --- | --- |
| **Library** | Add your music folders in *Settings ▸ Library* (or the button on the empty library). Juke indexes them in a low-priority background thread and only re-reads files that changed. |
| **Airsonic** | Open **Settings** from the ⋯ menu (or use *Set up Airsonic…* on the empty Airsonic view) ▸ *Airsonic* tab: server address (e.g. `http://your-server:4040`), user and password, then *Test connection*. *Sync Airsonic* imports the server; browse it under **Servers**. Finished songs are scrobbled to the server. Servers that cannot check salted tokens (Airsonic-Advanced with hashed passwords) are supported: Juke then signs in with the password and tells you to prefer `https://`. |
| **Radio** | Under **Radio**: *My Stations* (yours) and *Explore Radio* (search by name or pick a tag). ♥ saves a station, ▶ tunes in. *Add station by URL…* takes any web address. See below. |
| **Queue** | Right-click ▸ **Play next** / **Add to queue**. ⋯ ▸ *Show* ▸ *Current Queue* lists what is playing, what you queued, and what follows. |
| **Playlists** | Click the **+** next to *Playlists* (or `Ctrl` + `N`). Right-click songs ▸ *Add to playlist*; right-click a playlist to rename or delete it. Playlists survive rescans and Airsonic re-syncs. |
| **Favorites** | Right-click ▸ *Mark as favorite*. Show them from ⋯ ▸ *Show*. |
| **Folders** | Click the **+** next to *Folders*, or drag songs and folders in. Right-click a folder for the rest. |
| **Tags and cover** | Right-click ▸ *Edit metadata…* writes to the files (local songs), one or many at once, cover included. |
| **Theme** | *Settings ▸ Theme* (match the system / dark / light) or `Ctrl` + `T`. |

| Shortcut | Action |
| --- | --- |
| `Space` | Play / pause |
| `Enter` or double-click | Play the selected song |
| `Ctrl` + `→` / `←` | Next / previous |
| `Ctrl` + `F` | Search |
| `Ctrl` + `N` | New playlist |
| `Ctrl` + `E` | Equalizer |
| `Ctrl` + `T` | Switch light / dark |
| `Ctrl` + `,` | Settings |
| `Ctrl` + `Q` | Quit |

### Adding a station by URL

Paste an address and Juke shows *Searching for an audio signal…* while it works it out:

1. **Direct:** the address is a stream (`.mp3`, `.aac`, `.ogg`, `.m3u8`), an Icecast / Shoutcast mount (`http://host:8000/stream`), or a `.pls` / `.m3u` playlist — the first entry that works is used. Addresses that give no hint are asked what they are.
2. **Web pages:** stream addresses the page links to are tried first (a station's player usually embeds `…:8146/stream`, an `.m3u8`, a `.pls` or an `<audio>` tag), then [yt-dlp](https://github.com/yt-dlp/yt-dlp). Something that ends — an intro video, a jingle — is not a station and is only used if nothing live turns up.
3. **Name and icon:** from the stream's ICY header or the page title, and the page's icon.

News and blog sites often only *mention* their stations; if a page has no audio, Juke says so and points you to *Explore Radio*.

**Stations move.** They change their stream address all the time, so a saved station remembers where it came from — its Radio-Browser id, or the page or playlist you gave. When you tune in, Juke plays the saved address at once and checks in the background; if the station moved, or the stream dies, it switches to the new address and remembers it.

**Song on air.** The LCD shows the ICY title the station sends. libVLC does not ask for titles on `https://` streams, so Juke reads them itself — one small request when you tune in and every 30 seconds after that, only while the window is in front. Placeholders such as "Now Playing info goes here" are ignored.

## Privacy

Juke has no telemetry, no accounts and no analytics. It bundles its font and icons, so it makes no requests for them. It connects to:

| What | When |
| --- | --- |
| Your Airsonic / Subsonic server | Only if you configure one. |
| `api.github.com` | When it opens and every 30 minutes while open, to look for a new release, if you leave *Check for updates automatically* on. Only the program name and version are sent. |
| Radio Browser (`*.api.radio-browser.info`) and the stations themselves | Only when you open *Explore Radio*, add a station, or tune in. |
| `lrclib.net` | Only when you press *Find lyrics…*, or if you turn on *Search lyrics online* in Settings. It gets the song's name, artist, album and length, nothing else. |
| `github.com` (the issues page) | Only when you press *Open on GitHub* in *Send feedback…*. Juke sends nothing itself; the report opens in your browser. |

## Performance

Measured on an AMD Ryzen 7 2700U laptop running on battery (Fedora, Wayland), from `/proc`:

| | AppImage |
| --- | --- |
| Idle, window open | 0 wake-ups, ~0 % CPU, ~100 MB resident |
| Playing (level meter still on battery) | ~1.2 % of one core, ~136 MB |
| 60,000 tracks | default order in ~25 ms, a text search in ~100–140 ms, one page of rows in ~2 ms |
| Airsonic sync, 6,000 songs | ~8 s |

How: an idle Juke has no timers running; libVLC, httpx and mutagen load on first use; the poll timer only exists while playing and slows down when the window is hidden; start-up disk work is delayed and low priority; the animated level meter only runs when the window is in front **and** the machine is on mains power (*Settings ▸ Level meter*); the AppImage ships precompiled bytecode.

## How it stays fast

- **SQLite with explicit indexes** on `artist`, `album`, `title`, `genre`, `source_type` (and `folder`), plus a composite index for the default order.
- **Scanning runs in a `QThread`** and reports through signals; the interface never waits on `mutagen`.
- **A virtual, lazy `QAbstractTableModel`**: ids in memory, rows fetched 256 at a time, at most 48 pages cached.
- **One audio pipeline**: a single libVLC media player for the whole session.

## Project layout

```
juke/
├── main.py             entry point (Wayland/HiDPI setup, CLI)
├── config.py           XDG paths, settings persistence
├── updater.py          GitHub release check, verified in-place update
├── integration.py      applications-menu entry + icons (AppImage)
├── power.py            mains / battery detection
├── i18n.py, locales/   English / Spanish, live switching
├── audio/              libVLC engine, equalizer, queue, balance, ICY titles, source resolver
├── api/                Airsonic client, Radio-Browser client, stream resolver
├── db/                 SQLite library (tracks, playlists, stations) and the background indexer
└── gui/                main window, top bar, sidebar, song table, radio view, dialogs, themes, SVG icons
android/                Juke for Android (Kotlin, Jetpack Compose, Media3)
packaging/              AppImage build (AppRun, desktop entry, scripts)
docs/                   the project website (GitHub Pages)
tests/                  unit tests and offscreen GUI tests (incl. real playback through libVLC)
```

## Build the AppImage

```sh
packaging/build-appimage.sh     # writes dist/Juke-x86_64.AppImage
```

Build on the **oldest** distribution you want to support — an AppImage needs at least the glibc it was built with. Pushing a `v*` tag runs the [release workflow](.github/workflows/appimage.yml) (Ubuntu 22.04), which builds the AppImage and attaches it to the release. See the header of the script for the environment variables (`PYTHON_PREFIX`, `APPIMAGETOOL`, `RUNTIME_FROM`).

To ship a new version: raise `__version__` in `juke/__init__.py`, create the release, and every installed Juke will offer it.

## Development

```sh
pip install -e .
python -m unittest discover -s tests -t .
QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2 python tools/make_assets.py assets   # regenerate screenshots
```

The suite has over a hundred tests, including real playback through libVLC (skipped if libVLC is missing).

## Known limits

- The spectrum in the LCD is an **animated meter, not an analyser** — libVLC does not expose FFT data.
- **Karaoke** (full-screen lyrics with a countdown into each phrase) is on Android. On Linux you get the synced lyrics column. Juke never processes the sound of your songs beyond the equalizer you choose.
- Stereo **balance** needs PulseAudio or PipeWire (`pactl`) and a stereo stream; it is disabled otherwise.
- No MPRIS / global media keys yet, no gapless playback, no drag-and-drop reordering inside playlists, one Airsonic server at a time.
- Your own folders live in Juke (*Folders*), the Airsonic server is browsed by its folders, and the local library by artist, album and genre.
- Radio: stations that need a login or use protected streams are not supported. The song on air needs the station to send ICY metadata.

## License

Juke is free to use, for any purpose, on as many computers and devices as you own, personal or commercial. You may not modify it or redistribute it: to share it, point people to the [official downloads](https://github.com/vezzulab/juke/releases). The source is published so it can be read and checked. Your music, playlists and settings are always yours. The full terms are in the [Juke License 1.0](LICENSE), the same terms as [Piklin](https://github.com/vezzulab/Piklin), and the software made by others that Juke includes keeps its own licence, listed in [NOTICE.md](NOTICE.md).

## Credits

[libVLC](https://www.videolan.org/) for playback, [Qt for Python](https://doc.qt.io/qtforpython-6/) for the interface, [yt-dlp](https://github.com/yt-dlp/yt-dlp), [httpx](https://www.python-httpx.org/) and [mutagen](https://mutagen.readthedocs.io/), the community directory [radio-browser.info](https://www.radio-browser.info/), and the [Inter](https://rsms.me/inter/) typeface (SIL Open Font License, bundled).
