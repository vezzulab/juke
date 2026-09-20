package io.github.vezzulab.juke.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.net.ProtocolException
import java.net.URI
import java.util.concurrent.TimeUnit

class NoAudioException : Exception("no audio signal")

/**
 * Finds the live audio behind an address a person pastes: a stream, a .pls/.m3u playlist, or a station's web page
 * (including players that load their station list by script, like several stations on one portal).
 * Stations change their stream address constantly, so the caller keeps the page address to look again.
 */
object RadioResolver {
    private val http = OkHttpClient.Builder().connectTimeout(6, TimeUnit.SECONDS).readTimeout(8, TimeUnit.SECONDS)
        .followRedirects(true).followSslRedirects(true).build()

    private class Probe(val url: String, val kind: Kind, val live: Boolean, val name: String, val bitrate: Int, val codec: String, val text: String = "")
    private enum class Kind { AUDIO, PLAYLIST, HTML, NONE }

    fun normalize(input: String): String {
        val t = input.trim()
        require(t.isNotEmpty()) { "empty" }
        val withScheme = if (Regex("^[a-zA-Z][a-zA-Z0-9+.-]*://").containsMatchIn(t)) t else "https://$t"
        URI(withScheme).host ?: throw IllegalArgumentException("bad address")
        return withScheme
    }

    private fun codecOf(type: String): String = when {
        "mpeg" in type -> "MP3"; "aac" in type -> "AAC"; "ogg" in type -> "OGG"; "mpegurl" in type -> "HLS"; else -> ""
    }

    private fun probe(url: String): Probe = try {
        val request = Request.Builder().url(url).header("Icy-MetaData", "1").header("User-Agent", "Juke-Android/0.1").build()
        http.newCall(request).execute().use { r ->
            if (!r.isSuccessful) return@use Probe(url, Kind.NONE, false, "", 0, "")
            val type = r.header("content-type").orEmpty().lowercase().substringBefore(';').trim()
            val icy = r.headers.names().any { it.lowercase().startsWith("icy-") }
            val path = r.request.url.encodedPath.lowercase()
            when {
                type.contains("mpegurl") || type.contains("scpls") || path.endsWith(".pls") || path.endsWith(".m3u") ->
                    if (path.endsWith(".m3u8") || type.contains("apple")) Probe(url, Kind.AUDIO, true, "", 0, "HLS")
                    else Probe(url, Kind.PLAYLIST, false, "", 0, "", r.body?.source()?.let { it.request(65536); it.buffer.clone().readUtf8() }.orEmpty())
                type.startsWith("audio/") || type == "application/ogg" || icy ->
                    Probe(r.request.url.toString(), Kind.AUDIO, icy || r.header("content-length") == null,
                        r.header("icy-name").orEmpty().trim(), r.header("icy-br")?.substringBefore(',')?.trim()?.toIntOrNull() ?: 0, codecOf(type))
                type.contains("html") ->
                    Probe(url, Kind.HTML, false, "", 0, "", r.body?.source()?.let { it.request(600_000); it.buffer.clone().readUtf8() }.orEmpty())
                type.contains("json") || type.startsWith("text/") ->
                    Probe(url, Kind.HTML, false, "", 0, "", r.body?.source()?.let { it.request(600_000); it.buffer.clone().readUtf8() }.orEmpty())
                else -> Probe(url, Kind.NONE, false, "", 0, "")
            }
        }
    } catch (e: ProtocolException) {
        // Shoutcast v1 answers "ICY 200 OK", which HTTP parsers reject: that is a live stream
        if (e.message.orEmpty().contains("ICY 200")) Probe(url, Kind.AUDIO, true, "", 0, "MP3") else Probe(url, Kind.NONE, false, "", 0, "")
    } catch (e: Exception) {
        Probe(url, Kind.NONE, false, "", 0, "")
    }

    private fun playlistEntries(text: String, base: String): List<String> {
        val urls = Regex("""(?im)^\s*(?:File\d+\s*=\s*)?(https?://\S+)\s*$""").findAll(text).map { it.groupValues[1] }.toList()
        return urls.map { resolve(base, it) }.distinct()
    }

    private fun resolve(base: String, ref: String): String = try { URI(base).resolve(ref.trim()).toString() } catch (e: Exception) { ref }

    private fun unescape(s: String) = s.replace("\\/", "/").replace("&amp;", "&").replace("&#038;", "&").replace("&#38;", "&")

    private val streamish = Regex("""(?i)(\.(mp3|aac|m3u8|pls|m3u)(\?|$)|/stream\b|/live\b|/;$|:\d{2,5}/?;?$|/listen|icecast|shoutcast|radio\.co|streaming|/\d{3,5}/?;?$)""")

    private fun pageCandidates(html: String, base: String): List<String> {
        val text = unescape(html)
        val found = LinkedHashSet<String>()
        Regex("""(?i)(?:src|href|data-[a-z-]*(?:src|url|stream)[a-z-]*)\s*=\s*["']([^"']+)["']""").findAll(text).forEach {
            val u = resolve(base, it.groupValues[1]); if (u.startsWith("http") && streamish.containsMatchIn(u)) found += u
        }
        Regex("""["'](https?://[^"'\s<>\\]+)["']""").findAll(text).forEach { if (streamish.containsMatchIn(it.groupValues[1])) found += it.groupValues[1] }
        return found.take(12)
    }

    private fun embeddedLists(html: String, base: String): List<String> {
        val text = unescape(html)
        val found = LinkedHashSet<String>()
        Regex("""(?i)data-(?:tracks|playlist|stations)-url\s*=\s*["']([^"']+)["']""").findAll(text).forEach { found += resolve(base, it.groupValues[1]) }
        Regex("""["'](?:tracks_?url|tracksUrl|playlist_?url|playlistUrl|stations_?url)["']\s*:\s*["']([^"']+)["']""").findAll(text).forEach { found += resolve(base, it.groupValues[1]) }
        return found.take(4)
    }

    private class Listed(val title: String, val url: String, val cover: String)

    private fun jsonStations(node: Any?, base: String, out: MutableList<Listed>, depth: Int = 0) {
        if (depth > 6 || out.size > 40) return
        when (node) {
            is JSONArray -> for (i in 0 until node.length()) jsonStations(node.opt(i), base, out, depth + 1)
            is JSONObject -> {
                val raw = listOf("audio", "stream", "stream_url", "streamUrl", "url", "src", "file", "mp3").firstNotNullOfOrNull { k -> node.optString(k).takeIf { it.isNotBlank() } }
                if (raw != null) {
                    val url = resolve(base, raw)
                    if (url.startsWith("http") && !Regex("""(?i)\.(png|jpe?g|gif|webp|svg|ico|mp4|webm)(\?|$)""").containsMatchIn(url) && out.none { it.url == url }) {
                        val cover = listOf("cover", "image", "thumbnail", "logo", "artwork").firstNotNullOfOrNull { k -> node.optString(k).takeIf { it.isNotBlank() } }.orEmpty()
                        out += Listed(listOf("title", "name").firstNotNullOfOrNull { k -> node.optString(k).takeIf { it.isNotBlank() } }.orEmpty(), url, if (cover.isBlank()) "" else resolve(base, cover))
                    }
                }
                node.keys().forEach { k -> node.opt(k).let { if (it is JSONArray || it is JSONObject) jsonStations(it, base, out, depth + 1) } }
            }
        }
    }

    private fun pageTitle(html: String): String {
        val site = Regex("""(?i)<meta[^>]+property=["']og:site_name["'][^>]+content=["']([^"']+)["']""").find(html)?.groupValues?.get(1)
        val title = Regex("""(?is)<title[^>]*>(.*?)</title>""").find(html)?.groupValues?.get(1)
        return unescape((site ?: title).orEmpty()).replace(Regex("\\s+"), " ").trim().substringBefore(" | ").substringBefore(" - ").trim()
    }

    private fun pageIcon(html: String, base: String): String {
        val href = Regex("""(?i)<link[^>]+rel=["'][^"']*icon[^"']*["'][^>]+href=["']([^"']+)["']""").find(html)?.groupValues?.get(1)
            ?: Regex("""(?i)<meta[^>]+property=["']og:image["'][^>]+content=["']([^"']+)["']""").find(html)?.groupValues?.get(1)
        return if (href == null) "" else resolve(base, href)
    }

    /** Every live station an address offers: one for a stream or playlist, one or several for a web page. */
    suspend fun resolve(input: String): List<Station> = withContext(Dispatchers.IO) {
        val url = normalize(input)
        val first = probe(url)
        val stations: List<Station> = when (first.kind) {
            Kind.AUDIO -> listOf(stationOf(first, first.name.ifBlank { hostName(url) }, "", ""))
            Kind.PLAYLIST -> liveOf(playlistEntries(first.text, url)).map { stationOf(it, it.name.ifBlank { hostName(url) }, "", "") }.take(1)
            Kind.HTML -> fromPage(first.text, url)
            Kind.NONE -> emptyList()
        }
        if (stations.isEmpty()) throw NoAudioException()
        stations.map { if (it.streamUrl == url) it else it.copy(sourceUrl = if (first.kind == Kind.AUDIO) "" else url) }
    }

    private suspend fun liveOf(urls: List<String>): List<Probe> = coroutineScope {
        urls.take(12).map { async { probe(it) } }.awaitAll().filter { it.kind == Kind.AUDIO && it.live }
    }

    private fun hostName(url: String) = URI(url).host.orEmpty().removePrefix("www.")

    private fun stationOf(p: Probe, name: String, icon: String, page: String) =
        Station(name = name, streamUrl = p.url, favicon = icon, codec = p.codec, bitrate = p.bitrate, homepage = page)

    private suspend fun fromPage(html: String, base: String): List<Station> = coroutineScope {
        val title = pageTitle(html)
        val icon = pageIcon(html, base)
        // players that load their station list by script (several stations on one page)
        val listed = mutableListOf<Listed>()
        embeddedLists(html, base).forEach { listUrl ->
            val p = probe(listUrl)
            if (p.kind == Kind.HTML) runCatching { jsonStations(JSONArray(p.text.trim().let { if (it.startsWith("[")) it else "[$it]" }), listUrl, listed) }
        }
        if (listed.isNotEmpty()) {
            val probes = listed.take(20).map { l -> async { l to probe(l.url) } }.awaitAll()
            val live = probes.filter { (_, p) -> p.kind == Kind.AUDIO && p.live }
            if (live.isNotEmpty()) return@coroutineScope live.map { (l, p) -> stationOf(p, l.title.ifBlank { p.name.ifBlank { title } }, l.cover.ifBlank { icon }, base) }
        }
        val direct = liveOf(pageCandidates(html, base).flatMap { c ->
            if (Regex("""(?i)\.(pls|m3u)(\?|$)""").containsMatchIn(c)) probe(c).let { if (it.kind == Kind.PLAYLIST) playlistEntries(it.text, c) else listOf(c) } else listOf(c)
        }.distinct())
        direct.take(1).map { stationOf(it, it.name.ifBlank { title.ifBlank { hostName(base) } }, icon, base) }
    }

    /** Where does a saved station live now? Radio-Browser stations by id, others from the page they came from. */
    suspend fun refresh(station: Station): Station? {
        if (station.uuid.isNotBlank()) {
            val fresh = runCatching { RadioBrowser.byUuid(station.uuid) }.getOrNull()
            if (fresh != null && fresh.streamUrl != station.streamUrl) return station.copy(streamUrl = fresh.streamUrl, codec = fresh.codec, bitrate = fresh.bitrate)
        }
        if (station.sourceUrl.isBlank()) return null
        val offered = runCatching { resolve(station.sourceUrl) }.getOrNull().orEmpty()
        val pick = offered.singleOrNull() ?: offered.firstOrNull { it.name.equals(station.name, ignoreCase = true) }
            ?: offered.firstOrNull { it.name.contains(station.name, true) || station.name.contains(it.name, true) }
        return if (pick != null && pick.streamUrl != station.streamUrl) station.copy(streamUrl = pick.streamUrl, codec = pick.codec.ifBlank { station.codec }, bitrate = pick.bitrate.takeIf { it > 0 } ?: station.bitrate) else null
    }
}
