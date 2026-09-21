package io.github.vezzulab.juke.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.unit.sp
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import io.github.vezzulab.juke.BuildConfig
import io.github.vezzulab.juke.JukeViewModel
import io.github.vezzulab.juke.R

@Composable
fun SettingsScreen(vm: JukeViewModel, onLanguage: (String) -> Unit, onEqualizer: () -> Unit, onRescan: () -> Unit) {
    var language by remember { mutableStateOf(vm.store.language) }
    var page by rememberSaveable { mutableStateOf("") }               // "", "feedback" or "log"
    androidx.activity.compose.BackHandler(enabled = page != "") { page = "" }
    if (page == "feedback") { FeedbackScreen(vm) { page = "" }; return }
    if (page == "log") { LogScreen(vm) { page = "" }; return }
    Column(Modifier.fillMaxSize().padding(horizontal = 10.dp)) {
        Crumb(stringResource(R.string.nav_settings), "", canGoUp = false, onUp = {})
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 4.dp).widthIn(max = 640.dp),
            verticalArrangement = Arrangement.spacedBy(22.dp),
        ) {
            Block(stringResource(R.string.theme)) {
                Segmented(
                    listOf("system" to stringResource(R.string.theme_system), "dark" to stringResource(R.string.theme_dark), "light" to stringResource(R.string.theme_light)),
                    vm.theme, vm::applyTheme, Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(14.dp))
                Text(stringResource(R.string.theme_colors), style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(8.dp))
                ThemeChips(vm.theme, vm::applyTheme)
            }
            Block(stringResource(R.string.language)) {
                Segmented(
                    listOf("system" to stringResource(R.string.lang_system), "en" to "English", "es" to "Español"),
                    language, { language = it; vm.store.language = it; onLanguage(it) }, Modifier.fillMaxWidth(),
                )
            }
            Block(stringResource(R.string.lyrics)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(stringResource(R.string.lyrics_auto), Modifier.weight(1f), color = MaterialTheme.colorScheme.onSurface, style = MaterialTheme.typography.bodyMedium)
                    androidx.compose.material3.Switch(vm.lyricsAuto, vm::changeLyricsAuto)
                }
                Text(stringResource(R.string.lyrics_auto_hint), Modifier.padding(top = 4.dp), color = MaterialTheme.colorScheme.onSurfaceVariant, style = MaterialTheme.typography.bodySmall)
            }
            Block(stringResource(R.string.equalizer)) {
                ActionKey(stringResource(R.string.equalizer), onEqualizer, icon = R.drawable.ic_sliders, accent = false)
            }
            Block(stringResource(R.string.nav_library)) {
                ActionKey(stringResource(R.string.rescan), onRescan, icon = R.drawable.ic_refresh, accent = false)
            }
            Block(stringResource(R.string.support)) {
                SupportKey(Modifier.fillMaxWidth())
            }
            Block(stringResource(R.string.feedback_block)) {
                ActionKey(stringResource(R.string.feedback_title), { page = "feedback" }, Modifier.fillMaxWidth(), icon = R.drawable.ic_playlist, accent = false)
                Spacer(Modifier.height(8.dp))
                ActionKey(stringResource(R.string.log_title), { page = "log" }, Modifier.fillMaxWidth(), icon = R.drawable.ic_queue, accent = false)
            }
            Block(stringResource(R.string.about)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    JIcon(R.drawable.ic_album, tint = AccentA, size = 18.dp)
                    Text("Juke ${BuildConfig.VERSION_NAME}", Modifier.padding(start = 8.dp), style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Text("Juke by Vezzu Studio", Modifier.padding(top = 4.dp), style = MaterialTheme.typography.labelMedium.copy(letterSpacing = 0.sp),
                    color = MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha = 0.8f))
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class)
@Composable
private fun ThemeChips(current: String, onPick: (String) -> Unit) {
    androidx.compose.foundation.layout.FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        COLOR_LOOKS.forEach { look -> ThemeChip(look, look.id == current) { onPick(look.id) } }
    }
}

/** One look as a chip: its background with its two accents, named underneath; a ring marks the one in use. */
@Composable
private fun ThemeChip(look: Look, selected: Boolean, onClick: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    val shape = androidx.compose.foundation.shape.RoundedCornerShape(14.dp)
    Column(
        Modifier.width(74.dp).clip(shape).clickable(androidx.compose.runtime.remember { androidx.compose.foundation.interaction.MutableInteractionSource() }, null, onClick = onClick),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Box(
            Modifier.fillMaxWidth().height(48.dp).clip(shape).background(look.base)
                .border(if (selected) 2.5.dp else 1.dp, if (selected) look.accent else colors.outline, shape),
            contentAlignment = Alignment.Center,
        ) {
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Box(Modifier.size(16.dp).clip(androidx.compose.foundation.shape.CircleShape).background(look.accent))
                Box(Modifier.size(16.dp).clip(androidx.compose.foundation.shape.CircleShape).background(look.accent2))
            }
        }
        Text(themeName(look.id), Modifier.padding(top = 5.dp), maxLines = 1, style = MaterialTheme.typography.labelSmall.copy(letterSpacing = 0.sp, fontSize = 10.sp),
            color = if (selected) colors.onSurface else colors.onSurfaceVariant)
    }
}

@Composable
private fun themeName(id: String): String = stringResource(when (id) {
    "rose" -> R.string.theme_rose; "lavender" -> R.string.theme_lavender; "mint" -> R.string.theme_mint; "sky" -> R.string.theme_sky
    "peach" -> R.string.theme_peach; "sand" -> R.string.theme_sand; "lagoon" -> R.string.theme_lagoon; "coral" -> R.string.theme_coral
    "sage" -> R.string.theme_sage; "lemon" -> R.string.theme_lemon; "forest" -> R.string.theme_forest; "ocean" -> R.string.theme_ocean
    "sunset" -> R.string.theme_sunset; "neon" -> R.string.theme_neon; "ember" -> R.string.theme_ember; "arctic" -> R.string.theme_arctic
    "twilight" -> R.string.theme_twilight; "amber" -> R.string.theme_amber; "rosewood" -> R.string.theme_rosewood; else -> R.string.theme_graphite
})

@Composable
private fun Block(title: String, content: @Composable ColumnScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionLabel(title)
        content()
    }
}
