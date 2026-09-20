"""Run coroutines on a background QThread and report back with signals."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from PySide6.QtCore import QThread, Signal


class AsyncWorker(QThread):
    """Runs ``factory(progress_cb)`` (returning a coroutine) in its own event loop."""

    result = Signal(object)
    failed = Signal(str)
    progress = Signal(int)

    def __init__(self, factory: Callable[[Callable[[int], None]], Awaitable[Any]], parent=None) -> None:
        super().__init__(parent)
        self._factory = factory
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None

    def cancel(self) -> None:
        loop, task = self._loop, self._task
        if loop is not None and task is not None and not loop.is_closed():
            loop.call_soon_threadsafe(task.cancel)

    def run(self) -> None:  # noqa: D401 - QThread entry point
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            self._task = loop.create_task(self._factory(self.progress.emit))
            value = loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            self.failed.emit("cancelled")
        except Exception as exc:
            self.failed.emit(str(exc) or exc.__class__.__name__)
        else:
            self.result.emit(value)
        finally:
            loop.close()
