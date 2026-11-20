"""Checker accuracy (Exhibit 6): does the number trace separate real numbers from fabricated ones?

For each paper, every decimal number is shifted (+2.0 if >= 5, else +0.37) to make a fabricated version. We report
the share of real and fabricated decimals that trace (traced or derived), with and without the decoy specificity check.
Usage: python bench/tracer_specificity.py repos ../pilot/repos   |   python bench/tracer_specificity.py arxiv ../pilot/arxiv
"""
import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evw.numtrace import EvidenceMatcher, TraceConfig, build_evidence_index, trace  # noqa: E402


def shift(mo):
    s = mo.group()
    return f"{float(s) + (2.0 if float(s) >= 5 else 0.37):.{len(s.split('.')[1])}f}"


def one(job):
    name, tex, ev = job
    m = EvidenceMatcher(build_evidence_index(Path(ev)), TraceConfig(check_specific=True))
    fake = re.sub(r"(?<![\d.\w])\d+\.\d+(?![\d.])", shift, tex)
    out = {"paper": name, "n_evidence": len(m.index)}
    for tag, t in (("real", tex), ("fake", fake)):
        ns = [n for n in trace(t, m).numbers if n.decimals >= 1]
        out[tag] = {"n": len(ns), "traced": sum(n.status in ("traced", "derived") for n in ns),
                    "specific": sum(n.status in ("traced", "derived") and n.specific for n in ns)}
    return out


def main():
    kind, root = sys.argv[1], Path(sys.argv[2])
    jobs = []
    if kind == "repos":
        for d in sorted(p for p in root.iterdir() if (p / "review_r0.tex").exists()):
            jobs.append((d.name, (d / "review_r0.tex").read_text(), str(d / "evidence_snapshot")))
    else:
        for line in open(root / "manifest.jsonl"):
            m = json.loads(line)
            d = root / m["id"]
            jobs.append((m["id"], (d / "prose.tex").read_text(), str(d / "results")))
    with ProcessPoolExecutor(10) as ex:
        res = list(ex.map(one, jobs))
    tot = {t: {"n": 0, "traced": 0, "specific": 0} for t in ("real", "fake")}
    print(f"{'paper':14s} {'#evid':>7s} {'real traced':>11s} {'real spec':>9s} {'fake traced':>11s} {'fake spec':>9s}")
    for r in res:
        for t in tot:
            for k in tot[t]:
                tot[t][k] += r[t][k]
        f = lambda t, k: f"{100 * r[t][k] / max(r[t]['n'], 1):.0f}%"  # noqa: E731
        print(f"{r['paper']:14s} {r['n_evidence']:7d} {f('real', 'traced'):>11s} {f('real', 'specific'):>9s} "
              f"{f('fake', 'traced'):>11s} {f('fake', 'specific'):>9s}")
    for t in tot:
        print(f"ALL {t}: n={tot[t]['n']} traced {100 * tot[t]['traced'] / tot[t]['n']:.1f}% "
              f"specific {100 * tot[t]['specific'] / tot[t]['n']:.1f}%")
    out = root.parent / f"tracer_specificity_{kind}.json"
    out.write_text(json.dumps({"per_paper": res, "total": tot}, indent=1))


if __name__ == "__main__":
    main()
