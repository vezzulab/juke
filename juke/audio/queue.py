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
    def set_context(self, ids: list[int], start_id: int, index: int | None = None) -> None:
        """Start playing ``start_id`` from a list; the user queue is kept. ``index``: which row it was picked from, for a
        song that is in the list more than once."""
        self.original = list(ids)
        self.current = start_id
        self.history.clear()
        self._reorder(start_id)
        if index is not None and not self.shuffle and 0 <= index < len(self.order) and self.order[index] == start_id:
            self.cursor = index

    def update_context(self, ids: list[int]) -> None:
        """The list this queue is playing from changed (a song taken out or put in): follow it, keeping the place.

        Without this, a song deleted from the playlist while it plays would still come up when its turn arrives."""
        counts: dict[int, int] = {}
        for track_id in ids:
            counts[track_id] = counts.get(track_id, 0) + 1
        kept: list[int] = []
        cursor = -1
        for position, track_id in enumerate(self.order):
            if counts.get(track_id, 0) > 0:                  # one copy per copy still in the list
                counts[track_id] -= 1
                kept.append(track_id)
            if position == self.cursor:
                cursor = len(kept) - 1
        for track_id in ids:                                  # songs put in meanwhile wait at the end
            if counts.get(track_id, 0) > 0:
                counts[track_id] -= 1
                kept.append(track_id)
        self.original = list(ids)
        self.order = kept
        self.cursor = cursor

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

    def move_in_queue(self, source: int, target: int) -> None:
        """Take the song at ``source`` of the user queue and put it where ``target`` is (indexes into ``user``)."""
        if not (0 <= source < len(self.user)):
            return
        target = max(0, min(target, len(self.user) - 1))
        self.user.insert(target, self.user.pop(source))

    def peek_next(self) -> int | None:
        """The song that comes after the current one, if it is already known (not with shuffle's end-of-list reshuffle
        or repeat-one, where the answer is the song itself)."""
        if self.repeat == "one":
            return self.current
        if self.user:
            return self.user[0]
        if self.cursor + 1 < len(self.order):
            return self.order[self.cursor + 1]
        return None

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
                if len(self.order) > 1 and self.order[0] == self.current:     # not the song that just played, twice in a row
                    swap = random.randrange(1, len(self.order))
                    self.order[0], self.order[swap] = self.order[swap], self.order[0]
            self.cursor = 0
        else:
            return None
        self.current = self.order[self.cursor]
        return self.current

    def has_next(self, auto: bool = True) -> bool:
        """Would ``next`` find something to play? (Without moving anything.)"""
        if self.current is not None and auto and self.repeat == "one":
            return True
        return bool(self.user) or (bool(self.order) and (self.cursor + 1 < len(self.order) or self.repeat == "all"))

    def can_previous(self) -> bool:
        """Is there a song before this one: one played earlier, or one above it in the list?"""
        return bool(self.history) or self.cursor > 0 or (self.repeat == "all" and len(self.order) > 1)

    def previous(self) -> int | None:
        """The song before this one. After a song was picked from the middle of a list there is no history, so the
        song above it in the list is next; with none left, the caller restarts the track."""
        if self.history:
            self.current = self.history.pop()
            if self.current in self.order:
                self.cursor = self.order.index(self.current)
        elif self.cursor > 0:
            self.cursor -= 1
            self.current = self.order[self.cursor]
        elif self.repeat == "all" and len(self.order) > 1:
            self.cursor = len(self.order) - 1
            self.current = self.order[self.cursor]
        return self.current

    def upcoming(self) -> list[int]:
        """User queue first, then the rest of the context."""
        return self.user + self.order[self.cursor + 1:]

    def view(self) -> list[int]:
        """Now playing + upcoming, as shown in the "Current Queue" list."""
        head = [self.current] if self.current is not None else []
        return head + self.upcoming()
