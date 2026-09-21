package io.github.vezzulab.juke.data

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.Settings
import androidx.core.content.FileProvider
import io.github.vezzulab.juke.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

/** What GitHub says the newest release is, and what it would replace. */
data class UpdateRelease(
    val version: String, val notes: String, val pageUrl: String,
    val apkUrl: String, val apkSize: Long, val apkSha256: String, val installedSha256: String,
) {
    /** The same version number with a different file: a fix published without raising the version, told apart by the file's SHA-256. */
    val isRebuild get() = apkSha256.isNotBlank() && installedSha256.isNotBlank() && apkSha256 != installedSha256 && !Updater.isNewer(version, BuildConfig.VERSION_NAME)

    /** What "Later" and "Skip" remember: the version, plus the build when it is a rebuild of the same version. */
    val key get() = if (isRebuild) "$version+${apkSha256.take(8)}" else version
}

/**
 * Update check against GitHub Releases, the same idea as Juke for Linux: it looks at start and every 30 minutes, tells
 * you what changed, and installs only what you accept, after checking the file against the SHA-256 GitHub publishes.
 * The only things sent are the program name and version in the User-Agent.
 */
object Updater {
    private const val API = "https://api.github.com/repos/vezzulab/juke/releases/latest"
    const val RECHECK_MS = 30 * 60 * 1000L
    const val SNOOZE_MS = 24 * 60 * 60 * 1000L
    private val client = OkHttpClient.Builder().connectTimeout(15, TimeUnit.SECONDS).readTimeout(60, TimeUnit.SECONDS).build()
    private val agent get() = "Juke-Android/${BuildConfig.VERSION_NAME}"

    fun parse(text: String): List<Int>? =
        Regex("^\\s*v?(\\d+(?:\\.\\d+){0,3})").find(text)?.groupValues?.get(1)?.split(".")?.map { it.toInt() }

    fun isNewer(candidate: String, current: String = BuildConfig.VERSION_NAME): Boolean {
        val a = parse(candidate) ?: return false
        val b = parse(current) ?: return false
        for (i in 0 until maxOf(a.size, b.size)) {
            val x = a.getOrElse(i) { 0 }; val y = b.getOrElse(i) { 0 }
            if (x != y) return x > y
        }
        return false
    }

    fun isUpdate(r: UpdateRelease?): Boolean = r != null && (isNewer(r.version) || r.isRebuild)

    /** SHA-256 of the app that is running: its own installed file. */
    fun installedSha256(context: Context): String = runCatching { sha256(File(context.applicationInfo.sourceDir)) }.getOrDefault("")

    fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input -> val buffer = ByteArray(1 shl 16); while (true) { val n = input.read(buffer); if (n < 0) break; digest.update(buffer, 0, n) } }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    /** The newest stable release with an APK attached, or null if there is none. */
    suspend fun latest(context: Context): UpdateRelease? = withContext(Dispatchers.IO) {
        val request = Request.Builder().url(API).header("Accept", "application/vnd.github+json").header("User-Agent", agent).build()
        val body = client.newCall(request).execute().use { r ->
            if (r.code == 404) return@withContext null
            if (!r.isSuccessful) throw IOException("HTTP ${r.code}")
            r.body?.string().orEmpty()
        }
        val json = JSONObject(body)
        if (json.optBoolean("draft") || json.optBoolean("prerelease")) return@withContext null
        val tag = json.optString("tag_name")
        val version = parse(tag)?.joinToString(".") ?: return@withContext null
        val assets = json.optJSONArray("assets")
        var url = ""; var size = 0L; var sha = ""
        for (i in 0 until (assets?.length() ?: 0)) {
            val asset = assets!!.getJSONObject(i)
            if (Regex("^Juke-.*\\.apk$").matches(asset.optString("name"))) {
                url = asset.optString("browser_download_url"); size = asset.optLong("size"); sha = asset.optString("digest").removePrefix("sha256:").lowercase()
            }
        }
        if (url.isBlank()) return@withContext null
        UpdateRelease(version, json.optString("body").trim(), json.optString("html_url"), url, size, sha, installedSha256(context))
    }

    /** Downloads the APK next to the app's cache and checks it against the published SHA-256. Throws if anything is off. */
    suspend fun download(context: Context, release: UpdateRelease, onProgress: (Int) -> Unit): File = withContext(Dispatchers.IO) {
        val dir = File(context.cacheDir, "updates").apply { mkdirs(); listFiles()?.forEach { it.delete() } }
        val target = File(dir, "Juke-update.apk")
        val request = Request.Builder().url(release.apkUrl).header("User-Agent", agent).build()
        client.newCall(request).execute().use { r ->
            if (!r.isSuccessful) throw IOException("HTTP ${r.code}")
            val total = r.body?.contentLength()?.takeIf { it > 0 } ?: release.apkSize
            var done = 0L; var last = -1
            r.body!!.byteStream().use { input ->
                target.outputStream().use { out ->
                    val buffer = ByteArray(1 shl 16)
                    while (true) {
                        val n = input.read(buffer); if (n < 0) break
                        out.write(buffer, 0, n); done += n
                        val percent = if (total > 0) (done * 100 / total).toInt() else 0
                        if (percent != last) { last = percent; onProgress(percent) }
                    }
                }
            }
            if (release.apkSize > 0 && done != release.apkSize) { target.delete(); throw IOException("incomplete") }
        }
        if (release.apkSha256.isNotBlank() && sha256(target) != release.apkSha256) { target.delete(); throw IOException("checksum") }
        target
    }

    fun canInstall(context: Context): Boolean = context.packageManager.canRequestPackageInstalls()

    /** Opens the page where the person allows Juke to install apps. */
    fun askPermission(context: Context) {
        context.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }

    /** Hands the APK to Android's installer. False when Juke is not yet allowed to install: the settings page for that is opened instead. */
    fun install(context: Context, apk: File): Boolean {
        if (!context.packageManager.canRequestPackageInstalls()) {
            context.startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}")).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            return false
        }
        val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", apk)
        context.startActivity(Intent(Intent.ACTION_VIEW).setDataAndType(uri, "application/vnd.android.package-archive")
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK))
        return true
    }

    /** The release notes in the reader's language (they are written in English, then "## En español"), as plain text. */
    fun plainNotes(body: String, spanish: Boolean): String {
        val marker = Regex("(?m)^#+\\s*En espa[ñn]ol\\s*$")
        val split = marker.find(body)
        val part = when {
            split == null -> body
            spanish -> body.substring(split.range.last + 1)
            else -> body.substring(0, split.range.first)
        }
        return part.lines().map { it.trimEnd() }
            .filterNot { it.trim() == "---" }
            .joinToString("\n") {
                it.replace(Regex("^#+\\s*"), "").replace(Regex("\\[([^\\]]+)]\\([^)]*\\)"), "$1").replace("**", "").replace("`", "").replace(Regex("(?<!\\w)\\*([^*\\n]+)\\*"), "$1")
                    .replace(Regex("^\\s*[-*]\\s+"), "•  ")
            }.replace(Regex("\n{3,}"), "\n\n").trim()
    }
}
