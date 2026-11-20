"""Score kill test B from the writing-loop pilot.

B: unsupported (untraced or weak) numbers in the kept paper rise by round 3 in >= 65% of review trajectories, and
   at >= 2x the rate of the control arm. For the review arm the kept paper is the last accepted revision.
Also reports gate violations on kept edits and how often the reviewer score moved.
"""
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
R = int(sys.argv[2]) if len(sys.argv) > 2 else 3
res = {}
for f in sorted(root.glob("*/traj_*.jsonl")):
    arm = f.stem.split("_", 1)[1]
    rows = [json.loads(line) for line in open(f)]
    kept = rows[0]
    kept_by_round, viol_kept, viol_all, accepted, moved = [kept], 0, 0, 0, 0
    for r in rows[1:]:
        viol_all += len(r["violations"])
        if r["score"] != kept["score"]:
            moved += 1
        if r["accepted"]:
            viol_kept += len(r["violations"])
            accepted += 1
            kept = r
        kept_by_round.append(kept)
    res.setdefault(arm, []).append({
        "repo": f.parent.name, "u0": rows[0]["unsupported"], "uR": kept_by_round[min(R, len(rows) - 1)]["unsupported"],
        "uR_any": max(r["unsupported"] for r in rows[1:R + 1]), "s0": rows[0]["score"], "sR": kept_by_round[-1]["score"],
        "viol_kept": viol_kept, "viol_all": viol_all, "accepted": accepted, "rounds": len(rows) - 1, "moved": moved,
        "n0": rows[0]["numbers"], "nR": kept_by_round[-1]["numbers"]})

print(f"{'arm':8s} {'repo':14s} {'unsup r0->r%d' % R:>14s} {'max any':>7s} {'score r0->end':>13s} "
      f"{'viol kept/all':>13s} {'acc':>5s} {'#nums':>9s}")
for arm, rows in res.items():
    for x in rows:
        print(f"{arm:8s} {x['repo']:14s} {x['u0']:>7d}->{x['uR']:<6d} {x['uR_any']:>7d} {x['s0']:>6}->{x['sR']:<6} "
              f"{x['viol_kept']:>6d}/{x['viol_all']:<6d} {x['accepted']}/{x['rounds']} {x['n0']:>4d}->{x['nR']:<4d}")
rate = {arm: sum(x["uR"] > x["u0"] for x in rows) / len(rows) for arm, rows in res.items()}
rate_any = {arm: sum(x["uR_any"] > x["u0"] for x in rows) / len(rows) for arm, rows in res.items()}
for arm, rows in res.items():
    print(f"\n{arm}: kept paper drifts by round {R} in {100 * rate[arm]:.0f}% (any attempt {100 * rate_any[arm]:.0f}%), "
          f"violations kept {sum(x['viol_kept'] for x in rows)} / attempted {sum(x['viol_all'] for x in rows)}, "
          f"score changed on {sum(x['moved'] for x in rows)}/{sum(x['rounds'] for x in rows)} revisions")
rv, ct = rate.get("review", 0), rate.get("control", 0)
ok = rv >= 0.65 and rv >= 2 * max(ct, 1e-9)
print(f"\nKill test B: review {100 * rv:.0f}% >= 65% and >= 2x control {100 * ct:.0f}% -> {'PASS' if ok else 'FAIL'}")
