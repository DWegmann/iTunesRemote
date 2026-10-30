import sqlite3
import time
from threading import Event

import pytest
from conftest import HOST_KEY, browser_login
from itunesremote.api import COOKIE, create_app
from itunesremote.models import AppError, digest
from starlette.testclient import TestClient


def payload(client, track, stars, request):
    return {"libraryScope": client.get("/api/v1/status").json()["libraryScope"], "items": [{
        "trackId": track["id"], "stars": stars,
        "expectedRevision": track["ratingRevision"], "requestId": request,
    }]}


def jobs(client, ids=()):
    status = client.get("/api/v1/status").json()
    return client.get('/api/v1/rating-queue', params={
        "mode": status["mode"], "libraryScope": status["libraryScope"], "ids": ",".join(ids),
    }).json()["items"]


def settled(client, ids):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = {job["requestId"]: job for job in jobs(client, ids)}
        if all(ident in current and current[ident]["state"] not in {"queued", "running"} for ident in ids):
            return current
        time.sleep(0.02)
    raise AssertionError("Queue did not settle")


def test_enqueue_stays_fast_and_latest_choice_wins_while_music_is_busy(browser, monkeypatch):
    client, headers = browser
    library = client.app.state.library
    first, second = client.get('/api/v1/tracks?rating=unrated').json()["items"][:2]
    started, release = Event(), Event()
    writes = []
    original = library.adapter.write_rating

    def slow(ident, stars):
        writes.append((ident, stars))
        if len(writes) == 1:
            started.set()
            assert release.wait(5)
        return original(ident, stars)

    monkeypatch.setattr(library.adapter, "write_rating", slow)
    try:
        assert client.post('/api/v1/rating-queue', json=payload(client, first, 5, 'queue-first'), headers=headers).status_code == 202
        assert started.wait(2)
        assert client.post('/api/v1/rating-queue/queue-first/dismiss', json={}, headers=headers).status_code == 409
        began = time.monotonic()
        for track, stars, request in [(second, 4, 'queue-second'), (first, 1, 'queue-obsolete'), (first, 3, 'queue-latest')]:
            assert client.post('/api/v1/rating-queue', json=payload(client, track, stars, request), headers=headers).status_code == 202
        assert client.get('/api/v1/tracks?query=Radiohead').status_code == 200
        assert time.monotonic() - began < 0.5
        assert len(jobs(client)) == 3  # One running write, two latest choices.
    finally:
        release.set()
    result = settled(client, ['queue-first', 'queue-second', 'queue-obsolete', 'queue-latest'])
    assert result['queue-obsolete']['state'] == 'superseded'
    assert result['queue-latest']['state'] == 'confirmed'
    assert writes == [(first['id'], 5), (second['id'], 4), (first['id'], 3)]
    assert library.adapter.read_rating(first['id']) == (60, 'user')


def test_quick_changes_are_coalesced_before_the_batch_starts(browser, monkeypatch):
    client, headers = browser
    library = client.app.state.library
    track = client.get('/api/v1/tracks?rating=unrated').json()['items'][0]
    writes = []
    original = library.adapter.write_rating
    monkeypatch.setattr(library.adapter, 'write_rating', lambda ident, stars: (writes.append(stars), original(ident, stars))[1])
    data = payload(client, track, 5, 'batch-old')
    data['items'].append({**data['items'][0], 'stars': 2, 'requestId': 'batch-final'})
    assert client.post('/api/v1/rating-queue', json=data, headers=headers).status_code == 202
    current = settled(client, ['batch-old', 'batch-final'])
    assert current['batch-old']['state'] == 'superseded'
    assert current['batch-final']['state'] == 'confirmed'
    assert writes == [2]


def test_delayed_older_choices_do_not_replace_a_newer_choice(browser):
    client, headers = browser
    client.app.state.library.connected = False
    track = client.get('/api/v1/tracks?rating=unrated').json()['items'][0]
    newer = payload(client, track, 4, 'queue-newer-choice')
    newer['items'][0]['chosenAt'] = 200
    older = payload(client, track, 1, 'queue-delayed-choice')
    older['items'][0]['chosenAt'] = 100
    for data in [newer, older]:
        assert client.post('/api/v1/rating-queue', json=data, headers=headers).status_code == 202
    client.app.state.library.connected = True
    result = settled(client, ['queue-newer-choice', 'queue-delayed-choice'])
    assert result['queue-delayed-choice']['state'] == 'superseded'
    assert result['queue-newer-choice']['state'] == 'confirmed'
    assert client.app.state.library.adapter.read_rating(track['id']) == (80, 'user')


def test_own_chain_does_not_rebase_over_another_clients_change(browser):
    client, headers = browser
    track = client.get('/api/v1/tracks?rating=unrated').json()['items'][0]
    assert client.post('/api/v1/rating-queue', json=payload(client, track, 5, 'own-chain-first'), headers=headers).status_code == 202
    first = settled(client, ['own-chain-first'])['own-chain-first']['result']['track']
    response = client.put(f"/api/v1/tracks/{track['id']}/rating", headers={'Authorization': f'Bearer {HOST_KEY}'}, json={
        'stars': 2, 'libraryScope': client.get('/api/v1/status').json()['libraryScope'],
        'expectedRevision': first['ratingRevision'], 'requestId': 'other-client-change',
    })
    assert response.status_code == 200
    assert client.post('/api/v1/rating-queue', json=payload(client, track, 3, 'own-chain-stale'), headers=headers).status_code == 202
    result = settled(client, ['own-chain-stale'])['own-chain-stale']
    assert result['result']['error']['code'] == 'RATING_CONFLICT'
    assert client.app.state.library.adapter.read_rating(track['id']) == (40, 'user')


def test_queue_batches_are_atomic_idempotent_and_private(browser):
    client, headers = browser
    client.app.state.library.connected = False
    track = client.get('/api/v1/tracks').json()['items'][0]
    data = payload(client, track, 5, 'queue-private')
    invalid = {**data, 'items': [*data['items'], {**data['items'][0], 'requestId': 'queue-invalid', 'stars': True}]}
    assert client.post('/api/v1/rating-queue', json=invalid, headers=headers).status_code == 400
    assert jobs(client) == []
    for _ in range(2):
        assert client.post('/api/v1/rating-queue', json=data, headers=headers).status_code == 202
    assert len(jobs(client)) == 1
    changed = {**data, 'items': [{**data['items'][0], 'stars': 1}]}
    assert client.post('/api/v1/rating-queue', json=changed, headers=headers).status_code == 409
    other = {'Authorization': f'Bearer {HOST_KEY}'}
    status = client.get('/api/v1/status').json()
    assert client.get('/api/v1/rating-queue', params={'libraryScope': status['libraryScope']}, headers=other).json()['items'] == []
    assert client.post('/api/v1/rating-queue/queue-private/dismiss', json={}, headers=other).status_code == 404
    assert client.post('/api/v1/library/connect', json={'mode': 'music'}, headers=headers).status_code == 409
    assert client.post('/api/v1/rating-queue/queue-private/dismiss', json={}, headers=headers).status_code == 200
    assert jobs(client) == []


def test_conflicts_do_not_stop_other_ratings_and_need_a_new_choice(browser):
    client, headers = browser
    library = client.app.state.library
    first, second = client.get('/api/v1/tracks?rating=unrated').json()['items'][:2]
    library.adapter.write_rating(first['id'], 2)
    data = payload(client, first, 5, 'queue-conflict')
    data['items'] += payload(client, second, 4, 'queue-success')['items']
    assert client.post('/api/v1/rating-queue', json=data, headers=headers).status_code == 202
    current = settled(client, ['queue-conflict', 'queue-success'])
    assert current['queue-conflict']['state'] == 'failed'
    assert current['queue-conflict']['result']['error']['code'] == 'RATING_CONFLICT'
    assert current['queue-success']['state'] == 'confirmed'
    assert library.adapter.read_rating(first['id']) == (40, 'user')
    track = client.get(f"/api/v1/tracks/{first['id']}").json()
    assert client.post('/api/v1/rating-queue', json=payload(client, track, 5, 'queue-reconsidered'), headers=headers).status_code == 202
    assert settled(client, ['queue-reconsidered'])['queue-reconsidered']['state'] == 'confirmed'
    assert all(job['state'] != 'failed' for job in jobs(client))


@pytest.mark.parametrize('journal', ['untouched', 'confirmed', 'pending'])
def test_queue_recovers_after_restart_without_replaying_uncertain_writes(tmp_path, monkeypatch, journal):
    data_dir, web = tmp_path / 'data', tmp_path / 'web'
    web.mkdir()
    app = create_app(data_dir, web, HOST_KEY, 'demo')
    app.state.library.connected = False
    with TestClient(app) as client:
        headers = browser_login(client)
        track = client.get('/api/v1/tracks?rating=unrated').json()['items'][0]
        data = payload(client, track, 5, 'queue-restart')
        assert client.post('/api/v1/rating-queue', json=data, headers=headers).status_code == 202
        owner = app.state.auth.authenticate('', client.cookies[COOKIE]).owner
        if journal != 'untouched':
            job = app.state.rating_queue.claim('queue-restart', app.state.library.store.path)
            body = {key: data['items'][0][key] for key in ['stars', 'expectedRevision', 'requestId']}
            body['libraryScope'] = data['libraryScope']
            if journal == 'confirmed':
                app.state.library.connected = True
                app.state.library.rate(track['id'], body, owner)
                app.state.library.connected = False
            else:
                store = app.state.library.store
                store.db.execute(
                    "INSERT INTO operations (owner,request,fingerprint,scope,state) VALUES (?,?,?,?,'pending')",
                    (owner, job['id'], digest([track['id'], body]), data['libraryScope']),
                )
                store.db.commit()
        cookies = dict(client.cookies)
    restored = create_app(data_dir, web, HOST_KEY, 'demo')
    if journal != 'untouched':
        def unexpected(*args):
            raise AssertionError('Completed or ambiguous writes must not be replayed')
        monkeypatch.setattr(restored.state.library.adapter, 'write_rating', unexpected)
    with TestClient(restored) as client:
        client.cookies.update(cookies)
        result = settled(client, ['queue-restart'])['queue-restart']
        assert result['state'] == ('failed' if journal == 'pending' else 'confirmed')
        if journal == 'pending':
            assert result['result']['error']['code'] == 'WRITE_UNCONFIRMED'


def test_a_failed_write_is_kept_without_automatic_repetition(browser, monkeypatch):
    client, headers = browser
    track = client.get('/api/v1/tracks').json()['items'][0]
    writes = []

    def fail(*args):
        writes.append(args)
        raise AppError('AUTOMATION_DENIED', 'Simulierter Freigabefehler', 403)

    monkeypatch.setattr(client.app.state.library.adapter, 'write_rating', fail)
    assert client.post('/api/v1/rating-queue', json=payload(client, track, 5, 'queue-denied'), headers=headers).status_code == 202
    assert settled(client, ['queue-denied'])['queue-denied']['state'] == 'failed'
    time.sleep(0.5)
    assert len(writes) == 1
    assert jobs(client)[0]['state'] == 'failed'


def test_temporary_queue_errors_retry_the_journal_without_repeating_music_writes(browser, monkeypatch):
    client, headers = browser
    track = client.get('/api/v1/tracks?rating=unrated').json()['items'][0]
    queue = client.app.state.rating_queue
    counts = {'next_batch': 0, 'finish': 0, 'write': 0}
    for name in ['next_batch', 'finish']:
        original = getattr(queue, name)

        def flaky(*args, operation=name, function=original):
            counts[operation] += 1
            if counts[operation] == 1:
                raise sqlite3.OperationalError('Simulated queue contention')
            return function(*args)

        monkeypatch.setattr(queue, name, flaky)
    original_write = client.app.state.library.adapter.write_rating

    def write(*args):
        counts['write'] += 1
        return original_write(*args)

    monkeypatch.setattr(client.app.state.library.adapter, 'write_rating', write)
    assert client.post('/api/v1/rating-queue', json=payload(client, track, 5, 'queue-journal-retry'), headers=headers).status_code == 202
    assert settled(client, ['queue-journal-retry'])['queue-journal-retry']['state'] == 'confirmed'
    assert counts['write'] == 1
    assert counts['finish'] == 2
