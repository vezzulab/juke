package io.github.vezzulab.juke.ui

import androidx.annotation.DrawableRes
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.draw.rotate
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import coil3.compose.AsyncImage
import io.github.vezzulab.juke.R
import kotlin.math.abs
import kotlin.random.Random
import kotlinx.coroutines.delay

@Composable
fun JIcon(@DrawableRes id: Int, modifier: Modifier = Modifier, tint: Color = MaterialTheme.colorScheme.onSurface, size: Dp = 24.dp, description: String? = null) {
    Icon(painterResource(id), description, modifier.size(size), tint)
}

/** A panel with the hairline bezel and the soft top highlight of a machined metal body. */
@Composable
fun Modifier.chassis(corner: Dp = 22.dp, fill: Color = MaterialTheme.colorScheme.surfaceContainerLow): Modifier {
    val edge = MaterialTheme.colorScheme.outline
    val shape: Shape = RoundedCornerShape(corner)
    return this.clip(shape).background(fill)
        .drawBehind {
            drawRect(Brush.verticalGradient(listOf(Color.White.copy(alpha = 0.05f), Color.Transparent), endY = size.height * 0.35f))
        }
        .border(1.dp, edge, shape)
}

/** A round key: it sinks a little when pressed, like a real button. */
@Composable
fun Key(
    @DrawableRes id: Int, description: String, onClick: () -> Unit, modifier: Modifier = Modifier,
    size: Dp = 52.dp, icon: Dp = 24.dp, tint: Color = MaterialTheme.colorScheme.onSurface, enabled: Boolean = true, filled: Boolean = false,
    rotation: Float = 0f,
) {
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed) 0.92f else 1f, label = "key")
    val colors = MaterialTheme.colorScheme
    Box(
        modifier.size(maxOf(size, 48.dp)).scale(scale)
            .clip(CircleShape)
            .then(if (filled) Modifier.background(colors.surfaceContainerHigh).border(1.dp, colors.outline, CircleShape) else Modifier)
            .clickable(source, null, enabled = enabled, role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) { JIcon(id, Modifier.rotate(rotation), if (enabled) tint else tint.copy(alpha = 0.3f), icon, description) }
}

/** The transport key: the accent gradient with a glow under it. */
@Composable
fun PlayKey(playing: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier, size: Dp = 78.dp) {
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed) 0.94f else 1f, label = "play")
    Box(
        modifier.size(size).scale(scale)
            .shadow(18.dp, CircleShape, clip = false, ambientColor = AccentA, spotColor = AccentB)
            .clip(CircleShape).background(AccentBrush)
            .clickable(source, null, role = Role.Button, onClick = onClick),
        contentAlignment = Alignment.Center,
    ) {
        JIcon(if (playing) R.drawable.ic_pause else R.drawable.ic_play, tint = Color(0xFF0A0C14), size = size * 0.42f,
            description = if (playing) "Pause" else "Play")
    }
}

/** The format plate: gold, the way a player marks what it is feeding its amplifier. */
@Composable
fun FormatBadge(text: String, modifier: Modifier = Modifier) {
    if (text.isBlank()) return
    Text(
        text.uppercase(), modifier.clip(RoundedCornerShape(4.dp)).border(1.dp, Gold.copy(alpha = 0.7f), RoundedCornerShape(4.dp))
            .padding(horizontal = 7.dp, vertical = 2.dp),
        color = Gold, style = MaterialTheme.typography.labelSmall,
    )
}

@Composable
fun LiveBadge(text: String, modifier: Modifier = Modifier) {
    Row(modifier.clip(RoundedCornerShape(4.dp)).background(LiveRed.copy(alpha = 0.14f)).padding(horizontal = 7.dp, vertical = 3.dp),
        verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(5.dp).clip(CircleShape).background(LiveRed))
        Spacer(Modifier.width(5.dp))
        Text(text, color = LiveRed, style = MaterialTheme.typography.labelSmall)
    }
}

/** Album art, or the vinyl mark when there is none, with a coloured glow under it. */
@Composable
fun Art(url: String?, live: Boolean, modifier: Modifier = Modifier, corner: Dp = 20.dp, glow: Boolean = true) {
    val colors = MaterialTheme.colorScheme
    val shape = RoundedCornerShape(corner)
    Box(
        modifier.then(if (glow) Modifier.shadow(26.dp, shape, clip = false, ambientColor = AccentA, spotColor = AccentB) else Modifier)
            .clip(shape).background(colors.surfaceContainerHigh).border(1.dp, colors.outline, shape),
        contentAlignment = Alignment.Center,
    ) {
        var loaded by remember(url) { mutableStateOf(false) }
        // the mark only stands in until the art arrives: a logo with transparency must not show it through
        if (!loaded) JIcon(if (live) R.drawable.ic_radio else R.drawable.ic_album, tint = colors.onSurfaceVariant.copy(alpha = 0.55f), size = 40.dp)
        if (!url.isNullOrBlank()) AsyncImage(
            url, null, Modifier.matchParentSize().clip(shape), contentScale = ContentScale.Crop,
            onSuccess = { loaded = true }, onError = { loaded = false },
        )
    }
}

/** The level meter: decoration, and it only moves while sound is coming out and this screen is on. */
@Composable
fun LevelMeter(active: Boolean, modifier: Modifier = Modifier, bars: Int = 16) {
    val levels = remember { mutableStateListOf<Float>().apply { repeat(bars) { add(0.12f) } } }
    LaunchedEffect(active) {
        if (!active) { for (i in 0 until bars) levels[i] = 0.1f; return@LaunchedEffect }
        val random = Random(7)
        while (true) {
            for (i in 0 until bars) {
                val weight = 1f - abs(i - bars / 2f) / bars      // louder in the middle, like a real spectrum
                levels[i] = (levels[i] * 0.55f + random.nextFloat() * (0.35f + 0.65f * weight) * 0.45f).coerceIn(0.08f, 1f)
            }
            delay(110)
        }
    }
    val colors = MaterialTheme.colorScheme
    Row(modifier.height(22.dp), horizontalArrangement = Arrangement.spacedBy(3.dp), verticalAlignment = Alignment.Bottom) {
        levels.forEach { level ->
            val height by animateFloatAsState(level, label = "bar")
            Box(
                Modifier.weight(1f).fillMaxHeight(height.coerceAtLeast(0.08f)).clip(RoundedCornerShape(1.5.dp))
                    .background(if (active) AccentBrush else Brush.verticalGradient(listOf(colors.outline, colors.outline)))
            )
        }
    }
}

@Composable
fun SectionLabel(text: String, modifier: Modifier = Modifier) {
    Text(text.uppercase(), modifier, color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.labelMedium)
}

/** Two or three flat keys in a row, the way a player switches modes. */
@Composable
fun Segmented(options: List<Pair<String, String>>, selected: String, onSelect: (String) -> Unit, modifier: Modifier = Modifier) {
    val colors = MaterialTheme.colorScheme
    Row(modifier.chassis(14.dp, colors.surfaceContainerLowest).padding(4.dp), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
        options.forEach { (key, label) ->
            val on = key == selected
            Box(
                Modifier.weight(1f).heightIn(min = 40.dp).clip(RoundedCornerShape(11.dp))
                    .then(if (on) Modifier.background(AccentSoft).border(1.dp, AccentA.copy(alpha = 0.5f), RoundedCornerShape(11.dp)) else Modifier)
                    .clickable { onSelect(key) },
                contentAlignment = Alignment.Center,
            ) { Text(label, color = if (on) colors.onSurface else colors.onSurfaceVariant, style = MaterialTheme.typography.labelLarge, maxLines = 1, overflow = TextOverflow.Ellipsis) }
        }
    }
}

@Composable
fun EmptyState(@DrawableRes icon: Int, title: String, hint: String, modifier: Modifier = Modifier, action: (@Composable () -> Unit)? = null) {
    Column(modifier.fillMaxSize().padding(32.dp), Arrangement.Center, Alignment.CenterHorizontally) {
        Box(Modifier.size(84.dp).chassis(26.dp), contentAlignment = Alignment.Center) {
            JIcon(icon, tint = MaterialTheme.colorScheme.onSurfaceVariant, size = 34.dp)
        }
        Spacer(Modifier.height(18.dp))
        Text(title, style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center)
        if (hint.isNotBlank()) {
            Spacer(Modifier.height(6.dp))
            Text(hint, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
        }
        if (action != null) { Spacer(Modifier.height(20.dp)); action() }
    }
}

/** A flat, wide action key (used instead of Material buttons so everything shares the same body). */
@Composable
fun ActionKey(text: String, onClick: () -> Unit, modifier: Modifier = Modifier, @DrawableRes icon: Int? = null, accent: Boolean = true, enabled: Boolean = true) {
    val colors = MaterialTheme.colorScheme
    val source = remember { MutableInteractionSource() }
    val pressed by source.collectIsPressedAsState()
    val scale by animateFloatAsState(if (pressed) 0.97f else 1f, label = "action")
    Row(
        modifier.scale(scale).heightIn(min = 46.dp).clip(RoundedCornerShape(14.dp))
            .then(if (accent) Modifier.background(AccentBrush) else Modifier.background(colors.surfaceContainerHigh).border(1.dp, colors.outline, RoundedCornerShape(14.dp)))
            .clickable(source, null, enabled = enabled, onClick = onClick).padding(horizontal = 18.dp),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center,
    ) {
        val content = if (accent) Color(0xFF0A0C14) else colors.onSurface
        if (icon != null) { JIcon(icon, tint = content.copy(alpha = if (enabled) 1f else 0.4f), size = 18.dp); Spacer(Modifier.width(8.dp)) }
        Text(text, color = content.copy(alpha = if (enabled) 1f else 0.4f), style = MaterialTheme.typography.labelLarge)
    }
}

const val KOFI_URL = "https://ko-fi.com/S1K526XVUI"

/** "Support on Ko-fi": tinted with the accent so it stands out without leaving the theme. [compact] is the tall key for the rail. */
@Composable
fun SupportKey(modifier: Modifier = Modifier, compact: Boolean = false) {
    val links = androidx.compose.ui.platform.LocalUriHandler.current
    val shape = RoundedCornerShape(if (compact) 16.dp else 14.dp)
    val label = stringResource(if (compact) R.string.support_kofi_short else R.string.support_kofi)
    val body = modifier.clip(shape).background(AccentSoft).border(1.dp, AccentA.copy(alpha = 0.45f), shape)
        .clickable(remember { MutableInteractionSource() }, null) { links.openUri(KOFI_URL) }
    if (compact) {
        Column(body.padding(horizontal = 12.dp, vertical = 9.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            JIcon(R.drawable.ic_heart, tint = AccentA, size = 22.dp)
            Text(label, Modifier.padding(top = 5.dp), color = AccentA, style = MaterialTheme.typography.labelSmall, maxLines = 1)
        }
    } else {
        Row(body.heightIn(min = 46.dp).padding(horizontal = 18.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.Center) {
            JIcon(R.drawable.ic_heart, tint = AccentA, size = 18.dp)
            Spacer(Modifier.width(8.dp))
            Text(label, color = AccentA, style = MaterialTheme.typography.labelLarge)
        }
    }
}

fun formatTime(ms: Long): String {
    val s = (ms / 1000).coerceAtLeast(0)
    return "%d:%02d".format(s / 60, s % 60)
}
