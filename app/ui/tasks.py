"""Run a function in the thread pool; callbacks are delivered on the GUI thread."""
from __future__ import annotations
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

_alive: set = set()


class _Signals(QObject):
    progress = Signal(str, float, float)
    done = Signal(object)
    failed = Signal(object)


class _Relay(QObject):
    """Lives in the GUI thread, so queued signals land here."""
    def __init__(self, on_done, on_fail, on_progress, task):
        super().__init__()
        self._d, self._f, self._p, self._t = on_done, on_fail, on_progress, task

    def _finish(self):
        _alive.discard(self._t)
        _alive.discard(self)

    @Slot(object)
    def done(self, r):
        self._finish()
        if self._d:
            self._d(r)

    @Slot(object)
    def failed(self, e):
        self._finish()
        if self._f:
            self._f(e)

    @Slot(str, float, float)
    def progress(self, label, a, b):
        if self._p:
            self._p(label, a, b)


class _Task(QRunnable):
    def __init__(self, fn, args, with_progress):
        super().__init__()
        self.fn, self.args, self.wp = fn, args, with_progress
        self.signals = _Signals()

    def run(self):
        try:
            res = self.fn(self.signals.progress.emit, *self.args) if self.wp else self.fn(*self.args)
        except Exception as e:  # noqa: BLE001
            self.signals.failed.emit(e)
        else:
            self.signals.done.emit(res)


def run_task(fn, *args, on_done=None, on_fail=None, on_progress=None, with_progress=False):
    t = _Task(fn, args, with_progress)
    relay = _Relay(on_done, on_fail, on_progress, t)
    t.signals.done.connect(relay.done)
    t.signals.failed.connect(relay.failed)
    t.signals.progress.connect(relay.progress)
    _alive.update((t, relay))
    QThreadPool.globalInstance().start(t)
