"""Fetch public reference text and optionally extract a private local resume.
Outputs stay in ignored data/corpus/. No resume content is sent to a server.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import xml.etree.ElementTree as ET
from zipfile import ZipFile
import httpx

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data/corpus"
SOURCES = [
    (
        "python-glossary",
        "Python 官方术语表",
        "https://docs.python.org/3/glossary.html",
        "PSF License",
    ),
    (
        "postgres-glossary",
        "PostgreSQL 官方术语表",
        "https://www.postgresql.org/docs/current/glossary.html",
        "PostgreSQL License",
    ),
    (
        "code-review",
        "Google 代码审查指南",
        "https://raw.githubusercontent.com/google/eng-practices/master/review/reviewer/looking-for.md",
        "CC BY 3.0",
    ),
    (
        "review-comments",
        "Google 审查沟通指南",
        "https://raw.githubusercontent.com/google/eng-practices/master/review/reviewer/comments.md",
        "CC BY 3.0",
    ),
    (
        "small-changes",
        "Google 小步提交指南",
        "https://raw.githubusercontent.com/google/eng-practices/master/review/developer/small-cls.md",
        "CC BY 3.0",
    ),
    (
        "technical-writing",
        "Google 技术写作指南",
        "https://developers.google.com/tech-writing/one/words",
        "CC BY 4.0",
    ),
]


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        if tag in ("p", "div", "li", "dt", "dd", "h1", "h2", "h3"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def fetch(source):
    key, label, url, license_name = source
    response = httpx.get(url, follow_redirects=True, timeout=40)
    response.raise_for_status()
    raw = response.text
    if not url.endswith(".md"):
        parser = TextExtractor()
        parser.feed(raw)
        raw = "".join(parser.parts)
    text = "\n".join(
        " ".join(line.split()) for line in raw.splitlines() if line.strip()
    )
    (CORPUS / f"{key}.txt").write_text(text)
    return dict(
        id=key,
        label=label,
        url=url,
        license=license_name,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        characters=len(text),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", type=Path, help="Local DOCX, never uploaded")
    parser.add_argument(
        "--dictionary",
        action="store_true",
        help="Download ECDICT (~63 MB) and its license",
    )
    args = parser.parse_args()
    CORPUS.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        manifest = list(pool.map(fetch, SOURCES))
    (CORPUS / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    )
    if args.dictionary:
        for source_name, dest_name in [
            ("ecdict.csv", "ecdict.csv"),
            ("LICENSE", "ECDICT-LICENSE.txt"),
        ]:
            target = CORPUS / dest_name
            temporary = target.with_suffix(target.suffix + ".part")
            try:
                with httpx.stream(
                    "GET",
                    "https://raw.githubusercontent.com/skywind3000/ECDICT/master/"
                    + source_name,
                    follow_redirects=True,
                    timeout=120,
                ) as response:
                    response.raise_for_status()
                    with temporary.open("wb") as dest:
                        for chunk in response.iter_bytes():
                            dest.write(chunk)
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
    if args.resume:
        with ZipFile(args.resume) as archive:
            tree = ET.fromstring(archive.read("word/document.xml"))
        text = "\n".join(
            node.text or ""
            for node in tree.findall(
                ".//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
            )
        )
        (CORPUS / "resume.private.txt").write_text(text)
    print(
        f"Downloaded {len(manifest)} public sources; private source content is not logged."
    )


if __name__ == "__main__":
    main()
