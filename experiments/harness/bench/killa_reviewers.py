"""Kill test A (Exhibit 2): do LLM reviewers price wrong numbers below missing ones?

Versions per paper, all built from the original LaTeX:
  clean      original paper (reviewed twice, three times on the first 20 papers, for test-retest noise)
  vis5       5 prose numbers changed so they contradict the paper's own tables (the tables keep the true value)
  vis1       the first of those 5 changes only
  del5       the same 5 numbers removed from their sentences instead (Haiku rewrites the sentence without the number,
             every other number kept; if that fails three times, the sentence is dropped)
  posctrl2   experiments section and every table removed (positive control: no evidence at all)

Reviewers: Haiku, Sonnet and Opus, single-version reviews on the 0-100 percentile scale of reviewer_pilot.py.
On the first 20 eligible papers vis5 and del5 get 3 repeats each. Pre-registered analysis: notes/10_killA_prereg.md.

Usage:
    python3 bench/killa_reviewers.py build ../pilot/arxiv          # versions only, Haiku for del5
    python3 bench/killa_reviewers.py review ../pilot/arxiv --workers 8
    python3 bench/killa_reviewers.py analyze
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.reviewer_pilot import SYSTEM_100, _shift, paper_body, parse_review  # noqa: E402
from evw.claude_cli import ask  # noqa: E402
from evw.numtrace import EvidenceMatcher, build_evidence_index, trace  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "pilot" / "killa"
RUNGS = ["haiku", "sonnet", "opus"]
N_REPEAT = 20
N_PAPERS = 60

DEL_SYSTEM = """You edit one sentence of a LaTeX paper. Rewrite it so it no longer states the given number. Remove the
number and any words that exist only to state it; keep every other fact, every other number, citations, references
and LaTeX commands exactly as they are. The result must read naturally in the paper's style. Reply with the rewritten
sentence only."""

RESULT_SYSTEM = """You read numbered snippets from a research paper. Each marks one number with [[ ]]. Say which marked
numbers report a measured experimental result (a score, error, accuracy, gain, speed, cost or other outcome of a
run). Settings, hyperparameters, dataset sizes, counts of items, and constants are not results. Reply with a JSON list
of the snippet numbers that are results, nothing else."""


def result_like(cands: list[tuple[str, str]], pid: str) -> set[int]:
    """Indices of candidates (number text, context) that report results, by one Haiku call, cached per paper."""
    f = OUT / "versions" / pid / "result_like.json"
    if f.exists():
        return set(json.loads(f.read_text()))
    listing = "\n".join(f"{i}: ...{c.replace(t, '[[' + t + ']]', 1)}..." for i, (t, c) in enumerate(cands))
    for _ in range(3):
        out = ask(listing, system=RESULT_SYSTEM, model="haiku", tag="pilot/killa/resultlike")
        m = re.search(r"\[.*?\]", out, re.S)
        try:
            idx = [int(x) for x in json.loads(m.group())] if m else None
        except (ValueError, TypeError, json.JSONDecodeError):
            idx = None
        if idx is not None:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(idx))
            return set(idx)
    return set()


NUM = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?")


def sentence_span(body: str, pos: int) -> tuple[int, int]:
    """The sentence around pos: back to the previous '. ' / blank line, forward to the next one."""
    a = max(body.rfind(". ", 0, pos), body.rfind("\n\n", 0, pos))
    a = 0 if a < 0 else a + 2
    ends = [e for e in (body.find(". ", pos), body.find("\n\n", pos)) if e >= 0]
    b = min(ends) + 1 if ends else len(body)
    return a, b


def delete_number(sent: str, num: str) -> tuple[str, str]:
    others = sorted(m.group() for m in NUM.finditer(sent) if m.group() != num)
    for _ in range(3):
        out = ask(f"NUMBER TO REMOVE: {num}\n\nSENTENCE:\n{sent}", system=DEL_SYSTEM, model="haiku",
                  tag="pilot/killa/del").strip()
        kept = sorted(m.group() for m in NUM.finditer(out))
        if out and not re.search(r"(?<![\d.])" + re.escape(num) + r"(?![\d])", out) and kept == others:
            return out, "rewrite"
    return "", "drop_sentence"


def build_one(i: int, m: dict, root: Path) -> dict:
    d = root / m["id"]
    vd = OUT / "versions" / m["id"]
    if (vd / "meta.json").exists():
        return json.loads((vd / "meta.json").read_text())
    body = paper_body(root / m["main_tex"])
    matcher = EvidenceMatcher(build_evidence_index(d / "results"))
    nums = [n for n in trace((d / "prose.tex").read_text(), matcher).numbers if n.status == "traced" and n.decimals >= 1]
    cands = [n for n in nums if body.count(n.text) >= 2]  # also in a table, so a changed prose copy is visible
    rng = random.Random(i)
    rng.shuffle(cands)
    cands = cands[:40]
    wide = [(n.text, n.context[max(0, n.context.find(n.text) - 120): n.context.find(n.text) + len(n.text) + 80])
            for n in cands]
    res_idx = result_like(wide, m["id"]) if cands else set()
    targets, seen = [], set()
    for j, n in enumerate(cands):
        if j not in res_idx:
            continue
        ctx = n.context[max(0, n.context.find(n.text) - 30): n.context.find(n.text) + len(n.text) + 30]
        if not ctx or body.count(ctx) != 1 or n.text in seen:
            continue
        pos = body.find(ctx)
        span = sentence_span(body, pos + ctx.find(n.text))
        if any(not (span[1] <= t["span"][0] or span[0] >= t["span"][1]) for t in targets):
            continue  # one target per sentence, so del5 and vis5 touch the same 5 sentences
        targets.append({"text": n.text, "ctx": ctx, "span": span, "new": _shift(n.text, n.decimals, n.value, rng)})
        seen.add(n.text)
        if len(targets) == 5:
            break
    meta = {"paper": m["id"], "eligible": False}
    mm = re.search(r"\\section\*?\{[^}]*(Experiment|Evaluation|Results)[^}]*\}", body)
    cc = re.search(r"\\section\*?\{[^}]*(Conclusion|Discussion|Limitation)[^}]*\}", body[mm.end():]) if mm else None
    if len(targets) < 5 or not (mm and cc):
        vd.mkdir(parents=True, exist_ok=True)
        meta["reason"] = f"{len(targets)} visible targets" if len(targets) < 5 else "no experiments/conclusion section"
        (vd / "meta.json").write_text(json.dumps(meta))
        return meta
    vers = {"clean": body}
    for k in (1, 5):
        b = body
        for t in targets[:k]:
            b = b.replace(t["ctx"], t["ctx"].replace(t["text"], t["new"], 1), 1)
        vers[f"vis{k}"] = b
    # del5: rewrite the 5 sentences, last first so earlier spans stay valid
    b, methods = body, []
    for t in sorted(targets, key=lambda t: -t["span"][0]):
        a, e = t["span"]
        new, how = delete_number(body[a:e], t["text"])
        b = b[:a] + new + b[e:]
        methods.append(how)
        t["sent"], t["del_sent"] = body[a:e], new
    vers["del5"] = b
    strong = body[: mm.start()] + body[mm.end() + cc.start():]
    strong = re.sub(r"\\begin\{(table\*?)\}.*?\\end\{\1\}", "", strong, flags=re.S)
    vers["posctrl2"] = re.sub(r"\\begin\{(tabular\*?)\}.*?\\end\{\1\}", "", strong, flags=re.S)
    vd.mkdir(parents=True, exist_ok=True)
    for k, v in vers.items():
        (vd / f"{k}.tex").write_text(v)
    meta.update({"eligible": True, "targets": [{k: t[k] for k in ("text", "new", "ctx", "sent", "del_sent")} for t in targets],
                 "del_methods": methods, "chars": {k: len(v) for k, v in vers.items()}})
    (vd / "meta.json").write_text(json.dumps(meta, indent=1))
    return meta


def eligible(root: Path) -> list[str]:
    papers = [json.loads(line) for line in open(root / "manifest.jsonl")]
    out = []
    for m in papers:
        f = OUT / "versions" / m["id"] / "meta.json"
        if f.exists() and json.loads(f.read_text())["eligible"]:
            out.append(m["id"])
    return out[:N_PAPERS]  # pre-registered: the first 60 eligible papers in manifest order


def jobs_for(ids: list[str]) -> list[tuple]:
    jobs = []
    for j, pid in enumerate(ids):
        for model in RUNGS:
            plan = [("clean", 0), ("clean", 1), ("vis1", 0), ("vis5", 0), ("del5", 0), ("posctrl2", 0)]
            if j < N_REPEAT:
                plan += [("clean", 2), ("vis5", 1), ("vis5", 2), ("del5", 1), ("del5", 2)]
            jobs += [(pid, model, v, rep) for v, rep in plan]
    return jobs


def review(root: Path, workers: int, limit_models: list[str]) -> None:
    out = OUT / "reviews.jsonl"
    done = set()
    if out.exists():
        for r in map(json.loads, open(out)):
            done.add((r["paper"], r["model"], r["version"], r["rep"]))
    jobs = [j for j in jobs_for(eligible(root)) if j not in done and j[1] in limit_models]
    print(f"{len(jobs)} reviews to run", flush=True)

    def run(job):
        pid, model, v, rep = job
        text = (OUT / "versions" / pid / f"{v}.tex").read_text()
        try:
            raw = ask(text, system=SYSTEM_100, model=model, tag=f"pilot/killa/{model}")
        except Exception as e:  # noqa: BLE001  retried on the next run
            print(pid, model, v, rep, "error", str(e)[:120], flush=True)
            return None
        return {"paper": pid, "model": model, "version": v, "rep": rep, "review": parse_review(raw),
                "raw": raw if parse_review(raw) is None else None}

    with ThreadPoolExecutor(workers) as ex, out.open("a") as f:
        for r in ex.map(run, jobs):
            if r:
                f.write(json.dumps(r) + "\n")
                f.flush()


def analyze(margin: float = 3.0, n_boot: int = 10000) -> dict:
    rows = [json.loads(line) for line in open(OUT / "reviews.jsonl")]
    meta = {p.parent.name: json.loads(p.read_text()) for p in (OUT / "versions").glob("*/meta.json")}
    sc = defaultdict(list)
    mention = defaultdict(list)
    for r in rows:
        rv = r.get("review") or {}
        try:
            s = float(rv.get("overall"))
        except (TypeError, ValueError):
            continue
        sc[(r["model"], r["paper"], r["version"])].append(s)
        if r["version"] in ("vis1", "vis5"):
            k = 1 if r["version"] == "vis1" else 5
            txt = json.dumps({x: rv.get(x) for x in ("weaknesses", "questions", "summary")})
            hit = any(re.search(r"(?<![\d.])" + re.escape(t["new"]) + r"(?![\d])", txt)
                      for t in meta[r["paper"]]["targets"][:k])
            mention[(r["model"], r["version"])].append(hit)
    rng = random.Random(0)
    res = {}
    for model in RUNGS:
        papers = sorted({p for (mm, p, v) in sc if mm == model})
        mean = lambda p, v: sum(sc[(model, p, v)]) / len(sc[(model, p, v)])  # noqa: E731
        out = {"n_papers": len(papers)}
        contrasts = {"vis5_minus_del5": ("vis5", "del5"), "clean_minus_vis5": ("clean", "vis5"),
                     "clean_minus_vis1": ("clean", "vis1"), "clean_minus_del5": ("clean", "del5"),
                     "clean_minus_posctrl2": ("clean", "posctrl2")}
        for name, (a, b) in contrasts.items():
            diffs = [mean(p, a) - mean(p, b) for p in papers if sc[(model, p, a)] and sc[(model, p, b)]]
            if not diffs:
                continue
            boots = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(n_boot))
            out[name] = {"mean": round(sum(diffs) / len(diffs), 2), "n": len(diffs),
                         "ci90": [round(boots[int(0.05 * n_boot)], 2), round(boots[int(0.95 * n_boot)], 2)],
                         "ci95": [round(boots[int(0.025 * n_boot)], 2), round(boots[int(0.975 * n_boot)], 2)]}
        rr = [sc[(model, p, "clean")][:2] for p in papers if len(sc[(model, p, "clean")]) >= 2]
        out["retest_abs_diff"] = round(sum(abs(a - b) for a, b in rr) / max(len(rr), 1), 2)
        e = out.get("vis5_minus_del5")
        pc = out.get("clean_minus_posctrl2")
        out["equivalent"] = bool(e and -margin < e["ci90"][0] and e["ci90"][1] < margin)
        out["posctrl_registers"] = bool(pc and pc["ci95"][0] > 0 and pc["mean"] >= 10)
        out["mentions_planted_value"] = {v: f"{sum(mention[(model, v)])}/{len(mention[(model, v)])}"
                                         for v in ("vis1", "vis5")}
        res[model] = out
    (OUT / "analysis.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(res, indent=1))
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "review", "analyze"])
    ap.add_argument("root", nargs="?", default=str(OUT.parent / "arxiv"))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--models", default=",".join(RUNGS))
    a = ap.parse_args()
    root = Path(a.root)
    if a.cmd == "build":
        papers = [json.loads(line) for line in open(root / "manifest.jsonl")]
        with ThreadPoolExecutor(a.workers) as ex:
            metas = list(ex.map(lambda im: build_one(im[0], im[1], root), enumerate(papers)))
        ok = [m for m in metas if m["eligible"]]
        print(f"eligible {len(ok)} of {len(metas)}; del5 methods:",
              {k: sum(x == k for m in ok for x in m["del_methods"]) for k in ("rewrite", "drop_sentence")})
        for m in metas:
            if not m["eligible"]:
                print("  excluded", m["paper"], m["reason"])
    elif a.cmd == "review":
        review(root, a.workers, a.models.split(","))
    else:
        analyze()


if __name__ == "__main__":
    main()
