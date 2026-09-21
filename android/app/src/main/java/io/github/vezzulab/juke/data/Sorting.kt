package io.github.vezzulab.juke.data

/** How folders and songs are listed: as the card or the server gives them, A to Z, or Z to A (numbers count as numbers). */
enum class SortOrder { Original, AZ, ZA }

private val split = Regex("(?<=\\d)(?=\\D)|(?<=\\D)(?=\\d)")

/** "Album 2" comes before "Album 10"; capitals and accents do not decide the order. */
fun naturalCompare(a: String, b: String): Int {
    val ta = a.trim().split(split).filter { it.isNotEmpty() }
    val tb = b.trim().split(split).filter { it.isNotEmpty() }
    for (i in 0 until minOf(ta.size, tb.size)) {
        val x = ta[i]; val y = tb[i]
        val c = if (x[0].isDigit() && y[0].isDigit()) x.toBigInteger().compareTo(y.toBigInteger()) else x.compareTo(y, ignoreCase = true)
        if (c != 0) return c
    }
    return ta.size - tb.size
}

fun <T> List<T>.sortedBy(order: SortOrder, name: (T) -> String): List<T> = when (order) {
    SortOrder.Original -> this
    SortOrder.AZ -> sortedWith { x, y -> naturalCompare(name(x), name(y)) }
    SortOrder.ZA -> sortedWith { x, y -> naturalCompare(name(y), name(x)) }
}
