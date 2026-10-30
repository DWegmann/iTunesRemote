"""Durable rating outbox; accepting work never waits for the native Music worker."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .models import AppError, digest, validate_id
from .store import Store


class RatingQueue:
    def __init__(self, path: Path):
        self.path = path
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, mode TEXT NOT NULL,
                    scope TEXT NOT NULL, track TEXT NOT NULL, title TEXT NOT NULL,
                    stars INTEGER NOT NULL, revision TEXT NOT NULL, fingerprint TEXT NOT NULL,
                    state TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL,
                    attempted REAL, result TEXT, chosen REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS queue_order ON jobs(mode, state, created);
                CREATE INDEX IF NOT EXISTS queue_track ON jobs(owner, mode, scope, track, state);
            """)
            # The operation journal distinguishes completed, interrupted and untouched writes.
            db.execute("UPDATE jobs SET state='queued' WHERE state='running'")
        path.chmod(0o600)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def job(row) -> dict:
        return {
            "requestId": row["id"], "trackId": row["track"], "title": row["title"],
            "stars": row["stars"], "libraryScope": row["scope"], "mode": row["mode"],
            "state": row["state"], "createdAt": row["created"], "updatedAt": row["updated"],
            "chosenAt": row["chosen"],
            "result": json.loads(row["result"]) if row["result"] else None,
        }

    def enqueue(self, owner: str, mode: str, index: Path, data: dict) -> dict:
        items, scope = data.get("items"), data.get("libraryScope")
        if not isinstance(scope, str) or not isinstance(items, list) or not 1 <= len(items) <= 25:
            raise AppError("INVALID_QUEUE", "Ein Auftrag benötigt 1 bis 25 Bewertungen und den Bibliothekskontext.")
        prepared, ids = [], set()
        with Store.reader(index) as store:
            if scope != store.meta("libraryScope"):
                raise AppError("LIBRARY_CHANGED", "Die aktive Bibliothek hat sich geändert. Bitte lade die Liste neu.", 409)
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("trackId"), str):
                    raise AppError("INVALID_QUEUE", "Eine gültige Titel-ID ist erforderlich.")
                ident = validate_id(item["trackId"])
                stars, revision, request = item.get("stars"), item.get("expectedRevision"), item.get("requestId")
                if type(stars) is not int or not 0 <= stars <= 5:
                    raise AppError("INVALID_RATING", "Bitte wähle eine ganze Zahl von 0 bis 5.")
                if not isinstance(revision, str):
                    raise AppError("INVALID_REVISION", "Die erwartete Bewertungsrevision ist erforderlich.")
                if not isinstance(request, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,128}", request) or request in ids:
                    raise AppError("INVALID_REQUEST_ID", "Jede Bewertung benötigt eine eindeutige Anfrage-ID.")
                ids.add(request)
                track = store.track(ident)
                chosen = item.get("chosenAt", time.time() * 1000)
                if type(chosen) not in {int, float} or not math.isfinite(chosen) or chosen <= 0:
                    raise AppError("INVALID_QUEUE", "Der Zeitpunkt der Auswahl ist ungültig.")
                prepared.append((request, ident, track["title"], stars, revision, digest([scope, item]), chosen))
        now = time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # Validate every duplicate before changing any jobs in this batch.
            for request, _, _, _, _, fingerprint, _ in prepared:
                previous = db.execute("SELECT owner, fingerprint FROM jobs WHERE id=?", (request,)).fetchone()
                if previous and (previous["owner"] != owner or previous["fingerprint"] != fingerprint):
                    raise AppError("REQUEST_ID_REUSED", "Die Anfrage-ID wurde bereits anderweitig verwendet.", 409)
            for request, ident, title, stars, revision, fingerprint, chosen in prepared:
                if db.execute("SELECT 1 FROM jobs WHERE id=?", (request,)).fetchone():
                    continue
                latest = db.execute(
                    "SELECT max(chosen) FROM jobs WHERE owner=? AND mode=? AND scope=? AND track=?",
                    (owner, mode, scope, ident),
                ).fetchone()[0]
                state = "superseded" if latest is not None and latest > chosen else "queued"
                if state == "queued":
                    db.execute(
                        "UPDATE jobs SET state='superseded', updated=? "
                        "WHERE owner=? AND mode=? AND scope=? AND track=? AND state IN ('queued','failed')",
                        (now, owner, mode, scope, ident),
                    )
                db.execute(
                    "INSERT INTO jobs (id,owner,mode,scope,track,title,stars,revision,fingerprint,state,created,updated,chosen) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (request, owner, mode, scope, ident, title, stars, revision, fingerprint, state, now, now, chosen),
                )
            jobs = [self.job(db.execute("SELECT * FROM jobs WHERE id=?", (request,)).fetchone())
                    for request, *_ in prepared]
        return {"items": jobs}

    def list(self, owner: str, mode: str, scope: str, ids: list[str]) -> dict:
        if len(ids) > 100 or any(len(ident) > 128 for ident in ids):
            raise AppError("INVALID_QUEUE", "Es können höchstens 100 Aufträge gleichzeitig abgefragt werden.")
        with self.connection() as db:
            placeholders = ",".join("?" for _ in ids) or "NULL"
            rows = db.execute(
                "SELECT * FROM jobs WHERE owner=? AND mode=? AND scope=? "
                f"AND (state IN ('queued','running','failed') OR id IN ({placeholders})) ORDER BY created, rowid",
                (owner, mode, scope, *ids),
            ).fetchall()
            found = {row["id"] for row in rows}
            return {"items": [self.job(row) for row in rows], "missingIds": [ident for ident in ids if ident not in found]}

    def next_batch(self, mode: str) -> list[str]:
        with self.connection() as db:
            return [row[0] for row in db.execute(
                "SELECT id FROM jobs WHERE mode=? AND state='queued' ORDER BY created, rowid LIMIT 20", (mode,)
            )]

    def active(self, mode: str) -> bool:
        with self.connection() as db:
            return bool(db.execute(
                "SELECT 1 FROM jobs WHERE mode=? AND state IN ('queued','running') LIMIT 1", (mode,)
            ).fetchone())

    def claim(self, ident: str, index: Path) -> dict | None:
        with Store.reader(index) as store, self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM jobs WHERE id=? AND state='queued'", (ident,)).fetchone()
            if not row:
                return None
            revision = row["revision"]
            if row["attempted"] is None and row["scope"] == store.meta("libraryScope"):
                previous = db.execute(
                    "SELECT result FROM jobs WHERE owner=? AND mode=? AND scope=? AND track=? "
                    "AND state='confirmed' ORDER BY updated DESC, rowid DESC LIMIT 1",
                    (row["owner"], row["mode"], row["scope"], row["track"]),
                ).fetchone()
                if previous:
                    confirmed = json.loads(previous[0])["track"]["ratingRevision"]
                    # Rebase only our own confirmed chain, never another client's cached change.
                    if store.track(row["track"])["ratingRevision"] == confirmed:
                        revision = confirmed
            db.execute(
                "UPDATE jobs SET state='running', revision=?, attempted=coalesce(attempted,?), updated=? WHERE id=?",
                (revision, time.time(), time.time(), ident),
            )
            claimed = dict(db.execute("SELECT * FROM jobs WHERE id=?", (ident,)).fetchone())
        return claimed

    def finish(self, ident: str, result: dict):
        state = "failed" if "error" in result else "confirmed"
        with self.connection() as db:
            db.execute("UPDATE jobs SET state=?, result=?, updated=? WHERE id=?",
                       (state, json.dumps(result, ensure_ascii=False), time.time(), ident))

    def dismiss(self, owner: str, ident: str):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM jobs WHERE id=? AND owner=?", (ident, owner)).fetchone()
            if not row:
                raise AppError("REQUEST_NOT_FOUND", "Dieser Auftrag ist nicht vorhanden.", 404)
            if row[0] == "running":
                raise AppError("LIBRARY_BUSY", "Diese Bewertung wird bereits gespeichert.", 409)
            db.execute("UPDATE jobs SET state='dismissed', updated=? WHERE id=?", (time.time(), ident))
