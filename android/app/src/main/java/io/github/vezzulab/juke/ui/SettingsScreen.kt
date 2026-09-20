package io.github.vezzulab.juke.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import io.github.vezzulab.juke.BuildConfig
import io.github.vezzulab.juke.JukeViewModel
import io.github.vezzulab.juke.R

@Composable
fun SettingsScreen(vm: JukeViewModel, onLanguage: (String) -> Unit, onEqualizer: () -> Unit, onRescan: () -> Unit) {
    var language by remember { mutableStateOf(vm.store.language) }
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
            }
            Block(stringResource(R.string.language)) {
                Segmented(
                    listOf("system" to stringResource(R.string.lang_system), "en" to "English", "es" to "Español"),
                    language, { language = it; vm.store.language = it; onLanguage(it) }, Modifier.fillMaxWidth(),
                )
            }
            Block(stringResource(R.string.equalizer)) {
                ActionKey(stringResource(R.string.equalizer), onEqualizer, icon = R.drawable.ic_sliders, accent = false)
            }
            Block(stringResource(R.string.nav_library)) {
                ActionKey(stringResource(R.string.rescan), onRescan, icon = R.drawable.ic_refresh, accent = false)
            }
            Block(stringResource(R.string.about)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    JIcon(R.drawable.ic_album, tint = AccentA, size = 18.dp)
                    Text("Juke ${BuildConfig.VERSION_NAME}", Modifier.padding(start = 8.dp), style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun Block(title: String, content: @Composable ColumnScope.() -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        SectionLabel(title)
        content()
    }
}
