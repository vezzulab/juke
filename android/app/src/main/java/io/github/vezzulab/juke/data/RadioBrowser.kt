package io.github.vezzulab.juke.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import java.io.IOException
import java.util.concurrent.TimeUnit

/** Radio-Browser directory (community list of stations); tries several mirrors. */
object RadioBrowser {
    private val mirrors = listOf("de1.api.radio-browser.info", "nl1.api.radio-browser.info", "at1.api.radio-browser.info")
    private val http = OkHttpClient.Builder().connectTimeout(6, TimeUnit.SECONDS).readTimeout(12, TimeUnit.SECONDS).build()

    private suspend fun get(path: String, query: Map<String, String>): JSONArray = withContext(Dispatchers.IO) {
        var last: Exception? = null
        for (host in mirrors) {
            try {
                val url = "https://$host/json/$path".toHttpUrl().newBuilder().apply { query.forEach { addQueryParameter(it.key, it.value) } }.build()
                val request = Request.Builder().url(url).header("User-Agent", "Juke-Android/0.1").build()
                return@withContext http.newCall(request).execute().use { r ->
                    if (!r.isSuccessful) throw IOException("HTTP ${r.code}")
                    JSONArray(r.body?.string().orEmpty())
                }
            } catch (e: Exception) {
                last = e
            }
        }
        throw IOException(last?.message ?: "no server answered")
    }

    suspend fun search(name: String = "", tag: String = "", limit: Int = 60): List<Station> {
        val query = buildMap {
            put("limit", limit.toString()); put("hidebroken", "true"); put("order", "clickcount"); put("reverse", "true")
            if (name.isNotBlank()) put("name", name.trim())
            if (tag.isNotBlank()) put("tag", tag.trim())
        }
        return fromArray(get("stations/search", query))
    }

    suspend fun byUuid(uuid: String): Station? = fromArray(get("stations/byuuid/$uuid", emptyMap())).firstOrNull()

    private fun fromArray(array: JSONArray): List<Station> {
        val seen = HashSet<String>()
        return (0 until array.length()).mapNotNull { i ->
            val o = array.optJSONObject(i) ?: return@mapNotNull null
            val url = o.optString("url_resolved").ifBlank { o.optString("url") }
            if (url.isBlank() || !seen.add(url)) return@mapNotNull null
            Station(
                name = o.optString("name").trim().ifBlank { url }, streamUrl = url, favicon = o.optString("favicon"),
                tags = o.optString("tags"), country = o.optString("country"), codec = o.optString("codec"),
                bitrate = o.optInt("bitrate"), uuid = o.optString("stationuuid"), homepage = o.optString("homepage"),
            )
        }
    }
}
