package io.github.vezzulab.juke.ui

import android.graphics.BitmapFactory
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.withStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.vezzulab.juke.R
import io.github.vezzulab.juke.data.Manual
import io.github.vezzulab.juke.data.ManualBlock
import io.github.vezzulab.juke.data.ManualChapter

/**
 * The manual, inside the app: an index of chapters and sections, and a page per chapter with Previous / Next, like a book.
 * It follows the language of the app (the text is `manual-en.md` / `manual-es.md` in the assets).
 */
@Composable
fun ManualScreen(onClose: () -> Unit) {
    val context = LocalContext.current
    val language = LocalConfiguration.current.locales[0].language
    val chapters = remember(language) { Manual.load(context, language) }
    var open by rememberSaveable { mutableStateOf(-1) }            // -1: the index
    var section by rememberSaveable { mutableStateOf("") }         // a section to scroll to when a chapter opens
    BackHandler(enabled = open >= 0) { open = -1 }

    if (open < 0 || open >= chapters.size) {
        ManualIndex(chapters, onClose) { chapter, heading -> open = chapter; section = heading }
    } else {
        ManualPage(chapters, open, section, onIndex = { open = -1 }, onGo = { open = it; section = "" })
    }
}

@Composable
private fun ManualIndex(chapters: List<ManualChapter>, onClose: () -> Unit, onOpen: (Int, String) -> Unit) {
    val colors = MaterialTheme.colorScheme
    Column(Modifier.fillMaxSize().padding(horizontal = 10.dp)) {
        Crumb(stringResource(R.string.manual_title), "", canGoUp = true, onUp = onClose)
        Text(stringResource(R.string.manual_contents), Modifier.padding(start = 6.dp, bottom = 8.dp),
            color = colors.onSurfaceVariant, style = MaterialTheme.typography.labelMedium)
        LazyColumn(Modifier.fillMaxSize().widthIn(max = 640.dp), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            itemsIndexed(chapters) { number, chapter ->
                Column(Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                    Text("${number + 1}.  ${chapter.title}",
                        Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).clickable { onOpen(number, "") }.padding(horizontal = 10.dp, vertical = 10.dp),
                        color = colors.onSurface, style = MaterialTheme.typography.titleSmall)
                    for (heading in chapter.sections) {
                        Text(heading,
                            Modifier.fillMaxWidth().clip(RoundedCornerShape(8.dp)).clickable { onOpen(number, heading) }.padding(start = 30.dp, end = 10.dp, top = 6.dp, bottom = 6.dp),
                            color = colors.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
            item { Spacer(Modifier.height(24.dp)) }
        }
    }
}

@Composable
private fun ManualPage(chapters: List<ManualChapter>, number: Int, section: String, onIndex: () -> Unit, onGo: (Int) -> Unit) {
    val colors = MaterialTheme.colorScheme
    val chapter = chapters[number]
    val list = rememberLazyListState()
    LaunchedEffect(number, section) {
        val target = if (section.isEmpty()) 0 else chapter.blocks.indexOfFirst { it is ManualBlock.Heading && it.text == section }.coerceAtLeast(0)
        list.scrollToItem(target)
    }
    Column(Modifier.fillMaxSize().padding(horizontal = 10.dp)) {
        Crumb("${number + 1}.  ${chapter.title}", "", canGoUp = true, onUp = onIndex)
        LazyColumn(Modifier.weight(1f).fillMaxWidth().widthIn(max = 640.dp), list, verticalArrangement = Arrangement.spacedBy(12.dp),
            contentPadding = PaddingValues(horizontal = 6.dp, vertical = 8.dp)) {
            itemsIndexed(chapter.blocks) { _, block -> BlockView(block) }
        }
        Row(Modifier.fillMaxWidth().padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
            ActionKey(stringResource(R.string.manual_previous), { onGo(number - 1) }, Modifier.weight(1f), accent = false, enabled = number > 0)
            Text("${number + 1} / ${chapters.size}", color = colors.onSurfaceVariant, style = MaterialTheme.typography.labelMedium)
            ActionKey(stringResource(R.string.manual_next), { onGo(number + 1) }, Modifier.weight(1f), accent = false, enabled = number < chapters.size - 1)
        }
    }
}

@Composable
private fun BlockView(block: ManualBlock) {
    val colors = MaterialTheme.colorScheme
    when (block) {
        is ManualBlock.Heading -> Text(styled(block.text), Modifier.padding(top = if (block.level == 2) 10.dp else 4.dp),
            color = colors.onSurface, style = if (block.level == 2) MaterialTheme.typography.titleMedium else MaterialTheme.typography.titleSmall)
        is ManualBlock.Paragraph -> Text(styled(block.text), color = colors.onSurface, style = MaterialTheme.typography.bodyMedium.copy(lineHeight = 22.sp))
        is ManualBlock.Bullets -> Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            block.items.forEachIndexed { index, item ->
                Row {
                    Text(if (block.ordered) "${index + 1}." else "•", Modifier.width(24.dp), color = colors.onSurfaceVariant, style = MaterialTheme.typography.bodyMedium)
                    Text(styled(item), Modifier.weight(1f), color = colors.onSurface, style = MaterialTheme.typography.bodyMedium.copy(lineHeight = 22.sp))
                }
            }
        }
        is ManualBlock.Table -> Column(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(colors.surfaceContainerLow)) {
            TableRow(block.header, header = true)
            block.rows.forEach { TableRow(it, header = false) }
        }
        is ManualBlock.Code -> Text(block.text, Modifier.fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(colors.surfaceContainerHigh).padding(12.dp),
            color = colors.onSurface, fontFamily = FontFamily.Monospace, fontSize = 12.sp)
        is ManualBlock.Image -> ManualImage(block)
    }
}

@Composable
private fun TableRow(cells: List<String>, header: Boolean) {
    val colors = MaterialTheme.colorScheme
    Row(Modifier.fillMaxWidth().then(if (header) Modifier.background(colors.surfaceContainerHigh) else Modifier).padding(horizontal = 10.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        cells.forEachIndexed { column, cell ->
            Text(styled(cell), Modifier.weight(if (column == cells.lastIndex && cells.size > 2) 2f else 1f),
                color = if (header) colors.onSurfaceVariant else colors.onSurface,
                style = MaterialTheme.typography.bodySmall.copy(fontWeight = if (header) FontWeight.SemiBold else FontWeight.Normal))
        }
    }
}

@Composable
private fun ManualImage(block: ManualBlock.Image) {
    val context = LocalContext.current
    val bitmap = remember(block.path) {
        runCatching { context.assets.open(block.path).use { BitmapFactory.decodeStream(it) }?.asImageBitmap() }.getOrNull()
    }
    if (bitmap != null) {
        Image(bitmap, block.alt, Modifier.fillMaxWidth().widthIn(max = 360.dp).clip(RoundedCornerShape(14.dp)), contentScale = ContentScale.FillWidth)
    }
}

/** **bold**, *italic* and `code` inside a line of the manual. */
@Composable
private fun styled(text: String): AnnotatedString {
    val code = MaterialTheme.colorScheme.surfaceContainerHigh
    return buildAnnotatedString {
        var i = 0
        while (i < text.length) {
            when {
                text.startsWith("**", i) -> {
                    val end = text.indexOf("**", i + 2)
                    if (end > 0) { withStyle(SpanStyle(fontWeight = FontWeight.Bold)) { append(text.substring(i + 2, end)) }; i = end + 2 } else { append(text[i]); i++ }
                }
                text[i] == '`' -> {
                    val end = text.indexOf('`', i + 1)
                    if (end > 0) { withStyle(SpanStyle(fontFamily = FontFamily.Monospace, background = code)) { append(text.substring(i + 1, end)) }; i = end + 1 } else { append(text[i]); i++ }
                }
                text[i] == '*' -> {
                    val end = text.indexOf('*', i + 1)
                    if (end > 0) { withStyle(SpanStyle(fontStyle = FontStyle.Italic)) { append(text.substring(i + 1, end)) }; i = end + 1 } else { append(text[i]); i++ }
                }
                else -> { append(text[i]); i++ }
            }
        }
    }
}
