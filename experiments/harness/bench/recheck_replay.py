"""Re-run the recompute check on the saved replay drafts (no model calls) after a checker fix.

Writes repos/<id>/recipe_{w}_{arm}.v2.json with the same layout as the original and prints how many verdicts changed.
Usage: python3 bench/recheck_replay.py ../pilot/repos
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evw.sources import check  # noqa: E402


def one(f: str) -> str:
    f = Path(f)
    d = f.parent
    work = d / f.stem
    old = json.loads(f.read_text())
    draft = (d / "work" / "paper" / "main.tex").read_text()
    tagged = (work / "paper" / "main.tex").read_text()
    checks = [c.to_json() for c in check(draft, tagged, work)]
    (d / (f.stem + ".v2.json")).write_text(json.dumps({**old, "checks": checks}, indent=1))
    a = {(c["line"], c["number"], c["context"]): c["ok"] for c in old["checks"]}
    b = {(c["line"], c["number"], c["context"]): c["ok"] for c in checks}
    flips = sum(1 for k in a if k in b and a[k] != b[k])
    return f"{d.name} {f.stem}: {len(a)} -> {len(b)} checks, passes {sum(a.values())} -> {sum(b.values())}, flipped {flips}"


if __name__ == "__main__":
    files = sorted(str(f) for f in Path(sys.argv[1]).glob("*/recipe_*_*.json") if not f.name.endswith(".v2.json"))
    with ProcessPoolExecutor(6) as ex:
        for line in ex.map(one, files):
            print(line, flush=True)
