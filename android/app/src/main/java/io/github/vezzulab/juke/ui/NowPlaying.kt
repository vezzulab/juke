package io.github.vezzulab.juke.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.repeatOnLifecycle
import androidx.media3.common.Player
import io.github.vezzulab.juke.JukeViewModel
import io.github.vezzulab.juke.R
import kotlinx.coroutines.delay

/** The player face: art, readout, transport. Portrait stacks it, landscape and tablets set it side by side. */
@Composable
fun NowPlaying(vm: JukeViewModel, onEqualizer: () -> Unit, modifier: Modifier = Modifier, onClose: (() -> Unit)? = null,
               onLyrics: () -> Unit = {}, onKaraoke: () -> Unit = {}) {
    if (!vm.hasMedia) {
        Box(modifier.fillMaxSize()) {
            if (onClose != null) Key(R.drawable.ic_chevron, stringResource(R.string.back), onClose, Modifier.align(Alignment.TopStart).padding(6.dp), rotation = 90f,
                tint = MaterialTheme.colorScheme.onSurfaceVariant)
            EmptyState(R.drawable.ic_album, stringResource(R.string.nothing_playing), stringResource(R.string.nothing_playing_hint))
        }
        return
    }
    BoxWithConstraints(modifier.fillMaxSize().padding(horizontal = 18.dp, vertical = 8.dp)) {
        val wide = maxWidth > maxHeight * 1.05f && maxWidth >= 620.dp
        if (wide) {
            Row(Modifier.fillMaxSize(), Arrangement.spacedBy(28.dp), Alignment.CenterVertically) {
                Art(vm.artwork, vm.isLive, Modifier.weight(1f).aspectRatio(1f).sizeIn(maxHeight = this@BoxWithConstraints.maxHeight * 0.86f))
                Column(Modifier.weight(1f).widthIn(max = 480.dp)) {
                    Head(vm, onClose)
                    Spacer(Modifier.height(16.dp))
                    Readout(vm)
                    Spacer(Modifier.height(16.dp))
                    Seek(vm)
                    Spacer(Modifier.height(10.dp))
                    Transport(vm)
                    Spacer(Modifier.height(12.dp))
                    Extras(vm, onEqualizer, onLyrics, onKaraoke)
                }
            }
        } else {
            // the body of the player: one machined panel holding art, readout and transport
            val art = minOf(maxWidth - 76.dp, maxHeight * 0.42f, 560.dp)   // a tablet is taller: let the art grow with it
            Column(
                Modifier.fillMaxSize().widthIn(max = 520.dp).align(Alignment.TopCenter).chassis(30.dp).padding(horizontal = 18.dp, vertical = 14.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Head(vm, onClose)
                Spacer(Modifier.weight(0.3f))
                Art(vm.artwork, vm.isLive, Modifier.size(art))
                Spacer(Modifier.height(16.dp))
                LevelMeter(vm.isPlaying, Modifier.width(art * 0.6f))
                Spacer(Modifier.height(16.dp))
                Readout(vm)
                Spacer(Modifier.weight(0.3f))
                Column(Modifier.fillMaxWidth().chassis(22.dp, MaterialTheme.colorScheme.surfaceContainerLowest).padding(horizontal = 16.dp, vertical = 14.dp)) {
                    Seek(vm)
                    Spacer(Modifier.height(14.dp))
                    Transport(vm)
                    Spacer(Modifier.height(12.dp))
                    Extras(vm, onEqualizer, onLyrics, onKaraoke)
                }
            }
        }
    }
}

@Composable
private fun Head(vm: JukeViewModel, onClose: (() -> Unit)?) {
    Row(Modifier.fillMaxWidth().heightIn(min = 44.dp), verticalAlignment = Alignment.CenterVertically) {
        if (onClose != null) Key(R.drawable.ic_chevron, stringResource(R.string.back), onClose, size = 40.dp, icon = 20.dp, rotation = 90f,
            tint = MaterialTheme.colorScheme.onSurfaceVariant)
        JIcon(R.drawable.ic_album, Modifier.padding(start = if (onClose != null) 2.dp else 4.dp), AccentA, 16.dp)
        Text("JUKE", Modifier.padding(start = 7.dp), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.weight(1f))
        if (vm.isLive) { LiveBadge(stringResource(R.string.live)); Spacer(Modifier.width(7.dp)) }
        FormatBadge(vm.badge)
    }
}

@Composable
private fun Readout(vm: JukeViewModel) {
    val subtitle = when {
        vm.isLive && vm.nowPlaying.isNotBlank() -> vm.nowPlaying
        vm.isLive -> if (vm.buffering || !vm.isPlaying) stringResource(R.string.connecting) else stringResource(R.string.on_air)
        else -> listOf(vm.artist, vm.album).filter { it.isNotBlank() }.joinToString(" · ")
    }
    Column(Modifier.fillMaxWidth(), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(vm.itemTitle, style = MaterialTheme.typography.titleLarge, maxLines = 2, overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center)
        if (subtitle.isNotBlank()) {
            Spacer(Modifier.height(5.dp))
            Text(subtitle, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant,
                maxLines = 2, overflow = TextOverflow.Ellipsis, textAlign = TextAlign.Center)
        }
    }
}

/** A thin rail with a gradient fill: tap or drag anywhere on it. A live stream has no end, so it just glows. */
@Composable
internal fun Seek(vm: JukeViewModel) {
    val colors = MaterialTheme.colorScheme
    if (vm.isLive) {
        Box(Modifier.fillMaxWidth().height(3.dp).clip(CircleShape).background(LiveRed.copy(alpha = if (vm.isPlaying) 0.55f else 0.2f)))
        return
    }
    var position by remember { mutableStateOf(0L to 0L) }
    var dragging by remember { mutableStateOf<Float?>(null) }
    val owner = LocalLifecycleOwner.current
    // Reads the position again whenever it may have jumped (a seek, a new song, the length becoming known), even paused;
    // while sound plays it keeps ticking, only when this screen is up.
    LaunchedEffect(vm.isPlaying, vm.currentTrackId, vm.progressVersion) {
        position = vm.position()
        if (!vm.isPlaying) return@LaunchedEffect
        owner.lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) { while (true) { delay(250); if (dragging == null) position = vm.position() } }
    }
    val (pos, dur) = position
    val fraction = dragging ?: if (dur > 0) (pos.toFloat() / dur).coerceIn(0f, 1f) else 0f
    Column(Modifier.fillMaxWidth()) {
        Box(
            Modifier.fillMaxWidth().height(40.dp)
                .pointerInput(dur) {
                    if (dur <= 0) return@pointerInput
                    // one gesture for tap and drag: the thumb goes to the finger at once, follows it, and the song jumps on release
                    awaitEachGesture {
                        val down = awaitFirstDown(requireUnconsumed = false)
                        try {
                            dragging = (down.position.x / size.width).coerceIn(0f, 1f)
                            down.consume()
                            while (true) {
                                val change = awaitPointerEvent().changes.firstOrNull { it.id == down.id } ?: break
                                if (!change.pressed) { change.consume(); break }
                                dragging = (change.position.x / size.width).coerceIn(0f, 1f)
                                change.consume()
                            }
                            dragging?.let { f ->
                                position = (dur * f).toLong() to dur          // show the new place now, not after the next tick
                                vm.seekTo(f)
                            }
                        } finally {
                            dragging = null
                        }
                    }
                },
            contentAlignment = Alignment.Center,
        ) {
            androidx.compose.foundation.Canvas(Modifier.fillMaxWidth().height(20.dp)) {
                val y = size.height / 2
                val h = 3.dp.toPx()
                drawRoundRect(colors.outline, Offset(0f, y - h / 2), Size(size.width, h), androidx.compose.ui.geometry.CornerRadius(h))
                val w = size.width * fraction
                if (w > 0) drawRoundRect(AccentBrush, Offset(0f, y - h / 2), Size(w, h), androidx.compose.ui.geometry.CornerRadius(h))
                drawCircle(AccentB, 7.dp.toPx(), Offset(w.coerceIn(7.dp.toPx(), size.width - 7.dp.toPx()), y))
            }
        }
        Row(Modifier.fillMaxWidth()) {
            Text(formatTime(if (dragging != null) (dur * fraction).toLong() else pos), style = Meter, color = colors.onSurfaceVariant)
            Spacer(Modifier.weight(1f))
            Text(formatTime(dur), style = Meter, color = colors.onSurfaceVariant)
        }
    }
}

@Composable
internal fun Transport(vm: JukeViewModel) {
    Row(Modifier.fillMaxWidth(), Arrangement.Center, Alignment.CenterVertically) {
        Key(R.drawable.ic_prev, stringResource(R.string.previous), vm::previous, size = 58.dp, icon = 26.dp, enabled = !vm.isLive, filled = true)
        Spacer(Modifier.width(18.dp))
        PlayKey(vm.isPlaying, vm::togglePlay)
        Spacer(Modifier.width(18.dp))
        Key(R.drawable.ic_next, stringResource(R.string.next), vm::next, size = 58.dp, icon = 26.dp, enabled = !vm.isLive, filled = true)
    }
}

@Composable
private fun Extras(vm: JukeViewModel, onEqualizer: () -> Unit, onLyrics: () -> Unit, onKaraoke: () -> Unit) {
    val muted = MaterialTheme.colorScheme.onSurfaceVariant
    Row(Modifier.fillMaxWidth(), Arrangement.SpaceEvenly, Alignment.CenterVertically) {
        Key(R.drawable.ic_shuffle, "Shuffle", vm::toggleShuffle, size = 46.dp, icon = 20.dp, tint = if (vm.shuffle) AccentA else muted, enabled = !vm.isLive)
        Key(
            if (vm.repeat == Player.REPEAT_MODE_ONE) R.drawable.ic_repeat_one else R.drawable.ic_repeat, "Repeat", vm::cycleRepeat,
            size = 46.dp, icon = 20.dp, tint = if (vm.repeat != Player.REPEAT_MODE_OFF) AccentA else muted, enabled = !vm.isLive,
        )
        Key(R.drawable.ic_stop, stringResource(R.string.stop), vm::stop, size = 46.dp, icon = 18.dp, tint = muted)
        Key(R.drawable.ic_lyrics, stringResource(R.string.lyrics), onLyrics, size = 46.dp, icon = 20.dp, tint = if (vm.lyricsText.isNotBlank()) AccentA else muted, enabled = !vm.isLive)
        Key(R.drawable.ic_mic, stringResource(R.string.karaoke), onKaraoke, size = 46.dp, icon = 20.dp, tint = if (vm.lyricsLines.isNotEmpty()) AccentA else muted, enabled = !vm.isLive)
        Key(R.drawable.ic_sliders, stringResource(R.string.equalizer), onEqualizer, size = 46.dp, icon = 20.dp,
            tint = if (io.github.vezzulab.juke.playback.EqualizerHub.enabled) AccentA else muted)
    }
}

/** The strip above the navigation: tap it to raise the full player. */
@Composable
fun MiniPlayer(vm: JukeViewModel, onOpen: () -> Unit, modifier: Modifier = Modifier) {
    if (!vm.hasMedia) return
    val colors = MaterialTheme.colorScheme
    Row(
        modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 6.dp).chassis(18.dp, colors.surfaceContainer)
            .clickable(onClick = onOpen).padding(start = 8.dp, top = 7.dp, bottom = 7.dp, end = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Art(vm.artwork, vm.isLive, Modifier.size(44.dp), corner = 10.dp, glow = false)
        Column(Modifier.weight(1f).padding(horizontal = 12.dp)) {
            Text(vm.itemTitle, style = MaterialTheme.typography.bodyLarge, maxLines = 1, overflow = TextOverflow.Ellipsis)
            val sub = if (vm.isLive) vm.nowPlaying.ifBlank { stringResource(R.string.on_air) } else vm.artist
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (vm.isLive) { Box(Modifier.size(5.dp).clip(CircleShape).background(LiveRed)); Spacer(Modifier.width(5.dp)) }
                Text(sub, style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant, maxLines = 1, overflow = TextOverflow.Ellipsis)
            }
        }
        LevelMeter(vm.isPlaying, Modifier.width(26.dp).padding(end = 8.dp), bars = 4)
        PlayKey(vm.isPlaying, vm::togglePlay, size = 44.dp)
    }
}
