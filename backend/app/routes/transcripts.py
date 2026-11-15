from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import Field
from ..dictionary import lookup
from ..repository import require_video
from ..schemas import Model
from ..transcripts import (
    TranscriptError,
    begin_fetch,
    imported_transcript,
    read_transcript,
    run_fetch,
    save_transcript,
)
from .learning import db_dependency

router = APIRouter(prefix="/api", tags=["transcripts"])


class FetchInput(Model):
    refresh: bool = False


class ImportInput(Model):
    english: str = Field(default="", max_length=1_500_000)
    chinese: str = Field(default="", max_length=1_500_000)


@router.get("/videos/{video_id}/transcript")
def transcript(video_id: str, db=Depends(db_dependency, scope="function")):
    require_video(db, video_id)
    return read_transcript(db, video_id)


@router.post("/videos/{video_id}/transcript/fetch", status_code=202)
def fetch(
    video_id: str,
    body: FetchInput,
    tasks: BackgroundTasks,
    request: Request,
    db=Depends(db_dependency, scope="function"),
):
    require_video(db, video_id)
    db.execute("BEGIN IMMEDIATE")
    try:
        request_id = begin_fetch(db, video_id, body.refresh)
    except TranscriptError as error:
        raise HTTPException(409, str(error)) from None
    db.commit()
    if request_id:
        tasks.add_task(run_fetch, request.app.state.db_path, video_id, request_id)
    return read_transcript(db, video_id)


@router.put("/videos/{video_id}/transcript")
def import_transcript(
    video_id: str, body: ImportInput, db=Depends(db_dependency, scope="function")
):
    require_video(db, video_id)
    db.execute("BEGIN IMMEDIATE")
    try:
        data = imported_transcript(
            body.english, body.chinese, read_transcript(db, video_id)
        )
        save_transcript(db, video_id, data)
    except TranscriptError as error:
        raise HTTPException(422, str(error)) from None
    return read_transcript(db, video_id)


@router.get("/dictionary")
def dictionary(
    q: str = Query(min_length=1, max_length=60, pattern=r"^[a-zA-Z][a-zA-Z'’\-]*$"),
    db=Depends(db_dependency, scope="function"),
):
    return lookup(db, q)
