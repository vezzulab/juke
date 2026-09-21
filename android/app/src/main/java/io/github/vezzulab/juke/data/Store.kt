package io.github.vezzulab.juke.data

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/** Small settings store (app-private SharedPreferences): server, saved stations, theme, language, equalizer. */
class Store(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("juke", Context.MODE_PRIVATE)

    var server: ServerConfig
        get() = ServerConfig(prefs.getString("server.url", "").orEmpty(), prefs.getString("server.user", "").orEmpty(), prefs.getString("server.password", "").orEmpty())
        set(v) { prefs.edit().putString("server.url", v.url).putString("server.user", v.user).putString("server.password", v.password).apply() }

    var theme: String                     // "system" | "dark" | "light"
        get() = prefs.getString("theme", "dark").orEmpty()
        set(v) { prefs.edit().putString("theme", v).apply() }


    var lyricsAuto: Boolean               // ask LRCLIB for songs that have no lyrics (off: only when asked)
        get() = prefs.getBoolean("lyrics_auto", false)
        set(v) { prefs.edit().putBoolean("lyrics_auto", v).apply() }

    var updatesAuto: Boolean              // look for a new Juke on GitHub while the app is open
        get() = prefs.getBoolean("updates_auto", true)
        set(v) { prefs.edit().putBoolean("updates_auto", v).apply() }

    var updateSkipped: String             // "Skip this version": what was skipped (see UpdateRelease.key)
        get() = prefs.getString("update_skipped", "").orEmpty()
        set(v) { prefs.edit().putString("update_skipped", v).apply() }

    var updateSnoozeKey: String           // "Later": which version, and until when
        get() = prefs.getString("update_snooze_key", "").orEmpty()
        set(v) { prefs.edit().putString("update_snooze_key", v).apply() }

    var updateSnoozeUntil: Long
        get() = prefs.getLong("update_snooze_until", 0L)
        set(v) { prefs.edit().putLong("update_snooze_until", v).apply() }

    var sortOrder: String                 // "Original" | "AZ" | "ZA": how folders and songs are listed
        get() = prefs.getString("sort", "Original").orEmpty()
        set(v) { prefs.edit().putString("sort", v).apply() }

    var language: String                  // "system" | "en" | "es"
        get() = prefs.getString("language", "system").orEmpty()
        set(v) { prefs.edit().putString("language", v).apply() }

    var stations: List<Station>
        get() {
            val array = runCatching { JSONArray(prefs.getString("stations", "[]")) }.getOrDefault(JSONArray())
            return (0 until array.length()).mapNotNull { array.optJSONObject(it)?.let(Station::fromJson) }
        }
        set(v) { prefs.edit().putString("stations", JSONArray(v.map { it.toJson() }).toString()).apply() }

    fun equalizerJson(): JSONObject? = prefs.getString("equalizer", null)?.let { runCatching { JSONObject(it) }.getOrNull() }
    fun saveEqualizer(json: JSONObject) { prefs.edit().putString("equalizer", json.toString()).apply() }
}
