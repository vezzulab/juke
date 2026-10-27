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

    var playlistsSort: String             // how the list of playlists is ordered: az | za | recent | size
        get() = prefs.getString("playlists_sort", "az").orEmpty()
        set(v) { prefs.edit().putString("playlists_sort", v).apply() }
    var playlistSongsSort: String         // how the songs inside a playlist are ordered: original | az | za | artist
        get() = prefs.getString("playlist_songs_sort", "original").orEmpty()
        set(v) { prefs.edit().putString("playlist_songs_sort", v).apply() }

    var syncServer: String                // the Juke sync server (cloudflare/sync), this person's code and the copy last seen there
        get() = prefs.getString("sync.server", Sync.DEFAULT_SERVER).orEmpty()
        set(v) { prefs.edit().putString("sync.server", v).apply() }
    var syncCode: String
        get() = prefs.getString("sync.code", "").orEmpty()
        set(v) { prefs.edit().putString("sync.code", v).apply() }
    var syncUpdated: Long
        get() = prefs.getLong("sync.updated", 0L)
        set(v) { prefs.edit().putLong("sync.updated", v).apply() }
    var syncAuto: Boolean                 // keep this phone's playlists and stations the same as the other devices, by themselves
        get() = prefs.getBoolean("sync.auto", true)
        set(v) { prefs.edit().putBoolean("sync.auto", v).apply() }
    var syncSettingsAt: Long              // when the synced settings (here: the language) last changed
        get() = prefs.getLong("sync.settings_at", 0L)
        set(v) { prefs.edit().putLong("sync.settings_at", v).apply() }
    var syncLastOk: Long
        get() = prefs.getLong("sync.last_ok", 0L)
        set(v) { prefs.edit().putLong("sync.last_ok", v).apply() }
    var deletedLists: Map<String, Pair<String, Long>>      // playlists deleted here (key -> name, date), so other devices delete them too
        get() {
            val o = runCatching { JSONObject(prefs.getString("deleted_lists", "{}")) }.getOrDefault(JSONObject())
            return o.keys().asSequence().associateWith { k -> o.getJSONObject(k).let { it.optString("name") to it.optLong("at") } }
        }
        set(v) { prefs.edit().putString("deleted_lists", JSONObject().also { o -> v.forEach { (k, p) -> o.put(k, JSONObject().put("name", p.first).put("at", p.second)) } }.toString()).apply() }
    var deletedStations: Map<String, Long>
        get() {
            val o = runCatching { JSONObject(prefs.getString("deleted_stations", "{}")) }.getOrDefault(JSONObject())
            return o.keys().asSequence().associateWith { o.optLong(it) }
        }
        set(v) { prefs.edit().putString("deleted_stations", JSONObject().also { o -> v.forEach { (k, at) -> o.put(k, at) } }.toString()).apply() }

    var syncKept: String                  // what the copy holds that this phone does not use (favorites, the desktop's equalizer), handed back as it came
        get() = prefs.getString("sync.kept", "{}").orEmpty()
        set(v) { prefs.edit().putString("sync.kept", v).apply() }

    var stations: List<Station>
        get() {
            val array = runCatching { JSONArray(prefs.getString("stations", "[]")) }.getOrDefault(JSONArray())
            return (0 until array.length()).mapNotNull { array.optJSONObject(it)?.let(Station::fromJson) }
        }
        set(v) { prefs.edit().putString("stations", JSONArray(v.map { it.toJson() }).toString()).apply() }

    fun equalizerJson(): JSONObject? = prefs.getString("equalizer", null)?.let { runCatching { JSONObject(it) }.getOrNull() }
    fun saveEqualizer(json: JSONObject) { prefs.edit().putString("equalizer", json.toString()).apply() }
}
