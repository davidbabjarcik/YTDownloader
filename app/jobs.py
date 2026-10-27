"""Download queue (Qt side): schedules Pipeline runs, max N in parallel."""
from __future__ import annotations
import logging
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from .errors import AppError, Cancelled, classify
from .models import JobState
from .pipeline import Pipeline


class Job:
    def __init__(self, spec, settings, tools):
        self.id = uuid.uuid4().hex
        self.spec, self.settings, self.tools = spec, settings, tools
        self.reset()

    def reset(self):
        self.state = JobState.WAITING
        self.percent = 0.0
        self.speed = self.eta = self.size = ""
        self.message = self.detail = ""
        self.result: Path | None = None
        self.started = False
        self.pipeline = None
        self.runner = None

    @property
    def title(self) -> str:
        return self.spec.entry.title


class _Sig(QObject):
    state = Signal(object, object)
    progress = Signal(object, float, str, str, str)
    done = Signal(object, str, str)
    failed = Signal(object, str, str)
    cancelled = Signal(object)


class _Runner(QRunnable):
    def __init__(self, job: Job):
        super().__init__()
        self.job = job
        self.sig = _Sig()
        self.setAutoDelete(False)

    def run(self):
        job, sig = self.job, self.sig
        pipe = job.pipeline
        pipe.on_state = lambda s: sig.state.emit(job, s)
        pipe.on_progress = lambda p, sp, e, sz: sig.progress.emit(job, p, sp, e, sz)
        try:
            path = pipe.run()
            sig.done.emit(job, str(path), "; ".join(pipe.warnings))
        except Cancelled:
            sig.cancelled.emit(job)
        except AppError as e:
            sig.failed.emit(job, e.message, e.detail)
        except Exception as e:  # noqa: BLE001 - never crash the app
            logging.exception("job crashed")
            err = classify(str(e))
            sig.failed.emit(job, err.message, err.detail or str(e))


class QueueManager(QObject):
    job_added = Signal(object)
    job_changed = Signal(object)
    jobs_removed = Signal(list)
    batch_finished = Signal(list)

    def __init__(self, get_settings, parent=None):
        super().__init__(parent)
        self.get_settings = get_settings
        self.jobs: list[Job] = []
        self.batch: list[Job] = []
        self._batch_done = True
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(16)

    # -- public API
    def enqueue(self, specs, settings, tools) -> None:
        if not self.batch or all(j.state.finished for j in self.batch):
            self.batch = []
        self._batch_done = False
        for spec in specs:
            job = Job(spec, settings, tools)
            self.jobs.append(job)
            self.batch.append(job)
            self.job_added.emit(job)
        self._pump()

    def cancel(self, job: Job) -> None:
        if job.state.finished:
            return
        if not job.started:
            job.state = JobState.CANCELLED
            self.job_changed.emit(job)
            self._after()
        elif job.pipeline:
            job.pipeline.cancel()

    def retry(self, job: Job, tools) -> None:
        if not job.state.finished or job.state == JobState.COMPLETED:
            return
        job.tools = tools
        job.reset()
        if job not in self.batch:
            self.batch.append(job)
        self._batch_done = False
        self.job_changed.emit(job)
        self._pump()

    def clear_finished(self) -> None:
        gone = [j for j in self.jobs if j.state.finished]
        self.jobs = [j for j in self.jobs if not j.state.finished]
        self.batch = [j for j in self.batch if not j.state.finished]
        if gone:
            self.jobs_removed.emit(gone)

    # -- internals
    def _running(self) -> int:
        return sum(1 for j in self.jobs if j.started and not j.state.finished)

    def _pump(self) -> None:
        limit = max(1, self.get_settings().max_parallel)
        for job in self.jobs:
            if self._running() >= limit:
                break
            if job.state == JobState.WAITING and not job.started:
                self._start(job)

    def _start(self, job: Job) -> None:
        job.started = True
        job.state = JobState.DOWNLOADING
        job.pipeline = Pipeline(job.spec, job.settings, job.tools)
        job.runner = _Runner(job)
        s = job.runner.sig
        s.state.connect(self._on_state)
        s.progress.connect(self._on_progress)
        s.done.connect(self._on_done)
        s.failed.connect(self._on_failed)
        s.cancelled.connect(self._on_cancelled)
        self.job_changed.emit(job)
        self.pool.start(job.runner)

    @Slot(object, object)
    def _on_state(self, job, state):
        if not job.state.finished:
            job.state = state
            self.job_changed.emit(job)

    @Slot(object, float, str, str, str)
    def _on_progress(self, job, pct, speed, eta, size):
        if job.state.finished:
            return
        job.percent, job.speed, job.eta = pct, speed, eta
        if size:
            job.size = size
        self.job_changed.emit(job)

    @Slot(object, str, str)
    def _on_done(self, job, path, warn):
        job.state, job.percent, job.result = JobState.COMPLETED, 100.0, Path(path)
        job.speed = job.eta = ""
        job.message = warn
        job.runner = None
        self.job_changed.emit(job)
        self._after()

    @Slot(object, str, str)
    def _on_failed(self, job, msg, detail):
        job.state, job.message, job.detail = JobState.ERROR, msg, detail
        job.speed = job.eta = ""
        job.runner = None
        self.job_changed.emit(job)
        self._after()

    @Slot(object)
    def _on_cancelled(self, job):
        job.state = JobState.CANCELLED
        job.speed = job.eta = ""
        job.runner = None
        self.job_changed.emit(job)
        self._after()

    def _after(self) -> None:
        self._pump()
        if self.batch and not self._batch_done and all(j.state.finished for j in self.batch):
            self._batch_done = True
            self.batch_finished.emit(list(self.batch))
