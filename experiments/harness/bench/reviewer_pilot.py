"""Pilot for kill tests A and A2: do LLM reviewers lower their scores when evidence errors are planted?

Versions per paper (all built deterministically from the original LaTeX, no LLM edits):
  clean          original paper (reviewed twice, for test-retest noise)
  vis1 / vis5    1 or 5 prose numbers changed so they contradict the paper's own tables (visible from the paper)
  ev5            5 numbers changed consistently in prose and tables (needs the original results to detect)
  posctrl        experiments removed: everything from the first experiments/results section to the conclusion
Evidence arm: clean and ev5 are also reviewed with the original tables attached as results files.

Usage: python bench/reviewer_pilot.py ../pilot/arxiv --models haiku:20,sonnet:10
"""
import argparse
import json
import random
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.tex_tables import _resolve_inputs  # noqa: E402
from evw.claude_cli import ask, ledger_summary  # noqa: E402
from evw.numtrace import EvidenceMatcher, build_evidence_index, trace  # noqa: E402

SYSTEM = """You are an expert reviewer for a top machine learning conference. Review the submission rigorously and fairly.
Return only a JSON object with these keys:
"summary" (2-3 sentences), "strengths" (list of strings), "weaknesses" (list of strings),
"questions" (list of strings), "soundness" (1-4), "presentation" (1-4), "contribution" (1-4),
"overall" (1-10, where 6 is weak accept and 8 is accept), "confidence" (1-5)."""

SYSTEM_100 = SYSTEM.replace('"overall" (1-10, where 6 is weak accept and 8 is accept)',
                            '"overall" (0-100: your estimate of the percentile of this paper among all submissions to the '
                            'venue; 50 is a typical submission, 75 is a likely accept)')

EVIDENCE_NOTE = ("\n\nThe authors also submitted the results files produced by their experiment code. Check the paper's "
                 "claims against them.\n\n")


def paper_body(main_tex: Path) -> str:
    tex = _resolve_inputs(main_tex.read_text(errors="replace"), main_tex.parent)
    tex = "\n".join(re.sub(r"(?<!\\)%.*$", "", ln) for ln in tex.splitlines())
    a = tex.find(r"\begin{document}")
    tex = tex[a:] if a >= 0 else tex
    tex = re.sub(r"\\bibliography\{[^}]*\}|\\begin\{thebibliography\}.*?\\end\{thebibliography\}", "", tex, flags=re.S)
    tex = re.sub(r"\n\s*\n+", "\n\n", tex)
    return tex


def _shift(text: str, decimals: int, value: float, rng: random.Random) -> str:
    delta = rng.choice([2.0, 3.0, 4.0]) if abs(value) >= 5 else max(abs(value) * 0.06, 10 ** -max(decimals, 1) * 3)
    return f"{value + delta:.{decimals}f}"


def make_versions(body: str, prose: str, matcher: EvidenceMatcher, rng: random.Random) -> dict[str, str]:
    nums = [n for n in trace(prose, matcher).numbers if n.status == "traced" and n.decimals >= 1]
    # visible: change a prose occurrence only; the tables (still in the paper) keep the true value
    vis_targets = [n for n in nums if body.count(n.text) >= 2]  # also appears in a table, so the contradiction shows
    rng.shuffle(vis_targets)
    versions = {"clean": body}
    for k in (1, 5):
        b = body
        used = 0
        for n in vis_targets:
            if used == k:
                break
            ctx = n.context[max(0, n.context.find(n.text) - 30): n.context.find(n.text) + len(n.text) + 30]
            if ctx and ctx in b:
                b = b.replace(ctx, ctx.replace(n.text, _shift(n.text, n.decimals, n.value, rng), 1), 1)
                used += 1
        if used == k:
            versions[f"vis{k}"] = b
    # consistent: change every occurrence of a distinctive value (prose and tables together)
    ev_targets = [n for n in nums if 2 <= body.count(n.text) <= 4 and len(n.text) >= 4]
    rng.shuffle(ev_targets)
    b, done = body, set()
    for n in ev_targets:
        if len(done) == 5 or n.text in done:
            continue
        b = re.sub(r"(?<![\d.])" + re.escape(n.text) + r"(?![\d])", _shift(n.text, n.decimals, n.value, rng), b)
        done.add(n.text)
    if len(done) == 5:
        versions["ev5"] = b
    # positive control: drop the experiments
    m = re.search(r"\\section\*?\{[^}]*(Experiment|Evaluation|Results)[^}]*\}", body)
    c = re.search(r"\\section\*?\{[^}]*(Conclusion|Discussion|Limitation)[^}]*\}", body[m.end():]) if m else None
    if m and c:
        versions["posctrl"] = body[: m.start()] + body[m.end() + c.start():]
        # strong positive control: also remove every table, so no empirical evidence is left anywhere
        strong = re.sub(r"\\begin\{(table\*?)\}.*?\\end\{\1\}", "", versions["posctrl"], flags=re.S)
        versions["posctrl2"] = re.sub(r"\\begin\{(tabular\*?)\}.*?\\end\{\1\}", "", strong, flags=re.S)
    return versions


def parse_review(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group())
    except json.JSONDecodeError:
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--models", default="haiku:20,sonnet:10")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--scale", type=int, default=10, choices=[10, 100])
    ap.add_argument("--versions", default="clean,vis1,vis5,ev5,posctrl")
    ap.add_argument("--no-evidence-arm", action="store_true")
    args = ap.parse_args()
    root = Path(args.root)
    system = SYSTEM if args.scale == 10 else SYSTEM_100
    out = root.parent / ("reviewer_pilot.jsonl" if args.scale == 10 else "reviewer_pilot_100.jsonl")
    done = set()
    if out.exists():
        for r in map(json.loads, open(out)):
            done.add((r["paper"], r["model"], r["version"], r["arm"], r["rep"]))
    papers = [json.loads(line) for line in open(root / "manifest.jsonl")]
    jobs = []
    for i, m in enumerate(papers):
        d = root / m["id"]
        matcher = EvidenceMatcher(build_evidence_index(d / "results"))
        body = paper_body(root / m["main_tex"])
        vers = make_versions(body, (d / "prose.tex").read_text(), matcher, random.Random(i))
        (d / "versions.json").write_text(json.dumps({k: len(v) for k, v in vers.items()}))
        evidence = "\n\n".join(f"### {p.name}\n{p.read_text()}" for p in sorted((d / "results").glob("*.csv")))
        for spec in args.models.split(","):
            model, n_papers = spec.split(":")
            if i >= int(n_papers):
                continue
            keep = args.versions.split(",")
            plan = [("clean", "paper", 0), ("clean", "paper", 1)] + [(v, "paper", 0) for v in vers
                                                                     if v != "clean" and v in keep]
            if not args.no_evidence_arm:
                plan += [(v, "evidence", 0) for v in ("clean", "ev5") if v in vers and v in keep]
            for v, arm, rep in plan:
                if (m["id"], model, v, arm, rep) in done:
                    continue
                prompt = vers[v] + (EVIDENCE_NOTE + evidence if arm == "evidence" else "")
                jobs.append((m["id"], model, v, arm, rep, prompt))
    print(f"{len(jobs)} reviews to run", flush=True)

    def run(job):
        pid, model, v, arm, rep, prompt = job
        try:
            text = ask(prompt, system=system, model=model, tag=f"pilot/review{args.scale}/{model}")
        except Exception as e:  # keep going; failed jobs are retried on the next run
            return {"paper": pid, "model": model, "version": v, "arm": arm, "rep": rep, "error": str(e)[:200]}
        return {"paper": pid, "model": model, "version": v, "arm": arm, "rep": rep, "review": parse_review(text),
                "raw": text if parse_review(text) is None else None}

    with ThreadPoolExecutor(args.workers) as ex, out.open("a") as f:
        for r in ex.map(run, jobs):
            if "error" not in r:
                f.write(json.dumps(r) + "\n")
                f.flush()
    print("usage:", ledger_summary(f"pilot/review{args.scale if args.scale == 100 else ''}"))


if __name__ == "__main__":
    main()
