package io.github.vezzulab.juke.playback

import android.content.Context
import android.os.Bundle
import androidx.core.net.toUri
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.session.MediaSession.MediaItemsWithStartPosition
import org.json.JSONArray
import org.json.JSONObject

/**
 * What was playing, kept so the system can bring it back: the lock screen, a headset or Bluetooth button, or the
 * "resume" card can start the music again even after Android has closed the app.
 */
class ResumeStore(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("juke-resume", Context.MODE_PRIVATE)

    fun save(player: Player) {
        val count = player.mediaItemCount
        if (count == 0) return
        val index = player.currentMediaItemIndex.coerceIn(0, count - 1)
        val from = maxOf(0, index - WINDOW / 4)
        val to = minOf(count, from + WINDOW)
        val items = JSONArray()
        for (i in from until to) {
            val item = player.getMediaItemAt(i)
            val uri = item.localConfiguration?.uri?.toString() ?: continue
            val meta = item.mediaMetadata
            items.put(JSONObject().put("id", item.mediaId).put("uri", uri).put("title", meta.title?.toString().orEmpty())
                .put("artist", meta.artist?.toString().orEmpty()).put("album", meta.albumTitle?.toString().orEmpty())
                .put("art", meta.artworkUri?.toString().orEmpty()).put("live", meta.extras?.getBoolean("live") == true)
                .put("badge", meta.extras?.getString("badge").orEmpty()))
        }
        prefs.edit().putString("items", items.toString()).putInt("index", index - from).putLong("position", player.currentPosition.coerceAtLeast(0)).apply()
    }

    private fun items(): List<MediaItem> {
        val array = runCatching { JSONArray(prefs.getString("items", "[]")) }.getOrDefault(JSONArray())
        return (0 until array.length()).mapNotNull { i ->
            val o = array.optJSONObject(i) ?: return@mapNotNull null
            val uri = o.optString("uri").takeIf { it.isNotBlank() } ?: return@mapNotNull null
            MediaItem.Builder().setMediaId(o.optString("id")).setUri(uri)
                .setMediaMetadata(
                    MediaMetadata.Builder().setTitle(o.optString("title")).setArtist(o.optString("artist")).setAlbumTitle(o.optString("album"))
                        .setArtworkUri(o.optString("art").takeIf { it.isNotBlank() }?.toUri())
                        .setIsPlayable(true).setIsBrowsable(false)
                        .setExtras(Bundle().apply {
                            putBoolean("live", o.optBoolean("live"))
                            putString("badge", o.optString("badge"))
                        }).build()
                ).build()
        }
    }

    /** The queue as it was, for the system to resume. Null when nothing was ever played. */
    fun load(): MediaItemsWithStartPosition? {
        val list = items()
        if (list.isEmpty()) return null
        val live = list.getOrNull(prefs.getInt("index", 0))?.mediaMetadata?.extras?.getBoolean("live") == true
        return MediaItemsWithStartPosition(list, prefs.getInt("index", 0).coerceIn(0, list.lastIndex), if (live) 0 else prefs.getLong("position", 0))
    }

    /** Just the current song, for the system's "recent" shelf. */
    fun recent(): MediaItem? = items().getOrNull(prefs.getInt("index", 0))

    private companion object { const val WINDOW = 400 }
}
