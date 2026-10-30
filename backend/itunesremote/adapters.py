"""Native adapters follow the ITLibrary/ScriptingBridge split of apple-music-mcp.

This implementation is independent. No third-party source was copied.
All native calls are made on the service's single worker thread.
"""

from __future__ import annotations

import copy
import sys
from datetime import datetime, timezone
from functools import cache
from typing import Protocol

from .models import AppError, Playlist, Snapshot, Track, canonical_id, digest


class LibraryAdapter(Protocol):
    mode: str

    def snapshot(self) -> Snapshot: ...
    def library_scope(self) -> str: ...
    def read_rating(self, track_id: str) -> tuple[int, str]: ...
    def write_rating(self, track_id: str, stars: int) -> tuple[int, str]: ...
    def artwork(self, track_id: str) -> tuple[bytes, str] | None: ...
    def request_permissions(self) -> dict: ...


class DemoAdapter:
    mode = "demo"

    def __init__(self):
        albums = [
            (
                "In Rainbows",
                "Radiohead",
                "Alternative",
                2007,
                ["15 Step", "Bodysnatchers", "Nude", "Weird Fishes / Arpeggi", "All I Need", "Reckoner"],
            ),
            (
                "Random Access Memories",
                "Daft Punk",
                "Electronic",
                2013,
                [
                    "Give Life Back to Music",
                    "The Game of Love",
                    "Giorgio by Moroder",
                    "Within",
                    "Instant Crush",
                    "Get Lucky",
                ],
            ),
            (
                "Kind of Blue",
                "Miles Davis",
                "Jazz",
                1959,
                ["So What", "Freddie Freeloader", "Blue in Green", "All Blues", "Flamenco Sketches"],
            ),
            (
                "Rumours",
                "Fleetwood Mac",
                "Rock",
                1977,
                [
                    "Second Hand News",
                    "Dreams",
                    "Never Going Back Again",
                    "Don't Stop",
                    "Go Your Own Way",
                    "The Chain",
                ],
            ),
            (
                "Mezzanine",
                "Massive Attack",
                "Trip-Hop",
                1998,
                ["Angel", "Risingson", "Teardrop", "Inertia Creeps", "Dissolved Girl", "Mezzanine"],
            ),
            (
                "Spaces",
                "Nils Frahm",
                "Modern Classical",
                2013,
                ["Says", "Said and Done", "Went Missing", "Over There, It's Raining", "Familiar"],
            ),
        ]
        self.tracks = {}
        for album_index, (album, artist, genre, year, titles) in enumerate(albums):
            for index, title in enumerate(titles):
                ident = canonical_id(album_index * 100 + index + 1)
                raw = [0, 80, 0, 100, 60, 0][index % 6]
                inherited = album_index == 2 and index == 2
                self.tracks[ident] = Track(
                    id=ident,
                    title=title,
                    artist=artist,
                    album=album,
                    albumArtist=artist,
                    genre=genre,
                    year=year,
                    durationSeconds=187 + index * 31 + album_index * 17,
                    ratingRaw=80 if inherited else raw,
                    ratingOrigin="album" if inherited else "user" if raw else "none",
                    playCount=4 + index * 13,
                    addedDate=datetime(2024, album_index + 1, index + 1, 12, tzinfo=timezone.utc).isoformat(),
                    hasArtwork=False,
                    ratingCapability="writable",
                )
        self.playlists = [
            Playlist("000000000000F001", "Abends auflegen", list(self.tracks)[::3]),
            Playlist("000000000000F002", "Lieblingsstücke", list(self.tracks)[1::4]),
            Playlist("000000000000F003", "Zum Entdecken", list(self.tracks)[::2]),
        ]
        self.album_ratings = {canonical_id(203): 80}

    def snapshot(self) -> Snapshot:
        return Snapshot("demo-library-v1", copy.deepcopy(list(self.tracks.values())), self.playlists)

    def library_scope(self) -> str:
        return "demo-library-v1"

    def read_rating(self, track_id: str) -> tuple[int, str]:
        track = self.tracks.get(track_id)
        if not track:
            raise AppError("TRACK_NOT_FOUND", "Der Titel wurde nicht gefunden.", 404)
        return track.ratingRaw, track.ratingOrigin

    def write_rating(self, track_id: str, stars: int) -> tuple[int, str]:
        self.read_rating(track_id)
        track = self.tracks[track_id]
        track.ratingRaw = stars * 20 or self.album_ratings.get(track_id, 0)
        track.ratingOrigin = "user" if stars else "album" if track.ratingRaw else "none"
        return self.read_rating(track_id)

    def artwork(self, track_id: str) -> tuple[bytes, str] | None:
        return None

    def request_permissions(self) -> dict:
        message = "Im Demomodus sind keine Freigaben nötig. Wähle die Musikbibliothek für den echten Zugriff."
        return {
            "mode": "demo",
            "needsSettings": False,
            "media": {"status": "notRequired", "message": message},
            "automation": {"status": "notRequired", "message": message},
        }


@cache
def music_delegate_class():
    import objc
    from Foundation import NSObject

    class ITunesRemoteMusicEventDelegate(NSObject):
        @objc.typedSelector(b"@@:@@")
        def eventDidFail_withError_(self, event, error):
            self.last_error = int(error.code())
            return None

    return ITunesRemoteMusicEventDelegate


class MusicAdapter:
    mode = "music"

    @staticmethod
    def _rating_origin(raw: int, computed: bool) -> str:
        # A computed flag without any stars still means there is no rating.
        if not raw:
            return "none"
        return "album" if computed else "user"

    def __init__(self):
        self.library = None
        self.items = {}
        self.app = None
        self.delegate = None
        self.scope = None

    @staticmethod
    def _native_error(exc: Exception, default: str = "NATIVE_ERROR") -> AppError:
        if "-1743" in str(exc):
            return AppError(
                "AUTOMATION_DENIED",
                "Bitte erlaube iTunesRemote unter Datenschutz & Sicherheit > Automation den Zugriff auf Musik.",
                403,
            )
        return AppError(
            default,
            "Die Musik-Schnittstelle konnte die Anfrage nicht ausführen. Bitte prüfe die Berechtigungen und versuche es erneut.",
            503,
        )

    def _open_library(self):
        if sys.platform != "darwin":
            raise AppError(
                "MACOS_REQUIRED", "Die echte Bibliothek benötigt macOS. Der Demomodus ist verfügbar.", 503
            )
        import iTunesLibrary as IL

        if self.library is None:
            library, _error = IL.ITLibrary.alloc().initWithAPIVersion_error_("1.0", None)
            if library is None:
                raise AppError(
                    "MEDIA_ACCESS_DENIED",
                    "Der Bibliothekszugriff ist nicht verfügbar. Bitte prüfe die Freigabe unter Datenschutz & Sicherheit > Medien & Apple Music sowie deine Musikbibliothek.",
                    403,
                )
            self.library = library

    def _request_media_access(self):
        from .permissions import request_media_access

        request_media_access()

    def _request_automation_access(self):
        from .permissions import request_automation_access

        # Consent dialogs may wait for the user. Do not reuse the short timeout
        # intended for rating writes, and never change a rating to test access.
        request_automation_access()

    def request_permissions(self) -> dict:
        import objc

        results = {}
        with objc.autorelease_pool():
            for name, operation, message in [
                ("media", self._request_media_access, "Bibliothekszugriff ist verfügbar."),
                (
                    "automation",
                    self._request_automation_access,
                    "Automation für die Musik-App ist verfügbar.",
                ),
            ]:
                try:
                    operation()
                    results[name] = {"status": "granted", "message": message}
                except Exception as exc:
                    error = exc if isinstance(exc, AppError) else self._native_error(exc)
                    if error.code == "WRITE_UNCONFIRMED":
                        error = AppError(
                            "PERMISSION_REQUEST_PENDING",
                            "Musik hat die Freigabe noch nicht bestätigt. Bitte prüfe offene macOS-Dialoge und frage danach erneut an.",
                            504,
                        )
                    results[name] = {"status": "unavailable", "message": error.message, "code": error.code}
        return {
            "mode": "music",
            "needsSettings": any(value["status"] != "granted" for value in results.values()),
            **results,
        }

    def snapshot(self) -> Snapshot:
        import iTunesLibrary as IL
        import objc

        progress = getattr(self, "on_progress", None)
        with objc.autorelease_pool():
            try:
                from .permissions import require_media_access

                # Opening and reloading can themselves trigger a macOS consent
                # dialog. Ordinary connects must stop before either without access.
                if progress:
                    progress("permission-check", 0, 0)
                require_media_access()
                if self.library is None:
                    if progress:
                        progress("native-open", 0, 0)
                    self._open_library()
                else:
                    if progress:
                        progress("native-reload", 0, 0)
                    if not self.library.reloadData():
                        raise AppError(
                            "REFRESH_FAILED",
                            "Die Bibliothek konnte nicht aktualisiert werden. Der letzte Stand bleibt erhalten.",
                            503,
                        )
                if progress:
                    progress("native-playlists", 0, 0)
                native_playlists = list(self.library.allPlaylists())
                masters = sorted(canonical_id(p.persistentID()) for p in native_playlists if p.isMaster())
                if len(masters) != 1:
                    raise AppError(
                        "LIBRARY_ID_UNAVAILABLE",
                        "Die Hauptbibliothek konnte nicht eindeutig erkannt werden.",
                        503,
                    )
                scope = "music-" + digest(masters)
                if progress:
                    progress("native-tracks", 0, 0)
                native_items = self.library.allMediaItems()
                items = {}
                for index, item in enumerate(native_items, 1):
                    if item.mediaKind() == IL.ITLibMediaItemMediaKindSong:
                        items[canonical_id(item.persistentID())] = item
                    if progress and (index % 1000 == 0 or index == len(native_items)):
                        progress("native-tracks", index, len(native_items))
                tracks = []
                if progress:
                    progress("tracks", 0, len(items))
                for index, (ident, item) in enumerate(items.items(), 1):
                    artist, album = item.artist(), item.album()
                    raw = int(item.rating() or 0)
                    date = item.lastPlayedDate()
                    added = item.addedDate()
                    last = (
                        datetime.fromtimestamp(date.timeIntervalSince1970(), timezone.utc).isoformat()
                        if date
                        else None
                    )
                    tracks.append(
                        Track(
                            id=ident,
                            title=item.title() or "Ohne Titel",
                            artist=(artist.name() if artist else "") or "",
                            album=(album.title() if album else "") or "",
                            albumArtist=(album.albumArtist() if album else "") or "",
                            genre=item.genre() or "",
                            year=int(item.year()) or None,
                            durationSeconds=int((item.totalTime() or 0) / 1000),
                            ratingRaw=raw,
                            ratingOrigin=self._rating_origin(raw, item.isRatingComputed()),
                            playCount=int(item.playCount() or 0),
                            lastPlayed=last,
                            addedDate=(
                                datetime.fromtimestamp(added.timeIntervalSince1970(), timezone.utc).isoformat()
                                if added
                                else None
                            ),
                            isCloud=bool(item.isCloud()),
                            hasArtwork=bool(item.hasArtworkAvailable()),
                        )
                    )
                    if progress and (index % 250 == 0 or index == len(items)):
                        progress("tracks", index, len(items))
                playlists = []
                if progress:
                    progress("playlists", 0, len(native_playlists))
                for index, playlist in enumerate(native_playlists, 1):
                    if progress:
                        progress("playlists", index - 1, len(native_playlists))
                    members = []
                    for item in playlist.items() or []:
                        ident = canonical_id(item.persistentID())
                        if ident in items:
                            members.append(ident)
                    playlists.append(
                        Playlist(
                            canonical_id(playlist.persistentID()),
                            playlist.name() or "Ohne Namen",
                            members,
                            bool(playlist.isMaster()),
                        )
                    )
                    if progress and (index % 10 == 0 or index == len(native_playlists)):
                        progress("playlists", index, len(native_playlists))
                if progress:
                    progress("native-cleanup", 0, len(tracks))
                self.items = items
                self.scope = scope
                return Snapshot(scope, tracks, playlists)
            except AppError:
                raise
            except Exception as exc:
                raise self._native_error(exc, "LIBRARY_READ_FAILED") from exc

    def _music(self):
        from ScriptingBridge import SBApplication

        if self.app is None:
            self.delegate = music_delegate_class().alloc().init()
            self.delegate.last_error = 0
            self.app = SBApplication.applicationWithBundleIdentifier_("com.apple.Music")
            if self.app is None:
                raise AppError("MUSIC_UNAVAILABLE", "Die Musik-App konnte nicht gefunden werden.", 503)
            self.app.setDelegate_(self.delegate)
            self.app.setTimeout_(60 * 8)
        self.delegate.last_error = 0
        if not self.app.isRunning():
            self.app.activate()
        return self.app

    def _check_event(self):
        error = self.delegate.last_error if self.delegate else 0
        if error == -1743:
            raise self._native_error(Exception("-1743"))
        if error == -1712:
            raise AppError(
                "WRITE_UNCONFIRMED",
                "Musik antwortet nicht rechtzeitig. Bitte aktualisiere den Titel vor einem neuen Versuch.",
                504,
            )
        if error:
            raise AppError("MUSIC_EVENT_FAILED", f"Die Musik-App hat einen Fehler gemeldet ({error}).", 503)

    def _library_playlist(self):
        app = self._music()
        sources = app.sources()
        self._check_event()
        if not sources:
            raise AppError(
                "MUSIC_NOT_READY",
                "Musik liefert noch keine Bibliothek. Bitte öffne Musik und prüfe die Automation-Freigabe.",
                503,
            )
        libraries = [
            p
            for source in sources
            for p in (source.libraryPlaylists() or [])
        ]
        self._check_event()
        if len(libraries) != 1:
            raise AppError(
                "LIBRARY_AMBIGUOUS", "Die Musik-Hauptbibliothek konnte nicht eindeutig erkannt werden.", 503
            )
        return libraries[0]

    def _playlist_scope(self, playlist) -> str:
        ident = canonical_id(playlist.persistentID())
        self._check_event()
        return "music-" + digest([ident])

    def library_scope(self) -> str:
        import objc

        with objc.autorelease_pool():
            try:
                return self._playlist_scope(self._library_playlist())
            except AppError:
                raise
            except Exception as exc:
                raise self._native_error(exc) from exc

    def _checked_library_playlist(self):
        library = self._library_playlist()
        if self.scope is not None and self._playlist_scope(library) != self.scope:
            raise AppError(
                "LIBRARY_CHANGED", "Die aktive Bibliothek hat sich geändert. Bitte lade die Liste neu.", 409
            )
        return library

    def _find(self, track_id: str):
        from Foundation import NSPredicate

        library = self._checked_library_playlist()
        predicate = NSPredicate.predicateWithFormat_("persistentID == %@", track_id)
        matches = library.tracks().filteredArrayUsingPredicate_(predicate)
        count = len(matches) if matches is not None else 0
        self._check_event()
        # Resolve the predicate once; subsequent properties address the same track.
        track = matches[0].get() if count == 1 else None
        self._check_event()
        if track is None:
            raise AppError(
                "TRACK_NOT_SCRIPTABLE",
                "Dieser Titel ist in der Automation-Schnittstelle nicht verfügbar. Lade ihn gegebenenfalls zuerst in Musik.",
                422,
            )
        return track

    def _read_track_rating(self, track) -> tuple[int, str]:
        raw, kind = int(track.rating() or 0), int(track.ratingKind())
        self._check_event()
        return raw, self._rating_origin(raw, kind == 0x6B527443)

    def read_rating(self, track_id: str) -> tuple[int, str]:
        import objc

        with objc.autorelease_pool():
            try:
                return self._read_track_rating(self._find(track_id))
            except AppError:
                raise
            except Exception as exc:
                raise self._native_error(exc) from exc

    def write_rating(self, track_id: str, stars: int) -> tuple[int, str]:
        import objc

        with objc.autorelease_pool():
            try:
                track = self._find(track_id)
                track.setRating_(stars * 20)
                self._check_event()
                self._checked_library_playlist()
                raw, origin = self._read_track_rating(track)
                if (stars and (raw != stars * 20 or origin != "user")) or (not stars and origin == "user"):
                    raise AppError(
                        "WRITE_UNCONFIRMED",
                        "Musik hat die neue Bewertung noch nicht bestätigt. Bitte aktualisiere die Bibliothek.",
                        409,
                    )
                return raw, origin
            except AppError:
                raise
            except Exception as exc:
                raise self._native_error(exc) from exc

    def artwork(self, track_id: str) -> tuple[bytes, str] | None:
        import objc
        from AppKit import NSBitmapImageFileTypeJPEG, NSBitmapImageRep

        with objc.autorelease_pool():
            item = self.items.get(track_id)
            artwork = item.artwork() if item else None
            image = artwork.image() if artwork else None
            if image is None:
                return None
            bitmap = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
            data = (
                bitmap.representationUsingType_properties_(NSBitmapImageFileTypeJPEG, {}) if bitmap else None
            )
            return (bytes(data), "image/jpeg") if data else None
