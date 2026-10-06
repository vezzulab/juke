package io.github.vezzulab.juke.data

import android.content.Context

/**
 * The manual: the same Markdown files as Juke for Linux (`juke/assets/manual/manual-en.md`, `manual-es.md`, copied into the
 * app's assets at build time). Parts that only apply to one system sit between `<!--linux-->` … `<!--/linux-->` (or
 * `android`); this app keeps its own and drops the other's. Chapters start with `# N. Title`, sections with `## Title`.
 */
data class ManualChapter(val title: String, val sections: List<String>, val blocks: List<ManualBlock>)

sealed interface ManualBlock {
    data class Heading(val level: Int, val text: String) : ManualBlock
    data class Paragraph(val text: String) : ManualBlock
    data class Bullets(val items: List<String>, val ordered: Boolean) : ManualBlock
    data class Table(val header: List<String>, val rows: List<List<String>>) : ManualBlock
    data class Image(val path: String, val alt: String) : ManualBlock
    data class Code(val text: String) : ManualBlock
}

object Manual {
    private val tag = Regex("<!--(linux|android)-->(.*?)<!--/\\1-->", RegexOption.DOT_MATCHES_ALL)
    private val number = Regex("^\\s*\\d+\\.\\s*")
    private val ordered = Regex("^\\d+\\.\\s+(.*)$")
    private val image = Regex("^!\\[([^\\]]*)]\\(([^)]+)\\)\\s*$")

    fun load(context: Context, language: String): List<ManualChapter> {
        val code = if (language == "es") "es" else "en"
        val raw = context.assets.open("manual-$code.md").bufferedReader().use { it.readText() }
        return parse(raw)
    }

    /** What belongs to this system and to everyone; the other system's parts are gone. */
    fun forPlatform(text: String, platform: String = "android"): String =
        tag.replace(text) { if (it.groupValues[1] == platform) it.groupValues[2] else "" }

    fun parse(raw: String, platform: String = "android"): List<ManualChapter> {
        val chapters = mutableListOf<ManualChapter>()
        var title: String? = null
        var lines = mutableListOf<String>()
        fun close() {
            val t = title ?: return
            val blocks = blocks(lines)
            if (blocks.isNotEmpty()) chapters += ManualChapter(t, blocks.filterIsInstance<ManualBlock.Heading>().filter { it.level == 2 }.map { it.text }, blocks)
        }
        var inCode = false
        for (line in forPlatform(raw, platform).lines()) {
            if (line.startsWith("```")) inCode = !inCode
            if (!inCode && line.startsWith("# ")) {
                close()
                title = number.replace(line.removePrefix("# "), "").trim()
                lines = mutableListOf()
            } else if (title != null) lines += line
        }
        close()
        return chapters
    }

    private fun blocks(lines: List<String>): List<ManualBlock> {
        val out = mutableListOf<ManualBlock>()
        var i = 0
        while (i < lines.size) {
            val line = lines[i]
            val t = line.trim()
            when {
                t.isEmpty() || t == "---" -> i++
                t.startsWith("```") -> {
                    val code = StringBuilder()
                    i++
                    while (i < lines.size && !lines[i].trim().startsWith("```")) { code.appendLine(lines[i]); i++ }
                    i++
                    out += ManualBlock.Code(code.toString().trimEnd())
                }
                t.startsWith("### ") -> { out += ManualBlock.Heading(3, t.removePrefix("### ")); i++ }
                t.startsWith("## ") -> { out += ManualBlock.Heading(2, t.removePrefix("## ")); i++ }
                image.matches(t) -> { val m = image.find(t)!!; out += ManualBlock.Image(m.groupValues[2], m.groupValues[1]); i++ }
                t.startsWith("|") -> {
                    val rows = mutableListOf<List<String>>()
                    while (i < lines.size && lines[i].trim().startsWith("|")) {
                        val cells = lines[i].trim().trim('|').split("|").map { it.trim() }
                        if (!cells.all { c -> c.isNotEmpty() && c.all { ch -> ch == '-' || ch == ':' } }) rows += cells   // skip the --- row
                        i++
                    }
                    if (rows.isNotEmpty()) out += ManualBlock.Table(rows.first(), rows.drop(1))
                }
                t.startsWith("- ") || t.startsWith("* ") || ordered.matches(t) -> {
                    val numbered = ordered.matches(t)
                    val items = mutableListOf<String>()
                    while (i < lines.size) {
                        val l = lines[i].trim()
                        val isItem = l.startsWith("- ") || l.startsWith("* ") || ordered.matches(l)
                        if (isItem) items += (ordered.find(l)?.groupValues?.get(1) ?: l.drop(2)).trim()
                        else if (l.isNotEmpty() && lines[i].startsWith(" ") && items.isNotEmpty()) items[items.lastIndex] = items.last() + " " + l   // a wrapped line
                        else break
                        i++
                    }
                    out += ManualBlock.Bullets(items, numbered)
                }
                else -> {
                    val text = StringBuilder(t)
                    i++
                    while (i < lines.size) {
                        val l = lines[i].trim()
                        if (l.isEmpty() || l.startsWith("#") || l.startsWith("|") || l.startsWith("- ") || l.startsWith("* ") ||
                            l.startsWith("```") || ordered.matches(l) || image.matches(l)) break
                        text.append(' ').append(l)
                        i++
                    }
                    out += ManualBlock.Paragraph(text.toString())
                }
            }
        }
        return out
    }
}
