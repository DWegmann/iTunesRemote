"""Bounded import diagnostics containing counters and code locations, never library contents."""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import traceback
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .models import AppError, now


class PrivateRotatingHandler(RotatingFileHandler):
    def _open(self):
        descriptor = os.open(self.baseFilename, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
        os.fchmod(descriptor, 0o600)
        return os.fdopen(descriptor, "a", encoding="utf-8")


class ImportDiagnostics:
    def __init__(self, path: Path, *, clock=time.monotonic, watch: bool = True):
        self.clock = clock
        self.watch = watch
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.active = False
        self.progress = None
        self.worker_id = None
        self.worker_name = ""
        self.started = self.stage_started = self.updated = self.finished = 0.0
        self.cpu_started = 0.0
        self.run_id = ""
        self.mode = ""
        self.last_log = self.last_heartbeat = 0.0
        self.last_stack = None
        self.logger = logging.Logger("itunesremote.import", level=logging.INFO)
        self.handler = PrivateRotatingHandler(path, maxBytes=2 * 1024 * 1024, backupCount=2)
        self.handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(self.handler)

    def begin(self, mode: str):
        with self.lock:
            self.started = self.stage_started = self.updated = self.clock()
            self.cpu_started = time.process_time()
            self.finished = 0.0
            self.last_log = self.last_heartbeat = self.started
            self.last_stack = None
            self.active = True
            self.progress = None
            self.run_id = uuid.uuid4().hex[:12]
            self.mode = mode
            self.worker_id = threading.get_ident()
            self.worker_name = threading.current_thread().name
            self._record("start")
        if self.watch and self.thread is None:
            self.thread = threading.Thread(target=self._watch, name="import-diagnostics", daemon=True)
            self.thread.start()

    def _metrics(self) -> dict:
        current = self.clock() if self.active else self.finished
        return {
            "runId": self.run_id,
            "elapsedSeconds": round(max(0.0, current - self.started), 2),
            "stageElapsedSeconds": round(max(0.0, current - self.stage_started), 2),
            "idleSeconds": round(max(0.0, current - self.updated), 2),
        }

    def metrics(self) -> dict:
        with self.lock:
            return self._metrics()

    def status_progress(self) -> dict | None:
        with self.lock:
            return {**self.progress, **self._metrics()} if self.progress is not None else None

    def _record(self, event: str, **extra):
        # Only explicitly selected fields reach the log. Never log exceptions,
        # request bodies, track IDs, titles, playlist names, or stack locals.
        record = {
            "time": now(),
            "event": event,
            "mode": self.mode,
            "appBuild": os.environ.get("ITUNESREMOTE_APP_BUILD", "development"),
            "pid": os.getpid(),
            "workerThread": self.worker_name,
            **(self.progress or {}),
            **self._metrics(),
            "processCpuSeconds": round(max(0.0, time.process_time() - self.cpu_started), 2),
            **extra,
        }
        self.logger.info(json.dumps(record, ensure_ascii=False))

    def update(self, progress: dict) -> dict:
        with self.lock:
            current = self.clock()
            changed = self.progress is None or self.progress["stage"] != progress["stage"]
            if changed:
                if self.progress is not None:
                    self._record("phase-end")
                self.stage_started = current
                self.last_stack = None
            self.updated = current
            self.progress = {key: progress[key] for key in ("stage", "completed", "total", "sequence")}
            if progress["stage"] in {"done", "failed"}:
                self.active = False
                self.finished = current
            if changed or progress["completed"] == progress["total"] or current - self.last_log >= 2:
                self._record("progress")
                self.last_log = current
            return self._metrics()

    def failure(self, error: Exception):
        with self.lock:
            stack = [
                {"file": Path(item.filename).name, "line": item.lineno, "function": item.name}
                for item in traceback.extract_tb(error.__traceback__, limit=20)
            ]
            self._record(
                "exception",
                errorType=type(error).__name__,
                stack=stack,
                **({"errorCode": error.code} if isinstance(error, AppError) else {}),
            )

    def check(self):
        with self.lock:
            current = self.clock()
            if not self.active or current - self.last_heartbeat < 10:
                return
            self.last_heartbeat = current
            self._record("heartbeat")
            if current - self.updated < 30 or (
                self.last_stack is not None and current - self.last_stack < 60
            ):
                return
            self.last_stack = current
            frame = sys._current_frames().get(self.worker_id)
            if frame is not None:
                # Code locations only: omitting source lines and locals also
                # avoids accidentally logging literal credentials in test code.
                stack = [
                    {"file": Path(item.filename).name, "line": item.lineno, "function": item.name}
                    for item in traceback.extract_stack(frame, limit=20)
                ]
                self._record("worker-stack", stack=stack)
                del frame

    def _watch(self):
        while not self.stop.wait(10):
            self.check()

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=2)
        with self.lock:
            self.handler.close()
