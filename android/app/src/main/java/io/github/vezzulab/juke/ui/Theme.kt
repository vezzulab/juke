package io.github.vezzulab.juke.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/** Brand and chassis colours. The look is a modern digital audio player: near-black body, hairline bezels,
 *  a gradient accent taken from the Juke icon and a gold badge for the format, as the good players do. */
val AccentA = Color(0xFF7AA2F7)
val AccentB = Color(0xFFCBA6F7)
val Gold = Color(0xFFD8A54A)
val LiveRed = Color(0xFFFF4757)

val AccentBrush = Brush.linearGradient(listOf(AccentA, AccentB))
val AccentSoft = Brush.linearGradient(listOf(AccentA.copy(alpha = 0.22f), AccentB.copy(alpha = 0.22f)))

private val Dark = darkColorScheme(
    primary = AccentA, onPrimary = Color(0xFF0A0C14),
    primaryContainer = Color(0xFF1A2138), onPrimaryContainer = Color(0xFFBFD2FF),
    secondary = AccentB, onSecondary = Color(0xFF12101C),
    background = Color(0xFF06070A), onBackground = Color(0xFFEDEFF5),
    surface = Color(0xFF06070A), onSurface = Color(0xFFEDEFF5),
    surfaceVariant = Color(0xFF161A24), onSurfaceVariant = Color(0xFF8A93A8),
    surfaceContainerLowest = Color(0xFF040507), surfaceContainerLow = Color(0xFF0B0D13),
    surfaceContainer = Color(0xFF10131B), surfaceContainerHigh = Color(0xFF161A24), surfaceContainerHighest = Color(0xFF1D2230),
    outline = Color(0xFF262C3C), outlineVariant = Color(0xFF1A1F2C), error = LiveRed, scrim = Color(0xCC030406),
)

// The silver body: the same player in daylight.
private val Light = lightColorScheme(
    primary = Color(0xFF4C63C6), onPrimary = Color.White,
    primaryContainer = Color(0xFFE2E8FF), onPrimaryContainer = Color(0xFF1B2A63),
    secondary = Color(0xFF7D5BC4), onSecondary = Color.White,
    background = Color(0xFFEDEFF4), onBackground = Color(0xFF14161D),
    surface = Color(0xFFEDEFF4), onSurface = Color(0xFF14161D),
    surfaceVariant = Color(0xFFE0E3EC), onSurfaceVariant = Color(0xFF5B6376),
    surfaceContainerLowest = Color.White, surfaceContainerLow = Color(0xFFF7F8FB),
    surfaceContainer = Color(0xFFFFFFFF), surfaceContainerHigh = Color(0xFFE9ECF3), surfaceContainerHighest = Color(0xFFDFE3EC),
    outline = Color(0xFFCBD1DE), outlineVariant = Color(0xFFDDE1EA), error = Color(0xFFC62B3A), scrim = Color(0x99101218),
)

private val Type = Typography(
    titleLarge = TextStyle(fontSize = 24.sp, fontWeight = FontWeight.Bold, letterSpacing = (-0.3).sp),
    titleMedium = TextStyle(fontSize = 16.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontSize = 15.sp),
    bodyMedium = TextStyle(fontSize = 13.5.sp),
    bodySmall = TextStyle(fontSize = 12.sp),
    labelLarge = TextStyle(fontSize = 13.sp, fontWeight = FontWeight.SemiBold, letterSpacing = 0.4.sp),
    labelMedium = TextStyle(fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.2.sp),
    labelSmall = TextStyle(fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.6.sp),
)

/** Numbers on a player are monospaced: they must not jitter as they count. */
val Meter = TextStyle(fontSize = 12.sp, fontFamily = FontFamily.Monospace, letterSpacing = 0.sp)

@Composable
fun JukeTheme(mode: String, content: @Composable () -> Unit) {
    val dark = when (mode) { "dark" -> true; "light" -> false; else -> isSystemInDarkTheme() }
    val scheme = if (dark) Dark else Light
    MaterialTheme(colorScheme = scheme, typography = Type) {
        Surface(Modifier.fillMaxSize(), color = scheme.background, contentColor = scheme.onBackground, content = content)
    }
}
