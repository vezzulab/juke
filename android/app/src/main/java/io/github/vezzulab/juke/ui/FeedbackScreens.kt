package io.github.vezzulab.juke.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.vezzulab.juke.AppLog
import io.github.vezzulab.juke.JukeViewModel
import io.github.vezzulab.juke.R

private const val URL_BUDGET = 6500      // longer than this and the address is refused

/** A problem, a suggestion or a question: it opens as a new issue on GitHub, reviewed there before anything is sent. */
@Composable
fun FeedbackScreen(vm: JukeViewModel, onClose: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    val secrets = remember { AppLog.secretsOf(vm.store.server) }
    var kind by rememberSaveable { mutableStateOf("problem") }
    var message by rememberSaveable { mutableStateOf("") }
    var include by rememberSaveable { mutableStateOf(true) }
    val clipboard = LocalClipboardManager.current
    val links = LocalUriHandler.current
    var copied by remember { mutableStateOf(false) }

    val typed = AppLog.redact(message.trim(), secrets)
    val details = remember(include, message) { if (include) AppLog.redact(AppLog.summary() + "\n\n--- log ---\n" + AppLog.read(secrets, 20_000), secrets) else "" }
    fun full() = if (include) typed + "\n\n---\n" + details else typed
    fun title(): String {
        val label = when (kind) { "idea" -> "Suggestion"; "question" -> "Question"; else -> "Problem" }
        return "[$label] ${typed.lineSequence().firstOrNull().orEmpty().take(70)}".trim()
    }

    Column(Modifier.fillMaxSize().padding(horizontal = 10.dp)) {
        Crumb(stringResource(R.string.feedback_title), "", canGoUp = true, onUp = onClose)
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 4.dp).widthIn(max = 640.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(stringResource(R.string.feedback_intro), color = colors.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
            Segmented(
                listOf("problem" to stringResource(R.string.feedback_problem), "idea" to stringResource(R.string.feedback_idea), "question" to stringResource(R.string.feedback_question)),
                kind, { kind = it }, Modifier.fillMaxWidth(),
            )
            JukeField(message, { message = it; copied = false }, stringResource(R.string.feedback_message), Modifier.fillMaxWidth(),
                placeholder = stringResource(R.string.feedback_placeholder), singleLine = false, minLines = 5, maxLines = 10)
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(stringResource(R.string.feedback_include), Modifier.weight(1f), color = colors.onSurface, style = MaterialTheme.typography.bodyMedium)
                Switch(include, { include = it })
            }
            if (include) {
                Text(
                    details, Modifier.fillMaxWidth().heightIn(max = 170.dp).clipToBoundsScroll().border(1.dp, colors.outline, RoundedCornerShape(12.dp))
                        .background(colors.surfaceContainerLow, RoundedCornerShape(12.dp)).padding(10.dp),
                    fontFamily = FontFamily.Monospace, fontSize = 10.sp, color = colors.onSurfaceVariant,
                )
            }
            Text(if (copied) stringResource(R.string.feedback_copied) else stringResource(R.string.feedback_hint), color = colors.onSurfaceVariant, style = MaterialTheme.typography.labelMedium)
            ActionKey(
                stringResource(R.string.feedback_send),
                {
                    clipboard.setText(AnnotatedString(full()))            // the whole report, in case the address has to be shortened
                    var url = AppLog.issueUrl(title(), typed + if (include) "\n\n---\n" + AppLog.summary() else "")
                    if (url.length > URL_BUDGET) url = AppLog.issueUrl(title(), typed.take(2500) + "\n\n" + "(The technical details are long: they are copied to your clipboard, paste them here.)")
                    links.openUri(url)
                    onClose()
                },
                Modifier.fillMaxWidth(), icon = R.drawable.ic_globe, enabled = typed.isNotBlank(),
            )
            ActionKey(stringResource(R.string.feedback_copy), { clipboard.setText(AnnotatedString(full())); copied = true }, Modifier.fillMaxWidth(), icon = R.drawable.ic_queue, accent = false, enabled = typed.isNotBlank())
            Spacer(Modifier.height(24.dp))
        }
    }
}

@Composable
private fun Modifier.clipToBoundsScroll(): Modifier = this.verticalScroll(rememberScrollState())

/** Juke's log, private details hidden, to read or copy. */
@Composable
fun LogScreen(vm: JukeViewModel, onClose: () -> Unit) {
    val colors = MaterialTheme.colorScheme
    val secrets = remember { AppLog.secretsOf(vm.store.server) }
    var text by remember { mutableStateOf(AppLog.read(secrets)) }
    val clipboard = LocalClipboardManager.current
    val scroll = rememberScrollState()
    LaunchedEffect(text) { scroll.scrollTo(scroll.maxValue) }
    Column(Modifier.fillMaxSize().padding(horizontal = 10.dp)) {
        Crumb(stringResource(R.string.log_title), "", canGoUp = true, onUp = onClose)
        Text(stringResource(R.string.log_note), Modifier.padding(horizontal = 4.dp, vertical = 4.dp), color = colors.onSurfaceVariant, style = MaterialTheme.typography.labelMedium)
        Text(
            text.ifBlank { stringResource(R.string.log_empty) },
            Modifier.weight(1f).fillMaxWidth().padding(vertical = 8.dp).border(1.dp, colors.outline, RoundedCornerShape(12.dp))
                .background(colors.surfaceContainerLow, RoundedCornerShape(12.dp)).verticalScroll(scroll).padding(10.dp),
            fontFamily = FontFamily.Monospace, fontSize = 10.sp, color = colors.onSurfaceVariant,
        )
        Row(Modifier.fillMaxWidth().padding(bottom = 12.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            ActionKey(stringResource(R.string.log_refresh), { text = AppLog.read(secrets) }, Modifier.weight(1f), icon = R.drawable.ic_refresh, accent = false)
            ActionKey(stringResource(R.string.feedback_copy), { clipboard.setText(AnnotatedString(text)) }, Modifier.weight(1f), icon = R.drawable.ic_queue)
        }
    }
}
