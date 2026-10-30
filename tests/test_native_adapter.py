"""Native bridge behavior with fake Music objects; never contacts Music.app."""

from types import SimpleNamespace

import pytest

pytest.importorskip("iTunesLibrary")

from itunesremote.adapters import MusicAdapter, music_delegate_class  # noqa: E402
from itunesremote.models import AppError, Snapshot, Track, digest  # noqa: E402
from itunesremote.service import LibraryService  # noqa: E402


class FakeTrack:
    def __init__(self, ident="0000000000000001", raw=0, kind=0x6B527455):
        self.ident, self.raw, self.kind = ident, raw, kind
        self.ignore_write = False

    def rating(self):
        return self.raw

    def ratingKind(self):
        return self.kind

    def setRating_(self, value):
        if not self.ignore_write:
            self.raw = value
            self.kind = 0x6B527455

    def get(self):
        return self


class FakeTracks(list):
    def filteredArrayUsingPredicate_(self, predicate):
        return [t for t in self if predicate.evaluateWithObject_({"persistentID": t.ident})]


class FakePlaylist:
    def __init__(self, tracks):
        self.items = FakeTracks(tracks)

    def respondsToSelector_(self, selector):
        return True

    def specialKind(self):
        return 0x6B53704C

    def persistentID(self):
        return "00000000000000FF"

    def tracks(self):
        return self.items


def adapter_with(track):
    adapter = MusicAdapter()
    adapter.delegate = SimpleNamespace(last_error=0)
    playlist = FakePlaylist([track])
    source = SimpleNamespace(playlists=lambda: [playlist], libraryPlaylists=lambda: [playlist])
    adapter.app = SimpleNamespace(
        isRunning=lambda: True, sources=lambda: [source],
    )
    return adapter


def test_native_setter_reads_back_actual_value():
    track = FakeTrack()
    adapter = adapter_with(track)
    assert adapter.write_rating(track.ident, 4) == (80, "user")
    assert adapter.write_rating(track.ident, 0) == (0, "none")


def test_native_silent_write_failure_does_not_report_success():
    track = FakeTrack(raw=20)
    track.ignore_write = True
    with pytest.raises(AppError, match="noch nicht bestätigt") as error:
        adapter_with(track).write_rating(track.ident, 5)
    assert error.value.code == "WRITE_UNCONFIRMED"
    assert track.raw == 20


def test_rating_does_not_query_each_user_playlist():
    track = FakeTrack()
    adapter = adapter_with(track)
    source = adapter.app.sources()[0]
    playlist = source.libraryPlaylists()[0]

    def unexpected(*args):
        raise AssertionError("Ratings must not enumerate or inspect user playlists")

    source.playlists = unexpected
    playlist.specialKind = unexpected
    adapter.scope = adapter.library_scope()
    assert adapter.read_rating(track.ident) == (0, "none")
    assert adapter.write_rating(track.ident, 4) == (80, "user")


def test_write_resolves_the_track_once_and_reads_back_that_target(monkeypatch):
    track = FakeTrack()
    proxy = SimpleNamespace(ident=track.ident, get=lambda: track)
    adapter = adapter_with(proxy)
    adapter.scope = adapter.library_scope()
    playlist = adapter.app.sources()[0].libraryPlaylists()[0]
    original = playlist.items.filteredArrayUsingPredicate_
    lookups = []

    def lookup(predicate):
        lookups.append(predicate)
        assert len(lookups) == 1, "Readback must reuse the resolved target"
        return original(predicate)

    monkeypatch.setattr(playlist.items, "filteredArrayUsingPredicate_", lookup)
    assert adapter.write_rating(track.ident, 5) == (100, "user")
    assert track.raw == 100
    assert len(lookups) == 1


@pytest.mark.parametrize("event_error", [0, -1743])
def test_failed_target_resolution_never_writes(event_error):
    track = FakeTrack(raw=20)
    adapter = adapter_with(track)

    def missing_target():
        adapter.delegate.last_error = event_error
        return None

    track.get = missing_target
    with pytest.raises(AppError) as error:
        adapter.write_rating(track.ident, 5)
    assert error.value.code == ("AUTOMATION_DENIED" if event_error else "TRACK_NOT_SCRIPTABLE")
    assert track.raw == 20


def test_library_switch_after_write_is_not_reported_as_confirmed():
    track = FakeTrack()
    adapter = adapter_with(track)
    source = adapter.app.sources()[0]
    original = track.setRating_
    adapter.scope = adapter.library_scope()
    other = FakePlaylist([track])
    other.persistentID = lambda: "00000000000000FE"

    def write_and_switch(raw):
        original(raw)
        source.playlists = source.libraryPlaylists = lambda: [other]

    track.setRating_ = write_and_switch
    with pytest.raises(AppError) as error:
        adapter.write_rating(track.ident, 5)
    assert error.value.code == "LIBRARY_CHANGED"


@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_ambiguous_main_library_still_fails(count):
    adapter = adapter_with(FakeTrack())
    source = adapter.app.sources()[0]
    playlists = [FakePlaylist([]) for _ in range(count)]
    source.playlists = source.libraryPlaylists = lambda: playlists
    with pytest.raises(AppError) as error:
        adapter.library_scope()
    assert error.value.code == "LIBRARY_AMBIGUOUS"


@pytest.mark.parametrize(
    ("raw", "kind", "origin"),
    [(0, 0x6B527455, "none"), (0, 0x6B527443, "none"),
     (80, 0x6B527455, "user"), (80, 0x6B527443, "album")],
)
def test_native_rating_origin_requires_actual_stars(raw, kind, origin):
    track = FakeTrack(raw=raw, kind=kind)
    assert adapter_with(track).read_rating(track.ident) == (raw, origin)


@pytest.mark.parametrize("cached_origin", ["none", "album"])
@pytest.mark.parametrize("kind", [0x6B527455, 0x6B527443])
def test_first_native_rating_saves_with_different_zero_star_origins(
    tmp_path, monkeypatch, cached_origin, kind,
):
    native = FakeTrack(kind=kind)
    adapter = adapter_with(native)
    scope = adapter.library_scope()
    snapshot = Snapshot(scope, [Track(native.ident, "Unbewertet", ratingOrigin=cached_origin)], [])
    monkeypatch.setattr(adapter, "snapshot", lambda: snapshot)
    library = LibraryService(tmp_path, adapter=adapter)
    try:
        library.refresh()
        track = library.store.track(native.ident)
        result = library.rate(native.ident, {
            "stars": 4,
            "libraryScope": scope,
            "expectedRevision": track["ratingRevision"],
            "requestId": "first-native-rating",
        }, "owner")
        assert result["state"] == "confirmed"
        assert (result["track"]["ratingRaw"], result["track"]["ratingOrigin"]) == (80, "user")
        assert (native.raw, native.kind) == (80, 0x6B527455)
        assert library.store.track(native.ident) == result["track"]
    finally:
        library.close()


def test_native_lookup_does_not_fall_back_to_a_similar_title():
    adapter = adapter_with(FakeTrack())
    with pytest.raises(AppError) as error:
        adapter.read_rating("0000000000000002")
    assert error.value.code == "TRACK_NOT_SCRIPTABLE"


def test_library_identity_does_not_enumerate_tracks():
    adapter = adapter_with(FakeTrack())
    playlist = adapter.app.sources()[0].playlists()[0]

    def unexpected():
        raise AssertionError("Identity checks must not fetch tracks")

    playlist.tracks = unexpected
    assert adapter.library_scope() == "music-" + digest(["00000000000000FF"])
    assert adapter.library is None


@pytest.mark.parametrize("action", ["read_rating", "write_rating"])
def test_switched_library_is_rejected_during_track_lookup(action):
    track = FakeTrack(raw=20)
    adapter = adapter_with(track)
    adapter.scope = "previous-library"
    with pytest.raises(AppError) as error:
        getattr(adapter, action)(track.ident, *([5] if action == "write_rating" else []))
    assert error.value.code == "LIBRARY_CHANGED"
    assert track.raw == 20


def test_delegate_class_is_stable_and_declares_the_native_callback():
    assert music_delegate_class() is music_delegate_class()
    assert music_delegate_class().instancesRespondToSelector_(b"eventDidFail:withError:")


def test_permissions_do_not_read_or_change_music_tracks(monkeypatch):
    from itunesremote import permissions

    track = FakeTrack(raw=60)
    adapter = adapter_with(track)
    calls = []
    monkeypatch.setattr(permissions, "request_media_access", lambda: calls.append("media"))
    monkeypatch.setattr(permissions, "request_automation_access", lambda: calls.append("automation"))
    result = adapter.request_permissions()
    assert result["media"]["status"] == result["automation"]["status"] == "granted"
    assert calls == ["media", "automation"]
    assert result["needsSettings"] is False
    assert track.raw == 60
    assert adapter.library is None


def test_denied_media_access_does_not_skip_independent_automation_request(monkeypatch):
    adapter = MusicAdapter()
    requested = []

    def deny_media():
        requested.append("media")
        raise AppError("MEDIA_ACCESS_DENIED", "Medienfreigabe fehlt", 403)

    monkeypatch.setattr(adapter, "_request_media_access", deny_media)
    monkeypatch.setattr(adapter, "_request_automation_access", lambda: requested.append("automation"))
    result = adapter.request_permissions()
    assert requested == ["media", "automation"]
    assert result["media"]["status"] == "unavailable"
    assert result["automation"]["status"] == "granted"
    assert result["needsSettings"] is True


def test_denied_automation_is_reported_independently(monkeypatch):
    from itunesremote import permissions

    adapter = MusicAdapter()
    monkeypatch.setattr(permissions, "request_media_access", lambda: None)

    def deny():
        raise AppError("AUTOMATION_DENIED", "Automation fehlt", 403)

    monkeypatch.setattr(permissions, "request_automation_access", deny)
    result = adapter.request_permissions()
    assert result["media"]["status"] == "granted"
    assert result["automation"]["code"] == "AUTOMATION_DENIED"
    assert adapter.library is None


def test_permission_timeout_is_not_reported_as_a_rating_write(monkeypatch):
    adapter = MusicAdapter()
    monkeypatch.setattr(adapter, "_request_media_access", lambda: None)

    def timed_out():
        raise AppError("WRITE_UNCONFIRMED", "Rating timeout", 504)

    monkeypatch.setattr(adapter, "_request_automation_access", timed_out)
    result = adapter.request_permissions()
    assert result["automation"]["code"] == "PERMISSION_REQUEST_PENDING"
    assert "Dialog" in result["automation"]["message"]


@pytest.mark.parametrize("added_timestamp", [None, 1704110400.0])
@pytest.mark.parametrize(
    ("raw", "computed", "origin"),
    [(0, False, "none"), (0, True, "none"), (80, False, "user"), (80, True, "album")],
)
def test_native_library_accepts_missing_metadata_and_reads_added_date(
    added_timestamp, raw, computed, origin, monkeypatch,
):
    import iTunesLibrary as IL
    from itunesremote import permissions

    monkeypatch.setattr(permissions, "media_authorization_status", lambda: 3)

    item = SimpleNamespace(
        persistentID=lambda: 1,
        mediaKind=lambda: IL.ITLibMediaItemMediaKindSong,
        title=lambda: None,
        artist=lambda: SimpleNamespace(name=lambda: None),
        album=lambda: SimpleNamespace(title=lambda: None, albumArtist=lambda: None),
        rating=lambda: raw,
        lastPlayedDate=lambda: None,
        addedDate=lambda: (
            SimpleNamespace(timeIntervalSince1970=lambda: added_timestamp)
            if added_timestamp is not None
            else None
        ),
        genre=lambda: None,
        year=lambda: 0,
        totalTime=lambda: 0,
        isRatingComputed=lambda: computed,
        playCount=lambda: 0,
        isCloud=lambda: False,
        hasArtworkAvailable=lambda: False,
    )
    master = SimpleNamespace(
        persistentID=lambda: 255, isMaster=lambda: True, name=lambda: "Library", items=lambda: [item]
    )
    adapter = MusicAdapter()
    adapter.library = SimpleNamespace(
        reloadData=lambda: True, allPlaylists=lambda: [master], allMediaItems=lambda: [item]
    )
    track = adapter.snapshot().tracks[0]
    assert track.title == "Ohne Titel"
    assert track.artist == track.album == track.albumArtist == ""
    assert track.addedDate == ("2024-01-01T12:00:00+00:00" if added_timestamp is not None else None)
    assert (track.ratingRaw, track.ratingOrigin) == (raw, origin)
    assert track.rating_revision == digest([track.id, raw, origin])


@pytest.mark.parametrize("already_open", [False, True])
@pytest.mark.parametrize("status", [0, 1, 2])
def test_connect_without_media_permission_neither_opens_nor_reloads(monkeypatch, already_open, status):
    from itunesremote import permissions

    def unexpected(*args):
        raise AssertionError("Missing consent must stop before native library access")

    monkeypatch.setattr(permissions, "media_authorization_status", lambda: status)
    adapter = MusicAdapter()
    monkeypatch.setattr(adapter, "_open_library", unexpected)
    if already_open:
        adapter.library = SimpleNamespace(
            reloadData=unexpected, allPlaylists=unexpected, allMediaItems=unexpected
        )
    for _ in range(3):
        with pytest.raises(AppError) as error:
            adapter.snapshot()
        assert error.value.code == ("MEDIA_PERMISSION_REQUIRED" if status == 0 else "MEDIA_ACCESS_DENIED")
