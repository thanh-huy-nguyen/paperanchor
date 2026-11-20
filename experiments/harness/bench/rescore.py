"""Fresh reviews of the pressured-loop drafts, free of best-of-K selection.

For every repo with pressured runs, the round-0 draft and the four round-4 finals are each reviewed REPS times by the
loop reviewer (Sonnet) and by a held-out reviewer (Opus) on the 0-100 scale. Rows are appended to
<root>/../rescore.jsonl and the run resumes where it stopped.

Usage: python3 bench/rescore.py ../pilot/repos --reps 3 --workers 8
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.writing_loop_pressure import review  # noqa: E402

LOCK = threading.Lock()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--reviewers", default="sonnet,opus")
    a = ap.parse_args()
    root = Path(a.root)
    out = root.parent / "rescore.jsonl"
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            r = json.loads(line)
            done.add((r["repo"], r["doc"], r["reviewer"], r["rep"]))
    jobs = []
    for d in sorted(root.iterdir()):
        finals = sorted(d.glob("press_*_r4.tex"))
        if not finals:
            continue
        docs = {"r0": d / "work" / "paper" / "main.tex"}
        docs.update({f.stem[len("press_"):-len("_r4")]: f for f in finals})
        for doc, path in docs.items():
            for reviewer in a.reviewers.split(","):
                for rep in range(a.reps):
                    if (d.name, doc, reviewer, rep) not in done:
                        jobs.append((d.name, doc, path, reviewer, rep))
    print(f"{len(jobs)} reviews to run", flush=True)

    def run(job):
        repo, doc, path, reviewer, rep = job
        r = review(path.read_text(), reviewer, f"pilot/rescore/{reviewer}")
        row = {"repo": repo, "doc": doc, "reviewer": reviewer, "rep": rep, "overall": r.get("overall")}
        with LOCK, out.open("a") as f:
            f.write(json.dumps(row) + "\n")
        print(repo, doc, reviewer, rep, row["overall"], flush=True)

    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(run, jobs))


if __name__ == "__main__":
    main()
