from collections import OrderedDict, deque
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request
from starlette.responses import JSONResponse


_lock = Lock()
_origins = OrderedDict()
_global = deque()


def admit_ingest_request(request: Request):
    # Deliberately ignore forwarded headers: only a trusted proxy may aggregate peers.
    origin = request.client.host if request.client else "unknown"
    now = monotonic()
    with _lock:
        while _global and _global[0] <= now - 60:
            _global.popleft()
        if len(_global) >= 3000:
            raise HTTPException(status_code=429, detail="Ingest admission limit exceeded")
        if origin not in _origins and len(_origins) >= 4096:
            # Do not evict a live origin and allow an attacker to reset its quota.
            stale = [key for key, values in _origins.items() if not values or values[-1] <= now - 60]
            for key in stale:
                del _origins[key]
            if len(_origins) >= 4096:
                raise HTTPException(status_code=429, detail="Ingest admission capacity exceeded")
        window = _origins.setdefault(origin, deque())
        while window and window[0] <= now - 60:
            window.popleft()
        if len(window) >= 600:
            raise HTTPException(status_code=429, detail="Ingest origin limit exceeded")
        window.append(now)
        _global.append(now)


class IngestAdmissionMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/ingest/whatsapp/"):
            return await self.app(scope, receive, send)
        request = Request(scope)
        try:
            admit_ingest_request(request)
        except HTTPException as exc:
            return await JSONResponse({"detail": exc.detail}, status_code=exc.status_code)(scope, receive, send)
        request.state.ingest_admitted = True
        if scope["method"] != "POST":
            return await self.app(scope, receive, send)

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > 1_048_576:
                return await JSONResponse({"detail": "Ingest request exceeds the size limit"}, status_code=413)(scope, receive, send)
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)
