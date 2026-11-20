"""Fetch recent arXiv papers with LaTeX source for the planted-error split.

Usage: python bench/fetch_arxiv.py --out ../pilot/arxiv --since 2026-09-01 --n 20
Keeps papers whose main .tex has at least two tabular environments with numbers. Stores source only locally;
the released benchmark lists arXiv IDs and scripts, not text.
"""

from __future__ import annotations

import argparse
import gzip
import io
import json
import re
import tarfile
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

API = "http://export.arxiv.org/api/query?"
ATOM = {"a": "http://www.w3.org/2005/Atom"}
UA = {"User-Agent": "evidence-writing-research/0.1"}


def search(cats: list[str], since: str, start: int, page: int) -> list[dict]:
    q = " OR ".join(f"cat:{c}" for c in cats)
    d0 = since.replace("-", "") + "0000"
    query = f"({q}) AND submittedDate:[{d0} TO 203001010000]"
    url = API + urllib.parse.urlencode(
        {"search_query": query, "start": start, "max_results": page, "sortBy": "submittedDate", "sortOrder": "ascending"}
    )
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        root = ET.fromstring(r.read())
    out = []
    for e in root.findall("a:entry", ATOM):
        aid = e.find("a:id", ATOM).text.rsplit("/", 1)[-1]
        out.append(
            {
                "id": aid,
                "title": " ".join(e.find("a:title", ATOM).text.split()),
                "published": e.find("a:published", ATOM).text,
                "cats": [c.get("term") for c in e.findall("a:category", ATOM)],
            }
        )
    return out


def fetch_source(aid: str, dest: Path) -> Path | None:
    url = f"https://arxiv.org/e-print/{aid}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
        data = r.read()
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
            for m in tf.getmembers():
                name = Path(m.name)
                if m.isfile() and name.suffix in {".tex", ".bbl", ".bib"} and ".." not in name.parts and not name.is_absolute():
                    f = tf.extractfile(m)
                    if f:
                        (dest / name).parent.mkdir(parents=True, exist_ok=True)
                        (dest / name).write_bytes(f.read())
    except tarfile.ReadError:
        try:
            (dest / "main.tex").write_bytes(gzip.decompress(data))
        except OSError:
            return None
    return dest


def main_tex(src: Path) -> Path | None:
    cands = [p for p in src.rglob("*.tex") if r"\begin{document}" in p.read_text(errors="replace")]
    return max(cands, key=lambda p: p.stat().st_size) if cands else None


def numeric_tables(tex: str) -> int:
    tabs = re.findall(r"\\begin\{tabular\*?\}.*?\\end\{tabular\*?\}", tex, flags=re.S)
    return sum(1 for t in tabs if len(re.findall(r"\d+\.\d+", t)) >= 6)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--since", default="2026-09-01")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--cats", default="cs.LG,cs.CV,cs.CL")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / "manifest.jsonl"
    kept = [json.loads(line)["id"] for line in manifest.open()] if manifest.exists() else []
    start = 0
    while len(kept) < args.n and start < 2000:
        for meta in search(args.cats.split(","), args.since, start, 50):
            if len(kept) >= args.n:
                break
            if re.sub(r"v\d+$", "", meta["id"]) in {re.sub(r"v\d+$", "", k) for k in kept} or not any(c in args.cats.split(",") for c in meta["cats"][:1]):
                continue
            time.sleep(3)  # arXiv asks for at most one request every 3 s
            src = fetch_source(meta["id"], out / meta["id"].replace("/", "_") / "src")
            mt = main_tex(src) if src else None
            if not mt:
                continue
            k = numeric_tables(mt.read_text(errors="replace"))
            if k < 2:
                continue
            meta.update({"main_tex": str(mt.relative_to(out)), "numeric_tables": k})
            with manifest.open("a") as f:
                f.write(json.dumps(meta) + "\n")
            kept.append(meta["id"])
            print(len(kept), meta["id"], k, meta["title"][:70], flush=True)
        start += 50
        time.sleep(3)


if __name__ == "__main__":
    main()
