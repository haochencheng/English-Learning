"""Shared queries; all learning content and durable state live in SQLite."""

from fastapi import HTTPException


def progress(db):
    reviews = {
        r["word_id"]: {k: r[k] for k in ["stage", "due", "count"]}
        for r in db.execute("SELECT * FROM reviews")
    }
    days = {}
    for r in db.execute("SELECT * FROM daily_words ORDER BY day,word_id"):
        days.setdefault(r["day"], []).append(r["word_id"])
    drafts = {r["scenario_id"]: r["text"] for r in db.execute("SELECT * FROM drafts")}
    return {"version": 1, "reviews": reviews, "days": days, "drafts": drafts}


def require_word(db, word_id, active=True):
    r = db.execute("SELECT * FROM words WHERE id=?", (word_id,)).fetchone()
    if not r or (active and r["archived"]):
        raise HTTPException(404, "词条不存在或已归档")
    return dict(r)


def require_video(db, video_id):
    if not db.execute(
        "SELECT 1 FROM videos WHERE youtube_id=?", (video_id,)
    ).fetchone():
        raise HTTPException(404, "视频不存在")


def list_videos(db, deck=None, q="", favorite=False, page=1, page_size=12):
    clauses, values = ["1=1"], []
    if deck:
        clauses.append("v.deck=?")
        values.append(deck)
    if q:
        clauses.append("(v.title LIKE ? OR v.channel LIKE ? OR v.learning_hint LIKE ?)")
        values.extend(["%" + q + "%"] * 3)
    if favorite:
        clauses.append("p.favorite=1")
    where = " AND ".join(clauses)
    total = db.execute(
        "SELECT COUNT(*) FROM videos v LEFT JOIN video_progress p USING(youtube_id) WHERE "
        + where,
        values,
    ).fetchone()[0]
    page, pages = page_bounds(total, page, page_size)
    rows = db.execute(
        """SELECT v.*,COALESCE(p.notes,'') notes,COALESCE(p.favorite,0) favorite,
        COALESCE(p.completed,0) completed FROM videos v LEFT JOIN video_progress p USING(youtube_id)
        WHERE """
        + where
        + " ORDER BY v.fetched_at DESC,v.title,v.youtube_id LIMIT ? OFFSET ?",
        [*values, page_size, (page - 1) * page_size],
    )
    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }


def page_bounds(total, page, page_size):
    pages = max(1, (total + page_size - 1) // page_size)
    return min(page, pages), pages


def list_words(db, deck=None, q="", page=1, page_size=20):
    clauses, values = ["archived=0"], []
    if deck:
        clauses.append("deck=?")
        values.append(deck)
    if q:
        clauses.append("(term LIKE ? OR meaning LIKE ? OR collocation LIKE ?)")
        values.extend(["%" + q + "%"] * 3)
    where = " AND ".join(clauses)
    total = db.execute("SELECT COUNT(*) FROM words WHERE " + where, values).fetchone()[
        0
    ]
    page, pages = page_bounds(total, page, page_size)
    rows = db.execute(
        "SELECT * FROM words WHERE " + where + " ORDER BY rowid LIMIT ? OFFSET ?",
        [*values, page_size, (page - 1) * page_size],
    )
    return {
        "items": [dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }
