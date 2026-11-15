from datetime import datetime
import re
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Request
from ..db import get_db, now_ms
from ..repository import progress, require_word
from ..schemas import ReviewInput, DraftInput, LegacyProgress, QuizInput

router = APIRouter(prefix="/api", tags=["learning"])


def db_dependency(request: Request):
    yield from get_db(request)


@router.get("/progress")
def read_progress(db=Depends(db_dependency, scope="function")):
    return progress(db)


@router.post("/reviews")
def review(body: ReviewInput, db=Depends(db_dependency, scope="function")):
    db.execute("BEGIN IMMEDIATE")
    prior = db.execute(
        "SELECT * FROM review_events WHERE request_id=?", (body.request_id,)
    ).fetchone()
    if prior:
        if prior["word_id"] != body.word_id or prior["rating"] != body.rating:
            raise HTTPException(409, "请求标识已用于另一次复习")
        return progress(db)
    require_word(db, body.word_id)
    row = db.execute(
        "SELECT * FROM reviews WHERE word_id=?", (body.word_id,)
    ).fetchone()
    stage, count = (row["stage"], row["count"]) if row else (0, 0)
    delay = (
        600000
        if body.rating == "again"
        else 86400000
        if body.rating == "hard"
        else [1, 3, 7, 14, 30][min(stage, 4)] * 86400000
    )
    stage = (
        0
        if body.rating == "again"
        else min(stage + 1, 5)
        if body.rating == "good"
        else stage
    )
    now = now_ms()
    day = datetime.fromtimestamp(now / 1000, ZoneInfo(body.timezone)).date().isoformat()
    db.execute(
        "INSERT INTO reviews VALUES (?,?,?,?) ON CONFLICT(word_id) DO UPDATE SET stage=excluded.stage,due=excluded.due,count=excluded.count",
        (body.word_id, stage, now + delay, count + 1),
    )
    db.execute("INSERT OR IGNORE INTO daily_words VALUES (?,?)", (day, body.word_id))
    db.execute(
        "INSERT INTO review_events VALUES (?,?,?,?,?)",
        (body.request_id, body.word_id, body.rating, now, day),
    )
    return progress(db)


@router.put("/drafts/{scenario_id}")
def save_draft(
    scenario_id: str, body: DraftInput, db=Depends(db_dependency, scope="function")
):
    if not db.execute("SELECT 1 FROM scenarios WHERE id=?", (scenario_id,)).fetchone():
        raise HTTPException(404, "场景不存在")
    db.execute(
        "INSERT INTO drafts VALUES (?,?,?) ON CONFLICT(scenario_id) DO UPDATE SET text=excluded.text,updated_at=excluded.updated_at",
        (scenario_id, body.text, now_ms()),
    )
    return {"saved": True}


@router.post("/progress/import")
def import_progress(body: LegacyProgress, db=Depends(db_dependency, scope="function")):
    """Merge legacy progress atomically without resetting newer database progress."""
    ids = {r[0] for r in db.execute("SELECT id FROM words")}
    incoming_ids = set(body.reviews) | {
        i for items in body.days.values() for i in items
    }
    scenes = {r[0] for r in db.execute("SELECT id FROM scenarios")}
    if not incoming_ids.issubset(ids) or not set(body.drafts).issubset(scenes):
        raise HTTPException(422, "备份包含当前词库中不存在的词条或场景")
    for word_id, r in body.reviews.items():
        db.execute(
            """INSERT INTO reviews VALUES (?,?,?,?) ON CONFLICT(word_id) DO UPDATE SET
          stage=excluded.stage,due=excluded.due,count=excluded.count WHERE excluded.count>reviews.count""",
            (word_id, r.stage, r.due, r.count),
        )
    for day, items in body.days.items():
        db.executemany(
            "INSERT OR IGNORE INTO daily_words VALUES (?,?)",
            [(day, i) for i in set(items)],
        )
    for scenario_id, text in body.drafts.items():
        db.execute(
            "INSERT OR IGNORE INTO drafts VALUES (?,?,?)", (scenario_id, text, now_ms())
        )
    return progress(db)


def normalize(value):
    return re.sub(r"\s+", " ", re.sub("[‐‑–—]", "-", value.strip().lower()))


@router.post("/quiz-attempts")
def quiz(body: QuizInput, db=Depends(db_dependency, scope="function")):
    word = require_word(db, body.word_id)
    accepted = {normalize(word["term"])}
    if word["term"] == "prioritise":
        accepted.add("prioritize")
    if word["term"] == "root-cause analysis":
        accepted.add("root cause analysis")
    correct = normalize(body.answer) in accepted
    prior = db.execute(
        "SELECT * FROM quiz_attempts WHERE request_id=?", (body.request_id,)
    ).fetchone()
    if prior and (prior["word_id"] != body.word_id or prior["answer"] != body.answer):
        raise HTTPException(409, "请求标识已使用")
    db.execute(
        "INSERT OR IGNORE INTO quiz_attempts VALUES (?,?,?,?,?)",
        (body.request_id, body.word_id, body.answer, int(correct), now_ms()),
    )
    return {
        "correct": bool(prior["correct"]) if prior else correct,
        "term": word["term"],
        "example": word["example"],
        "example_kind": word["example_kind"],
    }
