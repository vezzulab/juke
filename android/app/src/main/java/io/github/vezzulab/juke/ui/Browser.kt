package io.github.vezzulab.juke.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.vezzulab.juke.BrowseState
import io.github.vezzulab.juke.JukeViewModel
import io.github.vezzulab.juke.R
import io.github.vezzulab.juke.data.Folder
import io.github.vezzulab.juke.data.SortOrder
import io.github.vezzulab.juke.data.Track

/** The title strip every screen wears: back key, where you are, and what is in there. */
@Composable
fun Crumb(title: String, subtitle: String, canGoUp: Boolean, onUp: () -> Unit, modifier: Modifier = Modifier, trailing: (@Composable RowScope.() -> Unit)? = null) {
    Row(modifier.fillMaxWidth().padding(start = 4.dp, end = 4.dp, top = 6.dp, bottom = 10.dp), verticalAlignment = Alignment.CenterVertically) {
        if (canGoUp) Key(R.drawable.ic_chevron, stringResource(R.string.back), onUp, size = 44.dp, icon = 20.dp,
            tint = MaterialTheme.colorScheme.onSurfaceVariant, rotation = 180f)
        Column(Modifier.weight(1f).padding(start = if (canGoUp) 2.dp else 12.dp)) {
            Text(title, style = MaterialTheme.typography.titleLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
            if (subtitle.isNotBlank()) SectionLabel(subtitle, Modifier.padding(top = 3.dp))
        }
        trailing?.invoke(this)
    }
}

/** "Sort": the original order, A to Z or Z to A. Shared by the card and the server. */
@Composable
fun SortKey(vm: JukeViewModel) {
    var open by remember { mutableStateOf(false) }
    val active = vm.sortOrder != SortOrder.Original
    Box {
        Key(R.drawable.ic_sort, stringResource(R.string.sort), { open = true }, size = 44.dp, icon = 20.dp,
            tint = if (active) AccentA else MaterialTheme.colorScheme.onSurfaceVariant)
        DropdownMenu(open, { open = false }) {
            listOf(SortOrder.Original to R.string.sort_original, SortOrder.AZ to R.string.sort_az, SortOrder.ZA to R.string.sort_za).forEach { (order, label) ->
                DropdownMenuItem(
                    text = { Text(stringResource(label), color = if (vm.sortOrder == order) AccentA else MaterialTheme.colorScheme.onSurface) },
                    onClick = { vm.setSort(order); open = false },
                )
            }
        }
    }
}

/** Folders and songs, used for the card and for the server alike. */
@Composable
fun BrowseList(
    state: BrowseState, vm: JukeViewModel, onOpen: (Folder) -> Unit, onRetry: () -> Unit,
    modifier: Modifier = Modifier, folderName: @Composable (Folder) -> String = { it.name }, empty: @Composable () -> Unit,
) {
    when (state) {
        BrowseState.Idle -> empty()
        BrowseState.Loading -> Box(modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator(color = MaterialTheme.colorScheme.primary) }
        is BrowseState.Failed -> EmptyState(R.drawable.ic_refresh, stringResource(R.string.error_generic), state.message) {
            ActionKey(stringResource(R.string.retry), onRetry, icon = R.drawable.ic_refresh)
        }
        is BrowseState.Ready ->
            if (state.folders.isEmpty() && state.tracks.isEmpty()) empty()
            else {
                val labels = state.folders.map { folderName(it) }         // names are read from resources, outside the list
                LazyColumn(modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
                itemsIndexed(state.folders, key = { _, f -> "f" + f.id }) { i, folder -> FolderRow(labels[i]) { onOpen(folder) } }
                itemsIndexed(state.tracks, key = { _, t -> "t" + t.id }) { index, track ->
                    TrackRow(track, index + 1, vm.currentTrackId == track.id, vm.isPlaying) { vm.playTracks(state.tracks, index) }
                }
                }
            }
    }
}

@Composable
private fun FolderRow(name: String, onOpen: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    Row(
        Modifier.fillMaxWidth().heightIn(min = 62.dp).clip(RoundedCornerShape(16.dp)).clickable(onClick = onOpen).padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(46.dp).chassis(14.dp, colors.surfaceContainerHigh), contentAlignment = Alignment.Center) {
            JIcon(R.drawable.ic_folder, tint = AccentA, size = 21.dp)
        }
        Text(name, Modifier.weight(1f).padding(horizontal = 14.dp), style = MaterialTheme.typography.bodyLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
        JIcon(R.drawable.ic_chevron, tint = colors.onSurfaceVariant.copy(alpha = 0.7f), size = 18.dp)
    }
}

@Composable
fun TrackRow(track: Track, number: Int, current: Boolean, playing: Boolean, onPlay: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    Row(
        Modifier.fillMaxWidth().heightIn(min = 62.dp).clip(RoundedCornerShape(16.dp))
            .background(if (current) colors.surfaceContainerHigh else Color.Transparent)
            .clickable(onClick = onPlay).padding(horizontal = 10.dp, vertical = 5.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.size(46.dp), contentAlignment = Alignment.Center) {
            if (current) LevelMeter(playing, Modifier.width(26.dp), bars = 4)
            else Text("%02d".format(number), style = Meter, color = colors.onSurfaceVariant.copy(alpha = 0.7f))
        }
        Column(Modifier.weight(1f).padding(horizontal = 14.dp)) {
            Text(track.title, style = MaterialTheme.typography.bodyLarge, color = if (current) AccentA else colors.onSurface, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val sub = listOf(track.artist, track.album).filter { it.isNotBlank() }.joinToString(" · ")
            if (sub.isNotBlank()) Text(sub, style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        if (track.durationSec > 0) Text(formatTime(track.durationSec * 1000L), style = Meter, color = colors.onSurfaceVariant)
    }
}

/** The card (or the phone's own storage): music browsed exactly as the folders sit on it. */
@Composable
fun CardScreen(vm: JukeViewModel, onGrant: () -> Unit) {
    val here = vm.localCrumbs.lastOrNull()
    val ready = vm.local as? BrowseState.Ready
    Column(Modifier.fillMaxSize().padding(horizontal = 10.dp)) {
        Crumb(
            title = here?.let { volumeName(it) } ?: stringResource(R.string.nav_library),
            subtitle = ready?.tracks?.size?.takeIf { it > 0 }?.let { stringResource(R.string.tracks, it) }.orEmpty(),
            canGoUp = vm.canGoUpLocal, onUp = { vm.localUp() },
        ) {
            SortKey(vm)
            if ((ready?.tracks?.size ?: 0) > 0 || (here != null && (ready?.folders?.isNotEmpty() == true)))
                ActionKey(stringResource(R.string.queue_songs), vm::playFolder, icon = R.drawable.ic_play)
        }
        BrowseList(vm.local, vm, onOpen = vm::openLocal, onRetry = vm::scanLocal, folderName = { volumeName(it) }) {
            if (!vm.hasAudioPermission) EmptyState(R.drawable.ic_folder, stringResource(R.string.no_access), stringResource(R.string.no_access_hint)) {
                ActionKey(stringResource(R.string.grant), onGrant)
            } else EmptyState(R.drawable.ic_note, stringResource(R.string.no_music), stringResource(R.string.no_music_hint)) {
                ActionKey(stringResource(R.string.retry), vm::scanLocal, icon = R.drawable.ic_refresh, accent = false)
            }
        }
    }
}

/** A volume root carries a marker instead of a name, so it can be said in the reader's language. */
@Composable
private fun volumeName(folder: Folder): String = when (folder.name) {
    "sd" -> stringResource(R.string.storage_sd)
    "internal" -> stringResource(R.string.storage_internal)
    else -> folder.name
}
