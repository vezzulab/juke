package io.github.vezzulab.juke.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import io.github.vezzulab.juke.BrowseState
import io.github.vezzulab.juke.JukeViewModel
import io.github.vezzulab.juke.R
import io.github.vezzulab.juke.data.ServerConfig

/** Text fields share the player's body: dark well, hairline edge, accent when in use. */
@Composable
fun JukeField(
    value: String, onChange: (String) -> Unit, label: String, modifier: Modifier = Modifier, enabled: Boolean = true,
    placeholder: String = "", password: Boolean = false, keyboard: KeyboardOptions = KeyboardOptions.Default,
    actions: KeyboardActions = KeyboardActions.Default, leading: (@Composable () -> Unit)? = null,
    singleLine: Boolean = true, minLines: Int = 1, maxLines: Int = if (singleLine) 1 else Int.MAX_VALUE,
) {
    val colors = MaterialTheme.colorScheme
    OutlinedTextField(
        value, onChange, modifier, enabled = enabled, singleLine = singleLine, minLines = minLines, maxLines = maxLines,
        label = { Text(label) }, placeholder = if (placeholder.isBlank()) null else ({ Text(placeholder) }),
        leadingIcon = leading, shape = RoundedCornerShape(14.dp),
        visualTransformation = if (password) PasswordVisualTransformation() else androidx.compose.ui.text.input.VisualTransformation.None,
        keyboardOptions = keyboard, keyboardActions = actions,
        colors = OutlinedTextFieldDefaults.colors(
            focusedBorderColor = AccentA, unfocusedBorderColor = colors.outline,
            focusedContainerColor = colors.surfaceContainerLow, unfocusedContainerColor = colors.surfaceContainerLow,
            disabledContainerColor = colors.surfaceContainerLow, focusedLabelColor = AccentA,
        ),
    )
}

/** The music server: its own place in the app, browsed by folders like the card. */
@Composable
fun ServerScreen(vm: JukeViewModel) {
    var editing by rememberSaveable { mutableStateOf(false) }
    val connected = vm.serverStatus == "" && vm.server.isComplete
    val ready = vm.remote as? BrowseState.Ready
    Column(Modifier.fillMaxSize().padding(horizontal = 10.dp)) {
        Crumb(
            title = if (vm.searchQuery.isNotBlank()) stringResource(R.string.search) else vm.serverCrumbs.lastOrNull()?.name ?: stringResource(R.string.nav_server),
            subtitle = ready?.tracks?.size?.takeIf { it > 0 }?.let { stringResource(R.string.tracks, it) }.orEmpty(),
            canGoUp = vm.canGoUpRemote, onUp = { vm.remoteUp() },
        ) {
            if (vm.server.isComplete) SortKey(vm)
            if (vm.server.isComplete) Key(R.drawable.ic_gear, stringResource(R.string.server), { editing = !editing }, size = 44.dp, icon = 20.dp,
                tint = if (editing) AccentA else MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (editing || !vm.server.isComplete) {
            ServerForm(vm, onDone = { editing = false }, Modifier.padding(bottom = 12.dp))
        }
        if (vm.server.isComplete && !editing) {
            var text by remember(vm.searchQuery) { mutableStateOf(vm.searchQuery) }
            JukeField(
                text, { text = it; if (it.isBlank() && vm.searchQuery.isNotBlank()) vm.search("") },
                stringResource(R.string.search_songs), Modifier.fillMaxWidth().padding(bottom = 10.dp),
                keyboard = KeyboardOptions(imeAction = ImeAction.Search), actions = KeyboardActions(onSearch = { vm.search(text.trim()) }),
                leading = { JIcon(R.drawable.ic_search, tint = MaterialTheme.colorScheme.onSurfaceVariant, size = 19.dp) },
            )
            BrowseList(vm.remote, vm, onOpen = vm::openRemote, onRetry = vm::loadRemote) {
                EmptyState(R.drawable.ic_folder, stringResource(R.string.empty_folder), "")
            }
        } else if (!vm.server.isComplete && vm.remote is BrowseState.Idle) {
            Spacer(Modifier.weight(1f))
        }
        if (connected && !editing && vm.remote is BrowseState.Idle) Spacer(Modifier.weight(1f))
    }
}

@Composable
private fun ServerForm(vm: JukeViewModel, onDone: () -> Unit, modifier: Modifier = Modifier) {
    var url by rememberSaveable { mutableStateOf(vm.server.url) }
    var user by rememberSaveable { mutableStateOf(vm.server.user) }
    var password by rememberSaveable { mutableStateOf(vm.server.password) }
    Column(modifier.fillMaxWidth().chassis().padding(16.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionLabel(stringResource(R.string.server))
        Text(stringResource(R.string.connect_hint), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        JukeField(url, { url = it }, stringResource(R.string.server_url), Modifier.fillMaxWidth(), placeholder = "http://192.168.1.10:4040",
            keyboard = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Next))
        JukeField(user, { user = it }, stringResource(R.string.username), Modifier.fillMaxWidth(),
            keyboard = KeyboardOptions(imeAction = ImeAction.Next))
        JukeField(password, { password = it }, stringResource(R.string.password), Modifier.fillMaxWidth(), password = true,
            keyboard = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = ImeAction.Go),
            actions = KeyboardActions(onGo = { vm.connect(ServerConfig(url.trim(), user.trim(), password)); onDone() }))
        Row(verticalAlignment = Alignment.CenterVertically) {
            ActionKey(stringResource(R.string.connect), { vm.connect(ServerConfig(url.trim(), user.trim(), password)); onDone() },
                enabled = url.isNotBlank() && user.isNotBlank() && !vm.serverBusy)
            Spacer(Modifier.width(14.dp))
            when {
                vm.serverBusy -> CircularProgressIndicator(Modifier.size(20.dp), strokeWidth = 2.dp, color = AccentA)
                vm.serverStatus == "" -> Text(stringResource(R.string.connected), color = AccentA, style = MaterialTheme.typography.bodyMedium)
                vm.serverStatus != null -> Text(vm.serverStatus.orEmpty(), color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
