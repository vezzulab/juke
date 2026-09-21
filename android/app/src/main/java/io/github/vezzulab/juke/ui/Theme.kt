package io.github.vezzulab.juke.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.ColorScheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.sp

/** Brand and chassis colours. The look is a modern digital audio player: near-black body, hairline bezels,
 *  a gradient accent taken from the Juke icon and a gold badge for the format, as the good players do. */
val Gold = Color(0xFFD8A54A)
val LiveRed = Color(0xFFFF4757)

/** The two accent colours of the look in use. They are state, so choosing another look repaints every screen at once. */
object Accents {
    var a by mutableStateOf(Color(0xFF7AA2F7)); private set
    var b by mutableStateOf(Color(0xFFCBA6F7)); private set
    fun use(id: String) {
        val look = lookOf(id)
        a = look?.accent ?: Color(0xFF7AA2F7)
        b = look?.accent2 ?: Color(0xFFCBA6F7)
    }
}

val AccentA: Color get() = Accents.a
val AccentB: Color get() = Accents.b
val AccentBrush: Brush get() = Brush.linearGradient(listOf(AccentA, AccentB))
val AccentSoft: Brush get() = Brush.linearGradient(listOf(AccentA.copy(alpha = 0.22f), AccentB.copy(alpha = 0.22f)))

/** A ready-made colour look (the same sixteen as Juke for Linux): soft pastels first, then the deeper ones. */
class Look(val id: String, val dark: Boolean, base: Long, text: Long, accent: Long, accent2: Long) {
    val base = Color(base); val text = Color(text); val accent = Color(accent); val accent2 = Color(accent2)
}

val COLOR_LOOKS = listOf(
    Look("rose", false, 0xFFFDF1F5, 0xFF3D2230, 0xFFB83266, 0xFF8A4FC4),
    Look("lavender", false, 0xFFF5F1FD, 0xFF2F2A4A, 0xFF6444C2, 0xFFB3408F),
    Look("mint", false, 0xFFEEF9F3, 0xFF1F3A33, 0xFF187A56, 0xFF1F709E),
    Look("sky", false, 0xFFF1F7FD, 0xFF1F3145, 0xFF1F68B8, 0xFF7A55C9),
    Look("peach", false, 0xFFFFF4EC, 0xFF42281A, 0xFFB8501A, 0xFFB83266),
    Look("sand", false, 0xFFFAF5E9, 0xFF3D3524, 0xFF8A5A00, 0xFF2A7A6A),
    Look("lagoon", false, 0xFFEDF9FA, 0xFF173A40, 0xFF0E7C86, 0xFF2F62C9),
    Look("coral", false, 0xFFFFF2EF, 0xFF4A2320, 0xFFB93A26, 0xFFA85F0C),
    Look("sage", false, 0xFFF1F5EC, 0xFF2B3829, 0xFF44762F, 0xFF8A5A1F),
    Look("lemon", false, 0xFFFDFAE6, 0xFF3B3818, 0xFF7A6600, 0xFFB3471A),
    Look("forest", true, 0xFF10231A, 0xFFE3F2E8, 0xFF5FD39A, 0xFFC5E063),
    Look("ocean", true, 0xFF08192C, 0xFFE6F5FF, 0xFF22D3FF, 0xFF6F9BFF),
    Look("sunset", true, 0xFF26121A, 0xFFFFEEE6, 0xFFFF8A4C, 0xFFFF5C9C),
    Look("neon", true, 0xFF150A26, 0xFFF6ECFF, 0xFFD868FF, 0xFF2EE6FF),
    Look("ember", true, 0xFF1C1414, 0xFFFBEEEA, 0xFFFF5A4F, 0xFFFFB84A),
    Look("arctic", true, 0xFF2E3440, 0xFFECEFF4, 0xFF88C0D0, 0xFFB48EAD),
    Look("twilight", true, 0xFF282A36, 0xFFF8F8F2, 0xFFBD93F9, 0xFFFF79C6),
    Look("amber", true, 0xFF282524, 0xFFEBDBB2, 0xFFFABD2F, 0xFFFE8019),
    Look("rosewood", true, 0xFF191724, 0xFFE0DEF4, 0xFFEB6F92, 0xFFC4A7E7),
    Look("graphite", true, 0xFF1F2226, 0xFFE6E8EA, 0xFF4FD1C5, 0xFFF6AD55),
)

fun lookOf(id: String): Look? = COLOR_LOOKS.firstOrNull { it.id == id }

private fun mix(a: Color, b: Color, t: Float) = Color(a.red + (b.red - a.red) * t, a.green + (b.green - a.green) * t, a.blue + (b.blue - a.blue) * t, 1f)

/** The whole Material scheme of a look, worked out from its four colours the way Juke for Linux does. */
private fun schemeOf(look: Look): ColorScheme {
    val white = Color.White; val black = Color.Black; val base = look.base; val text = look.text
    return if (look.dark) darkColorScheme(
        primary = look.accent, onPrimary = mix(base, black, .45f),
        primaryContainer = mix(base, look.accent, .22f), onPrimaryContainer = mix(look.accent, white, .5f),
        secondary = look.accent2, onSecondary = mix(base, black, .45f),
        background = base, onBackground = text, surface = base, onSurface = text,
        surfaceVariant = mix(base, white, .12f), onSurfaceVariant = mix(text, base, .36f),
        surfaceContainerLowest = mix(base, black, .28f), surfaceContainerLow = mix(base, white, .035f),
        surfaceContainer = mix(base, white, .06f), surfaceContainerHigh = mix(base, white, .1f), surfaceContainerHighest = mix(base, white, .15f),
        outline = mix(base, white, .16f), outlineVariant = mix(base, white, .09f), error = LiveRed, scrim = Color(0xCC030406),
    ) else lightColorScheme(
        primary = look.accent, onPrimary = white,
        primaryContainer = mix(base, look.accent, .16f), onPrimaryContainer = mix(look.accent, black, .5f),
        secondary = look.accent2, onSecondary = white,
        background = base, onBackground = text, surface = base, onSurface = text,
        surfaceVariant = mix(base, black, .075f), onSurfaceVariant = mix(text, base, .24f),
        surfaceContainerLowest = white, surfaceContainerLow = mix(base, white, .55f),
        surfaceContainer = white, surfaceContainerHigh = mix(base, black, .045f), surfaceContainerHighest = mix(base, black, .085f),
        outline = mix(base, black, .16f), outlineVariant = mix(base, black, .09f), error = Color(0xFFC62B3A), scrim = Color(0x99101218),
    )
}

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
    val look = lookOf(mode)
    val dark = look?.dark ?: when (mode) { "dark" -> true; "light" -> false; else -> isSystemInDarkTheme() }
    val scheme = look?.let(::schemeOf) ?: if (dark) Dark else Light
    MaterialTheme(colorScheme = scheme, typography = Type) {
        Surface(Modifier.fillMaxSize(), color = scheme.background, contentColor = scheme.onBackground, content = content)
    }
}
