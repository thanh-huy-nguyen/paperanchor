"""Plugin entry point for the hooks. Thin wrapper around plumbline.gate that

- acts only in projects that opted in: the nearest directory with a paper/ folder must contain paper/sources.py
  (run `plumbline init` to create it), so the plugin never touches other projects;
- takes the mode from the plugin option (CLAUDE_PLUGIN_OPTION_MODE), unless PLUMBLINE_MODE is set explicitly;
- on SessionStart, snapshots the repository (recipes may read only files that existed unchanged at this point) and
  tells the agent the convention.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from plumbline import gate as g

RULES = """This project uses Plumbline: every number in paper/*.tex must recompute from the repository's raw data.
- Every number you add or change needs \\src{key} right after it (after \\% if present), e.g. 70.4\\%\\src{acc12},
  and a recipe in paper/sources.py:

      @source("acc12", means="one line: exactly what this computes")
      def acc12():
          d = load("eval_results/frames.json")   # path relative to the repository root
          xs = [v["correct"] for v in d.values() if v["num_frames"] == 12]
          return 100 * sum(xs) / len(xs)          # unrounded; the checker rounds

  `source` and `load(path)` are provided; do not import or define them. Do not round inside a recipe or type the
  printed number into it. Recipes must read raw results, configs or scripts, not Markdown notes, and only files that
  existed when this session started.
- Instead of typing a number you may write \\val[d]{key}; `plumbline fill` replaces it with the recipe's value.
- Check the whole paper with `plumbline check`; print recipe values with `plumbline run [key ...]`.
- If a recipe disagrees with the text, first make sure the recipe computes exactly what the sentence claims; if it
  does, change the number in the text, never the recipe."""


def opted_in(root: Path | None) -> bool:
    return root is not None and (root / "paper" / "sources.py").exists()


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pre"
    if g.env("MODE") is None:
        os.environ["PLUMBLINE_MODE"] = os.environ.get("CLAUDE_PLUGIN_OPTION_MODE") or "feedback"
    if g.env("MAX_STOP_BLOCKS") is None and os.environ.get("CLAUDE_PLUGIN_OPTION_MAX_STOP_BLOCKS"):
        os.environ["PLUMBLINE_MAX_STOP_BLOCKS"] = str(int(float(os.environ["CLAUDE_PLUGIN_OPTION_MAX_STOP_BLOCKS"])))
    try:
        ev = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    cwd = Path(ev.get("cwd") or os.getcwd())
    if cmd == "start":
        root = g.find_root(cwd)
        if not opted_in(root):
            return
        g.init(root)
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext":
                                                 RULES + f"\n(Check mode: {g.mode()}.)"}}))
        return
    tool = ev.get("tool_name", "")
    if cmd in ("pre", "post") and tool in ("Edit", "MultiEdit", "Write"):
        path = g.paper_target(ev.get("tool_input") or {}, cwd)
        root = path.parent.parent if path else None
    else:
        root = g.find_root(cwd)
    if not opted_in(root):
        return
    if g.env("ROOT") is None:
        os.environ["PLUMBLINE_ROOT"] = str(root)
    {"pre": g.pre, "post": g.post, "stop": g.stop}[cmd](ev)


if __name__ == "__main__":
    main()
