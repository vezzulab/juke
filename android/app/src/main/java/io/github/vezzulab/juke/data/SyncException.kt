package io.github.vezzulab.juke.data

import java.io.IOException

/** [kind]: server (unreachable, or not a Juke sync server), denied, none, changed, big, soon, busy, full, corrupt, url, code. */
class SyncException(val kind: String, message: String = kind, val updated: Long = 0) : IOException(message)
