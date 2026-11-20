"""Find recent arXiv papers whose GitHub repos contain raw result files (the repo split).

Usage: GH_CONFIG_DIR=~/.config/gh-nw python bench/find_repos.py --out ../pilot/repos/candidates.jsonl --n 15
A repo qualifies if it has at least 3 result-like files: .csv/.json/.jsonl/.log/.txt/.tsv under a path containing
results, logs, outputs, runs, eval, metrics, or tables (configs, data, and package files excluded).
"""
import argparse
import json
import re
import subprocess
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ATOM = {"a": "http://www.w3.org/2005/Atom"}
RESULT_DIR = re.compile(r"(^|/)(results?|logs?|outputs?|runs|eval(uation)?s?|metrics|tables|scores)(/|$)", re.I)
RESULT_NAME = re.compile(r"result|metric|score|eval|benchmark|leaderboard|ablation", re.I)
RESULT_EXT = re.compile(r"\.(csv|tsv|json|jsonl|log|txt)$", re.I)
EXCLUDE = re.compile(r"(^|/)(data|datasets?|configs?|node_modules|\.github|assets|docs?)/|package(-lock)?\.json$|"
                     r"requirements|tokenizer|vocab", re.I)


def arxiv(since: str, start: int) -> list[dict]:
    q = f"(cat:cs.LG OR cat:cs.CV OR cat:cs.CL) AND abs:github AND submittedDate:[{since.replace('-', '')}0000 TO 203001010000]"
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"search_query": q, "start": start, "max_results": 100, "sortBy": "submittedDate", "sortOrder": "ascending"})
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "evidence-writing-research/0.1"}), timeout=60) as r:
        root = ET.fromstring(r.read())
    out = []
    for e in root.findall("a:entry", ATOM):
        abs_ = " ".join(e.find("a:summary", ATOM).text.split())
        m = re.search(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", abs_)
        if m:
            out.append({"id": e.find("a:id", ATOM).text.rsplit("/", 1)[-1],
                        "title": " ".join(e.find("a:title", ATOM).text.split()),
                        "repo": f"{m.group(1)}/{m.group(2).rstrip('.')}"})
    return out


def hf_daily(day: str) -> list[dict]:
    url = f"https://huggingface.co/api/daily_papers?date={day}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "evidence-writing-research/0.1"}), timeout=60) as r:
            items = json.load(r)
    except Exception:
        return []
    out = []
    for x in items:
        p = x.get("paper", x)
        m = re.search(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", p.get("githubRepo") or "")
        if m and str(p.get("id", "")) >= "2609":
            out.append({"id": p["id"], "title": " ".join(p.get("title", "").split()),
                        "repo": f"{m.group(1)}/{m.group(2).removesuffix('.git')}"})
    return out


def result_files(repo: str) -> list[str] | None:
    p = subprocess.run(["gh", "api", f"repos/{repo}/git/trees/HEAD?recursive=1"], capture_output=True, text=True)
    if p.returncode != 0:
        return None
    tree = json.loads(p.stdout).get("tree", [])
    return [t["path"] for t in tree if t["type"] == "blob" and RESULT_EXT.search(t["path"])
            and (RESULT_DIR.search(t["path"]) or RESULT_NAME.search(t["path"].rsplit("/", 1)[-1]))
            and not EXCLUDE.search(t["path"]) and t.get("size", 0) < 5_000_000]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--since", default="2026-09-01")
    ap.add_argument("--n", type=int, default=15)
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    seen = {json.loads(line)["id"] for line in out.open()} if out.exists() else set()
    kept, checked = len(seen), 0
    import datetime as dt

    days = [(dt.date.fromisoformat(args.since) + dt.timedelta(days=i)).isoformat() for i in range(75)]

    def sources():
        for day in days:
            yield from hf_daily(day)
            time.sleep(0.5)

    for m in sources():
        if kept >= args.n:
            break
        if True:
            if kept >= args.n:
                break
            if m["id"] in seen:
                continue
            files = result_files(m["repo"])
            checked += 1
            if files and len(files) >= 3:
                m["result_files"] = files[:200]
                m["n_result_files"] = len(files)
                with out.open("a") as f:
                    f.write(json.dumps(m) + "\n")
                kept += 1
                print(kept, m["id"], m["repo"], len(files), flush=True)
            seen.add(m["id"])
    print(f"checked {checked} repos, kept {kept}")


if __name__ == "__main__":
    main()
