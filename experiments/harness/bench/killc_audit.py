"""Kill test C: is the recompute check more than asking Claude Code to audit the paper?

Baseline (FabScore-style): a Claude Code agent with read and shell tools gets one finished draft and its repo, and is
asked to check every number in the paper against the raw data and report the wrong or unsupported ones. It is not
told which numbers were sampled. Its flags are matched to the random-300 audit sample (pilot/audit_random) by printed
value and line, and scored against the two-model blind labels exactly as the recompute check and the lookup gate were.

The audit gets the same evidence rule as the ground-truth auditors (raw result files only; Markdown notes are not
evidence). The ground-truth auditors were Sonnet and Opus, so a Sonnet or Opus baseline shares their readings; this
favors the baseline.

Usage:
    python3 bench/killc_audit.py run --model sonnet --workers 8
    python3 bench/killc_audit.py run --model opus --sens --workers 6
    python3 bench/killc_audit.py score
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.writing_loop import run_writer  # noqa: E402

PILOT = Path(__file__).resolve().parents[2] / "pilot"
AR = PILOT / "audit_random"
OUT = PILOT / "killc"

PROMPT = """You are auditing a research-paper draft against the code repository it was written from. The draft is
paper/main.tex in the current directory; the repository's raw data (result JSON/CSV/logs, configs, scripts that set
values) is elsewhere in this directory. Work read-only on everything except your output file.

Check every number in the draft that states a result or a fact about the data or experiments. For each, work out what
quantity the sentence claims and compute it yourself from the raw data with python3. Markdown, text notes, READMEs,
registries and proposed tables in the repository are NOT evidence: they can be stale. Do not rely on the paper's own
other sentences either. Constants, settings, confidence levels, citations, years and section numbers are not claims.

Write audit_flags.json in the current directory: a JSON list with one entry per number you find wrong or unsupported,
{"line": <line in paper/main.tex>, "number": <as printed>, "verdict": "wrong" | "unsupported",
 "data_value": <your value or null>, "note": <one short sentence>}.
A number is wrong if the data gives a different value at the printed precision (standard rounding), or it is the
wrong unit or quantity. It is unsupported if no raw data, config or script can back it. Leave correct numbers out.
Also write audit_checked.txt with the total count of numbers you checked. Reply with only the number of flags."""

# Sensitive variant: every checked number gets a probability of being wrong, so the audit can be thresholded at the
# recompute check's alarm rate (kill test C asks for recall at a matched alarm rate).
PROMPT_SENS = PROMPT.split("Write audit_flags.json")[0] + """Write audit_all.json in the current directory: a JSON list with one entry for EVERY number you checked, correct
ones included, {"line": <line in paper/main.tex>, "number": <as printed>, "verdict": "correct" | "wrong" |
"unsupported", "p_wrong": <0-100, your probability that the number is wrong or unsupported>, "data_value": <your
value or null>, "note": <one short sentence>}. Use the whole 0-100 range: give low but nonzero values when you could
only partly reproduce a number. A number is wrong if the data gives a different value at the printed precision
(standard rounding), or it is the wrong unit or quantity. It is unsupported if no raw data, config or script can back
it. Reply with only the number of entries."""


def norm(s: str) -> float | None:
    s = re.sub(r"[\\$,{}%~\s]|\\,", "", str(s)).replace("−", "-").lstrip("+")
    s = re.sub(r"[KMB]$", "", s, flags=re.I)
    try:
        return float(s)
    except ValueError:
        return None


def run_one(pid: str, model: str, sens: bool = False) -> dict:
    d = OUT / (model + ("_sens" if sens else "")) / pid
    work = d / "work"
    if (d / "result.json").exists():
        return json.loads((d / "result.json").read_text())
    if work.exists():
        shutil.rmtree(work)
    d.mkdir(parents=True, exist_ok=True)
    shutil.copytree(AR / "dirs" / pid, work, symlinks=True)
    r = run_writer(work, PROMPT_SENS if sens else PROMPT, model, tag=f"killc/{d.parent.name}/{pid}", timeout=3600,
                   tools="Read,Glob,Grep,Bash")
    flags_p = work / ("audit_all.json" if sens else "audit_flags.json")
    try:
        flags = json.loads(flags_p.read_text())
    except Exception as e:  # noqa: BLE001
        flags = None
        print(pid, model, "no flags file:", e, str(r.get("result"))[:200], flush=True)
    checked = (work / "audit_checked.txt").read_text().strip() if (work / "audit_checked.txt").exists() else None
    out = {"pid": pid, "model": model, "flags": flags, "checked": checked, "is_error": r.get("is_error"),
           "num_turns": r.get("num_turns"), "cost_usd_list": r.get("total_cost_usd")}
    (d / "result.json").write_text(json.dumps(out, indent=1))
    shutil.rmtree(work)  # the copy is 10s of MB to GB; flags are saved
    print(pid, model, "flags", None if flags is None else len(flags), "cost", out["cost_usd_list"], flush=True)
    return out


def flagged(item: dict, flags: list[dict], tol: int = 3) -> bool:
    v = norm(item["number"])
    for f in flags or []:
        try:
            line = int(f.get("line"))
        except (TypeError, ValueError):
            continue
        if abs(line - item["line"]) <= tol and v is not None and norm(f.get("number")) is not None \
                and abs(norm(f.get("number")) - v) < 1e-9 * max(1, abs(v)):
            return True
    return False


def p_wrong(item: dict, entries: list[dict], tol: int = 3) -> float:
    """Highest p_wrong among the audit's entries for this printed value near this line; -1 if never listed."""
    v, best = norm(item["number"]), -1.0
    for f in entries or []:
        try:
            line = int(f.get("line"))
        except (TypeError, ValueError):
            continue
        fv = norm(f.get("number"))
        if abs(line - item["line"]) <= tol and v is not None and fv is not None and abs(fv - v) < 1e-9 * max(1, abs(v)):
            try:
                best = max(best, float(f.get("p_wrong")))
            except (TypeError, ValueError):
                best = max(best, 100.0 if f.get("verdict") in ("wrong", "unsupported") else 0.0)
    return best


def score(models: list[str]) -> None:
    labels = json.loads((AR / "final_labels.json").read_text())
    key = json.loads((AR / "key.json").read_text())
    items = {it["id"]: it for g in range(4) for it in json.loads((AR / f"group{g}.json").read_text())}
    pid_of = {it["id"]: Path(it["dir"]).name for it in items.values()}
    def v2(s):  # current checker (after the src_key and recipe-source fixes), as in notes/07
        k = key[s]
        f = PILOT / "repos" / k["repo"] / f"recipe_{k['writer']}_{k['arm']}.v2.json"
        return not json.loads(f.read_text())["checks"][k["idx"]]["ok"]
    checkers = {"recompute": {s: v2(s) for s in key}}
    for m in models:
        res = {}
        for p in (OUT / m).glob("p*/result.json"):
            r = json.loads(p.read_text())
            res[r["pid"]] = r["flags"]
        missing = sorted({pid_of[s] for s in items} - set(res))
        if missing:
            print(f"{m}: missing {missing}")
        if m.endswith("_sens"):
            pw = {s: p_wrong(items[s], res.get(pid_of[s])) for s in items if pid_of[s] in res}
            n_ok = sum(labels[s] == "ok" for s in pw)
            target = sum(checkers["recompute"][s] for s in pw if labels[s] == "ok")  # recompute's alarms here
            # the lowest threshold whose alarms on correct numbers do not exceed recompute's
            thr = min((t for t in range(0, 102) if sum(pw[s] >= t for s in pw if labels[s] == "ok") <= target))
            print(f"{m}: threshold p_wrong >= {thr} (recompute flags {target}/{n_ok} correct numbers); "
                  f"listed {sum(pw[s] > -1 for s in pw)}/{len(pw)} sampled numbers")
            checkers[f"audit_{m}@{thr}"] = {s: pw[s] >= thr for s in pw}
            checkers[f"audit_{m}@50"] = {s: pw[s] >= 50 for s in pw}
        else:
            checkers[f"audit_{m}"] = {s: flagged(items[s], res.get(pid_of[s])) for s in items if pid_of[s] in res}
    rows = []
    for name, fl in checkers.items():
        c = {lab: [0, 0] for lab in ("err", "disputed", "ok")}
        for s, f in fl.items():
            if labels[s] in c:
                c[labels[s]][0] += f
                c[labels[s]][1] += 1
        rows.append((name, c))
        print(f"{name:16s} errors {c['err'][0]}/{c['err'][1]}  disputed {c['disputed'][0]}/{c['disputed'][1]}  "
              f"correct flagged {c['ok'][0]}/{c['ok'][1]}")
    # paired comparison on agreed errors, recompute vs each audit
    errs = [s for s in labels if labels[s] == "err"]
    for name in checkers:
        if name == "recompute":
            continue
        both = [s for s in errs if s in checkers[name]]
        only_r = sum(checkers["recompute"][s] and not checkers[name][s] for s in both)
        only_a = sum(checkers[name][s] and not checkers["recompute"][s] for s in both)
        print(f"recompute vs {name}: discordant errors recompute-only {only_r}, audit-only {only_a}")
    OUT.mkdir(exist_ok=True)
    (OUT / "score.json").write_text(json.dumps({n: c for n, c in rows}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "score"])
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--models", default="sonnet,opus,sonnet_sens,opus_sens")
    ap.add_argument("--pids", default="")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--sens", action="store_true", help="every number with p_wrong (matched-alarm variant)")
    a = ap.parse_args()
    if a.cmd == "run":
        pids = a.pids.split(",") if a.pids else sorted(p.name for p in (AR / "dirs").iterdir())
        with ThreadPoolExecutor(a.workers) as ex:
            list(ex.map(lambda p: run_one(p, a.model, a.sens), pids))
    else:
        score([m for m in a.models.split(",") if (OUT / m).exists()])


if __name__ == "__main__":
    main()
