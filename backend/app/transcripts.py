"""Public caption tracks and explicit imports; no audio downloads or invented text."""

import html
import re
from uuid import uuid4

from requests import Session
from youtube_transcript_api import YouTubeTranscriptApi

from .db import connect, now_ms

MAX_SEGMENTS = 15000
MAX_TEXT = 1_500_000


class TranscriptError(Exception):
    pass


class TimedSession(Session):
    def request(self, *args, **kwargs):
        kwargs.setdefault("timeout", 12)
        return super().request(*args, **kwargs)


def plain(text):
    return html.unescape(re.sub(r"<[^>]*>", "", text)).strip()


def caption_error(error):
    name = type(error).__name__
    if name in {"TranscriptsDisabled", "NoTranscriptFound"}:
        return "这个视频没有可获取的英文字幕。可导入已有的英文和中文字幕文件。"
    if name in {"RequestBlocked", "IpBlocked", "AgeRestricted", "VideoUnplayable"}:
        return "YouTube 当前限制了字幕访问。可在 YouTube 查看或导入已有字幕。"
    if name in {"VideoUnavailable", "InvalidVideoId"}:
        return "视频不可用，无法读取字幕。"
    if isinstance(error, TranscriptError):
        return str(error)
    return "字幕读取失败，可能是网络或平台接口变化。可稍后重试或导入字幕。"


def validate_segments(segments):
    if not segments:
        raise TranscriptError("字幕为空，没有导入内容。")
    if (
        len(segments) > MAX_SEGMENTS
        or sum(len(s["english"]) + len(s.get("chinese", "")) for s in segments)
        > MAX_TEXT
    ):
        raise TranscriptError("字幕过大，已停止处理；原有字幕保持不变。")
    return segments


def track_rows(track):
    return [
        {
            "start": float(s.start),
            "duration": max(0, float(s.duration)),
            "text": plain(s.text),
        }
        for s in track.fetch()
        if plain(s.text)
    ]


def align(english, chinese):
    """Align overlapping cues; never guess translations for unmatched English cues."""
    segments = []
    j = 0
    for en in english:
        start, end = en["start"], en["start"] + max(en["duration"], 0.1)
        while (
            j < len(chinese)
            and chinese[j]["start"] + max(chinese[j]["duration"], 0.1) <= start
        ):
            j += 1
        k, matches = j, []
        while k < len(chinese) and chinese[k]["start"] < end:
            zh = chinese[k]
            if (
                min(end, zh["start"] + max(zh["duration"], 0.1))
                - max(start, zh["start"])
                > 0
            ):
                if not matches or matches[-1] != zh["text"]:
                    matches.append(zh["text"])
            k += 1
        segments.append(
            dict(
                start=start,
                duration=en["duration"],
                english=en["text"],
                chinese=" ".join(matches),
            )
        )
    return validate_segments(segments)


def fetch_public(video_id):
    with TimedSession() as session:
        tracks = list(YouTubeTranscriptApi(http_client=session).list(video_id))
        candidates = [
            t for t in tracks if t.language_code.lower().split("-")[0] == "en"
        ]
        if not candidates:
            raise TranscriptError(
                "视频没有可获取的英文字幕；不会把其他语言冒充英文原文。"
            )
        en = sorted(
            candidates, key=lambda t: (t.is_generated, t.language_code != "en")
        )[0]
        english = track_rows(en)
        if not english:
            raise TranscriptError("平台返回了空字幕，可稍后重试或导入已有字幕。")
        translation_source, message, chinese = "", "", []
        native_zh = [t for t in tracks if t.language_code.lower().startswith("zh")]
        try:
            if native_zh:
                zh = sorted(
                    native_zh,
                    key=lambda t: (
                        t.is_generated,
                        t.language_code not in {"zh-Hans", "zh-CN", "zh"},
                    ),
                )[0]
                chinese = track_rows(zh)
                translation_source = "YouTube 中文字幕轨 · " + zh.language_code
            elif en.is_translatable:
                codes = [item.language_code for item in en.translation_languages]
                target = next(
                    (
                        code
                        for code in ["zh-Hans", "zh-CN", "zh", "zh-Hant", "zh-TW"]
                        if code in codes
                    ),
                    None,
                )
                if target:
                    chinese = track_rows(en.translate(target))
                    translation_source = "YouTube 自动翻译 · " + target
            if not chinese:
                message = "英文字幕已保存；这个视频暂时没有可获取的中文译文，可导入中文字幕补充。"
        except Exception as error:
            message = (
                "英文字幕已保存；YouTube 当前限制中文译文访问，可导入中文字幕补充。"
                if type(error).__name__ in {"IpBlocked", "RequestBlocked"}
                else "英文字幕已保存；中文译文读取失败，可重试或导入中文字幕补充。"
            )
        segments = align(english, sorted(chinese, key=lambda x: x["start"]))
        return dict(
            segments=segments,
            english_source="YouTube 英文"
            + ("自动字幕" if en.is_generated else "字幕轨")
            + " · "
            + en.language_code,
            translation_source=translation_source,
            is_generated=en.is_generated,
            message=message,
        )


def read_transcript(db, video_id):
    meta = db.execute(
        "SELECT * FROM video_transcripts WHERE youtube_id=?", (video_id,)
    ).fetchone()
    result = (
        dict(meta)
        if meta
        else dict(
            youtube_id=video_id,
            status="empty",
            english_source="",
            translation_source="",
            is_generated=0,
            message="",
            updated_at=0,
            last_attempt_at=0,
        )
    )
    result.pop("request_id", None)
    result["segments"] = [
        dict(r)
        for r in db.execute(
            "SELECT seq,start,duration,english,chinese FROM transcript_segments WHERE youtube_id=? ORDER BY seq",
            (video_id,),
        )
    ]
    result["total"] = len(result["segments"])
    result["translated"] = sum(bool(s["chinese"]) for s in result["segments"])
    return result


def save_transcript(db, video_id, data, request_id=""):
    segments = validate_segments(data["segments"])
    if request_id:
        row = db.execute(
            "SELECT request_id FROM video_transcripts WHERE youtube_id=?", (video_id,)
        ).fetchone()
        if not row or row[0] != request_id:
            return  # A newer import/request owns the content now.
    if request_id:
        old_rows = db.execute(
            "SELECT start,english,chinese FROM transcript_segments WHERE youtube_id=?",
            (video_id,),
        ).fetchall()
        previous = {
            (r["start"], r["english"]): r["chinese"] for r in old_rows if r["chinese"]
        }
        reused = False
        for segment in segments:
            if not segment.get("chinese") and previous.get(
                (segment["start"], segment["english"])
            ):
                segment["chinese"] = previous[(segment["start"], segment["english"])]
                reused = True
        if reused:
            old_source = db.execute(
                "SELECT translation_source FROM video_transcripts WHERE youtube_id=?",
                (video_id,),
            ).fetchone()[0]
            data["translation_source"] = (
                data["translation_source"] + "；部分沿用已保存译文"
                if data["translation_source"]
                else old_source
            )
            data["message"] = "本次部分译文未能读取，相同英文段落的已有译文已保留。"
    db.execute("DELETE FROM transcript_segments WHERE youtube_id=?", (video_id,))
    db.executemany(
        "INSERT INTO transcript_segments VALUES (?,?,?,?,?,?)",
        [
            (video_id, i, s["start"], s["duration"], s["english"], s.get("chinese", ""))
            for i, s in enumerate(segments)
        ],
    )
    status = "ready" if all(s.get("chinese") for s in segments) else "partial"
    db.execute(
        """INSERT INTO video_transcripts (youtube_id,status,request_id,english_source,translation_source,is_generated,message,updated_at,last_attempt_at)
    VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(youtube_id) DO UPDATE SET status=excluded.status,request_id=excluded.request_id,english_source=excluded.english_source,translation_source=excluded.translation_source,is_generated=excluded.is_generated,message=excluded.message,updated_at=excluded.updated_at,last_attempt_at=excluded.last_attempt_at""",
        (
            video_id,
            status,
            request_id,
            data["english_source"],
            data["translation_source"],
            int(data.get("is_generated", False)),
            data.get("message", ""),
            now_ms(),
            now_ms(),
        ),
    )


def begin_fetch(db, video_id, refresh=False):
    row = db.execute(
        "SELECT * FROM video_transcripts WHERE youtube_id=?", (video_id,)
    ).fetchone()
    if row and row["status"] == "fetching":
        return None
    if row and row["status"] in {"ready", "partial"} and not refresh:
        return None
    if row and now_ms() - row["last_attempt_at"] < 30000:
        raise TranscriptError("刚刚尝试过获取字幕，请稍等 30 秒再重试。")
    if (
        db.execute(
            "SELECT count(*) FROM video_transcripts WHERE status='fetching'"
        ).fetchone()[0]
        >= 2
    ):
        raise TranscriptError("已有两个视频正在获取字幕，请稍后再试。")
    request_id = uuid4().hex
    db.execute(
        """INSERT INTO video_transcripts (youtube_id,status,request_id,last_attempt_at) VALUES (?,'fetching',?,?) ON CONFLICT(youtube_id) DO UPDATE SET status='fetching',request_id=excluded.request_id,last_attempt_at=excluded.last_attempt_at,message='' """,
        (video_id, request_id, now_ms()),
    )
    return request_id


def run_fetch(path, video_id, request_id):
    try:
        data = fetch_public(video_id)
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            save_transcript(db, video_id, data, request_id)
    except Exception as error:
        with connect(path) as db:
            db.execute(
                "UPDATE video_transcripts SET status='error',message=? WHERE youtube_id=? AND request_id=?",
                (caption_error(error), video_id, request_id),
            )


TIME = r"(?:\d{1,3}:)?\d{2}:\d{2}[,.]\d{3}"
TIMING = re.compile(r"^(" + TIME + r")\s*-->\s*(" + TIME + r")")


def seconds(value):
    parts = value.replace(",", ".").split(":")
    if any(float(x) >= 60 for x in parts[-2:]):
        raise TranscriptError("字幕时间格式无效。")
    return sum(float(x) * 60**i for i, x in enumerate(reversed(parts)))


def parse_subtitles(text):
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    if len(text) > MAX_TEXT:
        raise TranscriptError("字幕文件过大。")
    if "-->" not in text:
        if text.startswith("WEBVTT"):
            raise TranscriptError("VTT 文件中没有有效的时间轴。")
        return [
            dict(start=None, duration=0, text=plain(line))
            for line in text.splitlines()
            if plain(line)
        ]
    rows = []
    for block in re.split(r"\n\s*\n", text):
        lines = block.splitlines()
        if not lines or lines[0].startswith(("NOTE", "STYLE", "REGION")):
            continue
        index = next(
            (i for i, line in enumerate(lines) if TIMING.match(line.strip())), None
        )
        if index is None:
            if "-->" in block:
                raise TranscriptError("字幕时间轴格式不支持，请使用标准 SRT 或 VTT。")
            continue
        match = TIMING.match(lines[index].strip())
        start, end = map(seconds, match.groups())
        content = plain(" ".join(lines[index + 1 :]))
        if end < start:
            raise TranscriptError("字幕结束时间不能早于开始时间。")
        if content:
            rows.append(dict(start=start, duration=end - start, text=content))
    if not rows:
        raise TranscriptError("没有识别到字幕内容，请检查文件格式。")
    return sorted(rows, key=lambda s: s["start"])


def imported_transcript(english_text, chinese_text, existing=None):
    if not english_text.strip() and not chinese_text.strip():
        raise TranscriptError("请提供英文字幕或中文译文，空请求不会清除已有内容。")
    english = (
        parse_subtitles(english_text)
        if english_text.strip()
        else [
            dict(start=s["start"], duration=s["duration"], text=s["english"])
            for s in (existing or {}).get("segments", [])
        ]
    )
    chinese = parse_subtitles(chinese_text)
    if not english:
        raise TranscriptError("请先提供英文字幕。")
    timed = all(s["start"] is not None for s in english)
    chinese_timed = bool(chinese) and all(s["start"] is not None for s in chinese)
    if timed and chinese_timed:
        segments = align(english, chinese)
    else:
        if chinese and len(chinese) != len(english):
            raise TranscriptError(
                "无时间轴的双语文本需要行数一致，才能准确对应；也可分别导入带时间轴的 SRT/VTT。"
            )
        segments = [
            dict(
                start=s["start"],
                duration=s["duration"],
                english=s["text"],
                chinese=chinese[i]["text"] if chinese else "",
            )
            for i, s in enumerate(english)
        ]
    return dict(
        segments=validate_segments(segments),
        english_source="手动导入英文字幕"
        if english_text.strip()
        else existing["english_source"],
        translation_source="手动导入中文译文" if chinese else "",
        is_generated=bool((existing or {}).get("is_generated"))
        if not english_text.strip()
        else False,
        message="",
    )
