from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from .db import ROOT, database_path, initialize, connect
from .routes import content, learning, videos, transcripts

load_dotenv(ROOT.parent / ".env")
ALLOWED_ORIGINS = [
    "http://127.0.0.1:8765",
    "http://localhost:8765",
    "http://127.0.0.1:8766",
    "http://localhost:8766",
]


def create_app(db_path=None):
    @asynccontextmanager
    async def lifespan(app):
        initialize(app.state.db_path)
        yield

    app = FastAPI(title="Wordcraft API", version="2.2.0", lifespan=lifespan)
    app.state.db_path = Path(db_path) if db_path else database_path()
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def local_writes(request: Request, call_next):
        origin = request.headers.get("origin")
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            if origin and origin not in ALLOWED_ORIGINS:
                return JSONResponse(
                    {"detail": "此本地服务不接受其他站点的写入"}, status_code=403
                )
            if (
                request.headers.get("content-length", "0").isdigit()
                and int(request.headers.get("content-length", "0")) > 2_000_000
            ):
                return JSONResponse(
                    {"detail": "提交内容不能超过 2 MB"}, status_code=413
                )
            if (
                request.method != "DELETE"
                and "application/json" not in request.headers.get("content-type", "")
            ):
                return JSONResponse({"detail": "写入接口只接受 JSON"}, status_code=415)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health():
        with connect(app.state.db_path) as db:
            return {
                "status": "ok",
                "version": "2.2.0",
                "words": db.execute(
                    "SELECT count(*) FROM words WHERE archived=0"
                ).fetchone()[0],
                "videos": db.execute("SELECT count(*) FROM videos").fetchone()[0],
                "storage": "sqlite",
                "migration": db.execute(
                    "SELECT max(version) FROM schema_migrations"
                ).fetchone()[0],
            }

    app.include_router(content.router)
    app.include_router(learning.router)
    app.include_router(videos.router)
    app.include_router(transcripts.router)
    return app


app = create_app()
