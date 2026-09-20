package io.github.vezzulab.juke.data

import android.content.ContentUris
import android.content.Context
import android.net.Uri
import android.provider.MediaStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * The music on the device and on the SD card, browsed by folders exactly as it sits on the card.
 * One MediaStore query builds the whole tree; every volume (internal, SD) becomes a root folder.
 */
object LocalLibrary {
    class Tree(val roots: List<Folder>, private val folders: Map<String, List<Folder>>, private val tracks: Map<String, List<Track>>) {
        fun children(path: String): List<Folder> = folders[path].orEmpty()
        fun tracks(path: String): List<Track> = tracks[path].orEmpty()
        val isEmpty get() = roots.isEmpty()
        /** Every song under a folder, in browsing order: what "play all" queues up. */
        fun deepTracks(path: String, limit: Int = 2000): List<Track> {
            val out = ArrayList<Track>()
            fun walk(p: String) {
                if (out.size >= limit) return
                out += tracks(p)
                children(p).forEach { walk(it.id) }
            }
            walk(path)
            return out
        }
    }

    private fun albumArt(albumId: Long): String? =
        if (albumId <= 0) null else ContentUris.withAppendedId(Uri.parse("content://media/external/audio/albumart"), albumId).toString()

    /** "/storage/emulated/0/Music/x.mp3" -> "/storage/emulated/0"; "/storage/1A2B-3C4D/..." -> "/storage/1A2B-3C4D". */
    private fun volumeRoot(path: String): String? {
        val parts = path.split('/')                                  // "", "storage", <vol>, ...
        if (parts.size < 4 || parts[1] != "storage") return null
        return if (parts[2] == "emulated") "/storage/emulated/${parts.getOrNull(3) ?: return null}" else "/storage/${parts[2]}"
    }

    fun isRemovable(root: String) = !root.startsWith("/storage/emulated")

    suspend fun scan(context: Context): Tree = withContext(Dispatchers.IO) {
        val projection = arrayOf(
            MediaStore.Audio.Media._ID, MediaStore.Audio.Media.TITLE, MediaStore.Audio.Media.ARTIST, MediaStore.Audio.Media.ALBUM,
            MediaStore.Audio.Media.DURATION, MediaStore.Audio.Media.ALBUM_ID, MediaStore.Audio.Media.DATA,
            MediaStore.Audio.Media.TRACK, MediaStore.Audio.Media.MIME_TYPE, MediaStore.Audio.Media.DISPLAY_NAME,
        )
        val tracks = HashMap<String, MutableList<Pair<Int, Track>>>()
        val folders = HashMap<String, MutableList<Folder>>()
        val known = HashSet<String>()
        val roots = LinkedHashSet<String>()

        fun register(path: String, stop: String) {
            var child = path
            while (child != stop && child.contains('/')) {
                val parent = child.substringBeforeLast('/')
                if (!known.add(child)) return                        // this branch is already in the tree
                folders.getOrPut(parent) { ArrayList() } += Folder(child, child.substringAfterLast('/'))
                if (parent == stop) return
                child = parent
            }
        }

        context.contentResolver.query(
            MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, projection,
            // anything that is not a ringtone, an alarm or a notification counts: music on a card sits in all kinds of folders
            "(${MediaStore.Audio.Media.IS_MUSIC} IS NULL OR ${MediaStore.Audio.Media.IS_MUSIC} != 0)" +
                " AND (${MediaStore.Audio.Media.IS_RINGTONE} IS NULL OR ${MediaStore.Audio.Media.IS_RINGTONE} = 0)" +
                " AND (${MediaStore.Audio.Media.IS_ALARM} IS NULL OR ${MediaStore.Audio.Media.IS_ALARM} = 0)" +
                " AND (${MediaStore.Audio.Media.IS_NOTIFICATION} IS NULL OR ${MediaStore.Audio.Media.IS_NOTIFICATION} = 0)", null, null,
        )?.use { cursor ->
            val id = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media._ID)
            val title = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.TITLE)
            val artist = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.ARTIST)
            val album = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.ALBUM)
            val duration = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DURATION)
            val albumId = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.ALBUM_ID)
            val data = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DATA)
            val trackNo = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.TRACK)
            val mime = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.MIME_TYPE)
            val display = cursor.getColumnIndexOrThrow(MediaStore.Audio.Media.DISPLAY_NAME)
            while (cursor.moveToNext()) {
                val path = cursor.getString(data) ?: continue
                val root = volumeRoot(path) ?: continue
                val parent = path.substringBeforeLast('/')
                if (parent.length <= root.length) roots += root else { roots += root; register(parent, root) }
                val songId = cursor.getLong(id)
                val song = Track(
                    id = "local:$songId",
                    title = cursor.getString(title)?.takeIf { it.isNotBlank() } ?: cursor.getString(display).orEmpty(),
                    artist = cursor.getString(artist).orEmpty().takeIf { it != "<unknown>" }.orEmpty(),
                    album = cursor.getString(album).orEmpty(),
                    durationSec = (cursor.getLong(duration) / 1000).toInt(),
                    coverArt = null,
                    codec = cursor.getString(mime).orEmpty().substringAfter('/').uppercase().removePrefix("X-"),
                    bitRate = 0,
                    uri = ContentUris.withAppendedId(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, songId).toString(),
                    artworkUri = albumArt(cursor.getLong(albumId)),
                )
                tracks.getOrPut(parent) { ArrayList() } += (cursor.getInt(trackNo) % 1000) to song
            }
        }

        val sortedFolders = folders.mapValues { (_, list) -> list.sortedBy { it.name.lowercase() } }
        val sortedTracks = tracks.mapValues { (_, list) ->
            list.sortedWith(compareBy({ it.first.takeIf { n -> n > 0 } ?: Int.MAX_VALUE }, { it.second.title.lowercase() })).map { it.second }
        }
        val rootFolders = roots.sorted().map { Folder(it, if (isRemovable(it)) "sd" else "internal") }
        Tree(rootFolders, sortedFolders, sortedTracks)
    }
}
