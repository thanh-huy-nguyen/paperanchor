"""List the new tagged numbers that do not pass the check at the end of each Exhibit 5 session, with the reason.

The summary rows only count them. This reruns the final check on every session that has any and writes
pilot/exh5/new_failing.json. Run from repo/: python3 bench/exh5_new_failing.py
"""
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.rlive import extract_paper_numbers, informative, src_key  # noqa: E402
from evw.sources import check  # noqa: E402

PILOT = Path(__file__).resolve().parents[2] / "pilot"


def printed_keys(tex: str) -> dict:
    nums = [n for n in extract_paper_numbers(tex) if informative(n)]
    out = {}
    for n in nums:
        k = src_key(tex, n, nums)
        if k:
            out.setdefault(k, n.text)
    return out


def main() -> None:
    out = []
    for line in open(PILOT / "exh5" / "summary.jsonl"):
        r = json.loads(line)
        if not r["new_tagged_failing"]:
            continue
        dst = PILOT / f"exh5_s{r['seed']}" / r["repo"] / r["arm"]
        root = dst / "repo"
        tex = (root / "paper" / "main.tex").read_text()
        printed, before = printed_keys(tex), printed_keys((dst / "clean.tex").read_text())
        final = {c.key: c for c in check("", tex, root, tagged_too=True) if c.key}
        for k in printed:
            if k not in before and k in final and not final[k].ok:
                out.append({"arm": r["arm"], "repo": r["repo"], "seed": r["seed"], "key": k, "printed": printed[k],
                            "reason": final[k].reason})
    (PILOT / "exh5" / "new_failing.json").write_text(json.dumps(out, indent=1))
    kinds = collections.Counter((o["arm"], re.sub(r"[-+]?\d[\d.,e-]*", "N", o["reason"])[:80]) for o in out)
    for k, v in sorted(kinds.items()):
        print(v, *k)


if __name__ == "__main__":
    main()
