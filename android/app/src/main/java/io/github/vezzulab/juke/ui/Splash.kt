package io.github.vezzulab.juke.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.vezzulab.juke.R
import kotlinx.coroutines.delay

/** What the app opens with: the record, the name, and then it gets out of the way. */
@Composable
fun Splash(onDone: () -> Unit) {
    var shown by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) { shown = true; delay(1500); onDone() }
    val enter by animateFloatAsState(if (shown) 1f else 0f, tween(650), label = "splash")
    Box(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background), Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            androidx.compose.foundation.Image(
                painterResource(R.drawable.ic_launcher_foreground), null,
                Modifier.size(150.dp).scale(0.86f + 0.14f * enter).alpha(enter)
                    .shadow(40.dp, CircleShape, clip = false, ambientColor = AccentA, spotColor = AccentB),
            )
            Spacer(Modifier.height(18.dp))
            androidx.compose.foundation.Image(
                painterResource(R.drawable.ic_wordmark), stringResource(R.string.app_name),
                Modifier.width(172.dp).alpha(enter),
            )
            Spacer(Modifier.height(10.dp))
            Box(Modifier.width((90 * enter).dp).height(2.dp).clip(CircleShape).background(AccentBrush))
            Spacer(Modifier.height(12.dp))
            Text(
                stringResource(R.string.tagline), Modifier.alpha(enter * 0.8f),
                style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
