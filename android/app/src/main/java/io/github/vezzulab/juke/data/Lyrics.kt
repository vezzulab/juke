package io.github.vezzulab.juke.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

/** One line of a synced song: when it starts, what it says and, when the file has them, when each word starts. */
data class LyricLine(val start: Long, val text: String, val words: List<Pair<Long, String>>)

/** Lyrics: plain text or the synced ``.lrc`` format ("[01:23.45] words"), read the same way Juke for Linux reads them. */
object Lyrics {
    private val stamp = Regex("\\[(\\d{1,3}):(\\d{2})(?:[.:](\\d{1,3}))?]")
    private val wordStamp = Regex("<(\\d{1,3}):(\\d{2})(?:[.:](\\d{1,3}))?>")
    private val header = Regex("^\\[(?:ar|ti|al|au|by|offset|re|ve|length):.*]$", RegexOption.IGNORE_CASE)
    const val LEAD_IN_MS = 3000L
    const val GAP_MS = 8000L

    private fun ms(m: String, s: String, f: String): Long = m.toLong() * 60_000 + s.toLong() * 1000 + f.ifEmpty { "0" }.padEnd(3, '0').take(3).toLong()

    fun parse(text: String): List<LyricLine> {
        val lines = ArrayList<LyricLine>()
        for (raw in text.lines()) {
            val stamps = stamp.findAll(raw).toList()
            if (stamps.isEmpty()) continue
            val body = raw.substring(stamps.last().range.last + 1)
            val marks = wordStamp.findAll(body).toList()
            val words = marks.mapIndexedNotNull { i, mark ->
                val end = if (i + 1 < marks.size) marks[i + 1].range.first else body.length
                val word = body.substring(mark.range.last + 1, end).trim()
                if (word.isEmpty()) null else ms(mark.groupValues[1], mark.groupValues[2], mark.groupValues[3]) to word
            }
            val spoken = wordStamp.replace(body, "").trim()
            stamps.forEach { s -> lines += LyricLine(ms(s.groupValues[1], s.groupValues[2], s.groupValues[3]), spoken, words) }
        }
        return lines.sortedBy { it.start }
    }

    fun isSynced(text: String) = parse(text).size >= 2

    fun plain(text: String): String = text.lines().filterNot { header.matches(it.trim()) }
        .joinToString("\n") { if (stamp.containsMatchIn(it)) stamp.replace(it, "").trim() else it.trimEnd() }.trim('\n')

    fun lineAt(lines: List<LyricLine>, position: Long): Int = lines.indexOfLast { it.start <= position }

    /** How much of the line has been sung, 0..1: by word times when there are some, else evenly until the next line. */
    fun sweep(lines: List<LyricLine>, index: Int, position: Long): Float {
        if (index !in lines.indices) return 0f
        val line = lines[index]
        if (line.words.isNotEmpty() && line.text.isNotEmpty()) {
            val total = line.words.sumOf { it.second.length + 1 }
            var done = 0.0
            for (i in line.words.indices) {
                val (start, word) = line.words[i]
                val end = if (i + 1 < line.words.size) line.words[i + 1].first else lines.getOrNull(index + 1)?.start ?: (start + 600)
                if (position >= end) done += word.length + 1
                else { if (position > start) done += (word.length + 1) * (position - start).toDouble() / maxOf(1L, end - start); break }
            }
            return (done / total).toFloat().coerceIn(0f, 1f)
        }
        val following = lines.getOrNull(index + 1)?.start ?: (line.start + 5000)
        val span = maxOf(800L, minOf(following - line.start, 7000L)) * 0.92
        return ((position - line.start) / span).toFloat().coerceIn(0f, 1f)
    }

    /** 3, 2 or 1 while the next line is about to begin after a long enough silence (or the intro); else 0. */
    fun countdown(lines: List<LyricLine>, index: Int, position: Long): Int {
        val following = lines.getOrNull(index + 1)?.start ?: return 0
        val quietSince = if (index >= 0) lines[index].start else 0L
        if (index >= 0 && following - quietSince < GAP_MS) return 0
        val remaining = following - position
        return if (remaining in 1..LEAD_IN_MS) ((remaining + 999) / 1000).toInt() else 0
    }
}

/** What the person saved, one small file per song, kept apart from the music. */
class LyricsStore(context: Context) {
    private val dir = File(context.applicationContext.filesDir, "lyrics").apply { mkdirs() }

    private fun file(key: String) = File(dir, MessageDigest.getInstance("SHA-1").digest(key.toByteArray()).joinToString("") { "%02x".format(it) } + ".txt")

    fun get(key: String): String = runCatching { file(key).takeIf { it.exists() }?.readText().orEmpty() }.getOrDefault("")

    fun set(key: String, text: String) {
        runCatching { if (text.isBlank()) file(key).delete() else file(key).writeText(text.trim()) }
    }
}

/** LRCLIB (lrclib.net): a free, open lyrics service. It is asked only when the person asks, or has turned the automatic option on. */
object LrcLib {
    data class Found(val title: String, val artist: String, val album: String, val duration: Double, val plain: String, val synced: String) {
        val text get() = synced.ifBlank { plain }
        val isSynced get() = synced.isNotBlank()
    }

    private val client = OkHttpClient.Builder().connectTimeout(12, TimeUnit.SECONDS).readTimeout(15, TimeUnit.SECONDS).build()
    private const val BASE = "https://lrclib.net/api"
    private const val AGENT = "Juke-Android/0.3.3 (https://github.com/vezzulab/juke)"

    private fun found(o: JSONObject): Found? {
        if (o.optBoolean("instrumental")) return null
        val plain = o.optString("plainLyrics").takeIf { it != "null" }.orEmpty()
        val synced = o.optString("syncedLyrics").takeIf { it != "null" }.orEmpty()
        if (plain.isBlank() && synced.isBlank()) return null
        return Found(o.optString("trackName"), o.optString("artistName"), o.optString("albumName"), o.optDouble("duration", 0.0), plain, synced)
    }

    private suspend fun call(path: String, params: Map<String, String>): String? = withContext(Dispatchers.IO) {
        val url = "$BASE/$path".toHttpUrl().newBuilder().apply { params.forEach { (k, v) -> if (v.isNotBlank()) addQueryParameter(k, v) } }.build()
        client.newCall(Request.Builder().url(url).header("User-Agent", AGENT).build()).execute().use { r ->
            if (r.code == 404) null else if (!r.isSuccessful) throw java.io.IOException("HTTP ${r.code}") else r.body?.string()
        }
    }

    suspend fun search(title: String, artist: String): List<Found> {
        val body = call("search", mapOf("track_name" to title, "artist_name" to artist)) ?: return emptyList()
        val array = JSONArray(body)
        return (0 until array.length()).mapNotNull { found(array.getJSONObject(it)) }.take(25)
    }

    suspend fun exact(title: String, artist: String, album: String, durationSec: Int): Found? {
        val body = call("get", mapOf("track_name" to title, "artist_name" to artist, "album_name" to album, "duration" to durationSec.takeIf { it > 0 }?.toString().orEmpty())) ?: return null
        return found(JSONObject(body))
    }
}
