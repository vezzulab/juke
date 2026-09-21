package io.github.vezzulab.juke.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import io.github.vezzulab.juke.BuildConfig
import io.github.vezzulab.juke.JukeViewModel
import io.github.vezzulab.juke.R
import io.github.vezzulab.juke.data.Updater

/** "You are on X. Update to Y?" with what changed; Update downloads, verifies and opens Android's installer. */
@Composable
fun UpdateDialog(vm: JukeViewModel) {
    val release = vm.update ?: return
    val colors = MaterialTheme.colorScheme
    val progress = vm.updateProgress
    val busy = progress != null && progress >= 0
    val spanish = LocalConfiguration.current.locales[0].language == "es"
    val notes = remember(release.version, spanish) { Updater.plainNotes(release.notes, spanish) }
    Dialog(onDismissRequest = { if (!busy) vm.dismissUpdate() }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Column(
            Modifier.padding(20.dp).widthIn(max = 460.dp).heightIn(max = 620.dp).clip(RoundedCornerShape(26.dp))
                .background(colors.surfaceContainerHigh).padding(22.dp),
        ) {
            Text(stringResource(R.string.update_title), style = MaterialTheme.typography.titleLarge, color = colors.onSurface)
            Spacer(Modifier.height(6.dp))
            Text(
                if (release.isRebuild) stringResource(R.string.update_body_rebuild, BuildConfig.VERSION_NAME)
                else stringResource(R.string.update_body, BuildConfig.VERSION_NAME, release.version),
                style = MaterialTheme.typography.bodyMedium, color = colors.onSurfaceVariant,
            )
            if (notes.isNotBlank()) {
                Spacer(Modifier.height(14.dp))
                Text(stringResource(R.string.update_changes), style = MaterialTheme.typography.labelMedium, color = colors.onSurfaceVariant)
                Spacer(Modifier.height(6.dp))
                Column(Modifier.weight(1f, fill = false).clip(RoundedCornerShape(14.dp)).background(colors.surfaceContainerLow).verticalScroll(rememberScrollState()).padding(14.dp)) {
                    Text(notes, style = MaterialTheme.typography.bodySmall, color = colors.onSurface)
                }
            }
            Spacer(Modifier.height(16.dp))
            when {
                busy -> {
                    Text(stringResource(R.string.update_downloading, progress!!), style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
                    Spacer(Modifier.height(8.dp))
                    LinearProgressIndicator(progress = { progress / 100f }, Modifier.fillMaxWidth().clip(RoundedCornerShape(50)), color = AccentA, trackColor = colors.surfaceContainerLow)
                }
                else -> {
                    if (progress == -1) Text(stringResource(R.string.update_failed), Modifier.padding(bottom = 10.dp), style = MaterialTheme.typography.bodySmall, color = colors.error)
                    if (progress == -2) Text(stringResource(R.string.update_permission), Modifier.padding(bottom = 10.dp), style = MaterialTheme.typography.bodySmall, color = colors.onSurfaceVariant)
                    ActionKey(stringResource(R.string.update_now), vm::updateNow, Modifier.fillMaxWidth(), icon = R.drawable.ic_refresh)
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        ActionKey(stringResource(R.string.update_later), vm::updateLater, Modifier.weight(1f), accent = false)
                        ActionKey(stringResource(R.string.update_skip), vm::updateSkip, Modifier.weight(1f), accent = false)
                    }
                }
            }
        }
    }
}
