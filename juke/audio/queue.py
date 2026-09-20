"""Playback queue: a *context* (the list a track was started from) plus a
temporary user queue that always plays first.

* ``play_next``  inserts right after the current track (newest plays first).
* ``add_to_queue`` appends to the end of the user queue.
* When the user queue is empty, playback continues through the context.
"""

from __future__ import annotations

import random

HISTORY_LIMIT = 300


class PlayQueue:
    def __init__(self) -> None:
        self.original: list[int] = []      # context in list order
        self.order: list[int] = []         # context in play order (shuffled or not)
        self.cursor: int = -1              # position in ``order`` of the last context track
        self.user: list[int] = []          # temporary queue, plays before the context resumes
        self.current: int | None = None
        self.history: list[int] = []
        self.shuffle = False
        self.repeat = "off"                # off | all | one

    # -- building ----------------------------------------------------------------
    def set_context(self, ids: list[int], start_id: int) -> None:
        """Start playing ``start_id`` from a list; the user queue is kept."""
        self.original = list(ids)
        self.current = start_id
        self.history.clear()
        self._reorder(start_id)

    def _reorder(self, current: int | None) -> None:
        if self.shuffle:
            rest = [i for i in self.original if i != current]
            random.shuffle(rest)
            self.order = ([current] if current in self.original else []) + rest
        else:
            self.order = list(self.original)
        try:
            self.cursor = self.order.index(current) if current is not None else -1
        except ValueError:
            self.cursor = -1

    def set_shuffle(self, enabled: bool) -> None:
        if enabled == self.shuffle:
            return
        self.shuffle = enabled
        self._reorder(self._context_anchor())

    def _context_anchor(self) -> int | None:
        return self.order[self.cursor] if 0 <= self.cursor < len(self.order) else None

    def play_next(self, ids: list[int]) -> None:
        self.user[0:0] = ids

    def add_to_queue(self, ids: list[int]) -> None:
        self.user.extend(ids)

    def remove_from_queue(self, ids: list[int]) -> None:
        for track_id in ids:
            if track_id in self.user:
                self.user.remove(track_id)

    def clear_user_queue(self) -> None:
        self.user.clear()

    def discard_missing(self, existing: set[int]) -> None:
        """Forget ids that vanished from the library."""
        self.user = [i for i in self.user if i in existing]
        self.original = [i for i in self.original if i in existing]
        anchor = self.current if self.current in existing else self._context_anchor()
        self._reorder(anchor if anchor in existing else None)

    # -- navigation -----------------------------------------------------------------
    def _remember(self) -> None:
        if self.current is not None:
            self.history.append(self.current)
            del self.history[:-HISTORY_LIMIT]

    def next(self, auto: bool = False) -> int | None:
        """The id to play after the current one, or None when playback should stop."""
        if self.current is not None and auto and self.repeat == "one":
            return self.current
        if self.user:
            self._remember()
            self.current = self.user.pop(0)
            return self.current
        if not self.order:
            return None
        if self.cursor + 1 < len(self.order):
            self._remember()
            self.cursor += 1
        elif self.repeat == "all" or (not auto and self.repeat == "one"):
            self._remember()
            if self.shuffle:
                self._reorder(None)
            self.cursor = 0
        else:
            return None
        self.current = self.order[self.cursor]
        return self.current

    def previous(self) -> int | None:
        """Step back through history; with none left, the caller restarts the track."""
        if self.history:
            self.current = self.history.pop()
            if self.current in self.order:
                self.cursor = self.order.index(self.current)
        return self.current

    def upcoming(self) -> list[int]:
        """User queue first, then the rest of the context."""
        return self.user + self.order[self.cursor + 1:]

    def view(self) -> list[int]:
        """Now playing + upcoming, as shown in the "Current Queue" list."""
        head = [self.current] if self.current is not None else []
        return head + self.upcoming()
