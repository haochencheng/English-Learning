from datetime import datetime
from zoneinfo import ZoneInfo
from app.db import connect, now_ms
from app.main import create_app
from fastapi.testclient import TestClient


def payload(rating="good", request_id="review-0001", word_id="job-0"):
    return {
        "word_id": word_id,
        "rating": rating,
        "request_id": request_id,
        "timezone": "Asia/Shanghai",
    }


def test_seed_restart_and_durable_progress(client):
    assert len(client.get("/api/bootstrap").json()["words"]) == 1200
    result = client.post("/api/reviews", json=payload())
    assert result.status_code == 200
    record = result.json()["reviews"]["job-0"]
    assert record["stage"] == 1 and record["count"] == 1
    assert abs(record["due"] - now_ms() - 86400000) < 3000
    with TestClient(create_app(client.app.state.db_path)) as restarted:
        assert restarted.get("/api/progress").json()["reviews"]["job-0"] == record
        assert len(restarted.get("/api/bootstrap").json()["words"]) == 1200


def test_idempotent_review_and_day_dedup(client):
    for _ in range(3):
        assert client.post("/api/reviews", json=payload()).status_code == 200
    p = client.get("/api/progress").json()
    assert p["reviews"]["job-0"]["count"] == 1
    assert client.post("/api/reviews", json=payload("hard")).status_code == 409
    assert (
        client.post("/api/reviews", json=payload("hard", "review-0002")).status_code
        == 200
    )
    p = client.get("/api/progress").json()
    assert p["reviews"]["job-0"]["count"] == 2
    today = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    assert p["days"][today] == ["job-0"]


def test_intervals_and_archive_preserves_history(client):
    with connect(client.app.state.db_path) as db:
        db.execute("INSERT INTO reviews VALUES (?,?,?,?)", ("job-0", 5, 1, 6))
    r = client.post("/api/reviews", json=payload()).json()["reviews"]["job-0"]
    assert r["stage"] == 5 and abs(r["due"] - now_ms() - 30 * 86400000) < 3000
    r = client.post("/api/reviews", json=payload("again", "review-0002")).json()[
        "reviews"
    ]["job-0"]
    assert r["stage"] == 0 and abs(r["due"] - now_ms() - 600000) < 3000
    assert client.delete("/api/words/job-0").status_code == 200
    assert "job-0" not in [
        w["id"] for w in client.get("/api/bootstrap").json()["words"]
    ]
    assert "job-0" in client.get("/api/progress").json()["reviews"]
    assert (
        client.post("/api/reviews", json=payload("good", "review-0003")).status_code
        == 404
    )
    with TestClient(create_app(client.app.state.db_path)) as restarted:
        assert len(restarted.get("/api/bootstrap").json()["words"]) == 1199


def test_legacy_import_is_atomic_merge(client):
    old = {
        "version": 1,
        "reviews": {"job-1": {"stage": 2, "due": 1000, "count": 2}},
        "days": {"2026-11-15": ["job-1", "job-1"]},
        "drafts": {"0": "Old draft"},
    }
    assert client.post("/api/progress/import", json=old).status_code == 200
    assert client.put("/api/drafts/0", json={"text": "New draft"}).status_code == 200
    assert client.post("/api/progress/import", json=old).status_code == 200
    current = client.get("/api/progress").json()
    assert current["drafts"]["0"] == "New draft"
    assert current["days"]["2026-11-15"] == ["job-1"]
    old["reviews"]["not-a-word"] = {"stage": 1, "due": 0, "count": 1}
    assert client.post("/api/progress/import", json=old).status_code == 422
    assert client.get("/api/progress").json() == current
    old["days"] = {"bad-date": ["job-1"]}
    assert client.post("/api/progress/import", json=old).status_code == 422


def test_quiz_validation_and_durable_result(client):
    q = {"word_id": "job-0", "answer": "  Reconciliation  ", "request_id": "quiz-0001"}
    assert client.post("/api/quiz-attempts", json=q).json()["correct"] is True
    assert client.post("/api/quiz-attempts", json=q).json()["correct"] is True
    with connect(client.app.state.db_path) as db:
        assert db.execute("SELECT count(*) FROM quiz_attempts").fetchone()[0] == 1
    q.update(answer="wrong", request_id="quiz-0002")
    assert client.post("/api/quiz-attempts", json=q).json()["correct"] is False
    assert client.put("/api/drafts/unknown", json={"text": "x"}).status_code == 404
    assert client.put("/api/drafts/0", json={"text": "x" * 20001}).status_code == 422
    assert (
        client.post(
            "/api/reviews", json=payload() | {"timezone": "not/timezone"}
        ).status_code
        == 422
    )


def test_word_crud_and_local_origin(client):
    data = {
        "deck": "job",
        "term": "durability",
        "pos": "n.",
        "meaning": "持久性",
        "collocation": "data durability",
        "example": "Durability matters.",
        "translation": "持久性很重要。",
        "source_url": "https://example.com/",
    }
    response = client.post("/api/words", json=data)
    assert response.status_code == 201
    word_id = response.json()["id"]
    data["meaning"] = "持久性；耐久性"
    assert (
        client.put("/api/words/" + word_id, json=data).json()["meaning"]
        == data["meaning"]
    )
    assert (
        client.post(
            "/api/words", json=data, headers={"origin": "https://untrusted.example"}
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/words", content="{}", headers={"content-type": "text/plain"}
        ).status_code
        == 415
    )
    assert client.delete("/api/words/" + word_id).status_code == 200


def test_concurrent_requests_have_independent_connections(client):
    from concurrent.futures import ThreadPoolExecutor

    def task(i):
        if i % 2:
            return client.get("/api/bootstrap").status_code
        return client.post(
            "/api/reviews", json=payload("good", f"parallel-{i:04d}")
        ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(task, range(30))) == [200] * 30
    assert client.get("/api/progress").json()["reviews"]["job-0"]["count"] == 15
