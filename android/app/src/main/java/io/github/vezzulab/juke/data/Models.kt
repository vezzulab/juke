package io.github.vezzulab.juke.data

import org.json.JSONObject

data class Track(
    val id: String,
    val title: String,
    val artist: String,
    val album: String,
    val durationSec: Int,
    val coverArt: String?,
    val codec: String,
    val bitRate: Int,
    /** Local files play straight from their MediaStore address; server songs ask for a URL only on Play. */
    val uri: String? = null,
    val artworkUri: String? = null,
)

data class Folder(val id: String, val name: String)

data class ServerConfig(val url: String, val user: String, val password: String) {
    val isComplete get() = url.isNotBlank() && user.isNotBlank()
}

/** A radio station. Stations move their stream address all the time, so the page they came from (or the
 *  Radio-Browser id) is kept to find the new address again. */
data class Station(
    val name: String,
    val streamUrl: String,
    val favicon: String = "",
    val tags: String = "",
    val country: String = "",
    val codec: String = "",
    val bitrate: Int = 0,
    val uuid: String = "",
    val homepage: String = "",
    val sourceUrl: String = "",
) {
    val detail: String
        get() = listOf(codec, if (bitrate > 0) "$bitrate kbps" else "", tags.split(",").firstOrNull()?.trim().orEmpty())
            .filter { it.isNotBlank() }.joinToString(" · ")

    fun toJson(): JSONObject = JSONObject().apply {
        put("name", name); put("streamUrl", streamUrl); put("favicon", favicon); put("tags", tags); put("country", country)
        put("codec", codec); put("bitrate", bitrate); put("uuid", uuid); put("homepage", homepage); put("sourceUrl", sourceUrl)
    }

    companion object {
        fun fromJson(o: JSONObject) = Station(
            o.optString("name"), o.optString("streamUrl"), o.optString("favicon"), o.optString("tags"), o.optString("country"),
            o.optString("codec"), o.optInt("bitrate"), o.optString("uuid"), o.optString("homepage"), o.optString("sourceUrl"),
        )
    }
}
