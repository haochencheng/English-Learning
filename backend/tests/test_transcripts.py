import pytest
from fastapi.testclient import TestClient
from app.db import connect
from app.main import create_app
from app.transcripts import (
    TranscriptError,
    align,
    parse_subtitles,
    imported_transcript,
    begin_fetch,
    save_transcript,
    run_fetch,
)
from app.youtube import upsert_video

VID = "subtitle001"


def add_video(client):
    with connect(client.app.state.db_path) as db:
        upsert_video(
            db,
            dict(
                youtube_id=VID,
                title="Original learning example",
                channel="Wordcraft",
                channel_url="",
                thumbnail_url="",
                deck="job",
                source="curated",
                source_query="",
                learning_hint="",
                fetched_at=1,
                published_at="",
            ),
        )


def example():
    return dict(
        segments=[
            dict(
                start=0.0,
                duration=3.0,
                english="Daily reconciliation helps our team.",
                chinese="每日对账帮助我们的团队。",
            ),
            dict(
                start=3.0,
                duration=2.0,
                english="We check payment records.",
                chinese="我们检查支付记录。",
            ),
        ],
        english_source="Original test material",
        translation_source="Original Chinese translation",
        is_generated=False,
        message="",
    )


def test_caption_import_alignment_and_restart(client):
    add_video(client)
    body = dict(
        english="1\n00:00:00,000 --> 00:00:03,000\nDaily reconciliation helps our team.\n\n2\n00:00:03,000 --> 00:00:05,000\nWe check payment records.",
        chinese="WEBVTT\n\n00:00.000 --> 00:03.000\n每日对账帮助我们的团队。\n\n00:03.000 --> 00:05.000\n我们检查支付记录。",
    )
    response = client.put(f"/api/videos/{VID}/transcript", json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["total"] == result["translated"] == 2 and result["status"] == "ready"
    assert (
        result["segments"][1]["start"] == 3
        and result["segments"][1]["chinese"] == "我们检查支付记录。"
    )
    client.patch(
        f"/api/videos/{VID}/progress", json={"notes": "Do not change my notes"}
    )
    with TestClient(create_app(client.app.state.db_path)) as restarted:
        assert restarted.get(f"/api/videos/{VID}/transcript").json() == result
    assert (
        client.get("/api/videos").json()["items"][0]["notes"]
        == "Do not change my notes"
    )
    assert client.put(f"/api/videos/{VID}/transcript", json={}).status_code == 422
    assert client.get(f"/api/videos/{VID}/transcript").json() == result


def test_import_plaintext_and_invalid_input_do_not_replace(client):
    add_video(client)
    path = f"/api/videos/{VID}/transcript"
    assert (
        client.put(
            path,
            json={
                "english": "We test changes.\nWe review results.",
                "chinese": "我们测试变更。\n我们审查结果。",
            },
        ).status_code
        == 200
    )
    before = client.get(path).json()
    assert all(s["start"] is None for s in before["segments"])
    assert client.put(path, json={"chinese": "只有一行"}).status_code == 422
    assert client.get(path).json() == before
    assert (
        client.put(path, json={"chinese": "测试。\n审查。"}).json()["translated"] == 2
    )
    for malformed in [
        "WEBVTT\nno timing here",
        "00:00:05,000 --> 00:00:01,000\nBad",
        "00:90:00,000 --> 00:91:01,000\nBad",
    ]:
        with pytest.raises(TranscriptError):
            parse_subtitles(malformed)
    assert client.get("/api/videos/unknown/transcript").status_code == 404


def test_failed_fetch_preserves_transcript_and_partial_preserves_translation(
    client, monkeypatch
):
    add_video(client)
    with connect(client.app.state.db_path) as db:
        save_transcript(db, VID, example())
        db.execute("UPDATE video_transcripts SET last_attempt_at=0")
        request = begin_fetch(db, VID, True)

    def fail(_):
        raise RuntimeError("private upstream details must not be returned")

    monkeypatch.setattr("app.transcripts.fetch_public", fail)
    run_fetch(client.app.state.db_path, VID, request)
    result = client.get(f"/api/videos/{VID}/transcript").json()
    assert result["status"] == "error" and result["total"] == result["translated"] == 2
    assert "private" not in result["message"]
    partial = example()
    partial["segments"][0]["chinese"] = ""
    partial["translation_source"] = ""
    with connect(client.app.state.db_path) as db:
        db.execute("UPDATE video_transcripts SET last_attempt_at=0")
        request = begin_fetch(db, VID, True)
        save_transcript(db, VID, partial, request)
    assert client.get(f"/api/videos/{VID}/transcript").json()["translated"] == 2


def test_new_import_wins_over_old_background_job(client):
    add_video(client)
    with connect(client.app.state.db_path) as db:
        old = begin_fetch(db, VID)
        assert begin_fetch(db, VID) is None
        save_transcript(db, VID, example())
        stale = example()
        stale["segments"][0]["english"] = "Stale text"
        save_transcript(db, VID, stale, old)
    assert (
        client.get(f"/api/videos/{VID}/transcript").json()["segments"][0]["english"]
        == "Daily reconciliation helps our team."
    )


def test_dictionary_prefers_learning_words_and_handles_inflection(client):
    with connect(client.app.state.db_path) as db:
        db.execute(
            "INSERT INTO dictionary_entries VALUES (?,?,?,?,?)",
            (
                "collaborate",
                "kəˈlæbəreɪt",
                "vi. 合作",
                "work together",
                "d:collaborated/i:collaborating",
            ),
        )
        db.execute(
            "INSERT INTO dictionary_forms VALUES (?,?)",
            ("collaborating", "collaborate"),
        )
        db.execute(
            "INSERT INTO dictionary_entries VALUES (?,?,?,?,?)",
            ("reconciliation", "", "和解", "restoring relations", ""),
        )
    result = client.get("/api/dictionary?q=reconciliation").json()
    assert result["source"] == "我的词库" and "对账" in result["meaning"]
    result = client.get("/api/dictionary?q=collaborating").json()
    assert (
        result["found"]
        and result["term"] == "collaborate"
        and "合作" in result["meaning"]
    )
    assert client.get("/api/dictionary?q=madeupzzzz").json()["found"] is False
    assert client.get("/api/dictionary?q=%3Cscript%3E").status_code == 422


def test_public_provider_selects_english_and_chinese_tracks(monkeypatch):
    from app.transcripts import fetch_public
    from types import SimpleNamespace as Obj

    class Track:
        def __init__(self, code, text, generated=False):
            self.language_code = code
            self.text = text
            self.is_generated = generated
            self.is_translatable = False

        def fetch(self):
            return [Obj(start=0, duration=2, text=self.text)]

    class Provider:
        def __init__(self, **kwargs):
            pass

        def list(self, _):
            return [
                Track("en", "Original English."),
                Track("zh-CN", "原创中文。"),
                Track("en-US", "Automatic.", True),
            ]

    monkeypatch.setattr("app.transcripts.YouTubeTranscriptApi", Provider)
    result = fetch_public(VID)
    assert result["segments"][0]["english"] == "Original English."
    assert result["segments"][0]["chinese"] == "原创中文。"
    assert result["is_generated"] is False


def test_alignment_does_not_fill_missing_translation():
    segments = align(
        [
            dict(start=0, duration=1, text="One."),
            dict(start=5, duration=1, text="Two."),
        ],
        [dict(start=0, duration=1, text="一。")],
    )
    assert segments[0]["chinese"] == "一。" and segments[1]["chinese"] == ""
    with pytest.raises(TranscriptError):
        imported_transcript("", "", None)


def test_background_endpoint_and_auto_translation_failure(client, monkeypatch):
    from app.transcripts import fetch_public
    from types import SimpleNamespace as Obj

    add_video(client)

    class IpBlocked(Exception):
        pass

    class Track:
        language_code = "en"
        is_generated = True
        is_translatable = True
        translation_languages = [Obj(language_code="zh-Hans")]

        def fetch(self):
            return [Obj(start=0, duration=2, text="We review changes.")]

        def translate(self, language):
            assert language == "zh-Hans"
            raise IpBlocked("must not leak upstream details")

    class Provider:
        def __init__(self, **kwargs):
            pass

        def list(self, _):
            return [Track()]

    monkeypatch.setattr("app.transcripts.YouTubeTranscriptApi", Provider)
    data = fetch_public(VID)
    assert (
        data["segments"][0]["english"] == "We review changes."
        and not data["segments"][0]["chinese"]
    )
    assert "限制中文译文访问" in data["message"]
    monkeypatch.setattr("app.transcripts.fetch_public", lambda _: example())
    assert (
        client.post(f"/api/videos/{VID}/transcript/fetch", json={}).status_code == 202
    )
    assert client.get(f"/api/videos/{VID}/transcript").json()["translated"] == 2
    assert (
        client.post(
            f"/api/videos/{VID}/transcript/fetch", json={"refresh": True}
        ).status_code
        == 409
    )


def test_dictionary_csv_import_is_repeatable(client, tmp_path):
    from app.dictionary import import_dictionary

    path = tmp_path / "dictionary.csv"
    path.write_text(
        "word,phonetic,translation,definition,exchange\ncollaborate,,合作,work together,i:collaborating\n"
    )
    with connect(client.app.state.db_path) as db:
        import_dictionary(db, path)
        import_dictionary(db, path)
        assert db.execute("SELECT count(*) FROM dictionary_entries").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM dictionary_forms").fetchone()[0] == 1
    assert client.get("/api/dictionary?q=collaborating").json()["term"] == "collaborate"
