"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from urllib.parse import urlsplit

from app.core.config import settings
from app.api.router import api_router

app = FastAPI(title="Sovereign On-Premise Agentic AI Workbench")


@app.middleware("http")
async def browser_origin_guard(request, call_next):
    sensitive = request.url.path.startswith(("/auth/", "/admin/", "/executions", "/approvals", "/audit/",
        "/bi/", "/documents/pid", "/equipment", "/sensors/", "/maintenance/", "/verified-knowledge", "/knowledge-gaps"))
    mutation = request.method not in {"GET", "HEAD", "OPTIONS"} or (
        request.url.path.startswith("/approvals/") and request.url.path.endswith("/release"))
    if mutation:
        origin, referer = request.headers.get("origin"), request.headers.get("referer")
        allowed = set(settings.cors_origins)
        rejected = origin is not None and origin not in allowed
        if origin is None and referer:
            parts = urlsplit(referer)
            rejected = f"{parts.scheme}://{parts.netloc}" not in allowed
        if origin is None and not referer and request.headers.get("sec-fetch-site") is not None:
            rejected = True
        if rejected:
            return JSONResponse({"detail": "Request origin is not allowed."}, status_code=403)
    try:
        response = await call_next(request)
    finally:
        if request.url.path == "/auth/google/callback":
            # Uvicorn formats the shared ASGI scope when sending the response.
            # Remove authorization codes/state before access logging, including 422s.
            request.scope["query_string"] = b""
    if sensitive:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, error):
    if request.url.path.startswith(("/auth/", "/admin/")):
        return JSONResponse({"detail": [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
                                         for e in error.errors()]}, status_code=422)
    from fastapi.exception_handlers import request_validation_exception_handler
    return await request_validation_exception_handler(request, error)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    # Phase 5B: the session cookie is HttpOnly and only useful if the browser
    # is allowed to send/receive it. Safe because cors_origins is an explicit
    # whitelist, never "*" (browsers refuse credentials with a wildcard origin).
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    expose_headers=["X-As-Of", "X-Sample-Size", "X-Has-More", "X-Next-Offset", "X-Scan-Limit"],
)


app.include_router(api_router)
