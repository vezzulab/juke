package io.github.vezzulab.juke.playback

import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.extractor.DefaultExtractorsFactory
import androidx.media3.exoplayer.audio.AudioSink
import androidx.media3.exoplayer.audio.DefaultAudioSink
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.session.LibraryResult
import androidx.media3.session.MediaLibraryService
import androidx.media3.session.MediaSession
import com.google.common.collect.ImmutableList
import com.google.common.util.concurrent.Futures
import com.google.common.util.concurrent.ListenableFuture
import io.github.vezzulab.juke.MainActivity
import io.github.vezzulab.juke.data.Store
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

@androidx.annotation.OptIn(androidx.media3.common.util.UnstableApi::class)
/**
 * Plays in the background with the media notification, lock-screen and Bluetooth controls; the equalizer rides on its
 * audio session. It is a media *library* service on purpose: that is what lets any lock screen, "island", headset,
 * car or Bluetooth device find the player, tap it open and resume it after Android has closed the app.
 */
class PlaybackService : MediaLibraryService() {
    private var session: MediaLibrarySession? = null
    private lateinit var resume: ResumeStore

    override fun onCreate() {
        super.onCreate()
        EqualizerHub.init(Store(this))
        KaraokeHub.load(this)
        resume = ResumeStore(this)
        val client = OkHttpClient.Builder().connectTimeout(15, TimeUnit.SECONDS).readTimeout(20, TimeUnit.SECONDS)
            // A Subsonic/Airsonic server sends "icy-*" (internet radio) headers with every song. The player takes that for a live
            // station and will not let anyone move forward or back in it. Songs from the server lose those headers; radio keeps them.
            .addInterceptor { chain ->
                val response = chain.proceed(chain.request())
                val path = chain.request().url.encodedPath
                if (!(path.endsWith("/stream") || path.endsWith("/stream.view") || path.endsWith("/download") || path.endsWith("/download.view"))) response
                else response.newBuilder().headers(response.headers.newBuilder().also { h ->
                    response.headers.names().filter { it.startsWith("icy-", ignoreCase = true) }.forEach { h.removeAll(it) }
                }.build()).build()
            }
            .build()
        // the voice reducer sits in the audio path for good; the karaoke switch decides whether it does anything
        val renderers = object : DefaultRenderersFactory(this) {
            override fun buildAudioSink(context: Context, enableFloatOutput: Boolean, enableAudioTrackPlaybackParams: Boolean): AudioSink =
                DefaultAudioSink.Builder(context).setAudioProcessorChain(DefaultAudioSink.DefaultAudioProcessorChain(VoiceReducer())).build()
        }
        val player = ExoPlayer.Builder(this, renderers)
            // files on the card come in as content:// and file://, streams over http: this factory serves both
            .setMediaSourceFactory(
                DefaultMediaSourceFactory(
                    DefaultDataSource.Factory(this, OkHttpDataSource.Factory(client).setUserAgent("Juke-Android/0.1")),
                    // MP3s of constant bitrate (most of them, with or without a Xing/Info header) can be jumped in: without this a song whose header has no index cannot be moved forward or back
                    DefaultExtractorsFactory().setConstantBitrateSeekingEnabled(true).setConstantBitrateSeekingAlwaysEnabled(true),
                )
            )
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MUSIC).build(), true)
            .setHandleAudioBecomingNoisy(true)
            .setWakeMode(C.WAKE_MODE_NETWORK)
            .build()
        player.addListener(object : Player.Listener {
            override fun onAudioSessionIdChanged(audioSessionId: Int) { EqualizerHub.attach(audioSessionId) }
            override fun onMediaItemTransition(mediaItem: MediaItem?, reason: Int) { resume.save(player) }
            override fun onIsPlayingChanged(isPlaying: Boolean) { resume.save(player) }
        })
        EqualizerHub.attach(player.audioSessionId)
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        session = MediaLibrarySession.Builder(this, player, LibraryCallback()).setSessionActivity(open).build()
    }

    /** What the system may ask: who we are, what was played last, and to start it again. */
    private inner class LibraryCallback : MediaLibrarySession.Callback {
        override fun onGetLibraryRoot(
            session: MediaLibrarySession, browser: MediaSession.ControllerInfo, params: LibraryParams?,
        ): ListenableFuture<LibraryResult<MediaItem>> {
            val root = MediaItem.Builder().setMediaId(ROOT).setMediaMetadata(MediaMetadata.Builder().setIsBrowsable(true).setIsPlayable(false).build()).build()
            return Futures.immediateFuture(LibraryResult.ofItem(root, params))
        }

        override fun onGetChildren(
            session: MediaLibrarySession, browser: MediaSession.ControllerInfo, parentId: String, page: Int, pageSize: Int, params: LibraryParams?,
        ): ListenableFuture<LibraryResult<ImmutableList<MediaItem>>> {
            val last = resume.recent()
            return Futures.immediateFuture(LibraryResult.ofItemList(if (last != null && parentId == ROOT) ImmutableList.of(last) else ImmutableList.of(), params))
        }

        override fun onGetItem(session: MediaLibrarySession, browser: MediaSession.ControllerInfo, mediaId: String): ListenableFuture<LibraryResult<MediaItem>> {
            val item = resume.recent()?.takeIf { it.mediaId == mediaId }
            return Futures.immediateFuture(if (item != null) LibraryResult.ofItem(item, null) else LibraryResult.ofError(LibraryResult.RESULT_ERROR_BAD_VALUE))
        }

        override fun onPlaybackResumption(mediaSession: MediaSession, controller: MediaSession.ControllerInfo): ListenableFuture<MediaSession.MediaItemsWithStartPosition> {
            val saved = resume.load() ?: return Futures.immediateFailedFuture(UnsupportedOperationException("nothing to resume"))
            return Futures.immediateFuture(saved)
        }
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaLibrarySession? = session

    override fun onTaskRemoved(rootIntent: Intent?) {
        val player = session?.player
        if (player == null || !player.playWhenReady || player.mediaItemCount == 0) stopSelf()   // nothing playing: do not linger
    }

    override fun onDestroy() {
        session?.player?.let { resume.save(it) }
        EqualizerHub.release()                      // detach the effect before the audio session goes away
        session?.run { release(); player.release() } // release the session first: it still calls into the player while tearing down
        session = null
        super.onDestroy()
    }

    private companion object { const val ROOT = "juke-root" }
}
