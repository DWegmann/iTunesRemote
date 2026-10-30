"""Authorization must not enumerate tracks or fetch Music's data."""

import asyncio
import ctypes
import sys
from types import SimpleNamespace

import pytest
from itunesremote import permissions
from itunesremote.models import AppError


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires the native Cocoa main queue")
def test_native_main_queue_callbacks_are_delivered_while_asyncio_is_running():
    from Foundation import NSOperationQueue

    async def verify():
        delivered = asyncio.Event()
        NSOperationQueue.mainQueue().addOperationWithBlock_(delivered.set)
        callback_service = asyncio.create_task(permissions.service_native_callbacks())
        try:
            await asyncio.wait_for(delivered.wait(), timeout=2)
        finally:
            callback_service.cancel()
            with pytest.raises(asyncio.CancelledError):
                await callback_service

    asyncio.run(verify())


def test_apple_event_descriptor_matches_sdk_two_byte_packing():
    assert permissions.AEDesc.dataHandle.offset == 4
    assert ctypes.sizeof(permissions.AEDesc) == 4 + ctypes.sizeof(ctypes.c_void_p)


def media_framework(monkeypatch, library, error=None):
    calls = []

    def initialize(version, options, output):
        calls.append((version, options))
        return library, error

    monkeypatch.setitem(
        sys.modules,
        "iTunesLibrary",
        SimpleNamespace(
            ITLibInitOptionLazyLoadData=1,
            ITLibrary=SimpleNamespace(
                alloc=lambda: SimpleNamespace(initWithAPIVersion_options_error_=initialize)
            ),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "StoreKit",
        SimpleNamespace(SKCloudServiceController=SimpleNamespace(authorizationStatus=lambda: 3)),
    )
    return calls


def test_media_check_uses_lazy_initialization(monkeypatch):
    calls = media_framework(monkeypatch, object())
    permissions.request_media_access()
    assert calls == [("1.0", 1)]


def test_unavailable_media_returns_permission_error(monkeypatch):
    media_framework(monkeypatch, None, object())
    with pytest.raises(AppError) as error:
        permissions.request_media_access()
    assert error.value.code == "MEDIA_ACCESS_DENIED"


def test_media_check_never_queries_or_reloads_library(monkeypatch):
    class UnloadedLibrary:
        def __getattr__(self, name):
            raise AssertionError(f"Authorization must not load library data: {name}")

    media_framework(monkeypatch, UnloadedLibrary())
    permissions.request_media_access()


@pytest.mark.parametrize(
    "status,code", [(0, "MEDIA_PERMISSION_REQUIRED"), (1, "MEDIA_ACCESS_DENIED"), (2, "MEDIA_ACCESS_DENIED")]
)
def test_media_preflight_never_prompts_when_permission_is_missing(monkeypatch, status, code):
    calls = media_framework(monkeypatch, object())
    monkeypatch.setattr(permissions, "media_authorization_status", lambda: status)
    with pytest.raises(AppError) as error:
        permissions.require_media_access()
    assert error.value.code == code
    assert calls == []


@pytest.mark.parametrize("status", [1, 2, 3])
def test_explicit_permission_action_does_not_reask_a_decided_status(monkeypatch, status):
    calls = media_framework(monkeypatch, object())
    requested = []
    monkeypatch.setitem(
        sys.modules,
        "StoreKit",
        SimpleNamespace(
            SKCloudServiceController=SimpleNamespace(
                authorizationStatus=lambda: status,
                requestAuthorization_=lambda callback: requested.append(True),
            )
        ),
    )
    if status == 3:
        permissions.request_media_access()
        assert calls == [("1.0", 1)]
    else:
        with pytest.raises(AppError) as error:
            permissions.request_media_access()
        assert error.value.code == "MEDIA_ACCESS_DENIED"
        assert calls == []
    assert requested == []


def test_only_explicit_media_permission_action_requests_undecided_access(monkeypatch):
    calls = media_framework(monkeypatch, object())
    status = 0
    requests = []

    def request(callback):
        nonlocal status
        requests.append(True)
        status = 3
        callback(status)

    monkeypatch.setitem(
        sys.modules,
        "StoreKit",
        SimpleNamespace(
            SKCloudServiceController=SimpleNamespace(
                authorizationStatus=lambda: status,
                requestAuthorization_=request,
            )
        ),
    )
    with pytest.raises(AppError, match="Medienfreigabe fehlt"):
        permissions.require_media_access()
    assert not requests and not calls
    permissions.request_media_access()
    assert requests == [True]
    assert calls == [("1.0", 1)]
    permissions.require_media_access()
    permissions.request_media_access()
    assert requests == [True]


def test_media_permission_is_rechecked_after_revocation(monkeypatch):
    media_framework(monkeypatch, object())
    status = 3
    monkeypatch.setattr(permissions, "media_authorization_status", lambda: status)
    permissions.require_media_access()
    status = 1
    with pytest.raises(AppError) as error:
        permissions.require_media_access()
    assert error.value.code == "MEDIA_ACCESS_DENIED"


def test_automation_preflight_disposes_descriptor_and_does_not_fetch_data(monkeypatch):
    calls = []
    api = SimpleNamespace(
        AECreateDesc=lambda *args: 0,
        AEDeterminePermissionToAutomateTarget=lambda *args: calls.append(bool(args[-1])) or 0,
        AEDisposeDesc=lambda target: calls.append("disposed"),
    )
    monkeypatch.setattr(permissions, "apple_events", lambda: api)
    assert permissions.automation_status(ask=False) == 0
    assert calls == [False, "disposed"]


def test_running_music_requires_only_preflight(monkeypatch):
    calls = []
    monkeypatch.setitem(
        sys.modules,
        "AppKit",
        SimpleNamespace(
            NSRunningApplication=SimpleNamespace(
                runningApplicationsWithBundleIdentifier_=lambda bundle: [object()]
            ),
            NSWorkspace=object(),
            NSWorkspaceOpenConfiguration=object(),
        ),
    )
    monkeypatch.setattr(permissions, "automation_status", lambda ask: calls.append(ask) or 0)
    permissions.request_automation_access()
    assert calls == [True]
