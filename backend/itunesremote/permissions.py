"""Lightweight, public authorization APIs. Never enumerate the Music library."""

from __future__ import annotations

import asyncio
import ctypes
import threading
from functools import cache

from .models import AppError


async def service_native_callbacks():
    """Let Cocoa deliver main-queue callbacks while asyncio owns the main thread."""
    import objc
    from CoreFoundation import CFRunLoopRunInMode, kCFRunLoopDefaultMode

    while True:
        with objc.autorelease_pool():
            CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.001, False)
        await asyncio.sleep(0.05)


def initialize_native_app():
    from AppKit import NSApplication

    # Native launch completions need a Cocoa agent application even though
    # this service has no window of its own.
    app = NSApplication.sharedApplication()
    app.finishLaunching()


def media_authorization_status() -> int:
    # StoreKit exposes the public Objective-C authorization API to the Python
    # helper. The replacement MusicKit API is Swift-only. A status read never asks.
    from StoreKit import SKCloudServiceController

    return int(SKCloudServiceController.authorizationStatus())


def require_media_access():
    status = media_authorization_status()
    if status == 3:
        return
    if status == 0:
        raise AppError(
            "MEDIA_PERMISSION_REQUIRED",
            "Die Medienfreigabe fehlt. Wähle in der Mac-App oder unter Verbindung & API ausdrücklich „Berechtigungen anfordern“ und verbinde danach erneut.",
            403,
        )
    raise AppError(
        "MEDIA_ACCESS_DENIED",
        "Bitte erlaube iTunesRemote unter Datenschutz & Sicherheit > Medien & Apple Music den Bibliothekszugriff.",
        403,
    )


def request_media_access():
    import iTunesLibrary as IL

    if media_authorization_status() == 0:
        from StoreKit import SKCloudServiceController

        done = threading.Event()

        def authorized(_status):
            done.set()

        # Only this explicit permission action may ask macOS for consent.
        SKCloudServiceController.requestAuthorization_(authorized)
        if not done.wait(180):
            raise AppError(
                "PERMISSION_REQUEST_PENDING",
                "Die Medienfreigabe wartet noch auf eine Antwort. Bitte prüfe offene macOS-Dialoge.",
                504,
            )
    require_media_access()
    # The lazy option checks initialization without parsing the entire library.
    # Do not request properties or reloadData here: either would start loading.
    library, _error = IL.ITLibrary.alloc().initWithAPIVersion_options_error_(
        "1.0", IL.ITLibInitOptionLazyLoadData, None
    )
    if library is None:
        raise AppError(
            "MEDIA_ACCESS_DENIED",
            "Bitte erlaube den Bibliothekszugriff unter Datenschutz & Sicherheit > Medien & Apple Music.",
            403,
        )


class AEDesc(ctypes.Structure):
    # AEDataModel.h uses #pragma pack(push, 2), including on Apple Silicon.
    _layout_ = "ms"
    _pack_ = 2
    _fields_ = [("descriptorType", ctypes.c_uint32), ("dataHandle", ctypes.c_void_p)]


@cache
def apple_events():
    api = ctypes.CDLL("/System/Library/Frameworks/CoreServices.framework/CoreServices")
    api.AECreateDesc.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_ssize_t, ctypes.POINTER(AEDesc)]
    api.AECreateDesc.restype = ctypes.c_int32
    api.AEDisposeDesc.argtypes = [ctypes.POINTER(AEDesc)]
    api.AEDisposeDesc.restype = ctypes.c_int32
    api.AEDeterminePermissionToAutomateTarget.argtypes = [
        ctypes.POINTER(AEDesc),
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.c_uint8,
    ]
    api.AEDeterminePermissionToAutomateTarget.restype = ctypes.c_int32
    return api


def automation_status(ask: bool = False) -> int:
    api = apple_events()
    target = AEDesc()
    bundle = b"com.apple.Music"
    buffer = ctypes.create_string_buffer(bundle)
    status = api.AECreateDesc(int.from_bytes(b"bund", "big"), buffer, len(bundle), ctypes.byref(target))
    if status:
        return int(status)
    try:
        wildcard = int.from_bytes(b"****", "big")
        return int(
            api.AEDeterminePermissionToAutomateTarget(ctypes.byref(target), wildcard, wildcard, int(ask))
        )
    finally:
        api.AEDisposeDesc(ctypes.byref(target))


def request_automation_access():
    from AppKit import NSRunningApplication, NSWorkspace, NSWorkspaceOpenConfiguration

    if not NSRunningApplication.runningApplicationsWithBundleIdentifier_("com.apple.Music"):
        workspace = NSWorkspace.sharedWorkspace()
        url = workspace.URLForApplicationWithBundleIdentifier_("com.apple.Music")
        if url is None:
            raise AppError("MUSIC_UNAVAILABLE", "Die Musik-App wurde nicht gefunden.", 503)
        config = NSWorkspaceOpenConfiguration.configuration()
        config.setActivates_(False)
        done = threading.Event()
        answer = []

        def launched(app, error):
            answer.append(app is not None and error is None)
            done.set()

        workspace.openApplicationAtURL_configuration_completionHandler_(url, config, launched)
        if not done.wait(15) or not answer[0]:
            raise AppError("MUSIC_NOT_READY", "Musik konnte nicht rechtzeitig geöffnet werden.", 503)
    # Ask the permission API directly. Fetching sources() would unnecessarily
    # wait on Music's data and could confuse consent with library loading.
    status = automation_status(ask=True)
    if status == -1743:
        raise AppError(
            "AUTOMATION_DENIED",
            "Bitte erlaube iTunesRemote unter Datenschutz & Sicherheit > Automation den Zugriff auf Musik.",
            403,
        )
    if status:
        raise AppError(
            "AUTOMATION_UNAVAILABLE",
            f"Die Automation-Freigabe konnte nicht bestätigt werden ({status}).",
            503,
        )
