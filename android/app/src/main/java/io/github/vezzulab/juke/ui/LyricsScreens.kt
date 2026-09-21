package io.github.vezzulab.juke.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import io.github.vezzulab.juke.JukeViewModel
import io.github.vezzulab.juke.R
import io.github.vezzulab.juke.data.LrcLib
import io.github.vezzulab.juke.data.Lyrics
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

/** The song's position, read again whenever it may have jumped and, while sound plays, every [everyMs] milliseconds. */
@Composable
private fun rememberPosition(vm: JukeViewModel, everyMs: Long = 150): MutableLongState {
    val position = remember { mutableLongStateOf(0L) }
    val owner = LocalLifecycleOwner.current
    LaunchedEffect(vm.isPlaying, vm.currentTrackId, vm.progressVersion) {
        position.longValue = vm.position().first
        if (!vm.isPlaying) return@LaunchedEffect
        owner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) { while (true) { delay(everyMs); position.longValue = vm.position().first } }
    }
    return position
}

/** The words themselves: following the song line by line when they are synced, plain and scrollable when not, an invitation when there are none. */
@Composable
fun LyricsBody(vm: JukeViewModel, onAdd: () -> Unit, onFind: () -> Unit, modifier: Modifier = Modifier) {
    val colors = MaterialTheme.colorScheme
    if (vm.lyricsText.isBlank()) {
        EmptyState(R.drawable.ic_lyrics, stringResource(R.string.lyrics_none), stringResource(R.string.lyrics_none_hint), modifier) {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                ActionKey(stringResource(R.string.lyrics_find), onFind, icon = R.drawable.ic_search)
                ActionKey(stringResource(R.string.lyrics_add), onAdd, icon = R.drawable.ic_edit, accent = false)
            }
        }
        return
    }
    val lines = vm.lyricsLines
    if (lines.isEmpty()) {
        Text(Lyrics.plain(vm.lyricsText), modifier.verticalScroll(rememberScrollState()).padding(horizontal = 22.dp, vertical = 24.dp),
            style = MaterialTheme.typography.bodyLarge.copy(fontSize = 18.sp, lineHeight = 28.sp), color = colors.onSurface, textAlign = TextAlign.Center)
        return
    }
    val position = rememberPosition(vm)
    val index = Lyrics.lineAt(lines, position.longValue)
    val list = rememberLazyListState()
    LaunchedEffect(index) { if (index >= 0) list.animateScrollToItem((index - 2).coerceAtLeast(0)) }
    LazyColumn(modifier, state = list, contentPadding = PaddingValues(vertical = 60.dp, horizontal = 22.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        itemsIndexed(lines) { i, line ->
            val current = i == index
            Text(line.text.ifBlank { "♪" }, Modifier.padding(vertical = 8.dp), textAlign = TextAlign.Center,
                style = TextStyle(fontSize = if (current) 24.sp else 19.sp, lineHeight = if (current) 32.sp else 26.sp, fontWeight = if (current) FontWeight.Bold else FontWeight.Medium),
                color = if (current) AccentA else colors.onSurfaceVariant.copy(alpha = if (i < index) 0.55f else 0.85f))
        }
    }
}

/** The lyrics page: read them, add or paste them, find them by the song's name, or go to karaoke. */
@Composable
fun LyricsScreen(vm: JukeViewModel, onClose: () -> Unit, onKaraoke: () -> Unit) {
    var mode by rememberSaveable { mutableStateOf("view") }          // view | edit | find
    BackHandler(enabled = mode != "view") { mode = "view" }
    when (mode) {
        "edit" -> LyricsEditor(vm) { mode = "view" }
        "find" -> LyricsFinder(vm) { mode = "view" }
        else -> Column(Modifier.fillMaxSize().padding(horizontal = 10.dp)) {
            Crumb(stringResource(R.string.lyrics), vm.itemTitle, canGoUp = true, onUp = onClose) {
                Key(R.drawable.ic_search, stringResource(R.string.lyrics_find), { mode = "find" }, size = 44.dp, icon = 20.dp, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                Key(R.drawable.ic_edit, stringResource(R.string.lyrics_edit), { mode = "edit" }, size = 44.dp, icon = 20.dp, tint = MaterialTheme.colorScheme.onSurfaceVariant)
                Key(R.drawable.ic_mic, stringResource(R.string.karaoke), onKaraoke, size = 44.dp, icon = 20.dp, tint = AccentA)
            }
            LyricsBody(vm, { mode = "edit" }, { mode = "find" }, Modifier.weight(1f).fillMaxWidth())
        }
    }
}

@Composable
private fun LyricsEditor(vm: JukeViewModel, onDone: () -> Unit) {
    var text by rememberSaveable(vm.currentTrackId) { mutableStateOf(vm.lyricsText) }
    Column(Modifier.fillMaxSize().padding(horizontal = 10.dp)) {
        Crumb(stringResource(R.string.lyrics_add), vm.itemTitle, canGoUp = true, onUp = onDone)
        Text(stringResource(R.string.lyrics_edit_hint), Modifier.padding(horizontal = 6.dp, vertical = 4.dp), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
        JukeField(text, { text = it }, stringResource(R.string.lyrics), Modifier.weight(1f).fillMaxWidth().padding(vertical = 8.dp),
            placeholder = stringResource(R.string.lyrics_placeholder), singleLine = false, minLines = 8)
        Row(Modifier.fillMaxWidth().padding(bottom = 14.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            ActionKey(stringResource(R.string.cancel), onDone, Modifier.weight(1f), accent = false)
            ActionKey(stringResource(R.string.lyrics_save), { vm.saveLyrics(text); onDone() }, Modifier.weight(1f), icon = R.drawable.ic_play)
        }
    }
}

@Composable
private fun LyricsFinder(vm: JukeViewModel, onDone: () -> Unit) {
    val scope = rememberCoroutineScope()
    var title by rememberSaveable { mutableStateOf(vm.itemTitle) }
    var by by rememberSaveable { mutableStateOf(vm.artist) }
    var results by remember { mutableStateOf<List<LrcLib.Found>?>(null) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var picked by remember { mutableIntStateOf(-1) }
    fun search() {
        if (title.isBlank() || busy) return
        scope.launch {
            busy = true; error = null; picked = -1
            results = try { vm.findLyrics(title.trim(), by.trim()) } catch (e: Exception) { error = e.message ?: "error"; null }
            busy = false
        }
    }
    LaunchedEffect(Unit) { if (results == null && title.isNotBlank()) search() }
    val colors = MaterialTheme.colorScheme
    Column(Modifier.fillMaxSize().padding(horizontal = 10.dp)) {
        Crumb(stringResource(R.string.lyrics_find), "LRCLIB", canGoUp = true, onUp = onDone)
        Text(stringResource(R.string.lyrics_find_hint), Modifier.padding(horizontal = 6.dp), color = colors.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
        Spacer(Modifier.height(8.dp))
        JukeField(title, { title = it }, stringResource(R.string.lyrics_song), Modifier.fillMaxWidth())
        Spacer(Modifier.height(8.dp))
        JukeField(by, { by = it }, stringResource(R.string.lyrics_artist), Modifier.fillMaxWidth())
        Spacer(Modifier.height(10.dp))
        ActionKey(stringResource(if (busy) R.string.lyrics_searching else R.string.lyrics_search), ::search, Modifier.fillMaxWidth(), icon = R.drawable.ic_search, enabled = !busy && title.isNotBlank())
        Spacer(Modifier.height(8.dp))
        val found = results
        when {
            error != null -> Text(stringResource(R.string.lyrics_failed, error.orEmpty()), Modifier.padding(6.dp), color = colors.error)
            found != null && found.isEmpty() -> Text(stringResource(R.string.lyrics_no_results), Modifier.padding(6.dp), color = colors.onSurfaceVariant)
        }
        LazyColumn(Modifier.weight(1f).fillMaxWidth()) {
            itemsIndexed(found.orEmpty()) { i, f ->
                Column(Modifier.fillMaxWidth().clip(MaterialTheme.shapes.medium).clickable { picked = i }
                    .background(if (picked == i) colors.primaryContainer else colors.surface).padding(horizontal = 12.dp, vertical = 10.dp)) {
                    Text(f.title, maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.titleMedium)
                    val minutes = f.duration.toInt() / 60; val seconds = f.duration.toInt() % 60
                    Text(listOf(f.artist, f.album, "%d:%02d".format(minutes, seconds), if (f.isSynced) stringResource(R.string.lyrics_synced) else "").filter { it.isNotBlank() }.joinToString(" · "),
                        maxLines = 1, overflow = TextOverflow.Ellipsis, color = if (f.isSynced) AccentA else colors.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                    if (picked == i) Text(Lyrics.plain(f.text).lines().take(8).joinToString("\n"), Modifier.padding(top = 8.dp), color = colors.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
                }
            }
        }
        val chosen = found?.getOrNull(picked)
        ActionKey(stringResource(R.string.lyrics_use), { chosen?.let { vm.saveLyrics(it.text); onDone() } }, Modifier.fillMaxWidth().padding(vertical = 10.dp), enabled = chosen != null)
    }
}

/** Karaoke: big lines that follow the song, with a countdown into each phrase. The sound is never touched. */
@Composable
fun KaraokeScreen(vm: JukeViewModel, onClose: () -> Unit, onLyrics: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    val lines = vm.lyricsLines
    val position = rememberPosition(vm, 60)
    val pos = position.longValue
    val index = Lyrics.lineAt(lines, pos)
    Column(Modifier.fillMaxSize().background(colors.background).padding(horizontal = 16.dp, vertical = 8.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Key(R.drawable.ic_chevron, stringResource(R.string.back), onClose, size = 44.dp, icon = 20.dp, rotation = 90f, tint = colors.onSurfaceVariant)
            Column(Modifier.weight(1f).padding(start = 6.dp)) {
                Text(vm.itemTitle, maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.titleMedium)
                Text(vm.artist, maxLines = 1, overflow = TextOverflow.Ellipsis, color = colors.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
            }
        }
        Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
            when {
                vm.lyricsText.isBlank() -> LyricsBody(vm, onLyrics, onLyrics)
                lines.isEmpty() -> Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
                    Text(stringResource(R.string.karaoke_no_times), textAlign = TextAlign.Center, color = colors.onSurfaceVariant, modifier = Modifier.padding(24.dp))
                    ActionKey(stringResource(R.string.lyrics_find), onLyrics, icon = R.drawable.ic_search)
                }
                else -> Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    val count = Lyrics.countdown(lines, index, pos)
                    Row(Modifier.height(20.dp), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                        if (count > 0) repeat(3) { i -> Box(Modifier.size(14.dp).clip(CircleShape).background(if (i < count) AccentA else colors.outline)) }
                    }
                    lines.getOrNull(index - 1)?.let { KaraokeLine(it.text, 20.sp, 0.45f) }
                    val fraction = Lyrics.sweep(lines, index, pos)
                    val current = lines.getOrNull(index)
                    if (current != null) {
                        val dim = colors.onSurfaceVariant
                        val edge = (fraction + 0.002f).coerceAtMost(1f)
                        Text(current.text.ifBlank { "♪" }, Modifier.fillMaxWidth().padding(vertical = 6.dp),
                            style = TextStyle(fontSize = 34.sp, lineHeight = 42.sp, fontWeight = FontWeight.Bold, textAlign = TextAlign.Center,
                                brush = Brush.horizontalGradient(0f to AccentA, fraction to AccentA, edge to dim, 1f to dim)))
                    } else Spacer(Modifier.height(48.dp))
                    lines.getOrNull(index + 1)?.let { KaraokeLine(it.text, 24.sp, 0.85f) }
                    lines.getOrNull(index + 2)?.let { KaraokeLine(it.text, 20.sp, 0.5f) }
                }
            }
        }
        Column(Modifier.fillMaxWidth().padding(bottom = 8.dp)) {
            Seek(vm)
            Spacer(Modifier.height(6.dp))
            Transport(vm)
        }
    }
}

@Composable
private fun KaraokeLine(text: String, size: androidx.compose.ui.unit.TextUnit, alpha: Float) {
    Text(text.ifBlank { "♪" }, Modifier.fillMaxWidth(), textAlign = TextAlign.Center, maxLines = 2, overflow = TextOverflow.Ellipsis,
        style = TextStyle(fontSize = size, lineHeight = size * 1.25f, fontWeight = FontWeight.Medium), color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = alpha))
}
