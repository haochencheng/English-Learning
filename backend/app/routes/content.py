from uuid import uuid4
from fastapi import APIRouter, Depends, Query
from ..db import now_ms
from ..repository import require_word, progress, list_words
from ..schemas import WordInput, Deck
from .learning import db_dependency

router = APIRouter(prefix="/api", tags=["content"])


@router.get("/bootstrap")
def bootstrap(db=Depends(db_dependency, scope="function")):
    return {
        "words": [
            dict(r)
            for r in db.execute("SELECT * FROM words WHERE archived=0 ORDER BY rowid")
        ],
        "scenarios": [
            dict(r) for r in db.execute("SELECT * FROM scenarios ORDER BY id")
        ],
        "progress": progress(db),
    }


@router.get("/words")
def words(
    deck: Deck | None = None,
    q: str = Query("", max_length=150),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db=Depends(db_dependency, scope="function"),
):
    return list_words(db, deck, q, page, page_size)


@router.post("/words", status_code=201)
def create_word(body: WordInput, db=Depends(db_dependency, scope="function")):
    data = body.model_dump(mode="json")
    word_id = "custom-" + uuid4().hex
    db.execute(
        f"INSERT INTO words (id,{','.join(data)},updated_at) VALUES ({','.join('?' for _ in range(len(data) + 2))})",
        [word_id, *data.values(), now_ms()],
    )
    return require_word(db, word_id)


@router.put("/words/{word_id}")
def update_word(
    word_id: str, body: WordInput, db=Depends(db_dependency, scope="function")
):
    require_word(db, word_id)
    data = body.model_dump(mode="json")
    db.execute(
        f"UPDATE words SET {','.join(k + '=?' for k in data)},updated_at=? WHERE id=?",
        [*data.values(), now_ms(), word_id],
    )
    return require_word(db, word_id)


@router.delete("/words/{word_id}")
def archive_word(word_id: str, db=Depends(db_dependency, scope="function")):
    require_word(db, word_id)
    db.execute(
        "UPDATE words SET archived=1,updated_at=? WHERE id=?", (now_ms(), word_id)
    )
    return {"archived": True}
