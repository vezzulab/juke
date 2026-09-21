package io.github.vezzulab.juke.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.concurrent.TimeUnit

class SubsonicException(val code: Int, message: String) : Exception(message)

/** Airsonic / Subsonic client: token auth (password fallback for servers that answer error 41), API version negotiation. */
class AirsonicClient(baseUrl: String, private val user: String, private val password: String) {
    private val base = baseUrl.trim().trimEnd('/')
    private val http = OkHttpClient.Builder().connectTimeout(10, TimeUnit.SECONDS).readTimeout(30, TimeUnit.SECONDS).build()

    @Volatile private var version = "1.16.1"
    @Volatile private var legacyAuth = false

    private fun builder(endpoint: String): HttpUrl.Builder {
        val b = "$base/rest/$endpoint.view".toHttpUrl().newBuilder()
        b.addQueryParameter("u", user)
        if (legacyAuth) {
            b.addQueryParameter("p", "enc:" + password.toByteArray().joinToString("") { "%02x".format(it) })
        } else {
            val salt = ByteArray(8).also { SecureRandom().nextBytes(it) }.joinToString("") { "%02x".format(it) }
            b.addQueryParameter("s", salt)
            b.addQueryParameter("t", md5(password + salt))
        }
        return b.addQueryParameter("v", version).addQueryParameter("c", "Juke").addQueryParameter("f", "json")
    }

    private fun md5(text: String) = MessageDigest.getInstance("MD5").digest(text.toByteArray()).joinToString("") { "%02x".format(it) }

    suspend fun call(endpoint: String, vararg extra: Pair<String, String>): JSONObject = withContext(Dispatchers.IO) {
        var renegotiated = false
        var result: JSONObject? = null
        while (result == null) {
            val url = builder(endpoint).apply { extra.forEach { addQueryParameter(it.first, it.second) } }.build()
            val text = http.newCall(Request.Builder().url(url).build()).execute().use { response ->
                if (!response.isSuccessful) throw IOException("HTTP ${response.code}")
                response.body?.string().orEmpty()
            }
            val root = JSONObject(text).getJSONObject("subsonic-response")
            if (root.optString("status") == "ok") { result = root; break }
            val error = root.optJSONObject("error")
            val code = error?.optInt("code") ?: 0
            val serverVersion = root.optString("version")
            when {
                code == 41 && !legacyAuth -> legacyAuth = true                         // token auth not supported: send the password
                (code == 20 || code == 30) && !renegotiated && serverVersion.isNotBlank() -> { renegotiated = true; version = serverVersion }
                else -> throw SubsonicException(code, error?.optString("message").orEmpty().ifBlank { "Error $code" })
            }
        }
        result!!
    }

    suspend fun ping() { call("ping") }

    suspend fun musicFolders(): List<Folder> =
        call("getMusicFolders").optJSONObject("musicFolders").objects("musicFolder").map { Folder(it.optString("id"), it.optString("name")) }

    /** The top level of one music folder (Airsonic lists its sub-folders as "artists"). */
    suspend fun indexes(folderId: String): Pair<List<Folder>, List<Track>> {
        val root = call("getIndexes", "musicFolderId" to folderId).optJSONObject("indexes")
        val folders = root.objects("index").flatMap { it.objects("artist") }.map { Folder(it.optString("id"), it.optString("name")) }
        return folders to root.objects("child").filter { !it.optBoolean("isDir") }.map(::track)
    }

    suspend fun directory(id: String): Pair<List<Folder>, List<Track>> {
        val children = call("getMusicDirectory", "id" to id).optJSONObject("directory").objects("child")
        val folders = children.filter { it.optBoolean("isDir") }.map { Folder(it.optString("id"), it.optString("title")) }
        return folders to children.filter { !it.optBoolean("isDir") }.map(::track)
    }

    suspend fun search(query: String): List<Track> =
        call("search3", "query" to query, "songCount" to "100", "artistCount" to "0", "albumCount" to "0")
            .optJSONObject("searchResult3").objects("song").map(::track)

    suspend fun scrobble(id: String) { call("scrobble", "id" to id, "submission" to "true") }

    /** Asked only when a song is played, so nothing is signed until then. */
    /** [estimateContentLength] makes the server say how long a transcoded song is, which is what lets the player jump around in it. */
    fun streamUrl(id: String): String = builder("stream").addQueryParameter("id", id).addQueryParameter("estimateContentLength", "true").build().toString()

    fun coverUrl(id: String, size: Int = 600): String =
        builder("getCoverArt").addQueryParameter("id", id).addQueryParameter("size", size.toString()).build().toString()

    private fun track(o: JSONObject) = Track(
        id = o.optString("id"), title = o.optString("title"), artist = o.optString("artist"), album = o.optString("album"),
        durationSec = o.optInt("duration"), coverArt = o.optString("coverArt").ifBlank { null },
        codec = o.optString("suffix").uppercase(), bitRate = o.optInt("bitRate"),
    )
}

private fun JSONObject?.objects(key: String): List<JSONObject> {
    val array: JSONArray = this?.optJSONArray(key) ?: return this?.optJSONObject(key)?.let { listOf(it) } ?: emptyList()
    return (0 until array.length()).mapNotNull { array.optJSONObject(it) }
}
