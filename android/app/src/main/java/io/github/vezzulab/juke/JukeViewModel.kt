package io.github.vezzulab.juke

import android.app.Application
import android.content.ComponentName
import android.database.ContentObserver
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.MediaStore
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.content.ContextCompat
import androidx.core.net.toUri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.C
import androidx.media3.common.MediaItem
import androidx.media3.common.MediaMetadata
import androidx.media3.common.Player
import androidx.media3.session.MediaController
import androidx.media3.session.SessionToken
import io.github.vezzulab.juke.data.*
import io.github.vezzulab.juke.playback.EqualizerHub
import io.github.vezzulab.juke.ui.Accents
import io.github.vezzulab.juke.playback.PlaybackService
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** What the YouTube page is showing right now. */
sealed interface YtState {
    data object Idle : YtState
    data object Searching : YtState
    data class Failed(val kind: String) : YtState
    data class Ready(val query: String, val songs: List<YtSong>) : YtState
}

/** What a browser screen is showing right now. */
sealed interface BrowseState {
    data object Idle : BrowseState                       // nothing set up yet (no server, no permission)
    data object Loading : BrowseState
    data class Failed(val message: String) : BrowseState
    data class Ready(val folders: List<Folder>, val tracks: List<Track>) : BrowseState
}

class JukeViewModel(app: Application) : AndroidViewModel(app) {
    val store = Store(app)
    val stations = mutableStateListOf<Station>()

    // ---- playlists (songs of the phone and of YouTube) --------------------------------------------------
    private val playlistStore = PlaylistStore(app)
    val playlists = mutableStateListOf<Playlist>()
    /** The songs waiting for a playlist to be picked (the "add to playlist" sheet shows while this is set). */
    var addTarget by mutableStateOf<List<TrackRef>?>(null); private set
    var notice by mutableStateOf<String?>(null); private set

    fun askAdd(refs: List<TrackRef>) { if (refs.isNotEmpty()) addTarget = refs }
    fun dismissAdd() { addTarget = null }
    fun clearNotice() { notice = null }

    private fun savePlaylists() = playlistStore.save(playlists.toList())

    private fun playlistIndex(name: String) = playlists.indexOfFirst { it.name.equals(name.trim(), ignoreCase = true) }

    /** Adds songs to a playlist, making it if there is none with that name. A song already in it is not added again. Returns how many went in. */
    fun addToPlaylist(name: String, refs: List<TrackRef>): Int {
        val clean = name.trim().ifEmpty { return 0 }
        val at = playlistIndex(clean)
        val have = if (at >= 0) playlists[at].tracks.map { it.key }.toHashSet() else HashSet()
        val fresh = refs.filter { have.add(it.key) }
        val now = System.currentTimeMillis()
        if (at >= 0) { if (fresh.isNotEmpty()) playlists[at] = playlists[at].copy(tracks = playlists[at].tracks + fresh, updated = now) }
        else { playlists += Playlist(clean, fresh, now); forgetDeleted(clean) }
        playlists.sortBy { it.name.lowercase() }
        savePlaylists()
        requestSync()
        return fresh.size
    }

    /** A playlist made again after it was deleted is new: the mark of its deletion goes. */
    private fun forgetDeleted(name: String) { store.deletedLists = store.deletedLists - Backup.key(name) }
    private fun markDeleted(name: String) { store.deletedLists = store.deletedLists + (Backup.key(name) to (name to System.currentTimeMillis())) }

    fun createPlaylist(name: String) { addToPlaylist(name, emptyList()) }

    /** "Add to playlist" answered: the songs go in, the panel closes and a short note says what happened. */
    fun addAndSay(name: String, refs: List<TrackRef>) {
        val app = getApplication<Application>()
        val added = addToPlaylist(name, refs)
        addTarget = null
        notice = if (added > 0) app.getString(R.string.added_to, added, name.trim()) else app.getString(R.string.already_in, name.trim())
    }
    fun deletePlaylist(name: String) { playlists.removeAll { it.name == name }; markDeleted(name); savePlaylists(); requestSync() }
    fun renamePlaylist(name: String, to: String) {
        val clean = to.trim()
        val at = playlists.indexOfFirst { it.name == name }
        if (at < 0 || clean.isEmpty() || (playlistIndex(clean) >= 0 && !clean.equals(name, ignoreCase = true))) return
        markDeleted(name); forgetDeleted(clean)                       // to the other devices the old name is a playlist that was deleted
        playlists[at] = playlists[at].copy(name = clean, updated = System.currentTimeMillis()); playlists.sortBy { it.name.lowercase() }; savePlaylists(); requestSync()
    }
    fun removeFromPlaylist(name: String, index: Int) {
        val at = playlists.indexOfFirst { it.name == name }
        if (at < 0 || index !in playlists[at].tracks.indices) return
        playlists[at] = playlists[at].copy(tracks = playlists[at].tracks.filterIndexed { i, _ -> i != index }, updated = System.currentTimeMillis()); savePlaylists(); requestSync()
    }

    // ---- backup and sync ---------------------------------------------------------------------------------
    var syncStatus by mutableStateOf<Pair<Boolean, String>?>(null); private set      // (ok?, what to tell the person)
    var syncBusy by mutableStateOf(false); private set
    var syncAuto by mutableStateOf(store.syncAuto); private set
    var syncLastOk by mutableStateOf(store.syncLastOk); private set

    private fun say(ok: Boolean, text: String) { syncStatus = ok to text }
    private fun kept() = runCatching { org.json.JSONObject(store.syncKept) }.getOrDefault(org.json.JSONObject())

    private fun localState() = Backup.State(playlists.toList(), stations.toList(), store.deletedLists, store.deletedStations, kept(), store.syncSettingsAt, store.language)

    private fun errorText(e: Exception): String {
        val app = getApplication<Application>()
        val kind = (e as? SyncException)?.kind ?: "server"
        val res = mapOf("server" to R.string.sync_err_server, "denied" to R.string.sync_err_denied, "none" to R.string.sync_err_none, "changed" to R.string.sync_err_changed,
            "big" to R.string.sync_err_big, "soon" to R.string.sync_err_soon, "busy" to R.string.sync_err_busy, "full" to R.string.sync_err_full,
            "corrupt" to R.string.sync_err_corrupt, "url" to R.string.sync_err_url, "code" to R.string.sync_err_code, "newer" to R.string.sync_err_newer)[kind] ?: R.string.sync_err_server
        return app.getString(res)
    }

    fun newSyncCode(): String = Sync.newCode().also { store.syncCode = it; store.syncUpdated = 0 }

    private fun usable(server: String = store.syncServer, code: String = store.syncCode) = server.isNotBlank() && Sync.cleanCode(code) != null

    /** The language is one of the settings that follow the person between devices: say when it changed. */
    fun languageChanged() { store.syncSettingsAt = System.currentTimeMillis(); requestSync() }

    fun changeSyncAuto(on: Boolean) { syncAuto = on; store.syncAuto = on; if (on) requestSync(1_000) }

    fun saveSyncSetup(server: String, code: String): Boolean {
        val clean = Sync.cleanCode(code) ?: run { say(false, getApplication<Application>().getString(R.string.sync_err_code)); return false }
        if (server.isBlank()) { say(false, getApplication<Application>().getString(R.string.sync_err_server_empty)); return false }
        store.syncServer = server.trim(); store.syncCode = clean
        return true
    }

    private val syncLock = kotlinx.coroutines.sync.Mutex()
    private var syncDebounce: Job? = null

    /** Something changed here (or the app just opened): a round soon, once, however many changes come. */
    fun requestSync(delayMs: Long = 8_000) {
        if (!syncAuto || !usable()) return
        syncDebounce?.cancel()
        syncDebounce = viewModelScope.launch { delay(delayMs); syncRound(manual = false) }
    }

    fun syncNow(server: String, code: String) {
        if (!saveSyncSetup(server, code)) return
        viewModelScope.launch { syncRound(manual = true) }
    }

    /** One round: ask the server for its copy, bring in what the other devices did, and send ours back only if it says something new. */
    private suspend fun syncRound(manual: Boolean) {
        if (!usable()) return
        if (!syncLock.tryLock()) return
        if (manual) { syncBusy = true; syncStatus = null }
        try {
            val server = store.syncServer
            val code = store.syncCode
            var tries = 0
            while (true) {
                val remote = try { Sync.pull(server, code) } catch (e: SyncException) { if (e.kind == "none") null else throw e }
                var changed = false
                val doc = remote?.let { Backup.parse(it.first) }
                if (doc != null) {
                    val merged = Backup.merge(doc, localState(), System.currentTimeMillis())
                    changed = merged.changed
                    adopt(merged)
                }
                val mine = Backup.snapshot(localState())
                if (doc != null && Backup.fingerprint(org.json.JSONObject(mine)) == Backup.fingerprint(doc)) { store.syncUpdated = remote!!.second; finishRound(manual, changed); return }
                try {
                    store.syncUpdated = Sync.push(server, code, mine, remote?.second ?: 0L)
                    finishRound(manual, changed); return
                } catch (e: SyncException) {
                    if (e.kind == "changed" && ++tries < 3) continue            // another device saved in between: look again
                    throw e
                }
            }
        } catch (e: Throwable) {
            if (e is CancellationException) throw e
            AppLog.w("sync", "Syncing failed", e)
            if (manual) say(false, errorText(e as? Exception ?: RuntimeException(e)))
        } finally {
            if (manual) syncBusy = false
            syncLock.unlock()
        }
    }

    private fun finishRound(manual: Boolean, changed: Boolean) {
        store.syncLastOk = System.currentTimeMillis(); syncLastOk = store.syncLastOk
        if (manual) say(true, getApplication<Application>().getString(R.string.sync_done))
    }

    /** Puts a merged copy in place: playlists, stations, the marks of what was deleted, and what the copy holds that this phone does not use. */
    private fun adopt(m: Backup.Merged) {
        val s = m.state
        playlists.clear(); playlists.addAll(s.playlists); savePlaylists()
        stations.clear(); stations.addAll(s.stations); store.stations = stations.toList()
        store.deletedLists = s.deletedLists; store.deletedStations = s.deletedStations
        store.syncKept = s.kept.toString(); store.syncSettingsAt = s.settingsAt
        m.language?.takeIf { it != store.language }?.let {
            store.language = it
            androidx.appcompat.app.AppCompatDelegate.setApplicationLocales(androidx.core.os.LocaleListCompat.forLanguageTags(it))
        }
    }

    fun syncForget(server: String, code: String) {
        if (!saveSyncSetup(server, code)) return
        syncBusy = true; syncStatus = null
        viewModelScope.launch {
            try { Sync.delete(store.syncServer, store.syncCode); store.syncUpdated = 0; say(true, getApplication<Application>().getString(R.string.sync_forgotten)) }
            catch (e: Exception) { if (e is CancellationException) throw e; say(false, errorText(e)) }
            syncBusy = false
        }
    }

    init {
        viewModelScope.launch {                       // a few seconds after opening, then every few minutes for as long as the app lives
            delay(6_000)
            while (true) {
                if (syncAuto && usable()) syncRound(manual = false)
                delay(5 * 60_000L)
            }
        }
    }

    fun exportTo(uri: android.net.Uri) {
        val app = getApplication<Application>()
        try {
            app.contentResolver.openOutputStream(uri)?.use { it.write(Backup.snapshot(localState()).toByteArray(Charsets.UTF_8)) } ?: throw java.io.IOException("no file")
            say(true, app.getString(R.string.backup_saved))
        } catch (e: Exception) { AppLog.w("sync", "Saving the copy failed", e); say(false, app.getString(R.string.backup_file_error, e.message ?: "")) }
    }

    fun importFrom(uri: android.net.Uri) {
        val app = getApplication<Application>()
        try {
            val text = app.contentResolver.openInputStream(uri)?.use { it.readBytes().toString(Charsets.UTF_8) } ?: throw java.io.IOException("no file")
            val merged = Backup.addFrom(Backup.parse(text), localState(), System.currentTimeMillis())
            adopt(merged)
            say(true, app.getString(R.string.backup_restored_file))
            requestSync()
        } catch (e: SyncException) { say(false, errorText(e)) }
        catch (e: Exception) { AppLog.w("sync", "Reading the copy failed", e); say(false, app.getString(R.string.backup_file_error, e.message ?: "")) }
    }

    // ---- YouTube ---------------------------------------------------------------------------------------
    var youtube by mutableStateOf<YtState>(YtState.Idle); private set
    private var ytJob: Job? = null

    fun searchYouTube(query: String) {
        val text = query.trim()
        ytJob?.cancel()
        if (text.isEmpty()) { youtube = YtState.Idle; return }
        youtube = YtState.Searching
        ytJob = viewModelScope.launch {
            youtube = try { YtState.Ready(text, YouTube.search(text)) } catch (e: Throwable) {
                if (e is CancellationException) throw e
                AppLog.w("youtube", "Searching YouTube failed", e)
                YtState.Failed((e as? YouTubeException)?.kind ?: "unavailable")
            }
        }
    }

    fun playYouTube(songs: List<YtSong>, start: Int) {
        val c = controller ?: return
        if (songs.isEmpty()) return
        c.setMediaItems(songs.map { ytItem(TrackRef.of(it)) }, start.coerceIn(0, songs.lastIndex), 0); c.prepare(); c.play()
    }

    private fun ytItem(ref: TrackRef) = MediaItem.Builder().setMediaId("yt:" + ref.yt).setUri("juke-yt://" + ref.yt)
        .setMediaMetadata(
            MediaMetadata.Builder().setTitle(ref.title).setArtist(ref.artist)
                .setDurationMs(ref.durationSec.takeIf { it > 0 }?.let { it * 1000L })
                .setArtworkUri(YouTube.thumbnail(ref.yt).toUri())
                .setExtras(Bundle().apply { putString("badge", "YouTube") }).build()
        ).build()

    private var hereFor: LocalLibrary.Tree? = null
    private var hereUris: Set<String> = emptySet()
    private var hereNames: Set<String> = emptySet()

    /** Can this device play the song? A YouTube song always, a song of the server when it is set up, a song of the card when it is there. */
    fun isHere(ref: TrackRef): Boolean {
        if (ref.isYouTube) return true
        if (ref.sid.isNotEmpty() && client() != null) return true
        val library = tree ?: return false
        if (hereFor !== library) {
            val all = library.all()
            hereUris = all.mapNotNullTo(HashSet()) { it.uri }
            hereNames = all.mapTo(HashSet()) { YouTube.normalize("${it.title}|${it.artist}") }
            hereFor = library
        }
        return (ref.uri.isNotEmpty() && ref.uri in hereUris) || YouTube.normalize("${ref.title}|${ref.artist}") in hereNames
    }

    /** Plays a playlist from [start]. Songs that this phone does not have are skipped (and said). */
    fun playRefs(refs: List<TrackRef>, start: Int) {
        val c = controller ?: return
        val all = tree?.all().orEmpty()
        val byUri = all.associateBy { it.uri }
        val byName = all.groupBy { YouTube.normalize("${it.title}|${it.artist}") }
        val api = client()
        val items = ArrayList<MediaItem>()
        var first = 0
        var skipped = 0
        refs.forEachIndexed { index, ref ->
            val item = when {
                ref.isYouTube -> ytItem(ref)
                else -> {
                    val track = byUri[ref.uri.takeIf { it.isNotEmpty() }]
                        ?: byName[YouTube.normalize("${ref.title}|${ref.artist}")]?.minByOrNull { kotlin.math.abs(it.durationSec - ref.durationSec) }
                        ?: ref.sid.takeIf { it.isNotEmpty() && api != null }?.let { Track(it, ref.title, ref.artist, ref.album, ref.durationSec, null, "", 0) }
                    track?.let { trackItem(it, api) }
                }
            }
            if (item == null) { skipped++; if (index <= start) first = items.size.coerceAtLeast(0) } else { if (index == start) first = items.size; items += item }
        }
        val app = getApplication<Application>()
        if (items.isEmpty()) { notice = app.getString(R.string.playlist_none_here); return }
        if (skipped > 0) notice = app.getString(R.string.playlist_skipped, skipped)
        c.setMediaItems(items, first.coerceIn(0, items.lastIndex), 0); c.prepare(); c.play()
    }

    var theme by mutableStateOf(store.theme.also { id -> Accents.use(id) }); private set
    fun applyTheme(value: String) { theme = value; store.theme = value; Accents.use(value) }

    // ---- the SD card and the device's own storage ------------------------------------------------
    private var tree: LocalLibrary.Tree? = null
    val localCrumbs = mutableStateListOf<Folder>()
    var local by mutableStateOf<BrowseState>(BrowseState.Idle); private set
    var hasAudioPermission by mutableStateOf(false); private set

    fun onAudioPermission(granted: Boolean) {
        hasAudioPermission = granted
        if (granted && tree == null) scanLocal() else if (!granted) local = BrowseState.Idle
    }

    fun scanLocal() {
        local = BrowseState.Loading
        viewModelScope.launch {
            try {
                val scanned = LocalLibrary.scan(getApplication())
                tree = scanned
                lastLook = SystemClock.elapsedRealtime()
                localCrumbs.clear()
                if (scanned.roots.size == 1) localCrumbs += scanned.roots.first()     // only one card or one storage: go straight in
                showLocal()
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                AppLog.w("library", "Scanning the card failed", e)
                local = BrowseState.Failed(e.message ?: "error")
            }
        }
    }

    // Songs that arrive while the app is open or asleep (copied over USB, downloaded, put on the card) show up by themselves:
    // Android tells us when its music index changes, and a look is taken every time the app comes back to the front.
    private var lastLook = 0L
    private var refreshJob: Job? = null
    private val mediaWatcher = object : ContentObserver(Handler(Looper.getMainLooper())) {
        override fun onChange(selfChange: Boolean) { refreshSoon(2_000) }
    }
    init { app.contentResolver.registerContentObserver(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, true, mediaWatcher) }

    /** A copy of a folder of songs makes hundreds of changes in a row: look once, when they have stopped. */
    private fun refreshSoon(afterMs: Long) {
        refreshJob?.cancel()
        refreshJob = viewModelScope.launch { delay(afterMs); refreshLocal() }
    }

    /** Read the library again without the spinner and without losing the folder that is open. */
    fun refreshLocal() {
        if (!hasAudioPermission || tree == null) return
        lastLook = SystemClock.elapsedRealtime()
        viewModelScope.launch {
            try {
                tree = LocalLibrary.scan(getApplication())
                showLocal()
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                AppLog.w("library", "Refreshing the library failed", e)
            }
        }
    }

    fun onForeground() { if (SystemClock.elapsedRealtime() - lastLook > 20_000) refreshSoon(300) }

    var sortOrder by mutableStateOf(runCatching { SortOrder.valueOf(store.sortOrder) }.getOrDefault(SortOrder.Original)); private set
    private var remoteRaw: BrowseState = BrowseState.Idle

    /** The list in the chosen order. Volumes (card, internal storage) keep their own order; songs sort by title. */
    private fun ordered(state: BrowseState): BrowseState {
        if (state !is BrowseState.Ready) return state
        val volumes = state.folders.any { it.name == "sd" || it.name == "internal" }
        return BrowseState.Ready(if (volumes) state.folders else state.folders.sortedBy(sortOrder) { it.name }, state.tracks.sortedBy(sortOrder) { it.title })
    }

    fun setSort(order: SortOrder) {
        sortOrder = order; store.sortOrder = order.name
        showLocal()
        remote = ordered(remoteRaw)
    }

    private fun showLocal() {
        val scanned = tree ?: return
        local = ordered(when {
            scanned.isEmpty -> BrowseState.Ready(emptyList(), emptyList())
            localCrumbs.isEmpty() -> BrowseState.Ready(scanned.roots, emptyList())
            else -> BrowseState.Ready(scanned.children(localCrumbs.last().id), scanned.tracks(localCrumbs.last().id))
        })
    }

    fun openLocal(folder: Folder) { localCrumbs += folder; showLocal() }

    val canGoUpLocal get() = localCrumbs.size > (if ((tree?.roots?.size ?: 0) > 1) 0 else 1)

    fun localUp(): Boolean {
        if (!canGoUpLocal) return false
        localCrumbs.removeAt(localCrumbs.lastIndex)
        showLocal()
        return true
    }

    fun playFolder() {
        val scanned = tree ?: return
        val path = localCrumbs.lastOrNull()?.id ?: return
        val songs = scanned.deepTracks(path)
        if (songs.isNotEmpty()) playTracks(songs, 0)
    }

    // ---- Airsonic / Subsonic --------------------------------------------------------------------
    var server by mutableStateOf(store.server); private set
    var serverStatus by mutableStateOf<String?>(null); private set     // null untested, "" connected, else the error
    var serverBusy by mutableStateOf(false); private set
    private var client: AirsonicClient? = null
    private var multiRoot = false
    private var loadJob: Job? = null

    val serverCrumbs = mutableStateListOf<Folder>()
    var remote by mutableStateOf<BrowseState>(BrowseState.Idle); private set
    var searchQuery by mutableStateOf(""); private set

    private fun client(): AirsonicClient? =
        client ?: server.takeIf { it.isComplete }?.let { AirsonicClient(it.url, it.user, it.password) }.also { client = it }

    fun connect(config: ServerConfig) {
        server = config; store.server = config; client = null; serverCrumbs.clear(); searchQuery = ""
        serverBusy = true; serverStatus = null
        viewModelScope.launch {
            serverStatus = try { client()!!.ping(); "" } catch (e: Exception) { AppLog.w("server", "Could not reach the server", e); e.message ?: "error" }
            serverBusy = false
            if (serverStatus == "") loadRemote() else remote = BrowseState.Failed(serverStatus.orEmpty())
        }
    }

    fun loadRemote() {
        val c = client()
        if (c == null) { remote = BrowseState.Idle; return }
        remote = BrowseState.Loading
        loadJob?.cancel()
        loadJob = viewModelScope.launch {
            val loaded = try {
                when {
                    searchQuery.isNotBlank() -> BrowseState.Ready(emptyList(), c.search(searchQuery))
                    serverCrumbs.isEmpty() -> {
                        val roots = c.musicFolders()
                        multiRoot = roots.size != 1
                        if (roots.size == 1) { serverCrumbs += roots.first(); c.indexes(roots.first().id).let { BrowseState.Ready(it.first, it.second) } }
                        else BrowseState.Ready(roots, emptyList())
                    }
                    // level one is a music folder of the server (getIndexes); deeper levels are directories
                    serverCrumbs.size == 1 -> c.indexes(serverCrumbs.first().id).let { BrowseState.Ready(it.first, it.second) }
                    else -> c.directory(serverCrumbs.last().id).let { BrowseState.Ready(it.first, it.second) }
                }
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                AppLog.w("server", "Loading the server failed", e)
                BrowseState.Failed(e.message ?: "error")
            }
            remoteRaw = loaded
            remote = ordered(loaded)
        }
    }

    fun openRemote(folder: Folder) { serverCrumbs += folder; loadRemote() }

    val canGoUpRemote get() = searchQuery.isNotBlank() || serverCrumbs.size > (if (multiRoot) 0 else 1)

    fun remoteUp(): Boolean {
        if (searchQuery.isNotBlank()) { search(""); return true }
        if (serverCrumbs.size <= (if (multiRoot) 0 else 1)) return false
        serverCrumbs.removeAt(serverCrumbs.lastIndex)
        loadRemote()
        return true
    }

    fun search(query: String) { searchQuery = query; loadRemote() }

    // ---- player ----------------------------------------------------------------------------------
    var controller by mutableStateOf<MediaController?>(null); private set
    var isPlaying by mutableStateOf(false); private set
    var buffering by mutableStateOf(false); private set
    var itemTitle by mutableStateOf(""); private set
    var nowPlaying by mutableStateOf(""); private set        // ICY "Artist - Song" while a live station plays
    var artist by mutableStateOf(""); private set
    var album by mutableStateOf(""); private set
    var artwork by mutableStateOf<String?>(null); private set
    var isLive by mutableStateOf(false); private set
    var badge by mutableStateOf(""); private set
    var currentStationUrl by mutableStateOf<String?>(null); private set
    var currentTrackId by mutableStateOf<String?>(null); private set
    var hasMedia by mutableStateOf(false); private set

    // ---- lyrics (and the karaoke page that follows them) ----------------------------------------------------------------------
    private val lyricsStore = LyricsStore(app)
    var lyricsText by mutableStateOf(""); private set
    var lyricsLines by mutableStateOf<List<LyricLine>>(emptyList()); private set        // the same lyrics with times, when they have them
    var lyricsAuto by mutableStateOf(store.lyricsAuto); private set
    private val retried = HashSet<String>()
    private var lyricsFor: String? = null
    private val lyricsTried = HashSet<String>()

    fun changeLyricsAuto(on: Boolean) { lyricsAuto = on; store.lyricsAuto = on; if (on) loadLyrics() }

    private fun loadLyrics() {
        val id = currentTrackId
        lyricsFor = id
        lyricsText = id?.let { lyricsStore.get(it) }.orEmpty()
        lyricsLines = if (Lyrics.isSynced(lyricsText)) Lyrics.parse(lyricsText) else emptyList()
        if (lyricsText.isBlank() && id != null && lyricsAuto && lyricsTried.add(id) && itemTitle.isNotBlank() && artist.isNotBlank()) {
            val (title, by, disc) = Triple(itemTitle, artist, album)
            val seconds = ((controller?.mediaMetadata?.durationMs ?: controller?.duration?.takeIf { it > 0 } ?: 0L) / 1000).toInt()
            viewModelScope.launch {
                val hit = runCatching { LrcLib.exact(title, by, disc, seconds) }.getOrNull() ?: return@launch
                if (currentTrackId == id) saveLyrics(hit.text)
            }
        }
    }

    fun saveLyrics(text: String) {
        val id = currentTrackId ?: return
        lyricsStore.set(id, text)
        loadLyrics()
    }

    suspend fun findLyrics(title: String, by: String): List<LrcLib.Found> = LrcLib.search(title, by)
    /** Goes up whenever the position or the length may have changed (a seek, a new song, the length becoming known). */
    var progressVersion by mutableIntStateOf(0); private set
    var shuffle by mutableStateOf(false); private set
    var repeat by mutableStateOf(Player.REPEAT_MODE_OFF); private set

    // ---- updates from GitHub ---------------------------------------------------------------------
    var updatesAuto by mutableStateOf(store.updatesAuto); private set
    fun changeUpdatesAuto(on: Boolean) { updatesAuto = on; store.updatesAuto = on; if (on) checkForUpdate(manual = false) }

    /** The release being offered right now (the pop-up shows while this is set), or null. */
    var update by mutableStateOf<UpdateRelease?>(null); private set
    /** null: nothing going on; 0..100: downloading; -1: the file could not be fetched or did not match its checksum; -2: waiting for permission to install. */
    var updateProgress by mutableStateOf<Int?>(null); private set
    /** Result of the "Check now" key in Settings: null until asked, then "checking", "current" or "failed". */
    var updateStatus by mutableStateOf<String?>(null); private set
    private var updateJob: Job? = null

    /** Looks at GitHub. The automatic look honours "Later" (24 h) and "Skip"; the manual one from Settings always answers. */
    fun checkForUpdate(manual: Boolean) { viewModelScope.launch { lookForUpdate(manual) } }

    /** False when the look failed (the automatic loop then tries again sooner). */
    private suspend fun lookForUpdate(manual: Boolean): Boolean {
        if (updateProgress != null && updateProgress != -1 && updateProgress != -2) return true        // busy downloading
        if (manual) updateStatus = "checking"
        val release = try { Updater.latest(getApplication()) } catch (e: Exception) {
            if (e is CancellationException) throw e
            AppLog.w("update", "Could not look for updates", e)
            if (manual) updateStatus = "failed"
            return false
        }
        if (!Updater.isUpdate(release)) { if (manual) updateStatus = "current"; return true }
        release!!
        val hidden = !manual && (store.updateSkipped == release.key || (store.updateSnoozeKey == release.key && System.currentTimeMillis() < store.updateSnoozeUntil))
        if (manual) updateStatus = null
        if (!hidden && update == null) { update = release; updateProgress = null }
        return true
    }

    fun updateLater() { update?.let { store.updateSnoozeKey = it.key; store.updateSnoozeUntil = System.currentTimeMillis() + Updater.SNOOZE_MS }; dismissUpdate() }
    fun updateSkip() { update?.let { store.updateSkipped = it.key }; dismissUpdate() }
    fun dismissUpdate() { updateJob?.cancel(); update = null; updateProgress = null }

    /** Downloads the file, checks it and hands it to Android's installer. */
    fun updateNow() {
        val release = update ?: return
        updateJob?.cancel()
        if (!Updater.canInstall(getApplication())) { Updater.askPermission(getApplication()); updateProgress = -2; return }   // ask first: no point downloading before Android allows it
        updateProgress = 0
        updateJob = viewModelScope.launch {
            try {
                val file = Updater.download(getApplication(), release) { updateProgress = it }
                if (Updater.install(getApplication(), file)) dismissUpdate() else updateProgress = -2
            } catch (e: Exception) {
                if (e is CancellationException) throw e
                AppLog.w("update", "The update could not be downloaded", e)
                updateProgress = -1
            }
        }
    }

    init {
        viewModelScope.launch {                       // a few seconds after opening, then every 30 minutes for as long as the app lives
            kotlinx.coroutines.delay(6_000)
            while (true) {
                val worked = if (updatesAuto) lookForUpdate(manual = false) else true
                kotlinx.coroutines.delay(if (worked) Updater.RECHECK_MS else Updater.RETRY_MS)
            }
        }
        EqualizerHub.init(store)
        stations.addAll(store.stations)
        playlists.addAll(playlistStore.load().sortedBy { it.name.lowercase() })
        val token = SessionToken(app, ComponentName(app, PlaybackService::class.java))
        val future = MediaController.Builder(app, token).buildAsync()
        future.addListener({
            val c = runCatching { future.get() }.getOrNull() ?: return@addListener
            controller = c
            c.addListener(object : Player.Listener {
                override fun onEvents(player: Player, events: Player.Events) {
                    syncFrom(player)
                    if (events.containsAny(Player.EVENT_TIMELINE_CHANGED, Player.EVENT_POSITION_DISCONTINUITY, Player.EVENT_PLAYBACK_STATE_CHANGED,
                            Player.EVENT_MEDIA_ITEM_TRANSITION, Player.EVENT_IS_PLAYING_CHANGED, Player.EVENT_MEDIA_METADATA_CHANGED)) progressVersion++
                }
                override fun onPlayerError(error: androidx.media3.common.PlaybackException) {
                    AppLog.e("player", "Playback failed (${error.errorCodeName}) for ${c.currentMediaItem?.mediaMetadata?.title}", error)
                    val id = c.currentMediaItem?.mediaId.orEmpty()
                    if (id.startsWith("yt:")) {                      // the audio address may have expired or been refused: ask for a new one, once
                        YouTube.forget(id.removePrefix("yt:"))
                        if (retried.add(id)) { c.prepare(); return }
                        if (c.hasNextMediaItem()) { c.seekToNextMediaItem(); c.prepare() }
                    }
                }
                override fun onMediaItemTransition(mediaItem: MediaItem?, reason: Int) {
                    val next = if (c.hasNextMediaItem()) c.getMediaItemAt(c.nextMediaItemIndex).mediaId else ""
                    if (next.startsWith("yt:")) viewModelScope.launch(kotlinx.coroutines.Dispatchers.IO) { runCatching { YouTube.streamUrl(next.removePrefix("yt:")) } }   // the next song starts without a pause
                    val id = mediaItem?.mediaId
                    if (id != null && !id.startsWith("local:") && !id.startsWith("yt:") && mediaItem.mediaMetadata.extras?.getBoolean("live") != true &&
                        reason != Player.MEDIA_ITEM_TRANSITION_REASON_PLAYLIST_CHANGED) {
                        viewModelScope.launch { runCatching { client()?.scrobble(id) } }
                    }
                }
            })
            syncFrom(c)
        }, ContextCompat.getMainExecutor(app))
        if (store.server.isComplete) loadRemote()
    }

    private fun syncFrom(p: Player) {
        isPlaying = p.isPlaying
        buffering = p.playbackState == Player.STATE_BUFFERING
        hasMedia = p.mediaItemCount > 0
        shuffle = p.shuffleModeEnabled; repeat = p.repeatMode
        val item = p.currentMediaItem
        val own = item?.mediaMetadata
        isLive = own?.extras?.getBoolean("live") == true
        itemTitle = own?.title?.toString().orEmpty()
        artist = own?.artist?.toString().orEmpty()
        album = own?.albumTitle?.toString().orEmpty()
        artwork = own?.artworkUri?.toString()
        badge = own?.extras?.getString("badge").orEmpty()
        currentStationUrl = if (isLive) item?.localConfiguration?.uri?.toString() else null
        currentTrackId = if (isLive) null else item?.mediaId
        if (currentTrackId != lyricsFor) loadLyrics()
        val stream = p.mediaMetadata.title?.toString().orEmpty()     // ICY metadata replaces the title on a live stream
        nowPlaying = if (isLive && stream.isNotBlank() && stream != itemTitle) stream else ""
    }

    fun playTracks(tracks: List<Track>, start: Int) {
        val c = controller ?: return
        val api = client()
        val items = tracks.mapNotNull { trackItem(it, api) }
        if (items.isEmpty()) return
        c.setMediaItems(items, start.coerceIn(0, items.lastIndex), 0); c.prepare(); c.play()
    }

    private fun trackItem(t: Track, api: AirsonicClient?): MediaItem? {
        val address = t.uri ?: api?.streamUrl(t.id) ?: return null                    // the server URL is asked for only here
        return MediaItem.Builder().setMediaId(t.id).setUri(address)
            .setMediaMetadata(
                MediaMetadata.Builder().setTitle(t.title).setArtist(t.artist).setAlbumTitle(t.album)
                    .setDurationMs(t.durationSec.takeIf { it > 0 }?.let { it * 1000L })
                    .setArtworkUri((t.artworkUri ?: t.coverArt?.let { api?.coverUrl(it) })?.toUri())
                    .setExtras(Bundle().apply {
                        putString("badge", listOf(t.codec, if (t.bitRate > 0) "${t.bitRate} kbps" else "").filter { it.isNotBlank() }.joinToString(" "))
                    }).build()
            ).build()
    }

    fun playStation(station: Station) {
        val c = controller ?: return
        c.setMediaItem(stationItem(station)); c.prepare(); c.play()
        viewModelScope.launch { watchStation(station) }          // a station may have moved since it was saved
    }

    private fun stationItem(s: Station) = MediaItem.Builder().setMediaId("station:" + s.streamUrl).setUri(s.streamUrl)
        .setMediaMetadata(
            MediaMetadata.Builder().setTitle(s.name).setStation(s.name)
                .setArtworkUri(s.favicon.takeIf { it.isNotBlank() }?.toUri())
                .setExtras(Bundle().apply {
                    putBoolean("live", true)
                    putString("badge", (s.codec + if (s.bitrate > 0) " ${s.bitrate} kbps" else "").trim())
                }).build()
        ).build()

    private suspend fun watchStation(station: Station) {
        val c = controller ?: return
        kotlinx.coroutines.delay(9000)
        if (c.currentMediaItem?.localConfiguration?.uri?.toString() != station.streamUrl || c.isPlaying) return
        val fresh = RadioResolver.refresh(station) ?: return
        if (controller?.currentMediaItem?.localConfiguration?.uri?.toString() != station.streamUrl) return
        replaceStation(station, fresh)
        c.setMediaItem(stationItem(fresh)); c.prepare(); c.play()
    }

    fun togglePlay() {
        controller?.let {
            if (it.isPlaying) { it.pause(); return }
            if (it.playbackState == Player.STATE_IDLE) it.prepare()
            if (it.playbackState == Player.STATE_ENDED) it.seekTo(it.currentMediaItemIndex, 0)   // the song ran out: start it again
            it.play()
        }
    }
    fun stop() { controller?.let { it.stop(); it.clearMediaItems() } }
    fun next() { controller?.seekToNextMediaItem() }
    fun previous() { controller?.let { if (it.currentPosition > 3000 || !it.hasPreviousMediaItem()) it.seekTo(0) else it.seekToPreviousMediaItem() } }
    fun seekTo(fraction: Float) {
        controller?.let {
            val d = lengthOf(it)
            if (d > 0) { it.seekTo((d * fraction.coerceIn(0f, 1f)).toLong()); progressVersion++ }
        }
    }

    /** The song's length: what the player found out, or, for a server song it cannot measure (transcoded streams), what the server said. */
    private fun lengthOf(p: Player): Long = p.duration.takeIf { it != C.TIME_UNSET && it > 0 } ?: (p.mediaMetadata.durationMs ?: 0L)
    fun toggleShuffle() { controller?.let { it.shuffleModeEnabled = !it.shuffleModeEnabled } }
    fun cycleRepeat() {
        controller?.let {
            it.repeatMode = when (it.repeatMode) {
                Player.REPEAT_MODE_OFF -> Player.REPEAT_MODE_ALL
                Player.REPEAT_MODE_ALL -> Player.REPEAT_MODE_ONE
                else -> Player.REPEAT_MODE_OFF
            }
        }
    }
    fun position(): Pair<Long, Long> = controller?.let { it.currentPosition.coerceAtLeast(0L) to lengthOf(it) } ?: (0L to 0L)

    // ---- stations ---------------------------------------------------------------------------------
    fun saveStations(list: List<Station>) {
        val now = System.currentTimeMillis()
        list.forEach { s -> if (stations.none { it.streamUrl == s.streamUrl }) { stations += s.copy(added = now); store.deletedStations = store.deletedStations - s.streamUrl } }
        stations.sortBy { it.name.lowercase() }
        store.stations = stations.toList()
        requestSync()
    }

    fun removeStation(station: Station) {
        stations.remove(station); store.stations = stations.toList()
        store.deletedStations = store.deletedStations + (station.streamUrl to System.currentTimeMillis())
        requestSync()
    }

    private fun replaceStation(old: Station, fresh: Station) {
        val i = stations.indexOfFirst { it.streamUrl == old.streamUrl }
        if (i >= 0) { stations[i] = fresh; store.stations = stations.toList() }
    }

    override fun onCleared() {
        getApplication<Application>().contentResolver.unregisterContentObserver(mediaWatcher)
        controller?.release()
        super.onCleared()
    }
}
