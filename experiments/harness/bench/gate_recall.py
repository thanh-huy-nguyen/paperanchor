"""Plant wrong numbers into papers and measure how often the gate blocks the edit (no LLM involved).

For each paper, up to 15 traced or derived decimal numbers are perturbed in three ways:
  small:  +3 units of the last shown digit (81.2 -> 81.5), a quiet rounding-in-your-favor edit, in place
  large:  +2.0 on the shown scale (81.2 -> 83.2), an inflated headline, in place
  insert: the sentence is repeated right after itself with the large change, i.e. a new claim with a made-up number
Usage: python bench/gate_recall.py arxiv ../pilot/arxiv   |   python bench/gate_recall.py repos ../pilot/repos
"""
import json
import random
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evw.numtrace import EvidenceMatcher, build_evidence_index, gate, trace  # noqa: E402

KINDS = ("small", "large", "insert")


def one(job):
    name, tex, ev, seed = job
    rng = random.Random(seed)
    matcher = EvidenceMatcher(build_evidence_index(Path(ev)))
    nums = [n for n in trace(tex, matcher).numbers if n.status in ("traced", "derived") and n.decimals >= 1]
    rng.shuffle(nums)
    lines = tex.splitlines()
    res = {k: [0, 0] for k in KINDS}
    for n in nums[:15]:
        ln = lines[n.line - 1]
        if n.text not in ln:
            continue
        for kind in KINDS:
            new_val = n.value + (3 * 10 ** (-n.decimals) if kind == "small" else 2.0)
            new_txt = f"{new_val:.{n.decimals}f}"
            if kind == "insert":
                i = ln.find(n.text)
                a = max(ln.rfind(". ", 0, i) + 2, 0)
                b = ln.find(". ", i)
                b = len(ln) if b < 0 else b + 1
                sent = ln[a:b]
                if not re.search(r"[A-Za-z]{3}", sent):
                    continue
                new_ln = ln[:b] + " " + sent.replace(n.text, new_txt, 1) + ln[b:]
            else:
                new_ln = ln.replace(n.text, new_txt, 1)
            edited = "\n".join(lines[: n.line - 1] + [new_ln] + lines[n.line:])
            res[kind][0] += not gate(tex, edited, matcher).allow
            res[kind][1] += 1
    return name, res


def main():
    kind, root = sys.argv[1], Path(sys.argv[2])
    jobs = []
    if kind == "repos":
        for i, d in enumerate(sorted(p for p in root.iterdir() if (p / "review_r0.tex").exists())):
            jobs.append((d.name, (d / "review_r0.tex").read_text(), str(d / "evidence_snapshot"), i))
    else:
        for i, line in enumerate(open(root / "manifest.jsonl")):
            m = json.loads(line)
            jobs.append((m["id"], (root / m["id"] / "prose.tex").read_text(), str(root / m["id"] / "results"), i))
    with ProcessPoolExecutor(10) as ex:
        out = list(ex.map(one, jobs))
    tot = {k: [0, 0] for k in KINDS}
    for name, res in out:
        print(f"{name:14s} " + "  ".join(f"{k} {c}/{t}" for k, (c, t) in res.items()))
        for k in KINDS:
            tot[k][0] += res[k][0]
            tot[k][1] += res[k][1]
    for k, (c, t) in tot.items():
        print(f"ALL {k:6s} planted {t:4d}  blocked {c:4d}  recall {100 * c / max(t, 1):.1f}%")
    (root.parent / f"gate_recall_{kind}.json").write_text(json.dumps({"per_paper": out, "total": tot}, indent=1))


if __name__ == "__main__":
    main()
