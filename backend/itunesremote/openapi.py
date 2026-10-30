"""Versioned, client-neutral API contract; exported by scripts/export_openapi.py."""

from __future__ import annotations


def ref(name: str) -> dict:
    return {"$ref": f"#/components/schemas/{name}"}


def obj(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties) if required is None else required,
    }


def schema() -> dict:
    string = {"type": "string"}
    nullable = {"type": ["string", "null"]}
    integer = {"type": "integer"}
    boolean = {"type": "boolean"}
    track = obj(
        {
            "id": {"type": "string", "pattern": "^[A-F0-9]{16}$"},
            **{key: string for key in ("title", "artist", "album", "albumArtist", "genre")},
            "year": {"type": ["integer", "null"]},
            "durationSeconds": integer,
            "ratingRaw": {"type": "integer", "minimum": 0, "maximum": 100},
            "ratingOrigin": {"type": "string", "enum": ["none", "user", "album"]},
            "ratingRevision": string,
            "ratingCapability": {"type": "string", "enum": ["unknown", "writable", "unavailable"]},
            "capabilityReason": nullable,
            "playCount": integer,
            "lastPlayed": nullable,
            "addedDate": {"type": ["string", "null"], "format": "date-time"},
            "isCloud": boolean,
            "hasArtwork": boolean,
        }
    )
    schemas = {
        "Track": track,
        "Playlist": obj({"id": string, "name": string, "trackCount": integer, "isMaster": boolean}),
        "Error": obj({"error": obj({"code": string, "message": string, "details": {"type": "object"}})}),
        "Counts": obj({"total": integer, "rated": integer, "unrated": integer}),
        "LibraryProgress": obj(
            {
                "stage": string, "completed": integer, "total": integer, "sequence": integer,
                "runId": string,
                **{key: {"type": "number", "minimum": 0} for key in (
                    "elapsedSeconds", "stageElapsedSeconds", "idleSeconds",
                )},
            }
        ),
        "Status": obj(
            {
                "serverId": string,
                "mode": {"type": "string", "enum": ["music", "demo"]},
                "connected": boolean,
                "refreshing": boolean,
                "progress": {"anyOf": [ref("LibraryProgress"), {"type": "null"}]},
                "hasCache": boolean,
                "libraryScope": nullable,
                "snapshotRevision": nullable,
                "lastSyncedAt": nullable,
                "counts": ref("Counts"),
                "error": {"type": ["object", "null"]},
            }
        ),
        "TrackPage": obj(
            {
                "items": {"type": "array", "items": ref("Track")},
                "total": integer,
                "nextCursor": nullable,
                "snapshotRevision": string,
                "libraryScope": nullable,
            }
        ),
        "RatingInput": obj(
            {
                "stars": {"type": "integer", "minimum": 0, "maximum": 5},
                "libraryScope": string,
                "expectedRevision": string,
                "requestId": {"type": "string", "minLength": 8, "maxLength": 128},
            }
        ),
        "QueuedRatingInput": obj({
            "trackId": track["properties"]["id"],
            "stars": {"type": "integer", "minimum": 0, "maximum": 5},
            "expectedRevision": string,
            "requestId": {"type": "string", "pattern": "^[A-Za-z0-9_-]{8,128}$"},
            "chosenAt": {"type": "number", "exclusiveMinimum": 0, "description": "Monotonic client choice time in milliseconds; older delayed choices are superseded."},
        }, ["trackId", "stars", "expectedRevision", "requestId"]),
        "RatingQueueInput": obj({
            "libraryScope": string,
            "items": {"type": "array", "items": ref("QueuedRatingInput"), "minItems": 1, "maxItems": 25},
        }),
        "QueuedRating": obj({
            "requestId": string, "trackId": string, "title": string, "stars": integer,
            "libraryScope": string, "mode": {"type": "string", "enum": ["music", "demo"]},
            "state": {"type": "string", "enum": ["queued", "running", "confirmed", "failed", "superseded", "dismissed"]},
            "createdAt": {"type": "number"}, "updatedAt": {"type": "number"}, "chosenAt": {"type": "number"},
            "result": {"anyOf": [ref("RatingResult"), ref("Error"), {"type": "null"}]},
        }),
        "RatingQueueResult": obj({
            "items": {"type": "array", "items": ref("QueuedRating")},
            "missingIds": {"type": "array", "items": string},
        }, ["items"]),
        "RefreshInput": obj(
            {
                "ifStale": {"type": "boolean", "default": False},
                "background": {
                    "type": "boolean", "default": False,
                    "description": "Return immediately and poll Status.refreshing; cached reads remain available.",
                },
            }, []
        ),
        "PermissionEntry": obj(
            {
                "status": {"type": "string", "enum": ["granted", "unavailable", "notRequired"]},
                "message": string,
                "code": string,
            },
            ["status", "message"],
        ),
        "PermissionResult": obj(
            {
                "mode": {"type": "string", "enum": ["music", "demo"]},
                "needsSettings": boolean,
                "libraryConnected": boolean,
                "media": ref("PermissionEntry"),
                "automation": ref("PermissionEntry"),
                "libraryError": {"type": "object"},
            },
            ["mode", "needsSettings", "libraryConnected", "media", "automation"],
        ),
        "RatingResult": obj(
            {
                "track": ref("Track"),
                "requestId": string,
                "state": {"const": "confirmed"},
                "libraryScope": string,
            }
        ),
        "Session": obj(
            {"kind": {"type": "string", "enum": ["cookie", "bearer", "host"]}, "csrfToken": string}
        ),
        "DeviceTokens": obj(
            {
                "accessToken": string,
                "refreshToken": string,
                "tokenType": {"const": "Bearer"},
                "expiresIn": integer,
            }
        ),
        "CreatedDevice": {"allOf": [ref("DeviceTokens"), obj({"deviceId": string})]},
        "Device": obj({"id": string, "name": string}),
        "OK": obj({"ok": boolean}),
        "Capabilities": obj(
            {
                "serverId": string,
                "apiVersions": {"type": "array", "items": string},
                "version": string,
                "features": {"type": "object", "additionalProperties": boolean},
                "authentication": {"type": "array", "items": string},
                "ratingScale": obj({"min": integer, "max": integer, "step": integer}),
                "pollIntervalSeconds": integer,
            }
        ),
    }

    def operation(
        ident: str,
        result: dict,
        *,
        method: str = "get",
        request: dict | None = None,
        public: bool = False,
        parameters: list | None = None,
        success: str = "200",
    ) -> dict:
        value = {
            "operationId": ident,
            "responses": {
                success: {
                    "description": "Successful response",
                    "content": {"application/json": {"schema": result}},
                },
                "default": {
                    "description": "Stable error code and German user-facing message",
                    "content": {"application/json": {"schema": ref("Error")}},
                },
            },
        }
        if public:
            value["security"] = []
        if parameters:
            value["parameters"] = parameters
        if request is not None:
            value["requestBody"] = {"required": True, "content": {"application/json": {"schema": request}}}
        if method not in {"get", "head"} and not public:
            value.setdefault("parameters", []).append(
                {
                    "name": "X-CSRF-Token",
                    "in": "header",
                    "required": False,
                    "description": "Required with cookie authentication together with an exact Origin header. Not used with Bearer authentication.",
                    "schema": string,
                }
            )
        return {method: value}

    def path_param(name: str) -> dict:
        return {"name": name, "in": "path", "required": True, "schema": string}

    def listing(name: str) -> dict:
        return obj({"items": {"type": "array", "items": ref(name)}})

    paths = {
        "/status": operation("getStatus", ref("Status")),
        "/capabilities": operation("getCapabilities", ref("Capabilities")),
        "/playlists": operation("listPlaylists", listing("Playlist")),
        "/tracks": operation(
            "listTracks",
            ref("TrackPage"),
            parameters=[
                {"name": name, "in": "query", "required": False, "schema": spec}
                for name, spec in {
                    "query": {"type": "string", "maxLength": 300},
                    "rating": {
                        "type": "string",
                        "enum": ["all", "rated", "unrated", "1", "2", "3", "4", "5"],
                    },
                    "playlistId": string,
                    "sort": {
                        "type": "string",
                        "enum": ["title", "artist", "album", "rating", "duration", "addedDate", "addedDateAsc"],
                        "description": "addedDate: newest first; addedDateAsc: oldest first. Missing dates sort last.",
                    },
                    "cursor": string,
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 100},
                }.items()
            ],
        ),
        "/tracks/{id}": operation("getTrack", ref("Track"), parameters=[path_param("id")]),
        "/tracks/{id}/rating": operation(
            "setRating",
            ref("RatingResult"),
            method="put",
            request=ref("RatingInput"),
            parameters=[path_param("id")],
        ),
        "/requests/{request_id}": operation(
            "getRequestResult", ref("RatingResult"), parameters=[path_param("request_id")]
        ),
        "/rating-queue": {
            **operation("enqueueRatings", ref("RatingQueueResult"), method="post", success="202", request=ref("RatingQueueInput")),
            **operation("getRatingQueue", ref("RatingQueueResult"), parameters=[
                {"name": "libraryScope", "in": "query", "required": True, "schema": string},
                {"name": "mode", "in": "query", "required": False, "schema": {"type": "string", "enum": ["music", "demo"]}},
                {"name": "ids", "in": "query", "required": False, "schema": string, "description": "Up to 100 comma-separated request IDs; active and failed jobs are also returned."},
            ]),
        },
        "/rating-queue/{id}/dismiss": operation(
            "dismissQueuedRating", obj({"ok": boolean}), method="post", request=obj({}), parameters=[path_param("id")],
        ),
        "/library/refresh": operation(
            "refreshLibrary", ref("Status"), method="post", request=ref("RefreshInput")
        ),
        "/permissions/request": operation(
            "requestPermissions", ref("PermissionResult"), method="post", request=obj({})
        ),
        "/library/connect": operation(
            "connectLibrary",
            ref("Status"),
            method="post",
            request=obj(
                {
                    "mode": {"type": "string", "enum": ["demo", "music"]},
                    "background": {"type": "boolean", "default": False},
                }, ["mode"]
            ),
        ),
        "/auth/bootstrap": operation(
            "createBrowserCode", obj({"code": string, "expiresIn": integer}), method="post", request=obj({})
        ),
        "/auth/password": operation("getWebPassword", obj({"password": string})),
        "/auth/login": operation(
            "loginWithPassword", obj({"csrfToken": string}), method="post",
            request=obj({"password": {"type": "string", "minLength": 1, "maxLength": 128, "writeOnly": True}}),
            public=True,
        ),
        "/auth/exchange": operation(
            "exchangeBrowserCode",
            obj({"csrfToken": string}),
            method="post",
            request=obj({"code": string}),
            public=True,
        ),
        "/auth/session": operation("getSession", ref("Session")),
        "/auth/logout": operation("logout", ref("OK"), method="post", request=obj({})),
        "/auth/refresh": operation(
            "refreshDeviceTokens",
            ref("DeviceTokens"),
            method="post",
            request=obj({"refreshToken": string}),
            public=True,
        ),
        "/auth/devices": {
            **operation("listDevices", listing("Device")),
            **operation(
                "createDevice",
                ref("CreatedDevice"),
                method="post",
                request=obj({"name": string}),
                success="201",
            ),
        },
        "/auth/devices/{id}": operation(
            "revokeDevice", ref("OK"), method="delete", request=obj({}), parameters=[path_param("id")]
        ),
        "/openapi.json": operation("getOpenAPI", {"type": "object"}),
        "/tracks/{id}/artwork": {
            "get": {
                "operationId": "getArtwork",
                "parameters": [path_param("id")],
                "responses": {
                    "200": {
                        "description": "Artwork",
                        "content": {"image/jpeg": {"schema": {"type": "string", "format": "binary"}}},
                    },
                    "404": {"description": "No artwork"},
                },
            }
        },
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "iTunesRemote API",
            "version": "1.0.0",
            "description": "Shared API for the web UI and future native iPad client. The service is available on loopback and private IPv4 interfaces over HTTP by default; --host 127.0.0.1 restricts it to this Mac. Browsers log in with a generated password that persists in Application Support across restarts and app updates. Only the Mac host can retrieve this password; cookie sessions and native devices cannot. Password login requires an exact Origin header and is rate-limited. Browser sessions last twelve hours and use CSRF protection. Legacy host-issued bootstrap codes remain supported for compatibility. Native credentials are explicitly issued by an administrator. HTTPS, automatic network pairing and discovery are not enabled. Ratings are confirmed by reading Music.app. IDs and revisions must be treated as opaque strings. Additive response fields are compatible; unknown enum values should be handled gracefully. Request IDs are retained for 24 hours and scoped to a session or device. HTTP 409 CURSOR_EXPIRED requires restarting pagination.",
        },
        "servers": [{"url": "/api/v1"}],
        "security": [{"browserSession": []}, {"deviceBearer": []}],
        "paths": paths,
        "components": {
            "securitySchemes": {
                "browserSession": {"type": "apiKey", "in": "cookie", "name": "itunesremote_session"},
                "deviceBearer": {"type": "http", "scheme": "bearer"},
            },
            "schemas": schemas,
        },
    }
