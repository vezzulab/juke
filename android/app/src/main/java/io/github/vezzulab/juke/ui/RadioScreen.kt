package io.github.vezzulab.juke.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.vezzulab.juke.JukeViewModel
import io.github.vezzulab.juke.R
import io.github.vezzulab.juke.data.RadioBrowser
import io.github.vezzulab.juke.data.Station
import kotlinx.coroutines.delay

@Composable
fun RadioScreen(vm: JukeViewModel, onAddStation: () -> Unit) {
    var tab by rememberSaveable { mutableStateOf("mine") }
    Column(Modifier.fillMaxSize().padding(horizontal = 10.dp)) {
        Crumb(stringResource(R.string.nav_radio), "", canGoUp = false, onUp = {}) {
            Key(R.drawable.ic_plus, stringResource(R.string.add_by_url), onAddStation, size = 46.dp, icon = 22.dp, tint = AccentA, filled = true)
        }
        Segmented(
            listOf("mine" to stringResource(R.string.my_stations), "explore" to stringResource(R.string.explore)),
            tab, { tab = it }, Modifier.fillMaxWidth().padding(bottom = 10.dp),
        )
        if (tab == "mine") MyStations(vm, onAddStation) else Explore(vm)
    }
}

@Composable
private fun MyStations(vm: JukeViewModel, onAdd: () -> Unit) {
    if (vm.stations.isEmpty()) {
        EmptyState(R.drawable.ic_radio, stringResource(R.string.no_stations), stringResource(R.string.no_stations_hint)) {
            ActionKey(stringResource(R.string.add_station), onAdd, icon = R.drawable.ic_plus)
        }
        return
    }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
        items(vm.stations, key = { it.streamUrl }) { station ->
            StationRow(vm, station) {
                Key(R.drawable.ic_trash, stringResource(R.string.remove), { vm.removeStation(station) }, size = 44.dp, icon = 19.dp,
                    tint = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}

/** The station on the air offers Stop where the others offer Play. */
@Composable
fun StationRow(vm: JukeViewModel, station: Station, trailing: @Composable () -> Unit) {
    val colors = MaterialTheme.colorScheme
    val current = vm.currentStationUrl == station.streamUrl
    val onAir = current && (vm.isPlaying || vm.buffering)
    Row(
        Modifier.fillMaxWidth().heightIn(min = 70.dp).clip(RoundedCornerShape(16.dp))
            .background(if (current) colors.surfaceContainerHigh else Color.Transparent)
            .clickable { if (onAir) vm.stop() else vm.playStation(station) }.padding(horizontal = 10.dp, vertical = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Art(station.favicon, live = true, modifier = Modifier.size(50.dp), corner = 12.dp, glow = false)
        Column(Modifier.weight(1f).padding(horizontal = 13.dp)) {
            Text(station.name, style = MaterialTheme.typography.bodyLarge, color = if (current) AccentA else colors.onSurface, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val sub = if (current && vm.nowPlaying.isNotBlank()) vm.nowPlaying else station.detail
            if (sub.isNotBlank()) Text(sub, style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
        Key(if (onAir) R.drawable.ic_stop else R.drawable.ic_play, stringResource(if (onAir) R.string.stop else R.string.play),
            { if (onAir) vm.stop() else vm.playStation(station) }, size = 46.dp, icon = if (onAir) 19.dp else 22.dp, tint = AccentA, filled = true)
        Spacer(Modifier.width(4.dp))
        trailing()
    }
}

private val Genres = listOf("pop", "rock", "jazz", "blues", "country", "electronic", "classical", "oldies", "news")

@Composable
private fun Explore(vm: JukeViewModel) {
    var query by rememberSaveable { mutableStateOf("") }
    var tag by rememberSaveable { mutableStateOf("") }
    var results by remember { mutableStateOf<List<Station>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var failed by remember { mutableStateOf(false) }
    var reload by remember { mutableIntStateOf(0) }
    LaunchedEffect(query, tag, reload) {
        loading = true; failed = false
        delay(350)                                              // let typing settle before asking the directory
        try { results = RadioBrowser.search(query, tag) } catch (e: Exception) {
            if (e is kotlinx.coroutines.CancellationException) throw e
            failed = true
        }
        loading = false
    }
    Column(Modifier.fillMaxSize()) {
        JukeField(query, { query = it }, stringResource(R.string.search_stations), Modifier.fillMaxWidth().padding(bottom = 10.dp),
            keyboard = KeyboardOptions(imeAction = ImeAction.Search), actions = KeyboardActions(),
            leading = { JIcon(R.drawable.ic_search, tint = MaterialTheme.colorScheme.onSurfaceVariant, size = 19.dp) })
        Row(Modifier.horizontalScroll(rememberScrollState()).padding(bottom = 10.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Genres.forEach { g -> Chip(g.replaceFirstChar { it.uppercase() }, tag == g) { tag = if (tag == g) "" else g } }
        }
        when {
            loading -> Box(Modifier.fillMaxSize(), Alignment.Center) { CircularProgressIndicator(color = AccentA) }
            failed -> EmptyState(R.drawable.ic_globe, stringResource(R.string.directory_error), "") {
                ActionKey(stringResource(R.string.retry), { reload++ }, icon = R.drawable.ic_refresh)
            }
            else -> LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
                items(results, key = { it.streamUrl }) { station ->
                    val saved = vm.stations.any { it.streamUrl == station.streamUrl }
                    StationRow(vm, station) {
                        Key(if (saved) R.drawable.ic_heart else R.drawable.ic_heart_outline, stringResource(R.string.add_station),
                            { if (!saved) vm.saveStations(listOf(station)) }, size = 44.dp, icon = 20.dp,
                            tint = if (saved) AccentB else MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
            }
        }
    }
}

@Composable
private fun Chip(text: String, on: Boolean, onClick: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    Text(
        text,
        Modifier.clip(RoundedCornerShape(11.dp))
            .then(if (on) Modifier.background(AccentSoft) else Modifier.background(colors.surfaceContainerLow))
            .then(if (on) Modifier.androidBorder(AccentA.copy(alpha = 0.55f)) else Modifier.androidBorder(colors.outline))
            .clickable(onClick = onClick).padding(horizontal = 14.dp, vertical = 9.dp),
        color = if (on) colors.onSurface else colors.onSurfaceVariant, style = MaterialTheme.typography.labelLarge,
    )
}

private fun Modifier.androidBorder(color: Color) = this.border(1.dp, color, RoundedCornerShape(11.dp))
