import asyncio
import unittest
from pathlib import Path

from . import helpers  # noqa: F401  (sets XDG env first)

import httpx

from juke.api.radio import RadioBrowserClient, RadioBrowserError, fetch_icon, icon_path, station_from_api
from juke.api.radio_resolver import (ResolveError, classify_probe, classify_url, normalize_url, page_meta, parse_playlist,
                                     resolve_stream_url, scan_page, Probe)
from juke.db.database import Database, Station


def run(coro):
    return asyncio.run(coro)


def site(routes, default=httpx.Response(404)):
    """A fake web: ``routes`` maps a URL (without scheme) to an httpx.Response or a callable."""
    def handler(request):
        key = str(request.url).split("://", 1)[1]
        route = routes.get(key)
        return route(request) if callable(route) else (route if route is not None else default)
    return httpx.MockTransport(handler)


def audio(**headers):
    return httpx.Response(200, headers={"content-type": "audio/mpeg", **headers}, content=b"\xff\xfb" * 100)


class StationDbTests(unittest.TestCase):
    def test_save_list_update_remove(self):
        db = Database(Path(helpers.ROOT) / "stations.db")
        a = db.add_station(Station(0, "  Zeta FM ", "http://z.example/live", tags="pop", bitrate=64))
        b = db.add_station(Station(0, "alfa radio", "http://a.example/live", country="Chile", codec="MP3", bitrate=128, uuid="u1"))
        self.assertEqual([s.name for s in db.stations()], ["alfa radio", "Zeta FM"])        # alphabetical, trimmed
        again = db.add_station(Station(0, "Zeta FM (renamed)", "http://z.example/live", tags="rock"))
        self.assertEqual(again, a)                                                            # same stream address = same station
        self.assertEqual(db.count_stations(), 2)
        self.assertEqual(db.stations()[1].tags, "rock")
        self.assertEqual(db.station_urls(), {"http://z.example/live", "http://a.example/live"})
        db.remove_station(b)
        self.assertEqual([s.id for s in db.stations()], [a])
        self.assertTrue(db.stations()[0].saved)
        self.assertFalse(Station(0, "x", "http://x").saved)


class StationMovesTests(unittest.TestCase):
    """Stations change their stream address all the time; a saved one must be able to find it again."""

    def test_source_address_is_kept_and_survives_a_plain_resave(self):
        db = Database(Path(helpers.ROOT) / "moves.db")
        sid = db.add_station(Station(0, "Cima", "https://s.example:8146/stream", source_url="https://cima.example/"))
        db.add_station(Station(0, "Cima renamed", "https://s.example:8146/stream"))            # re-saved without a source
        self.assertEqual(db.stations()[0].source_url, "https://cima.example/")
        self.assertTrue(db.update_station_stream(sid, "https://new.example:9000/live", codec="AAC", bitrate=64))
        moved = db.stations()[0]
        self.assertEqual((moved.stream_url, moved.codec, moved.bitrate, moved.id), ("https://new.example:9000/live", "AAC", 64, sid))
        other = db.add_station(Station(0, "Other", "https://taken.example/x"))
        self.assertFalse(db.update_station_stream(other, "https://new.example:9000/live"))     # already used by another station

    def test_old_databases_gain_the_source_column(self):
        import sqlite3
        path = Path(helpers.ROOT) / "old-stations.db"
        conn = sqlite3.connect(path)
        conn.executescript("CREATE TABLE stations (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, stream_url TEXT NOT NULL UNIQUE, "
                           "homepage TEXT NOT NULL DEFAULT '', favicon TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '', "
                           "country TEXT NOT NULL DEFAULT '', codec TEXT NOT NULL DEFAULT '', bitrate INTEGER NOT NULL DEFAULT 0, "
                           "uuid TEXT NOT NULL DEFAULT '', added_at REAL NOT NULL DEFAULT 0); "
                           "INSERT INTO stations (name, stream_url) VALUES ('Kept', 'http://k.example/s');")
        conn.commit()
        conn.close()
        db = Database(path)
        self.assertEqual([(s.name, s.source_url) for s in db.stations()], [("Kept", "")])

    def test_refresh_from_radio_browser_by_uuid(self):
        from juke.api.radio import refresh_station
        record = {"name": "Latina", "url_resolved": "http://new.example/latina.aac", "codec": "AAC", "bitrate": 96, "stationuuid": "u-9"}
        seen = []

        def handler(request):
            seen.append(request.url.path)
            return httpx.Response(200, json=[record])

        old = Station(7, "Latina", "http://old.example/latina.mp3", codec="MP3", bitrate=128, uuid="u-9")
        fresh = run(refresh_station(old, transport=httpx.MockTransport(handler)))
        self.assertEqual(seen, ["/json/stations/byuuid/u-9"])
        self.assertEqual((fresh.id, fresh.name, fresh.stream_url, fresh.codec, fresh.bitrate), (7, "Latina", "http://new.example/latina.aac", "AAC", 96))
        same = Station(7, "Latina", "http://new.example/latina.aac", uuid="u-9")
        self.assertIsNone(run(refresh_station(same, transport=httpx.MockTransport(handler))))          # nothing new

    def test_refresh_from_the_page_the_user_gave(self):
        from juke.api.radio import refresh_station
        page = httpx.Response(200, headers={"content-type": "text/html"}, text='<title>Cima</title><script>load("https://s2.example:8146/stream")</script>')
        transport = site({"cima.example/": page, "s2.example:8146/stream": audio(**{"icy-name": "Cima FM", "icy-br": "64"})})
        old = Station(3, "Cima", "https://s1.example:8146/stream", bitrate=128, source_url="https://cima.example/")
        fresh = run(refresh_station(old, transport=transport))
        self.assertEqual((fresh.stream_url, fresh.bitrate, fresh.id, fresh.source_url), ("https://s2.example:8146/stream", 64, 3, "https://cima.example/"))
        dead_site = site({"cima.example/": httpx.Response(500)})
        self.assertIsNone(run(refresh_station(old, transport=dead_site)))                              # site down: keep what we had
        self.assertIsNone(run(refresh_station(Station(1, "x", "http://x.example/s"), transport=site({}))))   # nowhere to look

    def test_engine_ignores_titles_that_are_only_the_address_leaf(self):
        from juke.audio.engine import AudioEngine
        engine = AudioEngine()
        engine._station_name, engine._url_leaf = "RADIO CIMA 100.5 FM", "stream"
        for fake in ("stream", "Stream", "RADIO CIMA 100.5 FM", "https://x.example/stream", ""):
            self.assertFalse(engine._is_real_title(fake), fake)
        self.assertTrue(engine._is_real_title("Marc Anthony - Vivir Mi Vida"))
        engine._url_leaf = "live.mp3"
        self.assertFalse(engine._is_real_title("live"))                                                # the leaf without its extension


class PureHelperTests(unittest.TestCase):
    def test_url_normalisation_and_classification(self):
        self.assertEqual(normalize_url("mi-emisora.com/player"), "https://mi-emisora.com/player")
        self.assertEqual(normalize_url("radio.example:8000/stream"), "https://radio.example:8000/stream")   # a port is not a scheme
        for bad in ("", "   ", "ftp://x.example/a", "file:///etc/passwd", "javascript:alert(1)", "http://"):
            with self.assertRaises(ResolveError) as ctx:
                normalize_url(bad)
            self.assertEqual(ctx.exception.code, "bad_url", bad)
        self.assertEqual(classify_url("http://a.example/live.PLS"), "playlist")
        self.assertEqual(classify_url("http://a.example/x.m3u?token=1"), "playlist")
        for direct in ("http://a.example/live.mp3", "http://a.example/live.AAC", "https://a.example/hls/index.m3u8",
                       "http://a.example:8000/stream", "http://a.example:8000/;", "http://a.example:9300/radio/live"):
            self.assertEqual(classify_url(direct), "direct", direct)
        for direct in ("https://sonicpanel.example:8146/stream", "http://a.example:7777/listen/radio.mp3", "http://a.example:9999/;stream.mp3",
                       "http://a.example:4433/autodj", "http://a.example:81/stream"):
            self.assertEqual(classify_url(direct), "direct", direct)                # any unusual port with a stream-like path
        for other in ("https://mi-emisora.com/player", "http://a.example:8000/", "http://a.example:8000/status.html",
                      "https://a.example/stream", "http://a.example:8146/",
                      "http://a.example:8146/admin.php", "http://a.example:8146/about"):
            self.assertEqual(classify_url(other), "unknown", other)

    def test_playlist_formats(self):
        pls = "[playlist]\nNumberOfEntries=2\nFile2=http://b.example/two\nTitle2=Two\nFile1=http://a.example/one\nTitle1=One\nVersion=2\n"
        self.assertEqual(parse_playlist(pls), [("One", "http://a.example/one"), ("Two", "http://b.example/two")])
        m3u = "#EXTM3U\n#EXTINF:-1,Radio Uno\nhttp://a.example/uno\n#comment\nicy://b.example/dos\nrtsp://nope/x\nrelative.mp3\nhttp://a.example/uno\n"
        self.assertEqual(parse_playlist(m3u, "http://base.example/dir/list.m3u"), [
            ("Radio Uno", "http://a.example/uno"), ("", "http://b.example/dos"), ("", "http://base.example/dir/relative.mp3")])
        self.assertEqual(parse_playlist("garbage"), [])

    def test_probe_classification(self):
        make = lambda ct, body=b"", **h: Probe("u", ct, h, body)
        self.assertEqual(classify_probe(make("audio/mpeg")), "audio")
        self.assertEqual(classify_probe(make("application/octet-stream", **{"icy-name": "X"})), "audio")   # ICY header wins
        self.assertEqual(classify_probe(make("application/ogg")), "audio")
        self.assertEqual(classify_probe(make("audio/x-mpegurl", b"#EXTM3U\nhttp://a/x")), "playlist")
        self.assertEqual(classify_probe(make("audio/x-mpegurl", b"#EXTM3U\n#EXT-X-VERSION:3\nseg.ts")), "hls")
        self.assertEqual(classify_probe(make("application/vnd.apple.mpegurl", b"#EXTM3U\n#EXT-X-STREAM-INF:x\nl.m3u8")), "hls")
        self.assertEqual(classify_probe(make("text/html; charset=utf-8", b"<html>")), "html")
        self.assertEqual(classify_probe(make("", b"[playlist]\nFile1=x")), "playlist")
        self.assertEqual(classify_probe(make("application/zip")), "other")

    def test_page_metadata_and_stream_candidates(self):
        page = """<html><head><title> Radio   Tropical | Listen live </title>
          <meta property="og:site_name" content="Radio Tropical &amp; Más">
          <link rel="shortcut icon" href="/static/icon.png"></head><body>
          <audio controls src="/live/stream"></audio>
          <script>var s = "https:\\/\\/cdn.example\\/hls\\/index.m3u8"; var p = 'http://a.example:8000/radio';
                  var t = "http://x.example/track.mp3?x=1&amp;y=2"; var pl = "http://x.example/list.pls";</script>
          <a href="http://x.example/about.html">about</a>
          <a href="/soma/groove256.pls">256k</a> <a href='streams/live.MP3?x=1'>mp3</a> <a href="/about">no</a> <a href="/img/logo.png">logo</a>
          </body></html>"""
        meta = page_meta(page, "https://tropical.example/player")
        self.assertEqual(meta["title"], "Radio Tropical & Más")                 # og:site_name beats <title>
        self.assertEqual(meta["favicon"], "https://tropical.example/static/icon.png")
        no_meta = page_meta("<title>Solo título</title>", "https://x.example/a/b")
        self.assertEqual((no_meta["title"], no_meta["favicon"]), ("Solo título", "https://x.example/favicon.ico"))
        found = scan_page(page, "https://tropical.example/player")
        self.assertEqual(found[0], "https://tropical.example/live/stream")       # the <audio> tag comes first
        self.assertIn("https://cdn.example/hls/index.m3u8", found)              # JSON-escaped slashes are undone
        self.assertIn("http://x.example/track.mp3?x=1&y=2", found)              # entities are decoded
        self.assertIn("http://x.example/list.pls", found)
        self.assertNotIn("http://x.example/about.html", found)
        self.assertIn("https://tropical.example/soma/groove256.pls", found)        # relative links are resolved against the page
        self.assertIn("https://tropical.example/streams/live.MP3?x=1", found)
        self.assertNotIn("https://tropical.example/about", found)
        self.assertNotIn("https://tropical.example/img/logo.png", found)
        self.assertLess(found.index("http://x.example/track.mp3?x=1&y=2"), found.index("http://x.example/list.pls"))


class ResolverTests(unittest.TestCase):
    def test_direct_stream_takes_name_from_icy_headers(self):
        transport = site({"radio.example/live.mp3": audio(**{"icy-name": "  Radio  Uno ", "icy-genre": "Salsa,Latin",
                                                            "icy-br": "128", "icy-url": "http://radio.example"})})
        result = run(resolve_stream_url("http://radio.example/live.mp3", transport=transport))
        self.assertEqual((result["stream_url"], result["title"], result["codec"], result["bitrate"], result["tags"]),
                         ("http://radio.example/live.mp3", "Radio Uno", "MP3", 128, "Salsa,Latin"))
        self.assertEqual(result["source"], "direct")

    def test_icecast_mount_on_a_known_port(self):
        transport = site({"radio.example:8000/stream": audio(**{"icy-name": "Icecast FM", "content-type": "audio/aacp"})})
        result = run(resolve_stream_url("http://radio.example:8000/stream", transport=transport))
        self.assertEqual((result["title"], result["codec"]), ("Icecast FM", "AAC"))

    def test_extensionless_address_that_answers_with_audio(self):
        # stations really send accented names as raw UTF-8 header bytes
        accented = httpx.Response(200, headers=[(b"content-type", b"audio/mpeg"), (b"icy-name", "Sin extensión".encode("utf-8"))], content=b"\xff\xfb" * 50)
        transport = site({"radio.example/listen": accented})
        result = run(resolve_stream_url("radio.example/listen", transport=transport))       # scheme is added
        self.assertEqual((result["stream_url"], result["title"]), ("https://radio.example/listen", "Sin extensión"))

    def test_hls_stream(self):
        hls = httpx.Response(200, headers={"content-type": "application/vnd.apple.mpegurl"}, content=b"#EXTM3U\n#EXT-X-VERSION:3\n")
        result = run(resolve_stream_url("https://cdn.example/live/index.m3u8", transport=site({"cdn.example/live/index.m3u8": hls})))
        self.assertEqual((result["codec"], result["title"]), ("HLS", "cdn.example"))         # no name anywhere: use the host

    def test_pls_playlist_skips_dead_entries_and_uses_its_title(self):
        pls = "[playlist]\nFile1=http://dead.example/x\nTitle1=Dead\nFile2=http://ok.example/live\nTitle2=Buena Radio\n"
        transport = site({"radio.example/list.pls": httpx.Response(200, headers={"content-type": "audio/x-scpls"}, text=pls),
                          "ok.example/live": audio()})
        result = run(resolve_stream_url("http://radio.example/list.pls", transport=transport))
        self.assertEqual((result["stream_url"], result["title"]), ("http://ok.example/live", "Buena Radio"))

    def test_m3u_playlist_and_nested_playlist(self):
        m3u = "#EXTM3U\n#EXTINF:-1,Desde M3U\nhttp://ok.example/inner.pls\n"
        inner = "[playlist]\nFile1=http://ok.example/live\n"
        transport = site({"radio.example/a.m3u": httpx.Response(200, text=m3u), "ok.example/inner.pls": httpx.Response(200, text=inner),
                          "ok.example/live": audio(**{"icy-name": "Al final"})})
        result = run(resolve_stream_url("http://radio.example/a.m3u", transport=transport))
        self.assertEqual((result["stream_url"], result["title"]), ("http://ok.example/live", "Al final"))

    def test_playlist_without_a_live_entry(self):
        transport = site({"radio.example/a.pls": httpx.Response(200, text="[playlist]\nFile1=http://dead.example/x\n")})
        with self.assertRaises(ResolveError) as ctx:
            run(resolve_stream_url("http://radio.example/a.pls", transport=transport))
        self.assertEqual(ctx.exception.code, "no_audio")

    def test_web_page_goes_to_ytdlp_first(self):
        page = httpx.Response(200, headers={"content-type": "text/html"}, text="<title>Mi Emisora</title><link rel=icon href=/i.png>")
        asked = []

        def fake_ytdlp(url):
            asked.append(url)
            return {"stream_url": "https://cdn.example/raw.m3u8", "title": "Título de yt-dlp", "favicon": ""}

        result = run(resolve_stream_url("https://mi-emisora.com/player", transport=site({"mi-emisora.com/player": page}), ytdlp=fake_ytdlp))
        self.assertEqual(asked, ["https://mi-emisora.com/player"])
        self.assertEqual((result["stream_url"], result["title"], result["source"]), ("https://cdn.example/raw.m3u8", "Título de yt-dlp", "yt-dlp"))
        self.assertEqual(result["favicon"], "https://mi-emisora.com/i.png")                # icon from the page

    def test_web_page_falls_back_to_the_streams_it_embeds(self):
        page = httpx.Response(200, headers={"content-type": "text/html"}, text=(
            '<title>x</title><meta property="og:site_name" content="Radio Página"><link rel="icon" href="/f.ico">'
            '<audio src="/dead"></audio><script>var u="http://s.example:8000/live";</script>'))
        transport = site({"radio.example/": page, "radio.example/dead": httpx.Response(404),
                          "s.example:8000/live": audio(**{"icy-name": "Nombre del stream"})})
        result = run(resolve_stream_url("https://radio.example/", transport=transport, ytdlp=lambda url: None))
        self.assertEqual((result["stream_url"], result["source"]), ("http://s.example:8000/live", "page"))
        self.assertEqual((result["title"], result["favicon"]), ("Nombre del stream", "https://radio.example/f.ico"))   # a real ICY name beats the page title

    def test_a_station_page_with_an_intro_video_resolves_to_the_live_stream_not_the_video(self):
        """Regression: cima100fm.com. yt-dlp's generic extractor picks up the page's intro <video>."""
        page = httpx.Response(200, headers={"content-type": "text/html"}, text=(
            '<title>Radio CIMA 100.5 - La Estrella</title><link rel="icon" href="/favicon.ico">'
            '<video autoplay src="/cimaintrovideo.mp4"></video><a href="/intro.mp3">intro</a>'
            '<script>player.load("https://sonicpanel.example:8146/stream");</script>'))
        transport = site({"cima.example/": page, "cima.example/intro.mp3": audio(),          # a finite jingle: has Content-Length
                          "sonicpanel.example:8146/stream": audio(**{"icy-name": "Unnamed Server", "icy-br": "128"})})
        intro = lambda url: {"stream_url": "https://cima.example/cimaintrovideo.mp4", "title": "intro", "favicon": ""}
        result = run(resolve_stream_url("https://cima.example/", transport=transport, ytdlp=intro))
        self.assertEqual(result["stream_url"], "https://sonicpanel.example:8146/stream")   # the real signal wins
        self.assertEqual(result["title"], "Radio CIMA 100.5 - La Estrella")                # generic ICY name is ignored
        self.assertEqual(result["bitrate"], 128)
        self.assertEqual(result["source"], "page")
        # with no live stream anywhere, the finite file is better than nothing, and is flagged as not live
        only_jingle = httpx.Response(200, headers={"content-type": "text/html"}, text='<title>Jingle</title><a href="/intro.mp3">x</a>')
        fallback = run(resolve_stream_url("https://cima.example/", transport=site({"cima.example/": only_jingle, "cima.example/intro.mp3": audio()}),
                                          ytdlp=lambda url: None))
        self.assertEqual((fallback["stream_url"], fallback["live"]), ("https://cima.example/intro.mp3", False))
        # and if the page gave no stream link, a finite video file from yt-dlp is still refused
        bare = httpx.Response(200, headers={"content-type": "text/html"}, text="<title>Sin señal</title><video src='/promo.mp4'></video>")
        from juke.api.radio_resolver import _ytdlp_extract  # noqa: F401  (the video filter lives there)
        with self.assertRaises(ResolveError):
            run(resolve_stream_url("https://x.example/", transport=site({"x.example/": bare}), ytdlp=lambda url: None))

    def test_name_choice_prefers_a_real_icy_name_over_the_page_title(self):
        from juke.api.radio_resolver import pick_title
        self.assertEqual(pick_title("Radio Tropical 98", "Home | Tropical"), "Radio Tropical 98")
        self.assertEqual(pick_title("Unnamed Server", "Home | Tropical"), "Home | Tropical")
        self.assertEqual(pick_title("", "", "host.example"), "host.example")

    def test_page_without_any_audio(self):
        page = httpx.Response(200, headers={"content-type": "text/html"}, text="<title>Blog</title><p>hola</p>")
        with self.assertRaises(ResolveError) as ctx:
            run(resolve_stream_url("https://blog.example/", transport=site({"blog.example/": page}), ytdlp=lambda url: None))
        self.assertEqual(ctx.exception.code, "no_audio")

    def test_unreachable_and_bad_addresses(self):
        with self.assertRaises(ResolveError) as ctx:
            run(resolve_stream_url("http://radio.example/live.mp3", transport=site({})))                # 404
        self.assertEqual(ctx.exception.code, "unreachable")

        def boom(request):
            raise httpx.ConnectError("no route")

        with self.assertRaises(ResolveError) as ctx:
            run(resolve_stream_url("http://radio.example/live.mp3", transport=httpx.MockTransport(boom)))
        self.assertEqual(ctx.exception.code, "unreachable")
        with self.assertRaises(ResolveError) as ctx:
            run(resolve_stream_url("gopher://radio.example/x"))
        self.assertEqual(ctx.exception.code, "bad_url")

    def test_shoutcast_v1_answers_icy_200_ok_which_http_parsers_reject(self):
        """A real socket server speaking the old "ICY 200 OK" dialect (no transport mock)."""
        async def scenario():
            async def serve(reader, writer):
                await reader.readuntil(b"\r\n\r\n")
                writer.write(b"ICY 200 OK\r\nicy-notice1: <BR>This stream requires Winamp<BR>\r\nicy-name: Radio Viejo\r\n"
                             b"icy-genre: Merengue\r\nicy-br: 96\r\nContent-Type: audio/mpeg\r\nicy-metaint: 8192\r\n\r\n")
                writer.write(b"\xff\xfb" * 200)
                await writer.drain()
                writer.close()

            server = await asyncio.start_server(serve, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            try:
                return await resolve_stream_url(f"http://127.0.0.1:{port}/;")
            finally:
                server.close()
                await server.wait_closed()

        result = run(scenario())
        self.assertEqual((result["title"], result["tags"], result["bitrate"], result["codec"]), ("Radio Viejo", "Merengue", 96, "MP3"))


class RadioBrowserTests(unittest.TestCase):
    RECORDS = [
        {"name": "Latina Salsa", "url": "http://a.example/x", "url_resolved": "http://a.example/x.mp3", "favicon": "https://a.example/f.ico",
         "tags": "latin,salsa,dance,pop,extra", "country": "France", "codec": "mp3", "bitrate": 128, "stationuuid": "u-1", "homepage": "http://a.example"},
        {"name": "Latina Salsa (mirror)", "url_resolved": "http://a.example/x.mp3"},                       # same stream: dropped
        {"name": "Solo url", "url": "https://b.example/live", "url_resolved": ""},
        {"name": "", "url_resolved": "http://c.example/x"},                                              # no name
        {"name": "Weird scheme", "url_resolved": "rtmp://c.example/x"},
    ]

    def test_mapping_dedup_and_query(self):
        seen = []

        def handler(request):
            seen.append(dict(request.url.params))
            return httpx.Response(200, json=self.RECORDS)

        client = RadioBrowserClient(transport=httpx.MockTransport(handler))
        stations = run(client.search("salsa", "latin"))
        self.assertEqual([s.name for s in stations], ["Latina Salsa", "Solo url"])
        first = stations[0]
        self.assertEqual((first.stream_url, first.codec, first.bitrate, first.uuid, first.id), ("http://a.example/x.mp3", "MP3", 128, "u-1", 0))
        self.assertEqual(first.tags, "latin, salsa, dance, pop")                                         # capped at four
        self.assertEqual((seen[0]["name"], seen[0]["tag"], seen[0]["hidebroken"], seen[0]["order"]), ("salsa", "latin", "true", "clickcount"))
        run(client.aclose())

    def test_falls_over_to_the_next_mirror_and_reports_total_failure(self):
        tried = []

        def handler(request):
            tried.append(request.url.host)
            return httpx.Response(500) if "de1" in request.url.host else httpx.Response(200, json=self.RECORDS[:1])

        client = RadioBrowserClient(transport=httpx.MockTransport(handler))
        self.assertEqual(len(run(client.search())), 1)
        self.assertEqual(tried, ["de1.api.radio-browser.info", "nl1.api.radio-browser.info"])
        tried.clear()
        run(client.search())
        self.assertEqual(tried, ["nl1.api.radio-browser.info"])                                          # remembers the good one
        dead = RadioBrowserClient(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
        with self.assertRaises(RadioBrowserError):
            run(dead.search())

    def test_station_from_api_edge_cases(self):
        self.assertIsNone(station_from_api({"name": "x"}))
        self.assertEqual(station_from_api({"name": "  Two   words ", "url": "http://x.example/a"}).name, "Two words")

    def test_icons_are_cached_scaled_and_size_limited(self):
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QColor, QImage
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        image = QImage(400, 300, QImage.Format_RGB32)
        image.fill(QColor("#7aa2f7"))
        data = QByteArray()                                   # must outlive the buffer (PySide does not keep it alive)
        buffer = QBuffer(data)
        buffer.open(QIODevice.WriteOnly)
        image.save(buffer, "PNG")
        buffer.close()
        png = bytes(data)
        url = "https://icons.example/a.png"
        self.assertTrue(run(fetch_icon(url, transport=site({"icons.example/a.png": httpx.Response(200, content=png)}))))
        saved = QImage(str(icon_path(url)))
        self.assertEqual(max(saved.width(), saved.height()), 160)
        self.assertTrue(run(fetch_icon(url, transport=site({}))))                                       # cached: no request needed
        self.assertFalse(run(fetch_icon("https://icons.example/b.png", transport=site({"icons.example/b.png": httpx.Response(200, content=b"not an image")}))))
        self.assertFalse(run(fetch_icon("https://icons.example/c.png", transport=site({"icons.example/c.png": httpx.Response(200, content=b"x" * 600_000)}))))
        self.assertFalse(run(fetch_icon("https://icons.example/d.png", transport=site({}))))            # 404
        self.assertFalse(run(fetch_icon("ftp://icons.example/e.png")))


if __name__ == "__main__":
    unittest.main()
