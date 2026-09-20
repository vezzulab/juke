package io.github.vezzulab.juke.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import io.github.vezzulab.juke.JukeViewModel
import io.github.vezzulab.juke.R

private enum class Dest(val label: Int, val icon: Int) {
    Card(R.string.nav_library, R.drawable.ic_folder),
    Server(R.string.nav_server, R.drawable.ic_server),
    Radio(R.string.nav_radio, R.drawable.ic_radio),
    Settings(R.string.nav_settings, R.drawable.ic_gear),
}

/**
 * One body, every screen size: a phone gets the keys along the bottom, a tablet a side rail, and a wide
 * tablet keeps the player open beside the list. Nothing is cut off because the app owns the whole screen.
 */
@Composable
fun JukeRoot(vm: JukeViewModel, onLanguage: (String) -> Unit, onGrantAudio: () -> Unit) {
    var dest by rememberSaveable { mutableStateOf(Dest.Card) }
    var showPlayer by rememberSaveable { mutableStateOf(false) }
    var showEq by rememberSaveable { mutableStateOf(false) }
    var showAdd by rememberSaveable { mutableStateOf(false) }
    val colors = MaterialTheme.colorScheme

    BackHandler(enabled = showAdd) { showAdd = false }
    BackHandler(enabled = showEq && !showAdd) { showEq = false }
    BackHandler(enabled = showPlayer && !showEq && !showAdd) { showPlayer = false }
    BackHandler(enabled = !showPlayer && !showEq && !showAdd && dest == Dest.Card && vm.canGoUpLocal) { vm.localUp() }
    BackHandler(enabled = !showPlayer && !showEq && !showAdd && dest == Dest.Server && vm.canGoUpRemote) { vm.remoteUp() }

    var opening by rememberSaveable { mutableStateOf(true) }
    BoxWithConstraints(Modifier.fillMaxSize().background(colors.background)) {
        val rail = maxWidth >= 620.dp
        val wide = maxWidth >= 980.dp
        Row(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)) {
            if (rail) Rail(dest) { dest = it }
            Column(Modifier.weight(1f).fillMaxHeight()) {
                Box(Modifier.weight(1f).fillMaxWidth()) {
                    when (dest) {
                        Dest.Card -> CardScreen(vm, onGrantAudio)
                        Dest.Server -> ServerScreen(vm)
                        Dest.Radio -> RadioScreen(vm) { showAdd = true }
                        Dest.Settings -> SettingsScreen(vm, onLanguage, onEqualizer = { showEq = true }, onRescan = vm::scanLocal)
                    }
                }
                if (!wide) MiniPlayer(vm, onOpen = { showPlayer = true })
                if (!rail) Bar(dest) { dest = it }
            }
            if (wide) {
                Box(Modifier.width(420.dp).fillMaxHeight().padding(10.dp).chassis(26.dp, colors.surfaceContainerLow)) {
                    NowPlaying(vm, onEqualizer = { showEq = true })
                }
            }
        }
        AnimatedVisibility(showPlayer && !wide, enter = slideInVertically { it }, exit = slideOutVertically { it }) {
            Box(Modifier.fillMaxSize().background(colors.background).windowInsetsPadding(WindowInsets.safeDrawing)) {
                NowPlaying(vm, onEqualizer = { showEq = true }, onClose = { showPlayer = false })
            }
        }
        AddStationSheet(vm, showAdd) { showAdd = false }
        EqualizerSheet(showEq) { showEq = false }
        androidx.compose.animation.AnimatedVisibility(opening, exit = androidx.compose.animation.fadeOut()) { Splash { opening = false } }
    }
}

@Composable
private fun Rail(dest: Dest, onSelect: (Dest) -> Unit) {
    val colors = MaterialTheme.colorScheme
    Column(
        Modifier.width(104.dp).fillMaxHeight().padding(8.dp).chassis(24.dp, colors.surfaceContainerLow).padding(vertical = 14.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        JIcon(R.drawable.ic_album, tint = AccentA, size = 22.dp)
        Text("JUKE", Modifier.padding(top = 6.dp), style = MaterialTheme.typography.labelSmall, color = colors.onSurfaceVariant)
        Spacer(Modifier.weight(1f))
        Dest.entries.forEach { d -> NavKey(d, d == dest, Modifier.padding(vertical = 6.dp)) { onSelect(d) } }
        Spacer(Modifier.weight(1f))
    }
}

@Composable
private fun Bar(dest: Dest, onSelect: (Dest) -> Unit) {
    val colors = MaterialTheme.colorScheme
    Row(
        Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 8.dp).chassis(22.dp, colors.surfaceContainerLow).padding(vertical = 6.dp),
        horizontalArrangement = Arrangement.SpaceEvenly, verticalAlignment = Alignment.CenterVertically,
    ) { Dest.entries.forEach { d -> NavKey(d, d == dest) { onSelect(d) } } }
}

@Composable
private fun NavKey(dest: Dest, on: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    Column(
        modifier.clip(RoundedCornerShape(16.dp))
            .then(if (on) Modifier.background(AccentSoft) else Modifier)
            .clickable(remember { MutableInteractionSource() }, null, onClick = onClick)
            .padding(horizontal = 12.dp, vertical = 9.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        JIcon(dest.icon, tint = if (on) AccentA else colors.onSurfaceVariant, size = 22.dp)
        Text(stringResource(dest.label), Modifier.padding(top = 5.dp), color = if (on) colors.onSurface else colors.onSurfaceVariant,
            style = MaterialTheme.typography.labelSmall, maxLines = 1)
    }
}
