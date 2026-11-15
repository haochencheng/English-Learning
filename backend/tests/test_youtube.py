import asyncio
import httpx
import pytest
from app.db import connect
from app.youtube import (
    CollectionError,
    parse_video_id,
    metadata,
    upsert_video,
    create_run,
    classify,
)


def test_video_url_allowlist():
    for url in [
        "https://youtu.be/KN2jyw6D1ak?t=3",
        "https://www.youtube.com/watch?v=KN2jyw6D1ak",
        "https://m.youtube.com/shorts/KN2jyw6D1ak",
        "KN2jyw6D1ak",
    ]:
        assert parse_video_id(url) == "KN2jyw6D1ak"
    for url in [
        "http://127.0.0.1/private",
        "https://youtube.com.evil.test/watch?v=KN2jyw6D1ak",
        "file:///secret",
        "https://user:pass@youtube.com/watch?v=KN2jyw6D1ak",
        "https://youtube.com/playlist?list=test",
    ]:
        with pytest.raises(CollectionError):
            parse_video_id(url)


def test_metadata_requests_only_youtube_and_ignores_html():
    def handler(request):
        assert request.url.host == "www.youtube.com"
        return httpx.Response(
            200,
            json={
                "title": "English Interview",
                "author_name": "Teacher",
                "author_url": "https://www.youtube.com/@teacher",
                "html": "<script>bad()</script>",
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            video = await metadata(client, "KN2jyw6D1ak", "job")
            assert video["title"] == "English Interview"
            assert "html" not in video
            assert (
                video["thumbnail_url"]
                == "https://i.ytimg.com/vi/KN2jyw6D1ak/hqdefault.jpg"
            )

    asyncio.run(run())


def test_resync_keeps_notes_and_deduplicates(client):
    video = {
        "youtube_id": "KN2jyw6D1ak",
        "title": "Original",
        "channel": "BBC",
        "channel_url": "https://www.youtube.com/@bbclearningenglish",
        "thumbnail_url": "https://i.ytimg.com/vi/KN2jyw6D1ak/hqdefault.jpg",
        "deck": "job",
        "source": "curated",
        "source_query": "",
        "learning_hint": "Practice",
        "fetched_at": 1,
        "published_at": "",
    }
    with connect(client.app.state.db_path) as db:
        upsert_video(db, video)
    assert (
        client.patch(
            "/api/videos/KN2jyw6D1ak/progress",
            json={"notes": "My notes", "favorite": True, "completed": True},
        ).status_code
        == 200
    )
    video["title"] = "Updated"
    with connect(client.app.state.db_path) as db:
        upsert_video(db, video)
    rows = client.get("/api/videos?favorite=true").json()["items"]
    assert (
        len(rows) == 1
        and rows[0]["title"] == "Updated"
        and rows[0]["notes"] == "My notes"
        and rows[0]["completed"] == 1
    )
    assert (
        client.patch(
            "/api/videos/KN2jyw6D1ak/progress", json={"favorite": False}
        ).status_code
        == 200
    )
    assert client.get("/api/videos").json()["items"][0]["notes"] == "My notes"


def test_key_missing_and_sync_failure_are_explicit(client, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    assert client.get("/api/video-config").json()["search_enabled"] is False
    assert (
        client.post(
            "/api/video-sync", json={"mode": "search", "deck": "job"}
        ).status_code
        == 409
    )

    async def unavailable(*args, **kwargs):
        raise CollectionError("Upstream unavailable")

    monkeypatch.setattr("app.youtube.metadata", unavailable)
    response = client.post("/api/video-sync", json={"mode": "curated"})
    assert response.status_code == 202
    run = client.get("/api/video-sync").json()[0]
    assert run["status"] == "failed" and run["imported"] == 0 and run["failed"] == 7
    assert client.get("/api/videos").json()["items"] == []


def test_partial_sync_and_single_active_run(client, monkeypatch):
    async def fake(client, video_id, deck, *args):
        if video_id != "KN2jyw6D1ak":
            raise CollectionError("Unavailable")
        return {
            "youtube_id": video_id,
            "title": "English Interview",
            "channel": "BBC",
            "channel_url": "",
            "thumbnail_url": "",
            "deck": deck,
            "source": "curated",
            "source_query": "",
            "learning_hint": "",
            "fetched_at": 1,
            "published_at": "",
        }

    monkeypatch.setattr("app.youtube.metadata", fake)
    assert client.post("/api/video-sync", json={"mode": "curated"}).status_code == 202
    run = client.get("/api/video-sync").json()[0]
    assert run["status"] == "partial" and run["imported"] == 1 and run["failed"] == 6
    with connect(client.app.state.db_path) as db:
        create_run(db, "curated")
    assert client.post("/api/video-sync", json={"mode": "curated"}).status_code == 409
    assert classify("IELTS speaking test") == "ielts"
    assert classify("Football highlights") is None


def test_public_channel_parser_supports_both_layouts():
    import json
    from app.youtube import parse_channel_page

    data = {
        "contents": {
            "items": [
                {
                    "videoRenderer": {
                        "videoId": "KN2jyw6D1ak",
                        "title": {"runs": [{"text": "Job interview English"}]},
                    }
                },
                {
                    "lockupViewModel": {
                        "contentId": "bqznnq9gOsU",
                        "contentType": "LOCKUP_CONTENT_TYPE_VIDEO",
                        "metadata": {
                            "lockupMetadataViewModel": {
                                "title": {"content": "IELTS speaking"}
                            }
                        },
                    }
                },
            ]
        }
    }
    result = parse_channel_page(
        "<script>var ytInitialData = " + json.dumps(data) + ";</script>"
    )
    assert result == [
        ("KN2jyw6D1ak", "Job interview English"),
        ("bqznnq9gOsU", "IELTS speaking"),
    ]
    with pytest.raises(CollectionError):
        parse_channel_page("<html>Please sign in</html>")


def test_channel_feed_fallback_does_not_request_private_api():
    import json
    from app.youtube import channel_candidates

    data = {
        "contents": {
            "videoRenderer": {
                "videoId": "KN2jyw6D1ak",
                "title": {"runs": [{"text": "English job interview"}]},
            }
        }
    }
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.url.path == "/feeds/videos.xml":
            return httpx.Response(404)
        return httpx.Response(200, text="var ytInitialData = " + json.dumps(data) + ";")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            candidates = await channel_candidates(
                client, {"id": "test-channel", "name": "Test"}
            )
            assert candidates[0]["id"] == "KN2jyw6D1ak"

    asyncio.run(run())
    assert paths == ["/feeds/videos.xml", "/channel/test-channel/videos"]


def test_keyword_search_uses_official_endpoint(monkeypatch):
    from app.youtube import search_candidates

    monkeypatch.setenv("YOUTUBE_API_KEY", "test-key-not-a-secret")

    def handler(request):
        assert request.url.host == "www.googleapis.com"
        assert request.url.path == "/youtube/v3/search"
        assert request.url.params["type"] == "video"
        assert request.url.params["videoEmbeddable"] == "true"
        assert request.url.params["relevanceLanguage"] == "en"
        return httpx.Response(200, json={"items": [{"id": {"videoId": "KN2jyw6D1ak"}}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            rows = await search_candidates(client, "job", "English interview")
            assert rows == [
                {"id": "KN2jyw6D1ak", "deck": "job", "query": "English interview"}
            ]

    asyncio.run(run())
