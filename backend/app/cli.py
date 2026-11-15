"""Operations: python -m app.cli sync|backup|init|dictionary."""

import argparse
import asyncio
from datetime import datetime
from pathlib import Path
import sqlite3
from dotenv import load_dotenv
from .db import ROOT, initialize, database_path, connect
from .youtube import create_run, run_sync


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["init", "sync", "backup", "dictionary"])
    parser.add_argument(
        "--mode", choices=["curated", "channels", "search"], default="curated"
    )
    parser.add_argument("--deck", choices=["job", "ielts", "business"], default="job")
    parser.add_argument("--query", default="")
    parser.add_argument("--output")
    parser.add_argument(
        "--limit", type=int, choices=range(1, 101), default=30, metavar="1..100"
    )
    args = parser.parse_args()
    load_dotenv(ROOT.parent / ".env")
    path = database_path()
    if args.command == "init" or not path.exists():
        initialize(path)
    if args.command == "dictionary":
        from .dictionary import import_dictionary

        source = ROOT.parent / "data" / "corpus" / "ecdict.csv"
        if not source.exists():
            raise SystemExit(
                "请先运行 scripts/fetch_corpus.py --dictionary 下载本地词典"
            )
        initialize(path)
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            print("Imported dictionary rows:", import_dictionary(db, source))
    elif args.command == "sync":
        with connect(path) as db:
            db.execute("BEGIN IMMEDIATE")
            run_id = create_run(db, args.mode)
        asyncio.run(
            run_sync(path, run_id, args.mode, args.deck, args.query, args.limit)
        )
        with connect(path) as db:
            result = dict(
                db.execute("SELECT * FROM sync_runs WHERE id=?", (run_id,)).fetchone()
            )
        print(result)
        if result["status"] == "failed":
            raise SystemExit(1)
    elif args.command == "backup":
        target = (
            Path(args.output)
            if args.output
            else ROOT.parent
            / "backups"
            / ("wordcraft-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".sqlite3")
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise SystemExit("备份文件已存在，请指定新文件名")
        with connect(path) as source, sqlite3.connect(target) as dest:
            source.backup(dest)
        print(target)
    else:
        print(path)


if __name__ == "__main__":
    main()
