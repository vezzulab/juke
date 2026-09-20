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
import kotlin.math.ln

/**
 * The 10-band curve the person edits (same bands and presets as Juke for Linux), applied to the phone's
 * hardware equalizer on the player's audio session without restarting playback. Android equalizers usually
 * have 5 bands, so the curve is interpolated on a log-frequency axis onto the device's own bands.
 */
object EqualizerHub {
    val BANDS_HZ = intArrayOf(60, 170, 310, 600, 1000, 3000, 6000, 12000, 14000, 16000)
    val PRESETS: Map<String, List<Float>> = linkedMapOf(
        "Flat" to listOf(0, 0, 0, 0, 0, 0, 0, 0, 0, 0), "Rock" to listOf(4, 3, 2, -1, -2, -1, 2, 4, 5, 5),
        "Pop" to listOf(-1, 3, 4, 5, 3, 0, -1, -2, -2, -2), "Jazz" to listOf(3, 2, 1, 2, -2, -2, 0, 1, 2, 3),
        "Bass Boost" to listOf(7, 6, 5, 3, 1, 0, 0, 0, 0, 0), "Vocal" to listOf(-3, -3, -2, 1, 4, 4, 3, 1, 0, -1),
        "Classical" to listOf(0, 0, 0, 0, 0, 0, -2, -3, -3, -4), "Electronic" to listOf(5, 4, 1, 0, -2, 2, 1, 1, 4, 5),
        "Heavy Metal" to listOf(5, 4, 0, -3, -1, 2, 5, 6, 5, 4), "Techno" to listOf(5, 4, 0, -4, -3, 0, 5, 6, 6, 5),
    ).mapValues { (_, v) -> v.map { it.toFloat() } }

    const val MAX_DB = 12f

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
    fun loadPreset(name: String) { PRESETS[name]?.let { p -> p.forEachIndexed { i, g -> gains[i] = g }; preamp = 0f; preset = name; changed() } }

    private fun changed() { apply(); persist() }

    private fun gainAt(hz: Double): Float {
        if (hz <= BANDS_HZ.first()) return gains.first()
        if (hz >= BANDS_HZ.last()) return gains.last()
        val i = BANDS_HZ.indexOfLast { it <= hz }
        val (lo, hi) = BANDS_HZ[i].toDouble() to BANDS_HZ[i + 1].toDouble()
        val t = ((ln(hz) - ln(lo)) / (ln(hi) - ln(lo))).toFloat()
        return gains[i] + (gains[i + 1] - gains[i]) * t
    }

    private fun apply() {
        val e = effect ?: return
        try {
            e.enabled = enabled
            if (!enabled) return
            val range = e.bandLevelRange
            for (band in 0 until e.numberOfBands) {
                val hz = e.getCenterFreq(band.toShort()) / 1000.0
                val level = ((gainAt(hz) + preamp) * 100).toInt().coerceIn(range[0].toInt(), range[1].toInt())
                e.setBandLevel(band.toShort(), level.toShort())
            }
        } catch (_: Exception) { /* the effect died with its session; the next attach rebuilds it */ }
    }

    private fun persist() {
        store?.saveEqualizer(JSONObject().put("enabled", enabled).put("preamp", preamp.toDouble()).put("preset", preset ?: "").put("gains", JSONArray(gains.map { it.toDouble() })))
    }
}
