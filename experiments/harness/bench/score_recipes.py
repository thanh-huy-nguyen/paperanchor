"""Score the recompute check against the blind audit of the gate's flags.

Usage: python3 bench/score_recipes.py ../pilot/repos ../pilot/audit_pressure
Prints, per writer/arm and overall: numbers checked, recomputed, and for audited numbers the pass rate on correct
ones and the catch rate on wrong or unsupported ones. Writes unaudited failures to <audit dir>/recipe_failures.json.
"""

from __future__ import annotations

import collections
import difflib
import json
import sys
from pathlib import Path


def load_audit(audit_dir: Path) -> dict:
    key = json.loads((audit_dir / "audit_key.json").read_text())
    items = {}
    for f in audit_dir.glob("2609*.json"):
        if f.name.endswith("_audit.json"):
            continue
        for it in json.loads(f.read_text()):
            items[it["id"]] = it
    labels = {}
    for f in audit_dir.glob("*_audit.json"):
        for r in json.loads(f.read_text()):
            labels[r["id"]] = r
    out = collections.defaultdict(list)  # (repo, writer, arm) -> [(number, context, label, id)]
    for i, it in items.items():
        w, arm = key[i][6:-7].split("_")[:2]
        out[(i.split("#")[0], w, arm)].append((it["number"], it["context"], labels[i]["label"], i))
    return out


def match(audited: list, c: dict):
    best, score = None, 0.0
    for num, ctx, lab, i in audited:
        if num != c["number"]:
            continue
        s = difflib.SequenceMatcher(None, ctx[:160], c["context"][:160]).ratio()
        if s > score:
            best, score = (lab, i), s
    return best if score >= 0.6 else None


def main() -> None:
    root, audit_dir = Path(sys.argv[1]), Path(sys.argv[2])
    audit = load_audit(audit_dir)
    tab = collections.defaultdict(collections.Counter)
    fails, used = [], set()
    for f in sorted(root.glob("*/recipe_*_*.json")):
        repo = f.parent.name
        w, arm = f.stem.split("_")[1:3]
        d = json.loads(f.read_text())
        t = tab[(w, arm)]
        t["tagger_changed_text"] += len(d["numbers_changed_by_tagger"])
        for c in d["checks"]:
            t["numbers"] += 1
            t["recomputed"] += c["ok"]
            m = match([a for a in audit.get((repo, w, arm), []) if a[3] not in used], c)
            if m:
                used.add(m[1])
                lab = m[0]
                t[f"audit_{lab}"] += 1
                t[f"audit_{lab}_pass"] += c["ok"]
            elif not c["ok"]:
                fails.append({"repo": repo, "writer": w, "arm": arm, **c})
    tot = collections.Counter()
    for k in sorted(tab):
        tot.update(tab[k])
    for k, t in sorted(tab.items()) + [(("all", ""), tot)]:
        def rate(a, b):
            return f"{t[a]}/{t[b]}" if t[b] else "-"
        wrong = t["audit_wrong"] + t["audit_unsupported"]
        caught = wrong - t["audit_wrong_pass"] - t["audit_unsupported_pass"]
        print(f"{k[0]:6s} {k[1]:8s} numbers {t['numbers']:4d}  recomputed {t['recomputed']:4d}  "
              f"audited-correct passed {rate('audit_correct_pass', 'audit_correct'):>7s}  "
              f"audited-wrong caught {caught}/{wrong}  tagger changed text {t['tagger_changed_text']}")
    (audit_dir / "recipe_failures.json").write_text(json.dumps(fails, indent=1))
    print("unaudited failures:", len(fails), "->", audit_dir / "recipe_failures.json")


if __name__ == "__main__":
    main()
