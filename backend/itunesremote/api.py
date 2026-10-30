from __future__ import annotations

import asyncio
import logging
import secrets
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .auth import Auth
from .models import AppError, validate_id
from .openapi import schema
from .rating_queue import RatingQueue
from .service import LibraryService

COOKIE = "itunesremote_session"
MAX_BODY = 8192


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, auth: Auth, authorities: set[str]):
        super().__init__(app)
        self.auth, self.authorities = auth, authorities
        self.attempts: deque[float] = deque()

    async def dispatch(self, request: Request, call_next):
        try:
            if request.headers.get("host", "").lower() not in self.authorities:
                raise AppError("INVALID_HOST", "Dieser Host ist nicht freigegeben.", 421)
            request.state.principal = None
            path = request.url.path
            bearer = request.headers.get("authorization", "")
            bearer = bearer[7:] if bearer.lower().startswith("bearer ") else ""
            mutating = request.method not in {"GET", "HEAD", "OPTIONS"}
            public = path in {"/api/v1/auth/login", "/api/v1/auth/exchange", "/api/v1/auth/refresh"}
            if public:
                while self.attempts and self.attempts[0] < time.monotonic() - 60:
                    self.attempts.popleft()
                if len(self.attempts) >= 30:
                    raise AppError("RATE_LIMITED", "Bitte warte vor einem weiteren Anmeldeversuch.", 429)
                self.attempts.append(time.monotonic())
            if path.startswith("/api/") and not public:
                request.state.principal = self.auth.authenticate(bearer, request.cookies.get(COOKIE, ""))
            if mutating:
                origin = request.headers.get("origin")
                if origin and origin != str(request.base_url).rstrip("/"):
                    raise AppError(
                        "INVALID_ORIGIN", "Der Ursprung dieser Anfrage ist nicht freigegeben.", 403
                    )
                principal = request.state.principal
                if principal and principal.kind == "cookie":
                    if not origin or not secrets.compare_digest(
                        request.headers.get("x-csrf-token", ""), principal.csrf
                    ):
                        raise AppError(
                            "CSRF_REJECTED",
                            "Die Browseranfrage konnte nicht bestätigt werden. Bitte lade die Seite neu.",
                            403,
                        )
                if path in {"/api/v1/auth/login", "/api/v1/auth/exchange"} and not origin:
                    raise AppError(
                        "INVALID_ORIGIN", "Die Browseranmeldung benötigt einen bestätigten Ursprung.", 403
                    )
                if request.headers.get("content-type", "").split(";")[0].lower() != "application/json":
                    raise AppError("JSON_REQUIRED", "Diese Anfrage benötigt JSON.", 415)
                # Bound the streamed body as well as Content-Length (which is untrusted).
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > MAX_BODY:
                        raise AppError("BODY_TOO_LARGE", "Die Anfrage ist zu groß.", 413)
                request._body = bytes(body)
            response = await call_next(request)
        except AppError as exc:
            response = JSONResponse(exc.payload(), status_code=exc.status)
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Cache-Control": "no-store",
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            }
        )
        return response


async def body(request: Request) -> dict:
    try:
        result = await request.json()
        if not isinstance(result, dict):
            raise ValueError("Object required")
        return result
    except (ValueError, UnicodeDecodeError):
        raise AppError("INVALID_JSON", "Die Anfrage enthält kein gültiges JSON-Objekt.") from None


def create_app(
    data_dir: Path,
    web_dir: Path,
    host_key: str,
    mode: str = "music",
    authorities: set[str] | None = None,
    service: LibraryService | None = None,
    on_library_progress=None,
) -> Starlette:
    data_dir.mkdir(parents=True, exist_ok=True)
    data_dir.chmod(0o700)
    auth = Auth(data_dir / "auth.sqlite3", host_key)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="music-library")
    readers = ThreadPoolExecutor(max_workers=1, thread_name_prefix="library-cache")
    queue_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rating-outbox")
    rating_queue = RatingQueue(data_dir / "rating-queue.sqlite3")
    queue_wake = asyncio.Event()
    # Construct and use the native adapters on the same worker.
    library = (
        service or executor.submit(LibraryService, data_dir, mode, on_progress=on_library_progress).result()
    )

    refresh_task = None
    mode_lock = asyncio.Lock()

    async def run(function, *args, _timeout=25, _timeout_error=None, _executor=executor, **kwargs):
        future = asyncio.get_running_loop().run_in_executor(_executor, lambda: function(*args, **kwargs))
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=_timeout)
        except TimeoutError:
            raise (
                _timeout_error
                or AppError(
                    "WRITE_UNCONFIRMED",
                    "Die Anfrage läuft noch. Bitte prüfe den Zustand vor einem neuen Versuch.",
                    504,
                )
            ) from None

    async def read(operation, *args, **kwargs):
        return await run(library.read_cached, operation, *args, _executor=readers, **kwargs)

    async def queue_call(operation, *args):
        return await run(getattr(rating_queue, operation), *args, _executor=queue_executor)

    def execute_queued(job):
        if job["attempted"] < time.time() - 86400:
            # The operation journal expires after a day; never replay an ambiguous old write.
            try:
                return library.operation(job["id"], job["owner"])
            except AppError:
                raise AppError("WRITE_UNCONFIRMED", "Der unterbrochene Auftrag muss erneut geprüft werden.", 409) from None
        return library.rate(job["track"], {
            "stars": job["stars"], "libraryScope": job["scope"],
            "expectedRevision": job["revision"], "requestId": job["id"],
        }, job["owner"])

    async def drain_ratings():
        while True:
            await queue_wake.wait()
            queue_wake.clear()
            # Collect quick successive choices before claiming a bounded batch.
            await asyncio.sleep(0.35)
            while True:
                try:
                    batch = await queue_call("next_batch", library.adapter.mode)
                except Exception as exc:
                    logging.getLogger("itunesremote").warning("Rating queue unavailable (%s)", type(exc).__name__)
                    queue_wake.set()
                    await asyncio.sleep(1)
                    break
                if not batch:
                    break
                if importing() or not library.connected:
                    await asyncio.sleep(1)
                    continue
                for ident in batch:
                    if importing() or not library.connected:
                        break
                    try:
                        job = await queue_call("claim", ident, library.store.path)
                        if job is None:
                            continue
                        result = await run(execute_queued, job, _timeout=None)
                    except AppError as exc:
                        result = exc.payload()
                    except Exception:
                        result = AppError(
                            "WRITE_UNCONFIRMED", "Die Bewertung konnte nicht bestätigt werden. Bitte prüfe den Titel.", 503
                        ).payload()
                    pending_result = True
                    while pending_result:
                        try:
                            await queue_call("finish", ident, result)
                            pending_result = False
                        except Exception:
                            # Keep the native result and retry only its journal commit.
                            await asyncio.sleep(1)

    def importing():
        return refresh_task is not None and not refresh_task.done()

    async def cached_status():
        result = await read("status")
        result["refreshing"] = importing() or result["refreshing"]
        return result

    def import_finished(task):
        # Retrieve exceptions even when no HTTP client waits for a background import.
        if not task.cancelled() and task.exception() is not None:
            logging.getLogger("itunesremote").warning("Library refresh failed (%s)", type(task.exception()).__name__)
        queue_wake.set()

    def validate_refresh(data):
        for key in ("ifStale", "background"):
            if type(data.get(key, False)) is not bool:
                raise AppError("INVALID_REFRESH", f"{key} muss ein Wahrheitswert sein.")

    def schedule_refresh(data):
        nonlocal refresh_task
        validate_refresh(data)
        if not importing() and data.get("ifStale", False) and not library.is_stale():
            return None
        if not importing():
            refresh_task = asyncio.create_task(
                run(library.refresh, force=not data.get("ifStale", False), _timeout=None)
            )
            refresh_task.add_done_callback(import_finished)
        return refresh_task

    async def refresh_response(data, task):
        if task is None or data.get("background", False):
            return JSONResponse(await cached_status())
        try:
            return JSONResponse(await asyncio.wait_for(asyncio.shield(task), timeout=600))
        except TimeoutError:
            raise AppError(
                "LIBRARY_IMPORT_PENDING",
                "Die Bibliothek wird im Hintergrund aktualisiert. Der gespeicherte Stand bleibt nutzbar.",
                504,
            ) from None

    def local_admin(request: Request):
        if request.state.principal.kind not in {"host", "cookie"}:
            raise AppError(
                "LOCAL_ADMIN_REQUIRED", "Diese Aktion ist nur über die lokale Mac-Oberfläche verfügbar.", 403
            )

    @asynccontextmanager
    async def lifespan(app):
        queue_task = asyncio.create_task(drain_ratings(), name="rating-queue")
        queue_wake.set()
        try:
            yield
        finally:
            queue_task.cancel()
            try:
                await queue_task
            except asyncio.CancelledError:
                pass
            if importing():
                try:
                    await refresh_task
                except Exception:
                    pass
            await run(library.close)
            executor.shutdown(wait=True)
            readers.shutdown(wait=True)
            queue_executor.shutdown(wait=True)
            auth.close()

    async def error_handler(request, exc: AppError):
        return JSONResponse(exc.payload(), status_code=exc.status)

    async def unexpected_error(request, exc):
        logging.getLogger("itunesremote").error("Request failed (%s)", type(exc).__name__)
        return JSONResponse(
            AppError("INTERNAL_ERROR", "Ein interner Fehler ist aufgetreten.", 500).payload(), status_code=500
        )

    async def health(request):
        return JSONResponse({"ok": True})

    async def status(request):
        return JSONResponse(await cached_status())

    async def capabilities(request):
        result = library.capabilities()
        result["features"]["libraryModeChange"] = request.state.principal.kind != "bearer"
        result["features"]["ratingQueue"] = request.state.principal.kind != "bearer"
        return JSONResponse(result)

    async def playlists(request):
        return JSONResponse({"items": await read("playlists")})

    async def tracks(request):
        q = request.query_params
        try:
            limit = int(q.get("limit", "100"))
        except ValueError:
            raise AppError("INVALID_LIMIT", "Die Seitengröße ist ungültig.") from None
        return JSONResponse(
            await read(
                "query",
                query=q.get("query", ""),
                rating=q.get("rating", "all"),
                playlist_id=q.get("playlistId", ""),
                sort=q.get("sort", "artist"),
                cursor=q.get("cursor", ""),
                limit=limit,
            )
        )

    async def track(request):
        ident = validate_id(request.path_params["id"])
        return JSONResponse(await read("track", ident))

    async def rating(request):
        data = await body(request)
        if importing():
            raise AppError("LIBRARY_BUSY", "Die Bibliothek wird aktualisiert. Bitte warte mit der Bewertung.", 409)
        return JSONResponse(
            await run(library.rate, request.path_params["id"], data, request.state.principal.owner)
        )

    async def rating_outbox(request):
        local_admin(request)
        owner = request.state.principal.owner
        if request.method == "GET":
            mode = request.query_params.get("mode", library.adapter.mode)
            if mode not in {"music", "demo"}:
                raise AppError("INVALID_MODE", "Unbekannter Bibliotheksmodus.")
            ids = request.query_params.get("ids", "").split(",")
            return JSONResponse(await queue_call(
                "list", owner, mode, request.query_params.get("libraryScope", ""), [ident for ident in ids if ident]
            ))
        data = await body(request)
        async with mode_lock:
            result = await queue_call("enqueue", owner, library.adapter.mode, library.store.path, data)
        queue_wake.set()
        return JSONResponse(result, status_code=202)

    async def dismiss_rating(request):
        local_admin(request)
        await body(request)
        await queue_call("dismiss", request.state.principal.owner, request.path_params["id"])
        return JSONResponse({"ok": True})

    async def refresh(request):
        data = await body(request)
        async with mode_lock:
            task = schedule_refresh(data)
        return await refresh_response(data, task)

    async def connect(request):
        local_admin(request)
        data = await body(request)
        mode = data.get("mode", "music")
        if not isinstance(mode, str) or mode not in {"music", "demo"}:
            raise AppError("INVALID_MODE", "Unbekannter Bibliotheksmodus.")
        validate_refresh(data)
        async with mode_lock:
            if mode != library.adapter.mode:
                if importing() or await queue_call("active", library.adapter.mode):
                    raise AppError("LIBRARY_BUSY", "Bitte warte, bis Bewertungen und Aktualisierung abgeschlossen sind.", 409)
                await run(library.set_mode, mode)
            task = schedule_refresh(data)
        return await refresh_response(data, task)

    async def request_permissions(request):
        local_admin(request)
        await body(request)
        return JSONResponse(
            await run(
                library.request_permissions,
                _timeout=300,
                _timeout_error=AppError(
                    "PERMISSION_REQUEST_PENDING",
                    "Die Berechtigungsabfrage wartet noch auf eine Antwort. Bitte prüfe den macOS-Dialog und frage danach erneut an.",
                    504,
                ),
            )
        )

    async def operation(request):
        return JSONResponse(
            await read("operation", request.path_params["request_id"], request.state.principal.owner)
        )

    async def artwork(request):
        if importing():
            return Response(status_code=404)
        result = await run(library.artwork, request.path_params["id"])
        return Response(result[0], media_type=result[1]) if result else Response(status_code=404)

    async def bootstrap(request):
        if request.state.principal.kind != "host":
            raise AppError("LOCAL_ADMIN_REQUIRED", "Nur die Mac-App darf Browseranmeldungen erzeugen.", 403)
        return JSONResponse({"code": auth.bootstrap(), "expiresIn": 60})

    async def password(request):
        if request.state.principal.kind != "host":
            raise AppError("LOCAL_ADMIN_REQUIRED", "Nur die Mac-App darf das Webpasswort anzeigen.", 403)
        return JSONResponse({"password": auth.web_password})

    def browser_response(request, session):
        sid, csrf = session
        response = JSONResponse({"csrfToken": csrf})
        response.set_cookie(
            COOKIE, sid, max_age=43200, httponly=True, samesite="strict", secure=request.url.scheme == "https"
        )
        return response

    async def login(request):
        data = await body(request)
        return browser_response(request, auth.login(data.get("password")))

    async def exchange(request):
        data = await body(request)
        code = data.get("code")
        if not isinstance(code, str) or len(code) > 128:
            raise AppError("INVALID_CODE", "Ungültiger Anmeldelink.")
        return browser_response(request, auth.exchange(code))

    async def session(request):
        principal = request.state.principal
        return JSONResponse({"kind": principal.kind, "csrfToken": principal.csrf})

    async def logout(request):
        auth.logout(request.cookies.get(COOKIE, ""))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE)
        return response

    async def devices(request):
        local_admin(request)
        if request.method == "GET":
            return JSONResponse({"items": auth.devices()})
        data = await body(request)
        return JSONResponse(auth.issue_device(data.get("name", "")), status_code=201)

    async def revoke(request):
        local_admin(request)
        auth.revoke(request.path_params["id"])
        return JSONResponse({"ok": True})

    async def refresh_token(request):
        data = await body(request)
        token = data.get("refreshToken")
        if not isinstance(token, str) or len(token) > 256:
            raise AppError("INVALID_REFRESH_TOKEN", "Ungültiger Gerätezugang.", 401)
        return JSONResponse(auth.refresh(token))

    async def openapi(request):
        return JSONResponse(schema())

    async def index(request):
        file = web_dir / "index.html"
        if not file.is_file():
            return Response(
                "Weboberfläche fehlt. Bitte zuerst npm run build in web/ ausführen.", status_code=503
            )
        return FileResponse(file)

    routes = [Route("/health", health), Route("/", index)]
    endpoints = [
        ("status", status, ["GET"]),
        ("capabilities", capabilities, ["GET"]),
        ("playlists", playlists, ["GET"]),
        ("tracks", tracks, ["GET"]),
        ("tracks/{id}", track, ["GET"]),
        ("tracks/{id}/rating", rating, ["PUT"]),
        ("rating-queue", rating_outbox, ["GET", "POST"]),
        ("rating-queue/{id}/dismiss", dismiss_rating, ["POST"]),
        ("tracks/{id}/artwork", artwork, ["GET"]),
        ("library/refresh", refresh, ["POST"]),
        ("library/connect", connect, ["POST"]),
        ("permissions/request", request_permissions, ["POST"]),
        ("requests/{request_id}", operation, ["GET"]),
        ("auth/bootstrap", bootstrap, ["POST"]),
        ("auth/password", password, ["GET"]),
        ("auth/login", login, ["POST"]),
        ("auth/exchange", exchange, ["POST"]),
        ("auth/session", session, ["GET"]),
        ("auth/logout", logout, ["POST"]),
        ("auth/devices", devices, ["GET", "POST"]),
        ("auth/devices/{id}", revoke, ["DELETE"]),
        ("auth/refresh", refresh_token, ["POST"]),
        ("openapi.json", openapi, ["GET"]),
    ]
    routes.extend(
        Route("/api/v1/" + path, endpoint, methods=methods) for path, endpoint, methods in endpoints
    )
    if (web_dir / "assets").is_dir():
        routes.append(Mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets"))
    app = Starlette(
        routes=routes,
        lifespan=lifespan,
        exception_handlers={AppError: error_handler, Exception: unexpected_error},
    )
    app.add_middleware(SecurityMiddleware, auth=auth, authorities=authorities or {"testserver"})
    app.state.auth, app.state.library = auth, library
    app.state.rating_queue = rating_queue
    return app
