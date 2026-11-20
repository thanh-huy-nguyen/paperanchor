"""Score the human check (pilot/human_check/returned) against the two-model labels and the recompute check.

Human 'flag' = wrong or unsupported. Model groups: err (both auditors: wrong/unsupported), disputed, ok.
Usage: python3 bench/human_score.py
"""
import csv, json
from collections import Counter
from pathlib import Path

PILOT = Path(__file__).resolve().parents[2] / "pilot"
HC, AR = PILOT / "human_check", PILOT / "audit_random"
key = json.loads((HC / "key_hidden.json").read_text())
labels = json.loads((AR / "final_labels.json").read_text())
akey = json.loads((AR / "key.json").read_text())

def recompute_flag(s):
    k = akey[s]
    f = PILOT / "repos" / k["repo"] / f"recipe_{k['writer']}_{k['arm']}.v2.json"
    return not json.loads(f.read_text())["checks"][k["idx"]]["ok"]

def load(name):
    return {r["item"]: r for r in csv.DictReader(open(HC / "returned" / name, encoding="utf-8-sig"))}

A, B = load("checker_A.csv"), load("checker_B.csv")
FLAG = {"wrong", "unsupported"}
def grp(h):
    s = key[h]; lab = labels[s]; rc = recompute_flag(s)
    if lab == "ok":
        return "ok_flagged_by_recompute" if rc else "ok_passed_by_recompute"
    return lab
out = {"rows": []}
for h in sorted(A):
    s = key[h]
    out["rows"].append({"h": h, "s": s, "group": grp(h), "model_label": labels[s], "recompute_flag": recompute_flag(s),
                        "A": A[h]["your_label"].strip(), "B": B[h]["your_label"].strip() if h in B else None,
                        "A_value": A[h]["your_value"], "number": A[h]["number"], "A_note": A[h]["note"],
                        "B_note": B[h]["note"] if h in B else None})
rows = out["rows"]
print("A labels by group")
for g in ["err", "disputed", "ok_flagged_by_recompute", "ok_passed_by_recompute"]:
    rs = [r for r in rows if r["group"] == g]
    print(f"  {g:26s} n={len(rs):3d}  A flags {sum(r['A'] in FLAG for r in rs):3d}  ", dict(Counter(r["A"] for r in rs)))
# A as ground truth: recompute and model audit
def conf(pred):
    tp = sum(pred(r) and r["A"] in FLAG for r in rows); fp = sum(pred(r) and r["A"] not in FLAG for r in rows)
    fn = sum(not pred(r) and r["A"] in FLAG for r in rows); return tp, fp, fn
print("vs A (A flag = truth): recompute tp/fp/fn", conf(lambda r: r["recompute_flag"]),
      " two-model 'err' tp/fp/fn", conf(lambda r: r["model_label"] == "err"))
# A vs B
both = [r for r in rows if r["B"]]
agree = sum((r["A"] in FLAG) == (r["B"] in FLAG) for r in both)
pa = sum(r["A"] in FLAG for r in both) / len(both); pb = sum(r["B"] in FLAG for r in both) / len(both)
po = agree / len(both); pe = pa * pb + (1 - pa) * (1 - pb)
print(f"A vs B on {len(both)}: flag agreement {agree}/{len(both)}, kappa {(po - pe) / (1 - pe):.2f}; exact label agreement "
      f"{sum(r['A'] == r['B'] for r in both)}/{len(both)}")
for r in both:
    if (r["A"] in FLAG) != (r["B"] in FLAG):
        print("  disagree", r["h"], r["group"], r["number"], "A:", r["A"], "B:", r["B"])
(HC / "scored.json").write_text(json.dumps(out, indent=1))
