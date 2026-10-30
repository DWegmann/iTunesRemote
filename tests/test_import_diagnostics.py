import json
import stat
from threading import Event, Thread

from itunesremote.adapters import DemoAdapter
from itunesremote.diagnostics import ImportDiagnostics
from itunesremote.models import AppError, Playlist, Snapshot, Track, canonical_id
from itunesremote.service import LibraryService


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_timings_advance_without_progress_and_freeze_on_completion(tmp_path):
    instant = [100.0]
    path = tmp_path / "import.log"
    diagnostics = ImportDiagnostics(path, clock=lambda: instant[0], watch=False)
    try:
        diagnostics.begin("music")
        diagnostics.update({"stage": "native-cleanup", "completed": 0, "total": 50000, "sequence": 1})
        run = diagnostics.metrics()["runId"]
        instant[0] = 112
        diagnostics.check()
        assert diagnostics.metrics()["elapsedSeconds"] == 12
        assert diagnostics.metrics()["idleSeconds"] == 12
        assert records(path)[-1]["event"] == "heartbeat"
        assert diagnostics.metrics()["idleSeconds"] == 12  # Heartbeats do not count as progress.
        diagnostics.update({"stage": "snapshot-tracks", "completed": 0, "total": 50000, "sequence": 2})
        assert diagnostics.metrics()["stageElapsedSeconds"] == 0
        instant[0] = 117
        assert diagnostics.metrics()["stageElapsedSeconds"] == 5
        diagnostics.update({"stage": "done", "completed": 50000, "total": 50000, "sequence": 3})
        instant[0] = 200
        assert diagnostics.metrics()["elapsedSeconds"] == 17
        diagnostics.begin("demo")
        assert diagnostics.metrics()["runId"] != run
        assert diagnostics.metrics()["elapsedSeconds"] == 0
    finally:
        diagnostics.close()


def test_stalled_worker_stack_is_bounded_and_contains_no_locals_or_source(tmp_path):
    instant = [100.0]
    path = tmp_path / "import.log"
    diagnostics = ImportDiagnostics(path, clock=lambda: instant[0], watch=False)
    ready, release = Event(), Event()

    def blocked_import():
        secret_title = "PRIVATE_TITLE_MUST_NOT_APPEAR"
        diagnostics.begin("music")
        diagnostics.update({"stage": "native-cleanup", "completed": 0, "total": 50000, "sequence": 1})
        ready.set()
        assert release.wait(5), secret_title

    worker = Thread(target=blocked_import)
    worker.start()
    try:
        assert ready.wait(2)
        instant[0] = 131
        diagnostics.check()
        stacks = [row for row in records(path) if row["event"] == "worker-stack"]
        assert len(stacks) == 1
        assert any(frame["function"] == "blocked_import" for frame in stacks[0]["stack"])
        assert all(set(frame) == {"file", "line", "function"} for frame in stacks[0]["stack"])
        assert len(stacks[0]["stack"]) <= 20
        instant[0] = 145
        diagnostics.check()
        assert sum(row["event"] == "worker-stack" for row in records(path)) == 1
        diagnostics.failure(AppError("IMPORT_FAILED", "PRIVATE_EXCEPTION_MUST_NOT_APPEAR"))
        content = path.read_text()
        assert "PRIVATE_TITLE_MUST_NOT_APPEAR" not in content
        assert "PRIVATE_EXCEPTION_MUST_NOT_APPEAR" not in content
        assert '"errorCode": "IMPORT_FAILED"' in content
    finally:
        release.set()
        worker.join(timeout=2)
        diagnostics.close()


def test_rotation_retains_three_private_files_and_monitor_stops(tmp_path):
    path = tmp_path / "import.log"
    diagnostics = ImportDiagnostics(path)
    diagnostics.handler.maxBytes = 500
    diagnostics.begin("demo")
    assert diagnostics.thread.is_alive()
    for sequence in range(1, 30):
        diagnostics.update({"stage": f"phase-{sequence}", "completed": 0, "total": 0, "sequence": sequence})
    diagnostics.close()
    assert not diagnostics.thread.is_alive()
    files = list(tmp_path.glob("import.log*"))
    assert len(files) == 3
    assert all(stat.S_IMODE(file.stat().st_mode) == 0o600 for file in files)


def test_snapshot_copy_reports_batches_and_preserves_shared_reference_isolation(tmp_path):
    library = LibraryService(tmp_path, "demo")
    tracks = [Track(canonical_id(index + 1), f"PRIVATE_TITLE_{index}") for index in range(2001)]
    shared = [track.id for track in tracks]
    source = Snapshot(
        "scope",
        tracks,
        [Playlist("one", "PRIVATE_PLAYLIST", shared), Playlist("two", "PRIVATE_PLAYLIST", shared)],
    )
    events = []
    library.on_progress = events.append
    library.diagnostics.begin("demo")
    try:
        copied = library._copy_snapshot(source)
        assert [event["completed"] for event in events if event["stage"] == "snapshot-tracks"] == [
            0,
            1000,
            2000,
            2001,
        ]
        assert copied.tracks == source.tracks
        assert copied.tracks[0] is not source.tracks[0]
        assert copied.playlists[0].trackIds is copied.playlists[1].trackIds
        assert copied.playlists[0].trackIds is not shared
        copied.tracks[0].title = "changed"
        copied.playlists[0].trackIds.clear()
        assert source.tracks[0].title == "PRIVATE_TITLE_0"
        assert len(shared) == 2001
        assert "PRIVATE_TITLE" not in (tmp_path / "import.log").read_text()
        assert "PRIVATE_PLAYLIST" not in (tmp_path / "import.log").read_text()
    finally:
        library.close()


def test_service_records_success_and_failure_with_no_library_contents(tmp_path, monkeypatch):
    library = LibraryService(tmp_path, "demo")
    try:
        path = tmp_path / "import.log"
        assert records(path)[-1]["stage"] == "done"
        assert any(row.get("stage") == "index-signature" for row in records(path))

        def fail():
            raise RuntimeError("PRIVATE_ERROR_DETAIL")

        monkeypatch.setattr(library.adapter, "snapshot", fail)
        try:
            library.refresh()
        except RuntimeError:
            pass
        assert records(path)[-1]["stage"] == "failed"
        content = path.read_text()
        assert "PRIVATE_ERROR_DETAIL" not in content
        assert all(track.title not in content for track in DemoAdapter().tracks.values())
    finally:
        library.close()
