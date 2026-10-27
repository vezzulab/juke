package io.github.vezzulab.juke.data
// Copyright © 2026 Vezzu Studio. Part of Juke, under the Juke License 1.0 (see LICENSE).

import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

/** One connection pool for the whole app; each part asks for its own timeouts. */
object Http {
    private val shared = OkHttpClient()

    fun client(connectSeconds: Long, readSeconds: Long): OkHttpClient =
        shared.newBuilder().connectTimeout(connectSeconds, TimeUnit.SECONDS).readTimeout(readSeconds, TimeUnit.SECONDS).build()
}
