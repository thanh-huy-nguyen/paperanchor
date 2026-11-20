"""Kill test A, pairwise form: does a reviewer prefer the clean paper over a version with planted evidence errors?

Absolute 1-10 reviews were compressed at 4/10 for nearly every paper and version, so they cannot register any edit.
Here a reviewer sees two versions side by side (both orders) and picks the stronger submission. A version "wins" a
pair only if it is preferred in both orders; otherwise the pair is a tie.

Arms: paper only, and paper plus the original results tables (evidence arm, for ev5 only).
Usage: python bench/pairwise_pilot.py ../pilot/arxiv --models haiku:20,sonnet:10
"""
import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.reviewer_pilot import make_versions, paper_body  # noqa: E402
from evw.claude_cli import ask, ledger_summary  # noqa: E402
from evw.numtrace import EvidenceMatcher, build_evidence_index  # noqa: E402

SYSTEM = """You are an expert reviewer for a top machine learning conference. You receive two versions of the same
submission, A and B. Read both carefully and decide which one is the stronger, more trustworthy submission.
Return only a JSON object: {"choice": "A" or "B" or "tie", "reason": "<two sentences naming the decisive difference>"}"""
EVIDENCE_NOTE = "\n\nThe authors also submitted the results files produced by their experiment code:\n\n"


def judge(a: str, b: str, model: str, evidence: str | None, tag: str) -> str | None:
    prompt = f"=== VERSION A ===\n{a}\n\n=== VERSION B ===\n{b}"
    if evidence:
        prompt += EVIDENCE_NOTE + evidence
    text = ask(prompt, system=SYSTEM, model=model, tag=tag)
    m = re.search(r"\{.*\}", text, re.S)
    try:
        d = json.loads(m.group()) if m else {}
    except json.JSONDecodeError:
        d = {}
    c = str(d.get("choice", "")).strip().upper()
    return {"A": "A", "B": "B"}.get(c, "tie"), d.get("reason", "")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--models", default="haiku:20,sonnet:10")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    root = Path(args.root)
    out = root.parent / "pairwise_pilot.jsonl"
    done = set()
    if out.exists():
        done = {(r["paper"], r["model"], r["version"], r["arm"], r["order"]) for r in map(json.loads, open(out))}
    jobs = []
    for i, line in enumerate(open(root / "manifest.jsonl")):
        m = json.loads(line)
        d = root / m["id"]
        vers = make_versions(paper_body(root / m["main_tex"]), (d / "prose.tex").read_text(),
                             EvidenceMatcher(build_evidence_index(d / "results")), random.Random(i))
        evidence = "\n\n".join(f"### {p.name}\n{p.read_text()}" for p in sorted((d / "results").glob("*.csv")))
        for spec in args.models.split(","):
            model, n = spec.split(":")
            if i >= int(n):
                continue
            plan = [(v, "paper") for v in ("vis1", "vis5", "ev5", "posctrl") if v in vers]
            plan += [("ev5", "evidence")] if "ev5" in vers else []
            for v, arm in plan:
                for order in ("clean_first", "edited_first"):
                    if (m["id"], model, v, arm, order) not in done:
                        jobs.append((m["id"], model, v, arm, order, vers["clean"], vers[v],
                                     evidence if arm == "evidence" else None))
    print(f"{len(jobs)} judgments to run", flush=True)

    def run(j):
        pid, model, v, arm, order, clean, edited, ev = j
        a, b = (clean, edited) if order == "clean_first" else (edited, clean)
        try:
            choice, reason = judge(a, b, model, ev, f"pilot/pairwise/{model}")
        except Exception as e:
            return {"error": str(e)[:200]}
        pref = "tie" if choice == "tie" else ("clean" if (choice == "A") == (order == "clean_first") else "edited")
        return {"paper": pid, "model": model, "version": v, "arm": arm, "order": order, "pref": pref, "reason": reason}

    with ThreadPoolExecutor(args.workers) as ex, out.open("a") as f:
        for r in ex.map(run, jobs):
            if "error" not in r:
                f.write(json.dumps(r) + "\n")
                f.flush()

    # summary: a side wins a pair only if preferred in both orders
    res = defaultdict(lambda: defaultdict(dict))
    for r in map(json.loads, open(out)):
        res[(r["model"], r["version"], r["arm"])][r["paper"]][r["order"]] = r["pref"]
    print(f"\n{'model':7s} {'version':8s} {'arm':9s} {'pairs':>5s} {'clean wins':>10s} {'edited wins':>11s} {'ties':>5s}")
    for (model, v, arm), papers in sorted(res.items()):
        c = Counter()
        for orders in papers.values():
            if len(orders) < 2:
                continue
            p = set(orders.values())
            c["clean" if p == {"clean"} else "edited" if p == {"edited"} else "tie"] += 1
        n = sum(c.values())
        print(f"{model:7s} {v:8s} {arm:9s} {n:5d} {100 * c['clean'] / max(n, 1):9.0f}% {100 * c['edited'] / max(n, 1):10.0f}% "
              f"{100 * c['tie'] / max(n, 1):4.0f}%")
    print("usage:", ledger_summary("pilot/pairwise"))


if __name__ == "__main__":
    main()
