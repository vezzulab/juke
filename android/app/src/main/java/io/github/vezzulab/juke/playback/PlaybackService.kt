package io.github.vezzulab.juke.playback

import android.app.PendingIntent
import android.content.Intent
import androidx.media3.common.AudioAttributes
import androidx.media3.common.C
import androidx.media3.common.Player
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService
import io.github.vezzulab.juke.MainActivity
import io.github.vezzulab.juke.data.Store
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

/** Plays in the background with the media notification, lock-screen and Bluetooth controls; the equalizer rides on its audio session. */
class PlaybackService : MediaSessionService() {
    private var session: MediaSession? = null

    override fun onCreate() {
        super.onCreate()
        EqualizerHub.init(Store(this))
        val client = OkHttpClient.Builder().connectTimeout(15, TimeUnit.SECONDS).readTimeout(20, TimeUnit.SECONDS).build()
        val player = ExoPlayer.Builder(this)
            // files on the card come in as content:// and file://, streams over http: this factory serves both
            .setMediaSourceFactory(
                DefaultMediaSourceFactory(
                    DefaultDataSource.Factory(this, OkHttpDataSource.Factory(client).setUserAgent("Juke-Android/0.1"))
                )
            )
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MUSIC).build(), true)
            .setHandleAudioBecomingNoisy(true)
            .setWakeMode(C.WAKE_MODE_NETWORK)
            .build()
        player.addListener(object : Player.Listener {
            override fun onAudioSessionIdChanged(audioSessionId: Int) { EqualizerHub.attach(audioSessionId) }
        })
        EqualizerHub.attach(player.audioSessionId)
        // tapping the notification or the lock-screen card opens Juke on the player
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        session = MediaSession.Builder(this, player).setSessionActivity(open).build()
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaSession? = session

    override fun onTaskRemoved(rootIntent: Intent?) {
        val player = session?.player
        if (player == null || !player.playWhenReady || player.mediaItemCount == 0) stopSelf()   // nothing playing: do not linger
    }

    override fun onDestroy() {
        EqualizerHub.release()                      // detach the effect before the audio session goes away
        session?.run { release(); player.release() } // release the session first: it still calls into the player while tearing down
        session = null
        super.onDestroy()
    }
}
