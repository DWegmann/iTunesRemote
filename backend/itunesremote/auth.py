from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from .models import AppError


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class Principal:
    owner: str
    kind: str
    csrf: str = ""


class Auth:
    """Browser sessions and native credentials share permissions, not transport."""

    def __init__(self, path: Path, host_key: str):
        self.host_key = host_key
        self.codes: dict[str, float] = {}
        self.db = sqlite3.connect(path, check_same_thread=False)
        path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, owner TEXT, csrf TEXT, expires REAL);
            CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, name TEXT, revoked INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS credentials (hash TEXT PRIMARY KEY, device TEXT, kind TEXT, expires REAL);
            CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        row = self.db.execute("SELECT value FROM settings WHERE name='web_password'").fetchone()
        if row is None:
            # This database lives in Application Support, outside the versioned app bundle.
            # INSERT OR IGNORE also preserves the first password during concurrent starts.
            self.db.execute(
                "INSERT OR IGNORE INTO settings VALUES ('web_password', ?)", (secrets.token_urlsafe(18),)
            )
            row = self.db.execute("SELECT value FROM settings WHERE name='web_password'").fetchone()
        self.web_password = row[0]
        self.password_hash = token_hash(self.web_password)
        self.db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))
        self.db.execute("DELETE FROM credentials WHERE expires < ?", (time.time(),))
        self.db.commit()

    def is_host(self, token: str) -> bool:
        return bool(token) and secrets.compare_digest(token, self.host_key)

    def bootstrap(self) -> str:
        self.codes = {k: v for k, v in self.codes.items() if v > time.time()}
        if len(self.codes) >= 30:
            raise AppError("RATE_LIMITED", "Zu viele Anmeldeversuche. Bitte warte kurz.", 429)
        code = secrets.token_urlsafe(32)
        self.codes[token_hash(code)] = time.time() + 60
        return code

    def exchange(self, code: str) -> tuple[str, str]:
        expires = self.codes.pop(token_hash(code), 0)
        if expires < time.time():
            raise AppError(
                "BOOTSTRAP_EXPIRED",
                "Der Anmeldelink ist abgelaufen. Öffne die Oberfläche erneut über die Mac-App.",
                401,
            )
        return self._session()

    def login(self, password: object) -> tuple[str, str]:
        # The generated password has 144 random bits; compare fixed-size hashes in constant time.
        if not isinstance(password, str) or not 1 <= len(password) <= 128 or not secrets.compare_digest(
            token_hash(password), self.password_hash
        ):
            raise AppError("INVALID_PASSWORD", "Das Passwort stimmt nicht. Bitte versuche es erneut.", 401)
        return self._session()

    def _session(self) -> tuple[str, str]:
        sid, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        self.db.execute(
            "INSERT INTO sessions VALUES (?,?,?,?)",
            (token_hash(sid), secrets.token_hex(16), csrf, time.time() + 43200),
        )
        self.db.commit()
        return sid, csrf

    def authenticate(self, bearer: str, cookie: str) -> Principal:
        if bearer:
            if self.is_host(bearer):
                return Principal("host", "host")
            row = self.db.execute(
                "SELECT c.device FROM credentials c JOIN devices d ON d.id=c.device WHERE c.hash=? AND c.kind='access' AND c.expires>? AND d.revoked=0",
                (token_hash(bearer), time.time()),
            ).fetchone()
            if row:
                return Principal(row[0], "bearer")
        elif cookie:
            row = self.db.execute(
                "SELECT owner, csrf FROM sessions WHERE hash=? AND expires>?",
                (token_hash(cookie), time.time()),
            ).fetchone()
            if row:
                return Principal(row[0], "cookie", row[1])
        raise AppError("UNAUTHORIZED", "Bitte melde dich mit dem Passwort aus der Mac-App an.", 401)

    def issue_device(self, name: str) -> dict:
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise AppError("INVALID_DEVICE_NAME", "Bitte gib einen Gerätenamen mit höchstens 80 Zeichen ein.")
        ident = secrets.token_hex(16)
        self.db.execute("INSERT INTO devices (id,name) VALUES (?,?)", (ident, name.strip()))
        return {"deviceId": ident, **self._tokens(ident)}

    def _tokens(self, ident: str) -> dict:
        access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(40)
        for token, kind, lifetime in [(access, "access", 3600), (refresh, "refresh", 2592000)]:
            self.db.execute(
                "INSERT INTO credentials VALUES (?,?,?,?)",
                (token_hash(token), ident, kind, time.time() + lifetime),
            )
        self.db.commit()
        return {"accessToken": access, "refreshToken": refresh, "tokenType": "Bearer", "expiresIn": 3600}

    def refresh(self, token: str) -> dict:
        row = self.db.execute(
            "SELECT c.device FROM credentials c JOIN devices d ON d.id=c.device WHERE c.hash=? AND c.kind='refresh' AND c.expires>? AND d.revoked=0",
            (token_hash(token), time.time()),
        ).fetchone()
        if not row:
            raise AppError(
                "INVALID_REFRESH_TOKEN", "Der Gerätezugang ist abgelaufen oder wurde widerrufen.", 401
            )
        # Rotation invalidates both previous tokens before issuing a new pair.
        self.db.execute("DELETE FROM credentials WHERE device=?", (row[0],))
        return self._tokens(row[0])

    def devices(self) -> list[dict]:
        return [
            dict(row) for row in self.db.execute("SELECT id, name FROM devices WHERE revoked=0 ORDER BY name")
        ]

    def revoke(self, ident: str):
        self.db.execute("UPDATE devices SET revoked=1 WHERE id=?", (ident,))
        self.db.execute("DELETE FROM credentials WHERE device=?", (ident,))
        self.db.commit()

    def logout(self, sid: str):
        self.db.execute("DELETE FROM sessions WHERE hash=?", (token_hash(sid),))
        self.db.commit()

    def close(self):
        self.db.close()
