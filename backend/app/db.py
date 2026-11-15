"""SQLite connections, ordered migrations and non-destructive initial content."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import sqlite3
import time

ROOT = Path(__file__).resolve().parents[1]


def now_ms():
    return int(time.time() * 1000)


def database_path():
    return Path(os.getenv("WORDCRAFT_DB") or ROOT.parent / "data" / "wordcraft.sqlite3")


@contextmanager
def connect(path):
    # FastAPI may enter/exit one request dependency on different worker threads.
    # Each request still owns its own connection and transaction.
    db = sqlite3.connect(str(path), timeout=15, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA busy_timeout=15000")
    try:
        with db:
            yield db
    finally:
        db.close()


def initialize(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at INTEGER NOT NULL)"
        )
        for migration in sorted((ROOT / "migrations").glob("*.sql")):
            if db.execute(
                "SELECT 1 FROM schema_migrations WHERE version=?", (migration.stem,)
            ).fetchone():
                continue
            # Each migration is atomic, including its version marker.
            script = migration.read_text()
            db.executescript(
                "BEGIN IMMEDIATE;\n"
                + script
                + f"\nINSERT INTO schema_migrations VALUES ('{migration.stem}',{now_ms()});\nCOMMIT;"
            )
        db.execute(
            "UPDATE video_transcripts SET status='error',message='服务重启中断了字幕获取，已有内容已保留，请重试。' WHERE status='fetching'"
        )
        seed = json.loads((ROOT / "seed" / "content.json").read_text())
        fields = [
            "id",
            "deck",
            "term",
            "pos",
            "meaning",
            "collocation",
            "example",
            "translation",
            "source_url",
        ]
        for word in seed["words"]:
            db.execute(
                f"INSERT OR IGNORE INTO words ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",
                [word[f] for f in fields],
            )
        expanded_path = ROOT / "seed" / "expanded.json"
        if expanded_path.exists():
            expanded_fields = fields + ["example_kind", "source_label"]
            for word in json.loads(expanded_path.read_text())["words"]:
                # Content upgrades must not revive archived words or replace user edits.
                db.execute(
                    f"INSERT OR IGNORE INTO words ({','.join(expanded_fields)}) SELECT {','.join('?' for _ in expanded_fields)} WHERE NOT EXISTS (SELECT 1 FROM words WHERE lower(term)=lower(?))",
                    [word[f] for f in expanded_fields] + [word["term"]],
                )
        for scene in seed["scenarios"]:
            db.execute(
                "INSERT OR IGNORE INTO scenarios VALUES (?,?,?,?)",
                [scene[k] for k in ["id", "q", "hint", "answer"]],
            )
        db.execute(
            "UPDATE sync_runs SET status='interrupted',finished_at=? WHERE status='running'",
            (now_ms(),),
        )


def get_db(request):
    with connect(request.app.state.db_path) as db:
        yield db
