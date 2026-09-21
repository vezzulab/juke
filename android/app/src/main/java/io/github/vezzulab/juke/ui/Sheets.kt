package io.github.vezzulab.juke.ui

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectVerticalDragGestures
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import io.github.vezzulab.juke.JukeViewModel
import io.github.vezzulab.juke.R
import io.github.vezzulab.juke.data.RadioResolver
import io.github.vezzulab.juke.data.Station
import io.github.vezzulab.juke.playback.EqualizerHub
import kotlinx.coroutines.launch

/** A panel that rises over the app. It lives in the same window, so the app never leaves full screen. */
@Composable
fun Sheet(visible: Boolean, onDismiss: () -> Unit, title: String, content: @Composable ColumnScope.() -> Unit) {
    val colors = MaterialTheme.colorScheme
    AnimatedVisibility(visible, enter = fadeIn(), exit = fadeOut()) {
        Box(
            Modifier.fillMaxSize().background(colors.scrim)
                .clickable(remember { MutableInteractionSource() }, null, onClick = onDismiss),
            contentAlignment = Alignment.BottomCenter,
        ) {
            AnimatedVisibility(visible, enter = slideInVertically { it }, exit = slideOutVertically { it }) {
                Column(
                    Modifier.fillMaxWidth().widthIn(max = 640.dp).padding(10.dp)
                        .chassis(26.dp, colors.surfaceContainer)
                        .clickable(remember { MutableInteractionSource() }, null) { }       // taps inside must not close it
                        .padding(18.dp)
                        .windowInsetsPadding(WindowInsets.ime),
                ) {
                    Row(Modifier.fillMaxWidth().padding(bottom = 14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(title, Modifier.weight(1f), style = MaterialTheme.typography.titleMedium)
                        Key(R.drawable.ic_close, stringResource(R.string.close), onDismiss, size = 40.dp, icon = 18.dp, tint = colors.onSurfaceVariant)
                    }
                    content()
                }
            }
        }
    }
}

private sealed interface Found {
    data object Idle : Found
    data object Searching : Found
    data object None : Found
    data class Some(val stations: List<Station>) : Found
}

/** Paste a stream, a playlist or a station's page. A page whose player lists several stations offers them all. */
@Composable
fun AddStationSheet(vm: JukeViewModel, visible: Boolean, onDismiss: () -> Unit) {
    val scope = rememberCoroutineScope()
    var address by rememberSaveable(visible) { mutableStateOf("") }
    var state by remember(visible) { mutableStateOf<Found>(Found.Idle) }
    val ticked = remember(visible) { mutableStateListOf<Int>() }

    fun find() {
        state = Found.Searching
        scope.launch {
            state = try {
                val list = RadioResolver.resolve(address)
                ticked.clear(); ticked.addAll(list.indices)
                Found.Some(list)
            } catch (e: Exception) {
                if (e is kotlinx.coroutines.CancellationException) throw e
                Found.None
            }
        }
    }

    Sheet(visible, onDismiss, stringResource(R.string.add_by_url)) {
        Text(stringResource(R.string.paste_address), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.height(12.dp))
        JukeField(
            address, { address = it; if (state !is Found.Searching) state = Found.Idle }, stringResource(R.string.add_by_url),
            Modifier.fillMaxWidth(), enabled = state !is Found.Searching, placeholder = "https://…",
            keyboard = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Go),
            actions = KeyboardActions(onGo = { if (address.isNotBlank()) find() }),
        )
        Spacer(Modifier.height(14.dp))
        when (val s = state) {
            Found.Searching -> Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = AccentA)
                Spacer(Modifier.width(12.dp))
                Text(stringResource(R.string.searching_signal), style = MaterialTheme.typography.bodyMedium)
            }
            Found.None -> Text(stringResource(R.string.no_signal), color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodyMedium)
            is Found.Some -> Column(Modifier.heightIn(max = 320.dp).verticalScroll(rememberScrollState())) {
                SectionLabel(if (s.stations.size == 1) stringResource(R.string.found) else stringResource(R.string.stations_found, s.stations.size))
                Spacer(Modifier.height(8.dp))
                s.stations.forEachIndexed { i, st ->
                    val on = i in ticked
                    Row(
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(14.dp)).clickable { if (on) ticked.remove(i) else ticked.add(i) }
                            .padding(vertical = 7.dp, horizontal = 4.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Box(Modifier.size(22.dp).clip(RoundedCornerShape(7.dp))
                            .background(if (on) AccentBrush else androidx.compose.ui.graphics.SolidColor(MaterialTheme.colorScheme.surfaceContainerHighest)),
                            contentAlignment = Alignment.Center) {
                            if (on) JIcon(R.drawable.ic_play, tint = MaterialTheme.colorScheme.onPrimary, size = 12.dp)
                        }
                        Spacer(Modifier.width(12.dp))
                        Art(st.favicon, live = true, modifier = Modifier.size(38.dp), corner = 10.dp, glow = false)
                        Column(Modifier.padding(start = 11.dp)) {
                            Text(st.name, maxLines = 1, overflow = TextOverflow.Ellipsis, style = MaterialTheme.typography.bodyLarge)
                            if (st.detail.isNotBlank()) Text(st.detail, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                }
            }
            Found.Idle -> {}
        }
        Spacer(Modifier.height(18.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            ActionKey(stringResource(R.string.cancel), onDismiss, accent = false)
            Spacer(Modifier.width(10.dp))
            val s = state
            if (s is Found.Some) ActionKey(stringResource(R.string.add), { vm.saveStations(ticked.sorted().map { s.stations[it] }); onDismiss() }, enabled = ticked.isNotEmpty())
            else ActionKey(stringResource(R.string.find_signal), ::find, enabled = address.isNotBlank() && s !is Found.Searching)
        }
    }
}

/** Ten bands, presets and preamp, applied to the sound that is already playing. */
@Composable
fun EqualizerSheet(visible: Boolean, onDismiss: () -> Unit) {
    Sheet(visible, onDismiss, stringResource(R.string.equalizer)) {
        val colors = MaterialTheme.colorScheme
        if (!EqualizerHub.available) {
            Text(stringResource(R.string.eq_unavailable), color = colors.error, style = MaterialTheme.typography.bodyMedium)
            Spacer(Modifier.height(12.dp))
        }
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.eq_on), Modifier.weight(1f), style = MaterialTheme.typography.bodyLarge)
            Switch(EqualizerHub.enabled, EqualizerHub::switchOn, colors = SwitchDefaults.colors(checkedThumbColor = Color(0xFF0A0C14), checkedTrackColor = AccentA))
        }
        Spacer(Modifier.height(12.dp))
        Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            EqualizerHub.PRESETS.keys.forEach { name ->
                val on = EqualizerHub.preset == name
                Text(
                    name, Modifier.clip(RoundedCornerShape(11.dp)).background(if (on) AccentSoft else androidx.compose.ui.graphics.SolidColor(colors.surfaceContainerLow))
                        .clickable { EqualizerHub.loadPreset(name) }.padding(horizontal = 13.dp, vertical = 8.dp),
                    color = if (on) colors.onSurface else colors.onSurfaceVariant, style = MaterialTheme.typography.labelLarge,
                )
            }
        }
        Spacer(Modifier.height(16.dp))
        Row(Modifier.fillMaxWidth().chassis(18.dp, colors.surfaceContainerLowest).padding(vertical = 12.dp, horizontal = 6.dp), Arrangement.SpaceEvenly) {
            EqualizerHub.BANDS_HZ.forEachIndexed { i, hz ->
                Band(if (hz >= 1000) "${hz / 1000}k" else "$hz", EqualizerHub.gains[i], EqualizerHub.enabled) { EqualizerHub.setGain(i, it) }
            }
        }
        Spacer(Modifier.height(14.dp))
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            SectionLabel(stringResource(R.string.preamp), Modifier.weight(1f))
            Text("%+.1f dB".format(EqualizerHub.preamp), style = Meter, color = colors.onSurfaceVariant)
        }
        Spacer(Modifier.height(6.dp))
        Rail(EqualizerHub.preamp, EqualizerHub.enabled) { EqualizerHub.changePreamp(it) }
        Spacer(Modifier.height(16.dp))
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
            ActionKey(stringResource(R.string.reset), { EqualizerHub.loadPreset("Flat") }, accent = false)
        }
    }
}

@Composable
private fun Band(label: String, gain: Float, enabled: Boolean, onChange: (Float) -> Unit) {
    val colors = MaterialTheme.colorScheme
    val update = rememberUpdatedState(onChange)
    Column(Modifier.width(28.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text("%+.0f".format(gain), style = Meter, color = if (gain == 0f) colors.onSurfaceVariant else AccentA)
        Canvas(
            Modifier.height(150.dp).fillMaxWidth().padding(vertical = 6.dp)
                .pointerInput(enabled) { if (enabled) detectTapGestures { update.value(level(it.y, size.height.toFloat())) } }
                .pointerInput(enabled) {
                    if (enabled) detectVerticalDragGestures { change, _ -> change.consume(); update.value(level(change.position.y, size.height.toFloat())) }
                },
        ) {
            val x = size.width / 2
            drawLine(colors.outline, Offset(x, 4.dp.toPx()), Offset(x, size.height - 4.dp.toPx()), 3.dp.toPx(), StrokeCap.Round)
            val y = (1f - (gain / EqualizerHub.MAX_DB + 1f) / 2f) * size.height
            val knob = y.coerceIn(8.dp.toPx(), size.height - 8.dp.toPx())
            if (enabled) {
                drawLine(AccentBrush, Offset(x, size.height / 2), Offset(x, knob), 3.dp.toPx(), StrokeCap.Round)
                drawCircle(AccentB, 7.dp.toPx(), Offset(x, knob))
            } else {
                drawCircle(colors.onSurfaceVariant.copy(alpha = 0.4f), 6.dp.toPx(), Offset(x, knob))
            }
        }
        Text(label, style = Meter, color = colors.onSurfaceVariant)
    }
}

private fun level(y: Float, height: Float): Float = ((1f - (y / height).coerceIn(0f, 1f)) * 2f - 1f) * EqualizerHub.MAX_DB

@Composable
private fun Rail(value: Float, enabled: Boolean, onChange: (Float) -> Unit) {
    val colors = MaterialTheme.colorScheme
    val update = rememberUpdatedState(onChange)
    Canvas(
        Modifier.fillMaxWidth().height(24.dp)
            .pointerInput(enabled) { if (enabled) detectTapGestures { update.value(across(it.x, size.width.toFloat())) } }
            .pointerInput(enabled) {
                if (enabled) detectHorizontalDragGestures { change, _ ->
                    change.consume(); update.value(across(change.position.x, size.width.toFloat()))
                }
            },
    ) {
        val y = size.height / 2
        val h = 3.dp.toPx()
        drawLine(colors.outline, Offset(0f, y), Offset(size.width, y), h, StrokeCap.Round)
        val x = ((value / EqualizerHub.MAX_DB + 1f) / 2f) * size.width
        drawLine(AccentBrush, Offset(size.width / 2, y), Offset(x, y), h, StrokeCap.Round)
        drawCircle(if (enabled) AccentB else colors.onSurfaceVariant, 7.dp.toPx(), Offset(x.coerceIn(7.dp.toPx(), size.width - 7.dp.toPx()), y))
    }
}

private fun across(x: Float, width: Float): Float = ((x / width).coerceIn(0f, 1f) * 2f - 1f) * EqualizerHub.MAX_DB
