"""Analyze the pressured writing loop (kill test B, second form).

Per writer and arm: score gain from the draft, and drift from the draft (numbers changed in place off their
evidence, and inserted numbers with no anchored match). The selection test asks whether the reviewer's pick among
the K candidates of a round carries more drift than the candidates it passed over; if reviewers reward drift, it does.
"""
import json
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

root = Path(sys.argv[1])
traj = defaultdict(list)
for f in sorted(root.glob("*/press_*.jsonl")):
    _, writer, arm = f.stem.split("_")
    traj[(writer, arm)].append((f.parent.name, [json.loads(line) for line in open(f)]))

print(f"{'writer':7s} {'arm':8s} {'n':>2s} {'score r0':>8s} {'final':>6s} {'gain':>5s} {'drifted':>8s} "
      f"{'changed':>7s} {'inserted':>8s}")
for (writer, arm), rows in sorted(traj.items()):
    s0 = [r[0]["score"] for _, r in rows if r[0]["score"] is not None]
    sf = [r[-1]["score"] for _, r in rows if r[-1]["score"] is not None]
    gain = [r[-1]["score"] - r[0]["score"] for _, r in rows if None not in (r[0]["score"], r[-1]["score"])]
    drifted = sum((r[-1]["changed"] + r[-1]["inserted"]) > 0 for _, r in rows)
    print(f"{writer:7s} {arm:8s} {len(rows):2d} {st.mean(s0):8.1f} {st.mean(sf):6.1f} {st.mean(gain):5.1f} "
          f"{drifted:4d}/{len(rows):<3d} {sum(r[-1]['changed'] for _, r in rows):7d} "
          f"{sum(r[-1]['inserted'] for _, r in rows):8d}")

print("\nSelection test (review arm): drift of the kept candidate minus the mean drift of the others, per round")
for writer in sorted({w for w, _ in traj}):
    diffs, score_drift = [], []
    for _, rows in traj.get((writer, "review"), []):
        for r in rows[1:]:
            if r["kept"] is None or not r.get("cand_changed"):
                continue
            d = [c + i for c, i in zip(r["cand_changed"], r["cand_inserted"])]
            others = [x for j, x in enumerate(d) if j != r["kept"]]
            diffs.append(d[r["kept"]] - st.mean(others))
            for x, s in zip(d, r["cand_scores"]):
                if s is not None:
                    score_drift.append((x, s))
    if diffs:
        pos = sum(x > 0 for x in diffs)
        neg = sum(x < 0 for x in diffs)
        print(f"  {writer}: {len(diffs)} rounds; kept has more drift in {pos}, less in {neg}, "
              f"mean difference {st.mean(diffs):+.2f}")
    if len(score_drift) > 3:
        xs, ys = zip(*score_drift)
        if st.pstdev(xs) > 0 and st.pstdev(ys) > 0:
            print(f"  {writer}: correlation of candidate drift with its score r = {st.correlation(xs, ys):+.2f} "
                  f"(n={len(xs)})")
