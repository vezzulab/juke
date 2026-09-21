package io.github.vezzulab.juke.data

import android.content.ContentProvider
import android.content.ContentUris
import android.content.ContentValues
import android.content.Context
import android.database.Cursor
import android.graphics.Bitmap
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.os.ParcelFileDescriptor
import android.provider.MediaStore
import android.util.Size
import java.io.ByteArrayOutputStream
import java.io.FileNotFoundException

/**
 * The picture of a song of the device, read from the song itself.
 *
 * Android's own "album art" address stopped working in Android 10 and is unreliable for files that arrived over a cable, so
 * the app asks this instead: the cover embedded in the file first, then what the system can make of the song (a cover next
 * to it), then the old address for the versions that still have it. It is an ordinary content:// address, so the image
 * loader, the notification, the lock screen and the car all read it the same way.
 */
class ArtProvider : ContentProvider() {
    override fun onCreate() = true
    override fun getType(uri: Uri) = "image/jpeg"
    override fun query(uri: Uri, projection: Array<String>?, selection: String?, selectionArgs: Array<String>?, sortOrder: String?): Cursor? = null
    override fun insert(uri: Uri, values: ContentValues?): Uri? = null
    override fun delete(uri: Uri, selection: String?, selectionArgs: Array<String>?) = 0
    override fun update(uri: Uri, values: ContentValues?, selection: String?, selectionArgs: Array<String>?) = 0

    override fun openFile(uri: Uri, mode: String): ParcelFileDescriptor {
        val id = uri.lastPathSegment?.toLongOrNull() ?: throw FileNotFoundException("no song in $uri")
        val bytes = picture(context ?: throw FileNotFoundException(), id) ?: throw FileNotFoundException("no artwork for $id")
        return openPipeHelper(uri, "image/jpeg", null, bytes) { output, _, _, _, data ->
            ParcelFileDescriptor.AutoCloseOutputStream(output).use { it.write(data ?: ByteArray(0)) }
        }
    }

    companion object {
        fun uri(context: Context, songId: Long): String = "content://${context.packageName}.art/$songId"

        private fun picture(context: Context, id: Long): ByteArray? {
            val song = ContentUris.withAppendedId(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, id)
            val retriever = MediaMetadataRetriever()
            try {
                retriever.setDataSource(context, song)
                retriever.embeddedPicture?.let { return it }
            } catch (_: Exception) {
            } finally {
                runCatching { retriever.release() }
            }
            if (Build.VERSION.SDK_INT >= 29) {
                runCatching {
                    val bitmap = context.contentResolver.loadThumbnail(song, Size(600, 600), null)
                    return ByteArrayOutputStream().also { bitmap.compress(Bitmap.CompressFormat.JPEG, 90, it) }.toByteArray()
                }
            }
            runCatching {
                context.contentResolver.query(song, arrayOf(MediaStore.Audio.Media.ALBUM_ID), null, null, null)?.use { cursor ->
                    if (cursor.moveToFirst()) {
                        val old = ContentUris.withAppendedId(Uri.parse("content://media/external/audio/albumart"), cursor.getLong(0))
                        context.contentResolver.openInputStream(old)?.use { return it.readBytes() }
                    }
                }
            }
            return null
        }
    }
}
