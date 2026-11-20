"""Trace each pilot paper's prose against evidence built from its own tables; print a summary table."""
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.tex_tables import split_paper  # noqa: E402
from evw.numtrace import EvidenceMatcher, build_evidence_index, trace  # noqa: E402

root = Path(sys.argv[1])
rows, why = [], Counter()
for line in open(root / "manifest.jsonl"):
    m = json.loads(line)
    d = root / m["id"]
    shutil.rmtree(d / "results", ignore_errors=True)
    prose, k = split_paper(root / m["main_tex"], d)
    (d / "prose.tex").write_text(prose)
    rep = trace(prose, EvidenceMatcher(build_evidence_index(d / "results")))
    c = rep.counts
    rows.append((m["id"], k, sum(c.values()), c.get("traced", 0), c.get("derived", 0), c.get("untraced", 0) + c.get("weak", 0)))
    json.dump(rep.to_json(), open(d / "trace_original.json", "w"), indent=1)
print(f"{'paper':14s} tabs nums traced derived weak+untraced")
for r in rows:
    print(f"{r[0]:14s} {r[1]:4d} {r[2]:4d} {r[3]:6d} {r[4]:7d} {r[5]:8d}")
T = sum(r[2] for r in rows); U = sum(r[5] for r in rows); D = sum(r[4] for r in rows)
print(f"total {T}, traced {T-U-D} ({100*(T-U-D)/T:.1f}%), derived {D} ({100*D/T:.1f}%), weak+untraced {U} ({100*U/T:.1f}%)")
