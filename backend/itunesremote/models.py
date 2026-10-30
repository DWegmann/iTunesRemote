from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:24]


def canonical_id(value: object) -> str:
    number = int(value, 16) if isinstance(value, str) else int(value)
    if number < 0 or number > 0xFFFFFFFFFFFFFFFF:
        raise ValueError("Persistent ID outside unsigned 64-bit range")
    return f"{number:016X}"


def validate_id(value: str) -> str:
    if not re.fullmatch(r"[a-fA-F0-9]{16}", value):
        raise AppError("INVALID_ID", "Die Titel-ID ist ungültig.", 400)
    return value.upper()


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.details = details or {}

    def payload(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}


@dataclass
class Track:
    id: str
    title: str
    artist: str = ""
    album: str = ""
    albumArtist: str = ""
    genre: str = ""
    year: int | None = None
    durationSeconds: int = 0
    ratingRaw: int = 0
    ratingOrigin: str = "none"
    playCount: int = 0
    lastPlayed: str | None = None
    addedDate: str | None = None
    isCloud: bool = False
    hasArtwork: bool = False
    ratingCapability: str = "unknown"
    capabilityReason: str | None = None

    @property
    def rating_revision(self) -> str:
        return digest([self.id, self.ratingRaw, self.ratingOrigin])

    def to_dict(self) -> dict:
        return {**asdict(self), "ratingRevision": self.rating_revision}


@dataclass
class Playlist:
    id: str
    name: str
    trackIds: list[str] = field(default_factory=list)
    isMaster: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "trackCount": len(self.trackIds), "isMaster": self.isMaster}


@dataclass
class Snapshot:
    scope: str
    tracks: list[Track]
    playlists: list[Playlist]
