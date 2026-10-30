from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import sqlite3
import unicodedata
from contextlib import contextmanager
from pathlib import Path

from .models import AppError, Snapshot, digest, now


def searchable(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c))


class Store:
    """Renewable index; writes use the native worker, readers use separate connections."""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS tracks (
                id TEXT PRIMARY KEY, title TEXT, artist TEXT, album TEXT, search TEXT,
                rating INTEGER, origin TEXT, duration INTEGER, payload TEXT NOT NULL, added REAL
            );
            CREATE TABLE IF NOT EXISTS playlists (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS members (
                playlist TEXT, track TEXT, PRIMARY KEY (playlist, track)
            );
            CREATE INDEX IF NOT EXISTS rating_index ON tracks(origin, rating);
            CREATE TABLE IF NOT EXISTS operations (
                owner TEXT, request TEXT, fingerprint TEXT, scope TEXT, state TEXT,
                status INTEGER, result TEXT, created REAL DEFAULT (unixepoch()),
                PRIMARY KEY (owner, request)
            );
            CREATE TABLE IF NOT EXISTS overrides (id TEXT PRIMARY KEY, raw INTEGER, origin TEXT);
        """)
        if "added" not in {row["name"] for row in self.db.execute("PRAGMA table_info(tracks)")}:
            self.db.execute("ALTER TABLE tracks ADD COLUMN added REAL")
            self.db.execute("""
                UPDATE tracks SET added=julianday(json_extract(payload, '$.addedDate')),
                    payload=json_set(payload, '$.addedDate', json_extract(payload, '$.addedDate'))
            """)
        if not self.meta("cursorSecret"):
            self.set_meta("cursorSecret", secrets.token_hex(32))
        # A killed process can leave an operation without a result. Never replay it implicitly.
        self.db.execute("UPDATE operations SET state='unknown' WHERE state='pending'")
        self.db.execute("DELETE FROM operations WHERE created < unixepoch() - 86400")
        self.db.commit()

    @classmethod
    @contextmanager
    def reader(cls, path: Path):
        # One SQLite read transaction keeps counts, rows and cursor revisions coherent
        # while the native worker atomically publishes a new snapshot in WAL mode.
        store = cls.__new__(cls)
        store.path = path
        store.db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        store.db.row_factory = sqlite3.Row
        try:
            store.db.execute("BEGIN")
            yield store
        finally:
            store.db.close()

    def meta(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_meta(self, key: str, value: str):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, value))
        self.db.commit()

    def track(self, ident: str) -> dict:
        row = self.db.execute("SELECT payload FROM tracks WHERE id=?", (ident,)).fetchone()
        if not row:
            raise AppError("TRACK_NOT_FOUND", "Der Titel ist nicht mehr in der Bibliothek.", 404)
        return json.loads(row[0])

    def _upsert(self, track: dict):
        self.db.execute(
            """INSERT OR REPLACE INTO tracks
                (id, title, artist, album, search, rating, origin, duration, payload, added)
                VALUES (?,?,?,?,?,?,?,?,?,julianday(?))""",
            (
                track["id"],
                searchable(track["title"]),
                searchable(track["artist"]),
                searchable(track["album"]),
                searchable(
                    " ".join(
                        str(track.get(k) or "") for k in ("title", "artist", "album", "albumArtist", "genre")
                    )
                ),
                track["ratingRaw"],
                track["ratingOrigin"],
                track["durationSeconds"],
                json.dumps(track, ensure_ascii=False),
                track.get("addedDate"),
            ),
        )

    def replace(self, snapshot: Snapshot, on_progress=None):
        if on_progress:
            on_progress("index-serialize", 0, len(snapshot.tracks))
        rows = []
        for index, track in enumerate(snapshot.tracks, 1):
            rows.append(track.to_dict())
            if on_progress and (index % 1000 == 0 or index == len(snapshot.tracks)):
                on_progress("index-serialize", index, len(snapshot.tracks))
        if on_progress:
            on_progress("index-signature", 0, len(rows))
        signature = digest(
            [snapshot.scope, rows, [p.to_dict() | {"members": p.trackIds} for p in snapshot.playlists]]
        )
        if signature == self.meta("contentSignature"):
            if on_progress:
                on_progress("saving")
            self.set_meta("lastSyncedAt", now())
            return
        with self.db:
            if on_progress:
                on_progress("index-reset", 0, len(rows))
            if snapshot.scope != self.meta("libraryScope"):
                self.db.execute("DELETE FROM overrides")
            self.db.execute("DELETE FROM tracks")
            self.db.execute("DELETE FROM playlists")
            self.db.execute("DELETE FROM members")
            if on_progress:
                on_progress("indexing", 0, len(rows))
            for index, track in enumerate(rows, 1):
                self._upsert(track)
                if on_progress and (index % 1000 == 0 or index == len(rows)):
                    on_progress("indexing", index, len(rows))
            if on_progress:
                on_progress("index-playlists", 0, len(snapshot.playlists))
            for index, playlist in enumerate(snapshot.playlists, 1):
                self.db.execute(
                    "INSERT INTO playlists VALUES (?, ?)", (playlist.id, json.dumps(playlist.to_dict()))
                )
                self.db.executemany(
                    "INSERT OR IGNORE INTO members VALUES (?, ?)",
                    ((playlist.id, ident) for ident in playlist.trackIds),
                )
                if on_progress:
                    on_progress("index-playlists", index, len(snapshot.playlists))
            if on_progress:
                on_progress("saving")
            for key, value in {
                "libraryScope": snapshot.scope,
                "contentSignature": signature,
                "snapshotRevision": secrets.token_hex(12),
                "lastSyncedAt": now(),
            }.items():
                self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))

    def update_rating(self, ident: str, raw: int, origin: str, *, confirmed: bool = True) -> dict:
        track = self.track(ident)
        track.update(ratingRaw=raw, ratingOrigin=origin, ratingRevision=digest([ident, raw, origin]))
        if confirmed:
            track.update(ratingCapability="writable", capabilityReason=None)
        with self.db:
            self._upsert(track)
            if confirmed:
                self.db.execute("INSERT OR REPLACE INTO overrides VALUES (?,?,?)", (ident, raw, origin))
            self.db.execute(
                "INSERT OR REPLACE INTO meta VALUES ('snapshotRevision',?)", (secrets.token_hex(12),)
            )
            self.db.execute("DELETE FROM meta WHERE key='contentSignature'")
        return track

    def summary(self) -> dict:
        row = self.db.execute(
            "SELECT COUNT(*) total, SUM(origin='user') rated, SUM(origin!='user') unrated FROM tracks"
        ).fetchone()
        return {"total": row["total"], "rated": row["rated"] or 0, "unrated": row["unrated"] or 0}

    def mark_unavailable(self, ident: str, reason: str) -> dict:
        track = self.track(ident)
        track.update(ratingCapability="unavailable", capabilityReason=reason)
        with self.db:
            self._upsert(track)
            self.db.execute(
                "INSERT OR REPLACE INTO meta VALUES ('snapshotRevision',?)", (secrets.token_hex(12),)
            )
            self.db.execute("DELETE FROM meta WHERE key='contentSignature'")
        return track

    def playlists(self) -> list[dict]:
        return sorted(
            (json.loads(r[0]) for r in self.db.execute("SELECT payload FROM playlists")),
            key=lambda p: p["name"].casefold(),
        )

    def _cursor(self, data: dict) -> str:
        body = json.dumps(data, separators=(",", ":")).encode()
        mac = hmac.new(self.meta("cursorSecret").encode(), body, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(mac + body).decode().rstrip("=")

    def query(
        self,
        query: str = "",
        rating: str = "all",
        playlist_id: str = "",
        sort: str = "artist",
        cursor: str = "",
        limit: int = 100,
    ) -> dict:
        sorts = {
            "title": "title, artist",
            "artist": "artist, album, title",
            "album": "album, artist, title",
            "rating": "rating DESC, artist, title",
            "duration": "duration DESC, artist, title",
            "addedDate": "added IS NULL, added DESC, artist, title",
            "addedDateAsc": "added IS NULL, added ASC, artist, title",
        }
        if sort not in sorts or rating not in {"all", "unrated", "rated", "1", "2", "3", "4", "5"}:
            raise AppError("INVALID_FILTER", "Der Filter oder die Sortierung ist ungültig.")
        if not 1 <= limit <= 200 or len(query) > 300:
            raise AppError("INVALID_QUERY", "Die Seitengröße oder Suchanfrage ist ungültig.")
        revision = self.meta("snapshotRevision") or "empty"
        signature = digest([query, rating, playlist_id, sort, limit])
        offset = 0
        if cursor:
            try:
                blob = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
                mac, body = blob[:32], blob[32:]
                expected = hmac.new(self.meta("cursorSecret").encode(), body, hashlib.sha256).digest()
                if not hmac.compare_digest(mac, expected):
                    raise ValueError("Invalid signature")
                data = json.loads(body)
                if data["revision"] != revision:
                    raise AppError(
                        "CURSOR_EXPIRED", "Die Bibliothek hat sich geändert. Die Liste wird neu geladen.", 409
                    )
                if data["query"] != signature or type(data["offset"]) is not int or data["offset"] < 0:
                    raise ValueError("Invalid cursor context")
                offset = data["offset"]
            except AppError:
                raise
            except (ValueError, KeyError, TypeError):
                raise AppError("INVALID_CURSOR", "Die Seitenmarkierung ist ungültig.") from None
        clauses, params = ["1=1"], []
        for word in searchable(query).split():
            clauses.append("instr(search, ?) > 0")
            params.append(word)
        if rating == "unrated":
            clauses.append("origin != 'user'")
        elif rating == "rated":
            clauses.append("origin = 'user'")
        elif rating.isdigit():
            clauses.append("origin = 'user' AND rating = ?")
            params.append(int(rating) * 20)
        if playlist_id:
            if not self.db.execute("SELECT 1 FROM playlists WHERE id=?", (playlist_id,)).fetchone():
                raise AppError("PLAYLIST_NOT_FOUND", "Die Playlist wurde nicht gefunden.", 404)
            clauses.append("id IN (SELECT track FROM members WHERE playlist=?)")
            params.append(playlist_id)
        where = " AND ".join(clauses)
        total = self.db.execute(f"SELECT COUNT(*) FROM tracks WHERE {where}", params).fetchone()[0]
        rows = self.db.execute(
            f"SELECT payload FROM tracks WHERE {where} ORDER BY {sorts[sort]}, id LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        end = offset + len(rows)
        return {
            "items": [json.loads(row[0]) for row in rows],
            "total": total,
            "nextCursor": self._cursor({"revision": revision, "query": signature, "offset": end})
            if end < total
            else None,
            "snapshotRevision": revision,
            "libraryScope": self.meta("libraryScope"),
        }

    def close(self):
        self.db.close()
