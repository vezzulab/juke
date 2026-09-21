package io.github.vezzulab.juke

import android.content.Context
import android.content.res.Resources
import android.net.Uri
import android.os.Build
import android.util.Log
import java.io.File
import java.io.PrintWriter
import java.io.StringWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * A small log file the person can read and send along with a problem report. Nothing leaves the phone by itself:
 * whatever is shown or copied goes through [redact] first (server address, login, passwords and tokens are hidden).
 */
object AppLog {
    private const val LIMIT = 256 * 1024L
    private var file: File? = null
    private val stamp = SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.US)
    private const val REPO = "https://github.com/vezzulab/juke"

    fun init(context: Context) {
        if (file != null) return
        file = File(context.filesDir, "juke.log")
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            e("crash", "Uncaught exception in ${thread.name}", error)
            previous?.uncaughtException(thread, error)
        }
        i("app", "---- Juke ${BuildConfig.VERSION_NAME} starting ----")
        summary().lines().forEach { i("app", it) }
    }

    @Synchronized
    private fun write(level: String, tag: String, message: String, error: Throwable?) {
        val target = file ?: return
        runCatching {
            if (target.length() > LIMIT) target.renameTo(File(target.path + ".1"))
            val trace = error?.let { StringWriter().also { w -> it.printStackTrace(PrintWriter(w)) }.toString() }.orEmpty()
            target.appendText("${stamp.format(Date())} $level $tag: $message\n${if (trace.isNotEmpty()) trace else ""}")
        }
    }

    fun i(tag: String, message: String) { Log.i(tag, message); write("INFO   ", tag, message, null) }
    fun w(tag: String, message: String, error: Throwable? = null) { Log.w(tag, message, error); write("WARNING", tag, message, error) }
    fun e(tag: String, message: String, error: Throwable? = null) { Log.e(tag, message, error); write("ERROR  ", tag, message, error) }

    fun summary(): String {
        val metrics = Resources.getSystem().displayMetrics
        return listOf(
            "Juke ${BuildConfig.VERSION_NAME} (${BuildConfig.VERSION_CODE})",
            "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT}) · ${Build.MANUFACTURER} ${Build.MODEL}",
            "Screen ${metrics.widthPixels}x${metrics.heightPixels} · ${metrics.densityDpi} dpi · ${Locale.getDefault().toLanguageTag()}",
        ).joinToString("\n")
    }

    private val querySecret = Regex("([?&;](?:p|t|s|u|pass|password|token|salt|apikey|api_key|key|auth)=)[^&\\s\"']+", RegexOption.IGNORE_CASE)
    private val urlLogin = Regex("(\\b[a-z][a-z0-9+.-]*://)[^/\\s:@]+:[^/\\s@]+@", RegexOption.IGNORE_CASE)

    /** Hide what should never be pasted into a public place. */
    fun redact(text: String, secrets: List<String> = emptyList()): String {
        var out = text
        secrets.filter { it.length >= 3 }.distinct().sortedByDescending { it.length }.forEach { out = out.replace(it, "<hidden>") }
        out = urlLogin.replace(out) { "${it.groupValues[1]}<hidden>@" }
        return querySecret.replace(out) { "${it.groupValues[1]}<hidden>" }
    }

    /** The newest part of the log, redacted. */
    fun read(secrets: List<String>, maxChars: Int = 60_000): String {
        val target = file ?: return ""
        val text = listOf(File(target.path + ".1"), target).filter { it.exists() }.joinToString("") { runCatching { it.readText() }.getOrDefault("") }
        val tail = if (text.length > maxChars) text.takeLast(maxChars).substringAfter('\n') else text
        return redact(tail, secrets)
    }

    fun secretsOf(server: io.github.vezzulab.juke.data.ServerConfig): List<String> =
        listOf(server.password, server.user, server.url, server.url.substringAfter("://").substringBefore('/'))

    fun issueUrl(title: String, body: String): String =
        "$REPO/issues/new?title=${Uri.encode(title)}&body=${Uri.encode(body)}"
}
