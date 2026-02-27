import asyncio
from collections.abc import Callable, Coroutine

from PySide6.QtCore import QThread, Signal


class AsyncWorker(QThread):
    """Runs an async coroutine in a background thread with its own event loop."""

    finished = Signal(object)
    error = Signal(str)

    def __init__(self, coro_factory: Callable[..., Coroutine], *args, **kwargs):
        super().__init__()
        self._coro_factory = coro_factory
        self._args = args
        self._kwargs = kwargs

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(self._coro_factory(*self._args, **self._kwargs))
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            loop.close()
