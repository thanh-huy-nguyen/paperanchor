"""False alarms of the number gate on harmless rewrites.

For each pilot paper, up to K paragraphs that contain traced numbers are rewritten by Haiku with an instruction to
keep every fact and number. The gate then judges old vs new. A block counts as a false alarm only if the multiset of
numbers in the paragraph is unchanged; if the rewrite changed a number, the block is correct and is counted apart.
"""
import json
import random
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evw.claude_cli import ask, ledger_summary  # noqa: E402
from evw.numtrace import EvidenceMatcher, build_evidence_index, extract_paper_numbers, gate, trace  # noqa: E402

SYSTEM = ("You edit LaTeX paragraphs from research papers. Rewrite the paragraph to read more clearly: you may reorder "
          "clauses, split or merge sentences, and change wording. Keep every fact, every number exactly as written, "
          "every \\cite and \\ref command, and the LaTeX markup valid. Output only the rewritten paragraph.")

root = Path(sys.argv[1])
K = int(sys.argv[2]) if len(sys.argv) > 2 else 4
rng = random.Random(1)
jobs = []
for line in open(root / "manifest.jsonl"):
    m = json.loads(line)
    d = root / m["id"]
    prose = (d / "prose.tex").read_text()
    matcher = EvidenceMatcher(build_evidence_index(d / "results"))
    traced_lines = {n.line for n in trace(prose, matcher).numbers if n.status in ("traced", "derived")}
    paras, cur, start = [], [], 1
    for i, ln in enumerate(prose.splitlines(), 1):
        if ln.strip():
            if not cur:
                start = i
            cur.append(ln)
        elif cur:
            paras.append((start, i - 1, "\n".join(cur)))
            cur = []
    cands = [p for p in paras if any(p[0] <= t <= p[1] for t in traced_lines) and 200 < len(p[2]) < 3000]
    rng.shuffle(cands)
    for p in cands[:K]:
        jobs.append((m["id"], prose, matcher, p))


def run(job):
    pid, prose, matcher, (a, b, para) = job
    new_para = ask(para, system=SYSTEM, model="haiku", tag="pilot/false_alarm").strip()
    new_para = re.sub(r"^```(?:latex)?\n|\n```$", "", new_para)
    lines = prose.splitlines()
    new_prose = "\n".join(lines[: a - 1] + new_para.splitlines() + lines[b:])
    dec = gate(prose, new_prose, matcher)
    nums_old = Counter(n.text for n in extract_paper_numbers(para))
    nums_new = Counter(n.text for n in extract_paper_numbers(new_para))
    return {"paper": pid, "lines": [a, b], "allow": dec.allow, "numbers_changed": nums_old != nums_new,
            "violations": [(k, n.text, n.context) for k, n, _ in dec.violations], "old": para, "new": new_para}


with ThreadPoolExecutor(4) as ex:
    results = list(ex.map(run, jobs))
out = root.parent / "false_alarms.jsonl"
with out.open("w") as f:
    for r in results:
        f.write(json.dumps(r) + "\n")
same = [r for r in results if not r["numbers_changed"]]
fa = [r for r in same if not r["allow"]]
chg = [r for r in results if r["numbers_changed"]]
print(f"rewrites {len(results)}; numbers unchanged {len(same)}, of which blocked (false alarms) {len(fa)} "
      f"({100 * len(fa) / max(len(same), 1):.1f}%)")
print(f"rewrites that changed a number {len(chg)}, of which blocked {sum(not r['allow'] for r in chg)}")
print("usage:", ledger_summary("pilot/false_alarm"))
