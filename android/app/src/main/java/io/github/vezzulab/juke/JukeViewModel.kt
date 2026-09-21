package io.github.vezzulab.juke

import android.app.Application
import android.content.ComponentName
import android.os.Bundle
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
import io.github.vezzulab.juke.playback.KaraokeHub
import io.github.vezzulab.juke.ui.Accents
import io.github.vezzulab.juke.playback.PlaybackService
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

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

    // ---- lyrics and karaoke ----------------------------------------------------------------------
    private val lyricsStore = LyricsStore(app)
    var lyricsText by mutableStateOf(""); private set
    var lyricsLines by mutableStateOf<List<LyricLine>>(emptyList()); private set        // the same lyrics with times, when they have them
    var lyricsAuto by mutableStateOf(store.lyricsAuto); private set
    var voiceReduction by mutableStateOf(store.voiceReduction.also { KaraokeHub.voiceReduction = it }); private set
    private var lyricsFor: String? = null
    private val lyricsTried = HashSet<String>()

    fun changeLyricsAuto(on: Boolean) { lyricsAuto = on; store.lyricsAuto = on; if (on) loadLyrics() }
    fun changeVoiceReduction(on: Boolean) { voiceReduction = on; store.voiceReduction = on; KaraokeHub.voiceReduction = on }

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

    init {
        EqualizerHub.init(store)
        stations.addAll(store.stations)
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
                }
                override fun onMediaItemTransition(mediaItem: MediaItem?, reason: Int) {
                    val id = mediaItem?.mediaId
                    if (id != null && !id.startsWith("local:") && mediaItem.mediaMetadata.extras?.getBoolean("live") != true &&
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
        val items = tracks.mapNotNull { t ->
            val address = t.uri ?: api?.streamUrl(t.id) ?: return@mapNotNull null     // the server URL is asked for only here
            MediaItem.Builder().setMediaId(t.id).setUri(address)
                .setMediaMetadata(
                    MediaMetadata.Builder().setTitle(t.title).setArtist(t.artist).setAlbumTitle(t.album)
                        .setDurationMs(t.durationSec.takeIf { it > 0 }?.let { it * 1000L })
                        .setArtworkUri((t.artworkUri ?: t.coverArt?.let { api?.coverUrl(it) })?.toUri())
                        .setExtras(Bundle().apply {
                            putString("badge", listOf(t.codec, if (t.bitRate > 0) "${t.bitRate} kbps" else "").filter { it.isNotBlank() }.joinToString(" "))
                        }).build()
                ).build()
        }
        if (items.isEmpty()) return
        c.setMediaItems(items, start.coerceIn(0, items.lastIndex), 0); c.prepare(); c.play()
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
        list.forEach { s -> if (stations.none { it.streamUrl == s.streamUrl }) stations += s }
        stations.sortBy { it.name.lowercase() }
        store.stations = stations.toList()
    }

    fun removeStation(station: Station) { stations.remove(station); store.stations = stations.toList() }

    private fun replaceStation(old: Station, fresh: Station) {
        val i = stations.indexOfFirst { it.streamUrl == old.streamUrl }
        if (i >= 0) { stations[i] = fresh; store.stations = stations.toList() }
    }

    override fun onCleared() { controller?.release(); super.onCleared() }
}
