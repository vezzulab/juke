# Third-party software

Juke is © 2026 Vezzu Studio and licensed under the [Juke License 1.0](LICENSE).

Juke's packages include the software below. Each part keeps its own licence, and those licences apply to that part only.

## Juke for Linux: Python packages

| Component | Used for | Licence |
|---|---|---|
| [Qt 6](https://www.qt.io) with [PySide6](https://doc.qt.io/qtforpython-6/) | The interface | LGPL-3.0 |
| [python-vlc](https://github.com/oaubert/python-vlc) | Python access to libVLC | LGPL-2.1-or-later |
| [mutagen](https://github.com/quodlibet/mutagen) | Reading and writing song tags and covers | GPL-2.0-or-later |
| [httpx](https://www.python-httpx.org), httpcore, h11 | Talking to your server and the internet | BSD-3-Clause; MIT |
| [anyio](https://github.com/agronholm/anyio), [idna](https://github.com/kjd/idna) | Networking | MIT; BSD-3-Clause |
| [certifi](https://github.com/certifi/python-certifi) | The certificates that secure connections | MPL-2.0 |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Finding the stream of a radio station's page | Unlicense |
| [Inter](https://rsms.me/inter/) | Typeface | SIL Open Font License 1.1 |

## Juke for Linux: libraries inside the AppImage

The AppImage carries these as separate shared libraries, and you can replace them with your own builds by extracting the AppImage (`--appimage-extract`) and repacking your copy for your own use. Their source code is available from the projects listed, and the packaged versions from the Ubuntu 22.04 source packages of the same names (`apt source <name>`).

| Component | Used for | Licence |
|---|---|---|
| [libVLC](https://www.videolan.org/vlc/libvlc.html) and its plugins | Playing sound | LGPL-2.1-or-later; some plugins GPL-2.0-or-later |
| [FFmpeg](https://ffmpeg.org) libraries (libavcodec, libavformat, libavutil, libswresample), as built by Ubuntu | Decoding AAC, ALAC, WMA and other formats | **GPL-2.0-or-later** (Ubuntu's build) |
| [x264](https://www.videolan.org/developers/x264.html), [x265](https://www.x265.org), [Xvid](https://www.xvid.com) | Pulled in by the FFmpeg build; not used to play music | **GPL-2.0-or-later** |
| [libdvdnav](https://code.videolan.org/videolan/libdvdnav), [libdvdread](https://code.videolan.org/videolan/libdvdread) | Pulled in by libVLC; not used to play music | **GPL-2.0-or-later** |
| [libass](https://github.com/libass/libass) | Pulled in by libVLC; not used to play music | ISC |
| [libmtp](https://libmtp.sourceforge.net) | Sending music to phones and tablets over USB | LGPL-2.1-or-later |
| [libusb](https://libusb.info) | USB access for libmtp | LGPL-2.1-or-later |
| [libgcrypt](https://gnupg.org/software/libgcrypt/), [libgpg-error](https://gnupg.org/software/libgpg-error/) | Cryptography used by libVLC | LGPL-2.1-or-later |
| [Python](https://www.python.org) 3.12 (python-build-standalone) | Runs Juke | PSF License |
| Qt 6 libraries | The interface | LGPL-3.0 |

## Juke for Android

| Component | Used for | Licence |
|---|---|---|
| [AndroidX Media3](https://github.com/androidx/media) (ExoPlayer, Session) | Playing sound, lock screen and Bluetooth controls | Apache-2.0 |
| [Jetpack Compose](https://developer.android.com/jetpack/compose), AndroidX | The interface | Apache-2.0 |
| [OkHttp](https://square.github.io/okhttp/) | Network | Apache-2.0 |
| [Coil](https://coil-kt.github.io/coil/) | Album covers and station logos | Apache-2.0 |
| [Kotlin](https://kotlinlang.org) standard library | Runs Juke | Apache-2.0 |

## Services Juke talks to, only when you ask

[Radio Browser](https://www.radio-browser.info) (the radio directory), [LRCLIB](https://lrclib.net) (lyrics) and your own Airsonic / Subsonic server. They are not part of Juke.
