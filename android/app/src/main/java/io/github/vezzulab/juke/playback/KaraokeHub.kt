package io.github.vezzulab.juke.playback

import android.content.Context
import androidx.media3.common.C
import androidx.media3.common.audio.AudioProcessor.AudioFormat
import androidx.media3.common.audio.BaseAudioProcessor
import androidx.media3.common.util.UnstableApi
import io.github.vezzulab.juke.data.Store
import java.nio.ByteBuffer
import kotlin.math.exp

/** Karaoke's voice reduction is one switch shared by the screen (which flips it) and the audio path (which obeys it). */
object KaraokeHub {
    @Volatile var voiceReduction = false

    fun load(context: Context) { voiceReduction = Store(context).voiceReduction }
}

/**
 * Takes the lead voice out of a stereo song. What the two channels have in common (the centre: the singer, but also
 * bass and kick) is cancelled by using only the difference; the low end of the centre is put back so the song keeps
 * its body. Works on 16-bit stereo, which is what nearly every song decodes to; anything else passes untouched.
 * It is always in the chain and does nothing until the switch is on, so turning it on or off never restarts the song.
 */
@UnstableApi
class VoiceReducer : BaseAudioProcessor() {
    private var alpha = 0f
    private var low = 0f

    override fun onConfigure(inputAudioFormat: AudioFormat): AudioFormat {
        if (inputAudioFormat.encoding != C.ENCODING_PCM_16BIT || inputAudioFormat.channelCount != 2) return AudioFormat.NOT_SET
        alpha = 1f - exp(-2.0 * Math.PI * BASS_HZ / inputAudioFormat.sampleRate).toFloat()
        return inputAudioFormat
    }

    private var scratch = ByteArray(0)

    override fun queueInput(inputBuffer: ByteBuffer) {
        val size = inputBuffer.remaining()
        if (size == 0) return
        if (scratch.size < size) scratch = ByteArray(size)
        val order = inputBuffer.order()
        inputBuffer.get(scratch, 0, size)                       // taken out of the input first: the output never reads from itself
        val out = replaceOutputBuffer(size)
        if (!KaraokeHub.voiceReduction) {
            out.put(scratch, 0, size)
        } else {
            val samples = ByteBuffer.wrap(scratch, 0, size).order(order)
            while (samples.remaining() >= 4) {
                val l = samples.short.toFloat(); val r = samples.short.toFloat()
                low += alpha * ((l + r) * 0.5f - low)          // the centre's bass, kept
                val v = ((l - r) * 0.5f + low * 0.85f).coerceIn(-32768f, 32767f).toInt().toShort()
                out.putShort(v); out.putShort(v)
            }
            if (samples.hasRemaining()) out.put(scratch, samples.position(), samples.remaining())
        }
        out.flip()
    }

    override fun onFlush() { low = 0f }
    override fun onReset() { low = 0f }

    private companion object { const val BASS_HZ = 140.0 }
}
