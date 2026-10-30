from __future__ import annotations

import copy
import json
import time
import uuid
from pathlib import Path

from .adapters import DemoAdapter, LibraryAdapter, MusicAdapter
from .diagnostics import ImportDiagnostics
from .models import AppError, Snapshot, digest, validate_id
from .store import Store


class LibraryService:
    def __init__(
        self, data_dir: Path, mode: str = "music", adapter: LibraryAdapter | None = None,
        on_progress=None, progress_sequence: int = 0,
    ):
        self.data_dir = data_dir
        self.adapter = adapter or (DemoAdapter() if mode == "demo" else MusicAdapter())
        self.on_progress = on_progress
        self.adapter.on_progress = self.report_progress
        self.store = Store(data_dir / f"index-{self.adapter.mode}.sqlite3")
        self.diagnostics = ImportDiagnostics(data_dir / "import.log")
        self.connected = False
        self.refreshing = False
        self.progress = None
        self.progress_sequence = progress_sequence
        self.last_error = None
        self.last_refresh = 0.0
        self.server_id = self._server_id()
        self.artwork_cache = {}
        if self.adapter.mode == "demo":
            # Restore persisted demo ratings without ever involving Music.app.
            for row in self.store.db.execute("SELECT id, payload FROM tracks"):
                if row[0] in self.adapter.tracks:
                    saved = json.loads(row[1])
                    track = self.adapter.tracks[row[0]]
                    track.ratingRaw, track.ratingOrigin = saved["ratingRaw"], saved["ratingOrigin"]
            self.refresh()

    def _server_id(self) -> str:
        path = self.data_dir / "server-id"
        if path.exists():
            return path.read_text().strip()
        ident = str(uuid.uuid4())
        path.write_text(ident)
        path.chmod(0o600)
        return ident

    def status(self, store: Store | None = None) -> dict:
        store = store or self.store
        return {
            "serverId": self.server_id,
            "mode": self.adapter.mode,
            "connected": self.connected,
            "refreshing": self.refreshing,
            "progress": self.diagnostics.status_progress(),
            "hasCache": bool(store.meta("libraryScope")),
            "libraryScope": store.meta("libraryScope"),
            "snapshotRevision": store.meta("snapshotRevision"),
            "lastSyncedAt": store.meta("lastSyncedAt"),
            "counts": store.summary(),
            "error": self.last_error,
        }

    def read_cached(self, operation: str, *args, **kwargs):
        with Store.reader(self.store.path) as store:
            if operation == "status":
                return self.status(store)
            if operation == "operation":
                return self.operation(*args, store=store, **kwargs)
            return getattr(store, operation)(*args, **kwargs)

    def is_stale(self) -> bool:
        return not self.connected or time.monotonic() - self.last_refresh >= 30

    def set_mode(self, mode: str):
        if not isinstance(mode, str) or mode not in {"music", "demo"}:
            raise AppError("INVALID_MODE", "Unbekannter Bibliotheksmodus.")
        if mode != self.adapter.mode:
            self.close()
            self.__init__(
                self.data_dir, mode, on_progress=self.on_progress, progress_sequence=self.progress_sequence
            )

    def connect(self, mode: str) -> dict:
        self.set_mode(mode)
        return self.refresh()

    def refresh(self, force: bool = True) -> dict:
        if not force and not self.is_stale():
            return self.status()
        self.refreshing = True
        self.diagnostics.begin(self.adapter.mode)
        try:
            self.report_progress("opening")
            snapshot = self.adapter.snapshot()
            snapshot = self._copy_snapshot(snapshot)
            if snapshot.scope == self.store.meta("libraryScope"):
                self.report_progress("rating-index", 0, len(snapshot.tracks))
                by_id = {track.id: track for track in snapshot.tracks}
                overrides = list(self.store.db.execute("SELECT id, raw, origin FROM overrides"))
                if overrides:
                    self.report_progress("ratings", 0, len(overrides))
                for index, (ident, raw, origin) in enumerate(overrides, 1):
                    track = by_id.get(ident)
                    if not track:
                        continue
                    if (track.ratingRaw, track.ratingOrigin) == (raw, origin):
                        self.store.db.execute("DELETE FROM overrides WHERE id=?", (ident,))
                    else:
                        try:
                            raw, origin = self.adapter.read_rating(ident)
                        except AppError:
                            # Preserve a confirmed value while the native snapshot lags.
                            pass
                        track.ratingRaw, track.ratingOrigin = raw, origin
                        self.store.db.execute(
                            "UPDATE overrides SET raw=?, origin=? WHERE id=?", (raw, origin, ident)
                        )
                        track.ratingCapability = "writable"
                    self.report_progress("ratings", index, len(overrides))
                self.store.db.commit()
            self.store.replace(snapshot, on_progress=self.report_progress)
            self.artwork_cache.clear()
            self.connected, self.last_error = True, None
            self.last_refresh = time.monotonic()
            self.refreshing = False
            self.report_progress("done", len(snapshot.tracks), len(snapshot.tracks))
            return self.status()
        except AppError as exc:
            self.diagnostics.failure(exc)
            self.last_error = exc.payload()["error"]
            self.connected = False
            self.report_progress("failed")
            raise
        except Exception as exc:
            self.diagnostics.failure(exc)
            self.connected = False
            self.last_error = AppError(
                "LIBRARY_READ_FAILED", "Die Bibliothek konnte nicht aktualisiert werden.", 503
            ).payload()["error"]
            self.report_progress("failed")
            raise
        finally:
            self.refreshing = False

    def report_progress(self, stage: str, completed: int = 0, total: int = 0):
        self.progress_sequence += 1
        progress = {
            "stage": stage, "completed": completed, "total": total, "sequence": self.progress_sequence,
        }
        progress.update(self.diagnostics.update(progress))
        self.progress = progress
        if self.on_progress:
            self.on_progress(self.progress)

    def _copy_snapshot(self, source: Snapshot) -> Snapshot:
        # Retain deepcopy's shared-reference semantics, but publish completed
        # batches so copying a large snapshot is no longer an opaque operation.
        memo = {}
        tracks, playlists = [], []
        for stage, source_items, target in (
            ("snapshot-tracks", source.tracks, tracks),
            ("snapshot-playlists", source.playlists, playlists),
        ):
            self.report_progress(stage, 0, len(source_items))
            memo[id(source_items)] = target
            for index, item in enumerate(source_items, 1):
                target.append(copy.deepcopy(item, memo))
                if index % 1000 == 0 or index == len(source_items):
                    self.report_progress(stage, index, len(source_items))
        return Snapshot(source.scope, tracks, playlists)

    def require_connected(self):
        if not self.connected:
            raise AppError("LIBRARY_NOT_CONNECTED", "Bitte verbinde die Musikbibliothek zuerst.", 409)

    def request_permissions(self) -> dict:
        result = self.adapter.request_permissions()
        if self.adapter.mode == "music" and result["media"]["status"] != "granted":
            self.connected = False
        # Authorization must finish independently of the potentially large import.
        # The caller can start an explicit refresh after showing the result.
        result["libraryConnected"] = self.connected
        return result

    def rate(self, ident: str, body: dict, owner: str) -> dict:
        ident = validate_id(ident)
        stars = body.get("stars")
        if type(stars) is not int or not 0 <= stars <= 5:
            raise AppError("INVALID_RATING", "Bitte wähle eine ganze Zahl von 0 bis 5.")
        request_id = body.get("requestId")
        if not isinstance(request_id, str) or not 8 <= len(request_id) <= 128:
            raise AppError("INVALID_REQUEST_ID", "Eine eindeutige Anfrage-ID ist erforderlich.")
        if not isinstance(body.get("expectedRevision"), str) or not isinstance(body.get("libraryScope"), str):
            raise AppError("INVALID_REVISION", "Bibliothekskontext und erwartete Revision sind erforderlich.")
        fingerprint = digest([ident, body])
        self.store.db.execute("DELETE FROM operations WHERE created < unixepoch() - 86400")
        self.store.db.commit()
        previous = self.store.db.execute(
            "SELECT * FROM operations WHERE owner=? AND request=?", (owner, request_id)
        ).fetchone()
        if previous:
            if previous["fingerprint"] != fingerprint:
                raise AppError(
                    "REQUEST_ID_REUSED",
                    "Die Anfrage-ID wurde bereits für eine andere Änderung verwendet.",
                    409,
                )
            return self._operation_result(previous)
        self.require_connected()
        if body["libraryScope"] != self.store.meta("libraryScope"):
            raise AppError(
                "LIBRARY_CHANGED", "Die aktive Bibliothek hat sich geändert. Bitte lade die Liste neu.", 409
            )
        # Recheck library identity before a write: a Music library may have changed outside the app.
        if self.adapter.mode == "music":
            if body["libraryScope"] != self.adapter.library_scope():
                self.connected = False
                raise AppError(
                    "LIBRARY_CHANGED",
                    "Die aktive Bibliothek hat sich geändert. Bitte lade die Liste neu.",
                    409,
                )
        self.store.track(ident)
        try:
            raw, origin = self.adapter.read_rating(ident)
        except AppError as exc:
            if exc.code == "TRACK_NOT_SCRIPTABLE":
                track = self.store.mark_unavailable(ident, exc.message)
                raise AppError(exc.code, exc.message, exc.status, {"track": track}) from exc
            raise
        revisions = {digest([ident, raw, origin])}
        if raw == 0:
            # Older caches may label zero stars as inherited. Both revisions
            # describe the same unrated state; nonzero changes still conflict.
            revisions.update(digest([ident, 0, source]) for source in ("none", "album"))
        if body["expectedRevision"] not in revisions:
            track = self.store.update_rating(ident, raw, origin)
            raise AppError(
                "RATING_CONFLICT",
                "Die Bewertung wurde inzwischen geändert. Der aktuelle Wert wurde geladen.",
                409,
                {"track": track},
            )
        self.store.db.execute(
            "INSERT INTO operations (owner,request,fingerprint,scope,state) VALUES (?,?,?,?, 'pending')",
            (owner, request_id, fingerprint, body["libraryScope"]),
        )
        self.store.db.commit()
        try:
            raw, origin = self.adapter.write_rating(ident, stars)
            track = self.store.update_rating(ident, raw, origin)
            result = {
                "track": track,
                "requestId": request_id,
                "state": "confirmed",
                "libraryScope": body["libraryScope"],
            }
            status = 200
        except AppError as exc:
            result, status = exc.payload(), exc.status
        except Exception:
            result = AppError(
                "WRITE_UNCONFIRMED",
                "Der Schreibvorgang konnte nicht bestätigt werden. Bitte aktualisiere den Titel.",
                503,
            ).payload()
            status = 503
        self.store.db.execute(
            "UPDATE operations SET state=?, status=?, result=? WHERE owner=? AND request=?",
            ("confirmed" if status == 200 else "failed", status, json.dumps(result), owner, request_id),
        )
        self.store.db.commit()
        if status != 200:
            error = result["error"]
            raise AppError(error["code"], error["message"], status, error.get("details"))
        return result

    def _operation_result(self, row) -> dict:
        if row["state"] in {"pending", "unknown"}:
            raise AppError(
                "WRITE_UNCONFIRMED",
                "Der Auftrag hat noch kein bestätigtes Ergebnis. Bitte aktualisiere den Titel.",
                409,
            )
        result = json.loads(row["result"])
        if row["status"] != 200:
            error = result["error"]
            raise AppError(error["code"], error["message"], row["status"], error.get("details"))
        return result

    def operation(self, request_id: str, owner: str, store: Store | None = None) -> dict:
        store = store or self.store
        row = store.db.execute(
            "SELECT * FROM operations WHERE owner=? AND request=? AND created>=unixepoch()-86400",
            (owner, request_id),
        ).fetchone()
        if not row:
            raise AppError(
                "REQUEST_NOT_FOUND", "Dieser Auftrag ist nicht vorhanden oder nicht mehr abrufbar.", 404
            )
        return self._operation_result(row)

    def artwork(self, ident: str) -> tuple[bytes, str] | None:
        ident = validate_id(ident)
        self.store.track(ident)
        if ident not in self.artwork_cache:
            if (
                len(self.artwork_cache) >= 100
                or sum(len(value[0]) for value in self.artwork_cache.values() if value) > 24 * 1024 * 1024
            ):
                self.artwork_cache.pop(next(iter(self.artwork_cache)))
            self.artwork_cache[ident] = self.adapter.artwork(ident)
        return self.artwork_cache[ident]

    def capabilities(self) -> dict:
        return {
            "serverId": self.server_id,
            "apiVersions": ["v1"],
            "version": "0.1.0",
            "features": {
                "ratings": True,
                "ratingQueue": True,
                "artwork": True,
                "playback": False,
                "networkPairing": False,
                "events": False,
                "libraryModeChange": True,
            },
            "authentication": ["cookie", "bearer"],
            "ratingScale": {"min": 0, "max": 5, "step": 1},
            "pollIntervalSeconds": 30,
        }

    def close(self):
        self.diagnostics.close()
        self.store.close()
