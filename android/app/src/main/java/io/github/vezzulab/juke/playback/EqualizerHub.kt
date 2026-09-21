package io.github.vezzulab.juke.playback

import android.media.audiofx.Equalizer
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import io.github.vezzulab.juke.data.Store
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.exp
import kotlin.math.ln

/**
 * The 10-band curve the person edits (same bands and presets as Juke for Linux), applied to the phone's
 * hardware equalizer on the player's audio session without restarting playback. Android equalizers usually
 * have 5 bands, so the curve is interpolated on a log-frequency axis onto the device's own bands.
 */
object EqualizerHub {
    val BANDS_HZ = intArrayOf(60, 170, 310, 600, 1000, 3000, 6000, 12000, 14000, 16000)
    // The same curves as Juke for Linux, kept in step by a test. They are deliberately smooth: neighbouring bands
    // never jump more than a few dB, because a jagged curve sounds phasey rather than better.
    val PRESETS: Map<String, List<Float>> = linkedMapOf(
        "Flat" to listOf(0, 0, 0, 0, 0, 0, 0, 0, 0, 0), "Rock" to listOf(5, 4, 1, -1, -1, 2, 4, 4, 4, 3),
        "Pop" to listOf(3, 2, 0, 0, 1, 3, 3, 3, 3, 2), "Jazz" to listOf(3, 2, 1, 0, 0, 1, 2, 2, 2, 2),
        "Bass Boost" to listOf(8, 6, 4, 2, 0, 0, 0, 0, 0, 0), "Vocal" to listOf(-3, -2, -1, 1, 3, 4, 3, 1, 1, 0),
        "Classical" to listOf(2, 1, 0, 0, 0, 1, 1, 2, 2, 2), "Electronic" to listOf(6, 5, 2, 0, -1, 1, 3, 4, 4, 4),
        "Heavy Metal" to listOf(5, 4, 1, -1, 0, 3, 4, 4, 4, 3), "Techno" to listOf(6, 5, 2, -1, -2, 1, 3, 4, 5, 4),
        // Caribbean genres, each tuned for what actually carries it: the sub kick of dembow and reggaeton, the brass
        // and timbales of salsa, the tambora and güira of merengue, the requinto guitar of bachata.
        "Dembow" to listOf(7, 5, 2, -1, 0, 2, 4, 4, 4, 3), "Reggaeton" to listOf(6, 5, 2, 0, 1, 2, 3, 3, 3, 2),
        "Salsa" to listOf(2, 2, 0, 1, 2, 3, 4, 3, 3, 2), "Merengue" to listOf(4, 3, 0, 1, 2, 3, 4, 4, 4, 3),
        "Bachata" to listOf(3, 2, -1, 0, 2, 4, 4, 3, 3, 2),
    ).mapValues { (_, v) -> v.map { it.toFloat() } }

    /**
     * The preamp a curve has to be played at so that its loudest boost cannot clip. A song is already mastered close
     * to the maximum, so lifting a band by +7 dB has nowhere to go and the sound breaks up. Shifting the whole curve
     * down by its own biggest boost keeps the shape and the headroom; the volume knob gives the loudness back cleanly.
     */
    fun headroom(gains: List<Float>): Float = -maxOf(0f, gains.maxOrNull() ?: 0f)

    const val MAX_DB = 12f
    private const val STEPS = 12          // samples taken across one device band

    var enabled by mutableStateOf(false); private set
    var preamp by mutableFloatStateOf(0f); private set
    var preset by mutableStateOf<String?>("Flat"); private set
    val gains = mutableStateListOf<Float>().apply { repeat(10) { add(0f) } }
    var available by mutableStateOf(true); private set

    private var store: Store? = null
    private var effect: Equalizer? = null
    private var sessionId = 0

    fun init(store: Store) {
        if (this.store != null) return
        this.store = store
        store.equalizerJson()?.let { j ->
            enabled = j.optBoolean("enabled"); preamp = j.optDouble("preamp", 0.0).toFloat(); preset = j.optString("preset").ifBlank { null }
            j.optJSONArray("gains")?.let { a -> for (i in 0 until minOf(10, a.length())) gains[i] = a.optDouble(i, 0.0).toFloat() }
        }
    }

    fun attach(audioSessionId: Int) {
        if (audioSessionId == 0 || audioSessionId == sessionId && effect != null) return
        release()
        sessionId = audioSessionId
        effect = try { Equalizer(0, audioSessionId).also { available = true } } catch (e: Exception) { available = false; null }
        apply()
    }

    fun release() { runCatching { effect?.release() }; effect = null; sessionId = 0 }

    fun switchOn(on: Boolean) { enabled = on; changed() }
    fun changePreamp(db: Float) { preamp = db.coerceIn(-MAX_DB, MAX_DB); preset = null; changed() }
    fun setGain(band: Int, db: Float) { gains[band] = db.coerceIn(-MAX_DB, MAX_DB); preset = null; changed() }
    fun loadPreset(name: String) { PRESETS[name]?.let { p -> p.forEachIndexed { i, g -> gains[i] = g }; preamp = headroom(p); preset = name; changed() } }

    private fun changed() { apply(); persist() }

    /** The 10-band curve read at one frequency. */
    private fun curveAt(hz: Double): Float {
        if (hz <= BANDS_HZ.first()) return gains.first()
        if (hz >= BANDS_HZ.last()) return gains.last()
        val i = BANDS_HZ.indexOfLast { it <= hz }
        val (lo, hi) = BANDS_HZ[i].toDouble() to BANDS_HZ[i + 1].toDouble()
        val t = ((ln(hz) - ln(lo)) / (ln(hi) - ln(lo))).toFloat()
        return gains[i] + (gains[i + 1] - gains[i]) * t
    }

    /**
     * The curve averaged over the whole width of one of the device's bands. Phones usually have five bands, each
     * covering two or three of ours, so reading the curve at the band's centre alone threw most of the shape away:
     * a boost that sat between two centres was simply not heard.
     */
    private fun gainForBand(lowHz: Double, highHz: Double, centerHz: Double): Float {
        val lo = lowHz.takeIf { it.isFinite() && it > 1.0 } ?: (centerHz / 2)
        val hi = highHz.takeIf { it.isFinite() && it > lo && it < 40_000 } ?: (centerHz * 2)
        if (!(hi > lo) || centerHz <= 0) return curveAt(centerHz.coerceAtLeast(1.0))
        var sum = 0f
        for (i in 0..STEPS) {
            sum += curveAt(exp(ln(lo) + (ln(hi) - ln(lo)) * i / STEPS))
        }
        return sum / (STEPS + 1)
    }

    private fun apply() {
        val e = effect ?: return
        try {
            if (!enabled) { e.enabled = false; return }
            val range = e.bandLevelRange
            for (band in 0 until e.numberOfBands) {
                val b = band.toShort()
                val center = e.getCenterFreq(b) / 1000.0
                val edges = runCatching { e.getBandFreqRange(b) }.getOrNull()
                val gain = gainForBand((edges?.get(0) ?: 0) / 1000.0, (edges?.get(1) ?: 0) / 1000.0, center)
                val level = ((gain + preamp) * 100).toInt().coerceIn(range[0].toInt(), range[1].toInt())
                e.setBandLevel(b, level.toShort())
            }
            e.enabled = true                        // the levels are in place before the effect starts working
        } catch (_: Exception) { /* the effect died with its session; the next attach rebuilds it */ }
    }



    private fun persist() {
        store?.saveEqualizer(JSONObject().put("enabled", enabled).put("preamp", preamp.toDouble()).put("preset", preset ?: "").put("gains", JSONArray(gains.map { it.toDouble() })))
    }
}
