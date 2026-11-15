import asyncio
import json
import httpx
from fastapi.testclient import TestClient
from app.db import ROOT, connect
from app.main import create_app
from app.schemas import WordInput
from app.youtube import search_candidates, upsert_video


def test_word_pages_filters_boundaries_and_seed_quality(client):
    first = client.get("/api/words?page=1&page_size=20").json()
    second = client.get("/api/words?page=2&page_size=20").json()
    assert first["total"] == 1200 and first["pages"] == 60
    assert len(first["items"]) == len(second["items"]) == 20
    assert not ({r["id"] for r in first["items"]} & {r["id"] for r in second["items"]})
    last = client.get("/api/words?page=999&page_size=80").json()
    assert last["page"] == last["pages"] == 15 and len(last["items"]) == 80
    selected = client.get("/api/words?q=reconciliation&deck=job").json()
    assert selected["total"] == 1 and selected["items"][0]["term"] == "reconciliation"
    empty = client.get("/api/words?q=does-not-exist-at-all&page=40").json()
    assert empty["total"] == 0 and empty["page"] == 1 and empty["items"] == []
    for path in [
        "/api/words?page=0",
        "/api/words?page_size=101",
        "/api/videos?page=-1",
        "/api/videos?page_size=0",
    ]:
        assert client.get(path).status_code == 422
    words = client.get("/api/bootstrap").json()["words"]
    assert len({w["term"].lower() for w in words}) == 1200
    for word in words:
        WordInput.model_validate(
            {k: v for k, v in word.items() if k in WordInput.model_fields}
        )
    expanded = json.loads((ROOT / "seed/expanded.json").read_text())["words"]
    assert any(w["term"] == "zero-downtime deployment" for w in expanded)
    assert any("个人简历" in w["source_label"] for w in expanded)
    assert all("@" not in w["source_label"] for w in expanded)


def test_video_pages_keep_favorites_and_notes(client):
    with connect(client.app.state.db_path) as db:
        for i in range(29):
            upsert_video(
                db,
                dict(
                    youtube_id=f"video{i:06d}",
                    title=f"Business English {i:02}",
                    channel="Test",
                    channel_url="",
                    thumbnail_url="",
                    deck="business",
                    source="curated",
                    source_query="",
                    learning_hint="",
                    fetched_at=1,
                    published_at="",
                ),
            )
    one = client.get("/api/videos?page_size=12").json()
    two = client.get("/api/videos?page_size=12&page=2").json()
    last = client.get("/api/videos?page_size=12&page=99").json()
    assert (one["total"], one["pages"], len(last["items"]), last["page"]) == (
        29,
        3,
        5,
        3,
    )
    assert not (
        {v["youtube_id"] for v in one["items"]}
        & {v["youtube_id"] for v in two["items"]}
    )
    vid = two["items"][0]["youtube_id"]
    client.patch(
        f"/api/videos/{vid}/progress", json={"favorite": True, "notes": "Keep my notes"}
    )
    filtered = client.get(
        "/api/videos?favorite=true&page=3&deck=business&q=English"
    ).json()
    assert (
        filtered["total"] == 1
        and filtered["page"] == 1
        and filtered["items"][0]["notes"] == "Keep my notes"
    )


def test_official_search_follows_page_token_and_deduplicates(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key")
    calls = []

    def handle(request):
        calls.append(dict(request.url.params))
        ids = range(50) if len(calls) == 1 else range(49, 99)
        return httpx.Response(
            200,
            json={
                "items": [{"id": {"videoId": f"video{i:06d}"}} for i in ids],
                "nextPageToken": "second",
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
            rows = await search_candidates(client, "business", "meetings", 75)
            assert len(rows) == 75 and len({r["id"] for r in rows}) == 75

    asyncio.run(run())
    assert (
        len(calls) == 2
        and calls[0]["maxResults"] == "50"
        and calls[1]["pageToken"] == "second"
    )
    assert calls[1]["maxResults"] == "25"


def test_expanded_seed_preserves_edits_and_archival(client):
    word = next(
        w
        for w in client.get("/api/bootstrap").json()["words"]
        if w["id"].startswith("expanded-")
    )
    edited = {k: v for k, v in word.items() if k in WordInput.model_fields}
    edited.update(
        meaning="My custom meaning",
        collocation="",
        example_kind="definition",
        source_label="My source",
    )
    saved = client.put("/api/words/" + word["id"], json=edited)
    assert saved.status_code == 200
    assert saved.json()["source_label"] == "My source"
    assert (
        saved.json()["example_kind"] == "definition"
        and saved.json()["collocation"] == ""
    )
    assert client.delete("/api/words/" + word["id"]).status_code == 200
    with TestClient(create_app(client.app.state.db_path)) as restarted:
        assert word["id"] not in [
            w["id"]
            for w in restarted.get("/api/words?q=" + word["term"]).json()["items"]
        ]
    with connect(client.app.state.db_path) as db:
        row = db.execute(
            "SELECT meaning,archived FROM words WHERE id=?", (word["id"],)
        ).fetchone()
        assert tuple(row) == ("My custom meaning", 1)
