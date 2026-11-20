"""Score kill tests A and A2 from the reviewer pilot.

A  (flat score): mean paired drop in "overall" vs the clean mean, per version; pass if vis1 < 0.25, vis5 < 0.5,
   and the positive control drops >= 1.0.
A2 (evidence restores the price): for ev5 with the results attached, share of papers where the reviewer flags a
   numeric inconsistency AND the score drops vs clean-with-evidence; pass if >= 70%.
"Flags" = the weaknesses or questions mention an inconsistency, discrepancy, or mismatch in reported numbers.
"""
import json
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

FLAG = re.compile(r"inconsisten|discrepan|mismatch|contradict|does not match|do not match|differ(s|ent)? from|"
                  r"typo|error in (the )?(table|number|result)|conflict", re.I)


def flagged(review: dict) -> bool:
    text = " ".join(map(str, (review.get("weaknesses") or []) + (review.get("questions") or [])))
    return bool(FLAG.search(text))


rows = [json.loads(line) for line in open(Path(sys.argv[1]))]
by = defaultdict(dict)  # (model, paper) -> {(version, arm, rep): review}
for r in rows:
    if r.get("review") and isinstance(r["review"].get("overall"), (int, float)):
        by[(r["model"], r["paper"])][(r["version"], r["arm"], r["rep"])] = r["review"]

for model in sorted({k[0] for k in by}):
    papers = [p for (m, p) in by if m == model]
    drops = defaultdict(list)
    flags = defaultdict(list)
    retest = []
    a2 = []
    for p in papers:
        R = by[(model, p)]
        cl = [R[k]["overall"] for k in R if k[0] == "clean" and k[1] == "paper"]
        if not cl:
            continue
        base = st.mean(cl)
        if len(cl) == 2:
            retest.append(abs(cl[0] - cl[1]))
        clean_flag = any(flagged(R[k]) for k in R if k[0] == "clean" and k[1] == "paper")
        flags["clean"].append(clean_flag)
        for v in ("vis1", "vis5", "ev5", "posctrl", "posctrl2"):
            if (v, "paper", 0) in R:
                drops[v].append(base - R[(v, "paper", 0)]["overall"])
                flags[v].append(flagged(R[(v, "paper", 0)]))
        if ("ev5", "evidence", 0) in R and ("clean", "evidence", 0) in R:
            ce, ee = R[("clean", "evidence", 0)], R[("ev5", "evidence", 0)]
            drops["ev5+evidence"].append(ce["overall"] - ee["overall"])
            flags["clean+evidence"].append(flagged(ce))
            flags["ev5+evidence"].append(flagged(ee))
            a2.append(flagged(ee) and ee["overall"] < ce["overall"])
    print(f"\n== {model}: {len(papers)} papers; test-retest |diff| mean "
          f"{st.mean(retest) if retest else float('nan'):.2f} (n={len(retest)})")
    print(f"{'version':14s} {'n':>3s} {'mean drop':>9s} {'flag rate':>9s}")
    for v in ("clean", "vis1", "vis5", "ev5", "posctrl", "posctrl2", "clean+evidence", "ev5+evidence"):
        d = drops.get(v, [])
        f = flags.get(v, [])
        md = f"{st.mean(d):9.2f}" if d else f"{'-':>9s}"
        fr = f"{100 * sum(f) / len(f):8.0f}%" if f else f"{'-':>9s}"
        print(f"{v:14s} {max(len(d), len(f)):3d} {md} {fr}")
    v1, v5, pc = (st.mean(drops[k]) if drops[k] else float("nan") for k in ("vis1", "vis5", "posctrl"))
    print(f"Kill test A  (score flat for visible errors): vis1 {v1:.2f} < 0.25, vis5 {v5:.2f} < 0.5, "
          f"posctrl {pc:.2f} >= 1.0 -> {'PASS' if v1 < 0.25 and v5 < 0.5 and pc >= 1.0 else 'FAIL'}")
    if a2:
        print(f"Kill test A2 (evidence restores the price): {100 * sum(a2) / len(a2):.0f}% flagged with a drop "
              f"(n={len(a2)}) -> {'PASS' if sum(a2) / len(a2) >= 0.7 else 'FAIL'}")
