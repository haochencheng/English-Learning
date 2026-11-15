import json
import os
import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Query
from ..db import now_ms
from ..repository import list_videos, require_video
from ..schemas import Deck, VideoImport, VideoProgress, SyncInput
from ..youtube import (
    parse_video_id,
    metadata,
    upsert_video,
    CollectionError,
    run_sync,
    create_run,
    CATALOG,
)
from .learning import db_dependency

router = APIRouter(prefix="/api", tags=["videos"])


@router.get("/videos")
def videos(
    deck: Deck | None = None,
    q: str = Query("", max_length=150),
    favorite: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=100),
    db=Depends(db_dependency, scope="function"),
):
    return list_videos(db, deck, q, favorite, page, page_size)


@router.get("/video-config")
def config():
    return {
        "search_enabled": bool(os.getenv("YOUTUBE_API_KEY")),
        "channels": CATALOG["channels"],
        "curated_count": len(CATALOG["curated"]),
    }


@router.post("/videos/import")
async def import_video(body: VideoImport, db=Depends(db_dependency, scope="function")):
    try:
        video_id = parse_video_id(body.url)
        async with httpx.AsyncClient(timeout=12, follow_redirects=False) as client:
            video = await metadata(client, video_id, body.deck)
    except CollectionError as error:
        raise HTTPException(422 if "链接" in str(error) else 502, str(error)) from None
    upsert_video(db, video)
    return video


@router.patch("/videos/{video_id}/progress")
def update_progress(
    video_id: str, body: VideoProgress, db=Depends(db_dependency, scope="function")
):
    require_video(db, video_id)
    db.execute(
        "INSERT OR IGNORE INTO video_progress (youtube_id,updated_at) VALUES (?,?)",
        (video_id, now_ms()),
    )
    data = body.model_dump(exclude_none=True)
    if data:
        db.execute(
            "UPDATE video_progress SET "
            + ",".join(k + "=?" for k in data)
            + ",updated_at=? WHERE youtube_id=?",
            [*data.values(), now_ms(), video_id],
        )
    return dict(
        db.execute(
            "SELECT * FROM video_progress WHERE youtube_id=?", (video_id,)
        ).fetchone()
    )


@router.post("/video-sync", status_code=202)
def sync(
    body: SyncInput,
    request: Request,
    tasks: BackgroundTasks,
    db=Depends(db_dependency, scope="function"),
):
    if body.mode == "search" and not os.getenv("YOUTUBE_API_KEY"):
        raise HTTPException(
            409, "关键词检索需要配置后端 YOUTUBE_API_KEY；可先使用精选同步或链接导入"
        )
    db.execute("BEGIN IMMEDIATE")
    try:
        run_id = create_run(db, body.mode)
    except CollectionError as error:
        raise HTTPException(409, str(error)) from None
    db.commit()  # Worker uses a separate connection after the response is sent.
    tasks.add_task(
        run_sync,
        request.app.state.db_path,
        run_id,
        body.mode,
        body.deck,
        body.query,
        body.limit,
    )
    return {"id": run_id, "status": "running"}


@router.get("/video-sync")
def sync_history(db=Depends(db_dependency, scope="function")):
    rows = []
    for row in db.execute("SELECT * FROM sync_runs ORDER BY started_at DESC LIMIT 20"):
        item = dict(row)
        item["details"] = json.loads(item["details"])
        rows.append(item)
    return rows
