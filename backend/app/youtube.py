"""Bounded public metadata collection. No media downloads or credential scraping."""

import asyncio
import json
import os
import re
from urllib.parse import urlparse, parse_qs
from uuid import uuid4
import xml.etree.ElementTree as ET
import httpx
from .db import ROOT, connect, now_ms

CATALOG = json.loads((ROOT / "seed" / "videos.json").read_text())
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
TOPICS = {
    "job": [
        "interview",
        "career",
        "job",
        "java",
        "engineer",
        "software",
        "system design",
    ],
    "ielts": ["ielts", "speaking test", "band 7", "band 8", "band 9", "writing task"],
    "business": [
        "business",
        "work",
        "meeting",
        "negotiat",
        "presentation",
        "email",
        "request",
        "formal",
    ],
}
QUERIES = {
    "job": "English job interview software engineer",
    "ielts": "IELTS speaking work technology",
    "business": "business English meetings communication",
}


class CollectionError(Exception):
    pass


def parse_video_id(url):
    if VIDEO_ID.fullmatch(url):
        return url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.username or parsed.password:
        raise CollectionError("请输入有效的 YouTube 视频链接")
    host = (parsed.hostname or "").lower()
    if host in ("youtu.be", "www.youtu.be"):
        candidate = parsed.path.strip("/").split("/")[0]
    elif host in ("youtube.com", "www.youtube.com", "m.youtube.com"):
        segments = parsed.path.strip("/").split("/")
        candidate = (
            parse_qs(parsed.query).get("v", [""])[0]
            if parsed.path == "/watch"
            else segments[1]
            if len(segments) == 2 and segments[0] in ("shorts", "embed", "live")
            else ""
        )
    else:
        raise CollectionError("仅支持 YouTube 视频链接")
    if not VIDEO_ID.fullmatch(candidate):
        raise CollectionError("无法识别视频编号，请粘贴单个视频的完整链接")
    return candidate


async def request(client, url, params=None):
    for attempt in range(2):
        try:
            response = await client.get(url, params=params)
        except (httpx.TimeoutException, httpx.NetworkError):
            if attempt == 0:
                await asyncio.sleep(0.4)
                continue
            raise CollectionError("连接 YouTube 超时或网络不可用，请稍后重试") from None
        if response.status_code == 200:
            if len(response.content) > 5_000_000:
                raise CollectionError("上游响应过大，已停止采集")
            return response
        if response.status_code in (429, 500, 502, 503, 504) and attempt == 0:
            await asyncio.sleep(0.6)
            continue
        if response.status_code == 403:
            raise CollectionError("YouTube 拒绝请求：请检查 API 权限、配额或网络")
        if response.status_code in (400, 404, 401):
            raise CollectionError(
                f"YouTube 返回 {response.status_code}，视频、频道或 API 配置可能不可用"
            )
        raise CollectionError(f"YouTube 暂不可用（HTTP {response.status_code}）")


async def metadata(client, video_id, deck, source="url", query="", hint=""):
    response = await request(
        client,
        "https://www.youtube.com/oembed",
        {"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
    )
    try:
        data = response.json()
        if not data.get("title") or not data.get("author_name"):
            raise ValueError()
    except (ValueError, KeyError):
        raise CollectionError("YouTube 未返回有效的视频信息") from None
    return {
        "youtube_id": video_id,
        "title": data["title"][:500],
        "channel": data["author_name"][:200],
        "channel_url": data.get("author_url", ""),
        "thumbnail_url": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "deck": deck,
        "source": source,
        "source_query": query,
        "learning_hint": hint or "先听一遍理解大意，再记录三个表达，用自己的经历复述。",
        "fetched_at": now_ms(),
        "published_at": "",
    }


def upsert_video(db, video):
    fields = list(video)
    db.execute(
        f"INSERT INTO videos ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)}) ON CONFLICT(youtube_id) DO UPDATE SET "
        + ",".join(f"{k}=excluded.{k}" for k in fields if k != "youtube_id"),
        list(video.values()),
    )
    # Separate table deliberately preserves notes and favorites on every refresh.


def classify(title, fallback=None):
    text = title.lower()
    scored = {deck: sum(key in text for key in keys) for deck, keys in TOPICS.items()}
    best = max(scored, key=scored.get)
    return best if scored[best] else fallback


async def search_candidates(client, deck, query, limit=30):
    key = os.getenv("YOUTUBE_API_KEY", "")
    if not key:
        raise CollectionError(
            "关键词检索需要在后端 .env 配置 YOUTUBE_API_KEY；链接导入和精选同步无需密钥"
        )
    q = query or QUERIES[deck]
    found, token, seen_tokens = {}, None, set()
    # Two API pages at most. Search limits are independent of UI pagination.
    for _ in range(2):
        params = {
            "part": "snippet",
            "type": "video",
            "q": q,
            "maxResults": min(50, limit - len(found)),
            "relevanceLanguage": "en",
            "videoEmbeddable": "true",
            "videoSyndicated": "true",
            "safeSearch": "strict",
            "key": key,
        }
        if token:
            params["pageToken"] = token
        response = await request(
            client, "https://www.googleapis.com/youtube/v3/search", params
        )
        try:
            data = response.json()
            for item in data["items"]:
                video_id = item["id"].get("videoId", "")
                if VIDEO_ID.fullmatch(video_id):
                    found[video_id] = {"id": video_id, "deck": deck, "query": q}
            token = data.get("nextPageToken")
            if len(found) >= limit or not token or token in seen_tokens:
                break
            seen_tokens.add(token)
        except (ValueError, KeyError, TypeError):
            raise CollectionError("搜索接口返回格式异常") from None
    return list(found.values())[:limit]


def parse_channel_page(page):
    """Read public page metadata only; stop if YouTube changes its page format."""
    marker = re.search(r"(?:var\s+)?ytInitialData\s*=\s*", page)
    if not marker:
        raise CollectionError("频道页面没有公开视频列表，可能需要登录或页面结构已变更")
    try:
        data, _ = json.JSONDecoder().raw_decode(page[marker.end() :])
    except ValueError:
        raise CollectionError(
            "无法解析公开频道信息，请改用官方 API 检索或链接导入"
        ) from None
    found = {}

    def walk(value):
        if isinstance(value, dict):
            if "lockupViewModel" in value:
                item = value["lockupViewModel"]
                if item.get("contentType") == "LOCKUP_CONTENT_TYPE_VIDEO":
                    title = (
                        item.get("metadata", {})
                        .get("lockupMetadataViewModel", {})
                        .get("title", {})
                        .get("content", "")
                    )
                    found[item.get("contentId", "")] = title
            if "videoRenderer" in value:
                item = value["videoRenderer"]
                found[item.get("videoId", "")] = "".join(
                    r.get("text", "") for r in item.get("title", {}).get("runs", [])
                )
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(data.get("contents", {}))
    if not found:
        raise CollectionError(
            "频道列表结构已变更或没有公开视频；请使用链接导入或官方 API"
        )
    return [
        (video_id, title)
        for video_id, title in found.items()
        if VIDEO_ID.fullmatch(video_id)
    ][:30]


async def channel_candidates(client, channel):
    try:
        response = await request(
            client,
            "https://www.youtube.com/feeds/videos.xml",
            {"channel_id": channel["id"]},
        )
        root = ET.fromstring(response.content)
        ns = {
            "a": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }
        pairs = [
            (entry.findtext("yt:videoId", "", ns), entry.findtext("a:title", "", ns))
            for entry in root.findall("a:entry", ns)[:15]
        ]
    except (CollectionError, ET.ParseError):
        # The public RSS endpoint can be unavailable. No login, internal API,
        # browser cookies or access-control bypass is used by this fallback.
        response = await request(
            client,
            f"https://www.youtube.com/channel/{channel['id']}/videos",
            {"hl": "en"},
        )
        pairs = parse_channel_page(response.text)
    return [
        {"id": video_id, "deck": classify(title), "query": channel["name"]}
        for video_id, title in pairs
        if VIDEO_ID.fullmatch(video_id) and classify(title)
    ]


async def run_sync(path, run_id, mode, deck="job", query="", limit=30):
    details = []
    imported = 0
    failed = 0
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(12), follow_redirects=False
        ) as client:
            candidates = []
            if mode == "curated":
                candidates = CATALOG["curated"]
            elif mode == "search":
                candidates = await search_candidates(client, deck, query, limit)
            else:
                for channel in CATALOG["channels"]:
                    try:
                        candidates.extend(await channel_candidates(client, channel))
                    except CollectionError as error:
                        failed += 1
                        details.append({"source": channel["name"], "error": str(error)})
            # Bound workload; refresh each identifier at most once.
            candidates = list({c["id"]: c for c in candidates}.values())[:limit]
            semaphore = asyncio.Semaphore(3)

            async def fetch(item):
                async with semaphore:
                    try:
                        result = await metadata(
                            client,
                            item["id"],
                            item["deck"],
                            mode,
                            item.get("query", ""),
                            item.get("hint", ""),
                        )
                        return result, None
                    except CollectionError as error:
                        return None, {"source": item["id"], "error": str(error)}

            for video, error in await asyncio.gather(
                *(fetch(item) for item in candidates)
            ):
                if error:
                    failed += 1
                    details.append(error)
                else:
                    with connect(path) as db:
                        upsert_video(db, video)
                    imported += 1
            if not candidates and not failed:
                details.append({"message": "本次没有找到匹配视频；原有资料保持不变。"})
    except CollectionError as error:
        failed += 1
        details.append({"error": str(error)})
    except Exception:
        failed += 1
        details.append(
            {"error": "采集任务异常，原有数据已保留。请检查后端日志与网络。"}
        )
    status = "partial" if imported and failed else "failed" if failed else "completed"
    with connect(path) as db:
        db.execute(
            "UPDATE sync_runs SET status=?,finished_at=?,imported=?,failed=?,details=? WHERE id=?",
            (
                status,
                now_ms(),
                imported,
                failed,
                json.dumps(details, ensure_ascii=False),
                run_id,
            ),
        )


def create_run(db, mode):
    if db.execute("SELECT 1 FROM sync_runs WHERE status='running'").fetchone():
        raise CollectionError("已有采集任务运行中，请等待完成")
    run_id = uuid4().hex
    db.execute(
        "INSERT INTO sync_runs (id,status,started_at,mode) VALUES (?,?,?,?)",
        (run_id, "running", now_ms(), mode),
    )
    return run_id
