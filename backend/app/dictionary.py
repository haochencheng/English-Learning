"""Offline lookup. The learning glossary wins over broad dictionary senses."""

import csv
import re
from .db import now_ms


def normalize(term):
    return term.strip().lower().replace("’", "'")


def import_dictionary(db, path):
    # Build in one transaction: readers see either the previous version or all new rows.
    rows, forms, count = [], [], 0
    with open(path, newline="", encoding="utf-8-sig") as source:
        for row in csv.DictReader(source):
            term = normalize(row["word"])
            if not re.fullmatch(r"[a-z][a-z'-]{0,59}", term) or not row["translation"]:
                continue
            rows.append(
                (
                    term,
                    row["phonetic"],
                    row["translation"].replace("\\n", "\n"),
                    row["definition"].replace("\\n", "\n"),
                    row["exchange"],
                )
            )
            for field in row["exchange"].split("/"):
                key, _, values = field.partition(":")
                if key in {"p", "d", "i", "3", "s"}:
                    forms.extend(
                        (normalize(value), term)
                        for value in values.split(",")
                        if re.fullmatch(r"[a-z][a-z'-]{0,59}", normalize(value))
                    )
            count += 1
            if len(rows) >= 5000:
                db.executemany(
                    "INSERT OR REPLACE INTO dictionary_entries VALUES (?,?,?,?,?)", rows
                )
                db.executemany(
                    "INSERT OR IGNORE INTO dictionary_forms VALUES (?,?)", forms
                )
                rows, forms = [], []
    if rows:
        db.executemany(
            "INSERT OR REPLACE INTO dictionary_entries VALUES (?,?,?,?,?)", rows
        )
        db.executemany("INSERT OR IGNORE INTO dictionary_forms VALUES (?,?)", forms)
    db.executemany(
        "INSERT OR REPLACE INTO dictionary_meta VALUES (?,?)",
        [
            ("source", "ECDICT · MIT"),
            ("imported_at", str(now_ms())),
            (
                "count",
                str(
                    db.execute("SELECT count(*) FROM dictionary_entries").fetchone()[0]
                ),
            ),
        ],
    )
    return count


def lookup(db, term):
    query = normalize(term)
    exact = db.execute(
        "SELECT * FROM dictionary_entries WHERE term=?", (query,)
    ).fetchone()
    candidates = [query]
    if exact:
        for item in exact["exchange"].split("/"):
            if item.startswith("0:"):
                candidates.extend(item[2:].split(","))
    candidates.extend(
        r[0]
        for r in db.execute(
            "SELECT lemma FROM dictionary_forms WHERE form=? ORDER BY lemma LIMIT 12",
            (query,),
        )
    )
    # Handle common contractions without rewriting the displayed original word.
    contractions = {
        "can't": "can",
        "won't": "will",
        "don't": "do",
        "doesn't": "do",
        "isn't": "be",
        "aren't": "be",
        "didn't": "do",
        "it's": "it",
        "we're": "we",
        "you're": "you",
        "they're": "they",
        "i'm": "i",
        "i've": "have",
        "we've": "have",
        "wouldn't": "would",
        "couldn't": "could",
        "shouldn't": "should",
    }
    if query in contractions:
        candidates.append(contractions[query])
    if query.endswith("'s"):
        candidates.append(query[:-2])
    candidates = list(dict.fromkeys(candidates))
    for candidate in candidates:
        row = db.execute(
            "SELECT * FROM words WHERE lower(term)=? AND archived=0 ORDER BY rowid LIMIT 1",
            (candidate,),
        ).fetchone()
        if row:
            phonetic = db.execute(
                "SELECT phonetic FROM dictionary_entries WHERE term=?", (candidate,)
            ).fetchone()
            return dict(
                found=True,
                query=query,
                term=row["term"],
                phonetic=phonetic[0] if phonetic else "",
                meaning=row["meaning"],
                definition=row["example"]
                if row["example_kind"] == "definition"
                else "",
                example=row["example"] if row["example_kind"] == "example" else "",
                translation=row["translation"],
                source="我的词库",
                word_id=row["id"],
            )
    # A base form generally has a fuller definition than an inflected-form entry.
    for candidate in candidates[1:] + candidates[:1]:
        row = db.execute(
            "SELECT * FROM dictionary_entries WHERE term=?", (candidate,)
        ).fetchone()
        if row:
            return dict(
                found=True,
                query=query,
                term=row["term"],
                phonetic=row["phonetic"],
                meaning=row["translation"],
                definition=row["definition"],
                example="",
                translation="",
                source="ECDICT 本地词典",
                word_id=None,
            )
    return dict(
        found=False,
        query=query,
        term=query,
        phonetic="",
        meaning="本地词典暂无释义，可能是专有名词、缩写或拼写变体。仍可朗读并查看所在句子的译文。",
        definition="",
        example="",
        translation="",
        source="",
        word_id=None,
    )
