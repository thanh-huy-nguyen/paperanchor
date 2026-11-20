"""Claude Code hooks: numbers written into paper/*.tex must be recomputable from the repository's data.

Four entry points (the first argument of `python -m paperanchor.gate`, or called from paperanchor.hook):

    init <root>  snapshot the repository (files recipes may read) and the paper as approved; run before a session
    pre          PreToolUse on Edit|MultiEdit|Write|Bash
    post         PostToolUse on Edit|MultiEdit|Write|Bash
    stop         Stop

Modes (PAPERANCHOR_MODE):
    gate      (default) an edit to paper/*.tex that adds or changes a number without a working recipe is denied;
              a shell command that changes a .tex file is reverted; the session cannot stop while any tagged number
              fails (at most PAPERANCHOR_MAX_STOP_BLOCKS times, default 3)
    feedback  edits always go through; after each one the agent is told which numbers failed, never blocked
    log       nothing is shown to the agent; decisions are only logged

State lives outside the repository in PAPERANCHOR_STATE (default ~/.cache/paperanchor/<hash of the root>), so the agent
cannot edit it by accident. Every decision is appended to PAPERANCHOR_LOG if set.

Settings (pass with ``claude --settings``)::

    {"hooks": {
      "PreToolUse":  [{"matcher": "Edit|MultiEdit|Write|Bash", "hooks": [{"type": "command", "command": "python3 HOOK pre"}]}],
      "PostToolUse": [{"matcher": "Edit|MultiEdit|Write|Bash", "hooks": [{"type": "command", "command": "python3 HOOK post"}]}],
      "Stop":        [{"hooks": [{"type": "command", "command": "python3 HOOK stop"}]}]}}
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

from paperanchor.sources import check, deny_message, snapshot

_SHELL_WRITE = re.compile(r"(>|\btee\b|\bsed\s+-i|\bperl\s+-p?i|\bcp\b|\bmv\b|\bdd\b|python|\bawk\b|truncate|rm\b)")


# ---------------------------------------------------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------------------------------------------------


def env(name: str, default: str | None = None) -> str | None:
    """PAPERANCHOR_<NAME>; the EVW_<NAME> spelling of the experiment harness is accepted as a fallback."""
    return os.environ.get(f"PAPERANCHOR_{name}") or os.environ.get(f"EVW_{name}") or default


def state_dir(root: Path) -> Path:
    d = env("STATE")
    if d:
        return Path(d)
    h = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
    return Path.home() / ".cache" / "paperanchor" / h


def find_root(cwd: Path) -> Path | None:
    """PAPERANCHOR_ROOT if set, else the nearest directory at or above cwd that has a paper/ folder."""
    if env("ROOT"):
        return Path(env("ROOT"))
    for d in [cwd, *cwd.parents]:
        if (d / "paper").is_dir():
            return d
    return None


def papers(root: Path) -> list[Path]:
    return sorted((root / "paper").glob("*.tex"))


def init(root: Path) -> Path:
    root = root.resolve()
    st = state_dir(root)
    (st / "approved").mkdir(parents=True, exist_ok=True)
    (st / "original").mkdir(parents=True, exist_ok=True)
    (st / "baseline.json").write_text(json.dumps(snapshot(root)))
    for p in papers(root):
        (st / "approved" / p.name).write_text(p.read_text())
        (st / "original" / p.name).write_text(p.read_text())
    (st / "stop_blocks").write_text("0")
    return st


def load_state(root: Path) -> tuple[Path, dict]:
    st = state_dir(root)
    if not (st / "baseline.json").exists():
        init(root)  # late start: snapshot now (weaker, since files written earlier in the session count as original)
    return st, json.loads((st / "baseline.json").read_text())


def approved(st: Path, p: Path) -> str:
    f = st / "approved" / p.name
    return f.read_text() if f.exists() else ""


def set_approved(st: Path, p: Path, text: str) -> None:
    (st / "approved" / p.name).write_text(text)


# ---------------------------------------------------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------------------------------------------------


def log(entry: dict) -> None:
    path = env("LOG") or env("GATE_LOG")
    if path:
        with open(path, "a") as f:
            f.write(json.dumps({"t": time.time(), "mode": mode(), **entry}) + "\n")


def mode() -> str:
    return env("MODE", "gate")


def deny_pre(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))


def tell(reason: str) -> None:
    """PostToolUse and Stop: 'block' feeds the reason back to the agent (the tool call itself already ran)."""
    print(json.dumps({"decision": "block", "reason": reason}))


# ---------------------------------------------------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------------------------------------------------


def apply_edit(tool: str, inp: dict, old: str) -> str | None:
    if tool == "Write":
        return inp.get("content", "")
    edits = inp.get("edits") if tool == "MultiEdit" else [inp]
    new = old
    for e in edits or []:
        a, b = e.get("old_string", ""), e.get("new_string", "")
        if a not in new:
            return None  # the tool itself will reject this edit
        new = new.replace(a, b) if e.get("replace_all") else new.replace(a, b, 1)
    return new


def paper_target(inp: dict, cwd: Path) -> Path | None:
    path = Path(inp.get("file_path", ""))
    if not path.is_absolute():
        path = cwd / path
    return path if path.suffix == ".tex" and path.parent.name == "paper" else None


def pre(ev: dict) -> None:
    tool, inp = ev.get("tool_name", ""), ev.get("tool_input", {}) or {}
    cwd = Path(ev.get("cwd") or os.getcwd())
    if mode() != "gate":
        return
    if tool == "Bash":
        cmd = inp.get("command", "")
        if re.search(r"\.tex\b", cmd) and _SHELL_WRITE.search(cmd):
            reason = "Shell commands may not write .tex files. Edit the paper with the Edit or Write tool."
            log({"event": "pre", "tool": tool, "decision": "deny", "reason": reason, "command": cmd[:300]})
            deny_pre(reason)
        return
    path = paper_target(inp, cwd)
    if tool not in ("Edit", "MultiEdit", "Write") or path is None:
        return
    root = path.parent.parent
    st, base = load_state(root)
    old = path.read_text() if path.exists() else ""
    new = apply_edit(tool, inp, old)
    if new is None:
        return
    checks = check(old, new, root, baseline=base)
    bad = [c for c in checks if not c.ok]
    log({"event": "pre", "tool": tool, "file": str(path), "decision": "deny" if bad else "allow",
         "checks": [c.to_json() for c in checks]})
    if bad:
        deny_pre(deny_message(checks))


def full_report(root: Path, st: Path, base: dict) -> tuple[list, list]:
    """Every tagged number and every number added or changed since the session started, across the paper's files."""
    allchecks = []
    for p in papers(root):
        orig = st / "original" / p.name
        allchecks += check(orig.read_text() if orig.exists() else "", p.read_text(), root, tagged_too=True,
                           baseline=base)
    return allchecks, [c for c in allchecks if not c.ok]


def post(ev: dict) -> None:
    tool, inp = ev.get("tool_name", ""), ev.get("tool_input", {}) or {}
    cwd = Path(ev.get("cwd") or os.getcwd())
    if tool in ("Edit", "MultiEdit", "Write"):
        path = paper_target(inp, cwd)
        if path is None or not path.exists():
            return
        root = path.parent.parent
        st, base = load_state(root)
        set_approved(st, path, path.read_text())
        if mode() == "feedback":
            feedback(root, st, base, tool)
        return
    if tool == "Bash":
        root = find_root(cwd)
        if root is None:
            return
        st, base = load_state(root)
        changed = [p for p in papers(root) if p.read_text() != approved(st, p)]
        if not changed:
            return
        if mode() == "gate":
            for p in changed:
                p.write_text(approved(st, p))
            reason = ("Your shell command changed " + ", ".join(p.name for p in changed) + "; the change was reverted. "
                      "Edit the paper only with the Edit or Write tool.")
            log({"event": "post", "tool": tool, "decision": "revert", "files": [str(p) for p in changed],
                 "command": inp.get("command", "")[:300]})
            tell(reason)
            return
        for p in changed:
            set_approved(st, p, p.read_text())
        log({"event": "post", "tool": tool, "decision": "shell-edit", "files": [str(p) for p in changed]})
        if mode() == "feedback":
            feedback(root, st, base, tool)


def feedback(root: Path, st: Path, base: dict, tool: str) -> None:
    """Non-blocking: after any change to the paper, report every number that fails (the same list the gate's Stop
    check would give), and keep the edit."""
    allchecks, bad = full_report(root, st, base)
    log({"event": "post", "tool": tool, "decision": "feedback" if bad else "ok",
         "checks": [c.to_json() for c in allchecks]})
    if bad:
        tell("Feedback only, your edit was kept. " + deny_message(allchecks))


def stop(ev: dict) -> None:
    cwd = Path(ev.get("cwd") or os.getcwd())
    root = find_root(cwd)
    if root is None:
        return
    st, base = load_state(root)
    allchecks, allbad = full_report(root, st, base)
    n = int((st / "stop_blocks").read_text() or 0) if (st / "stop_blocks").exists() else 0
    block = bool(allbad) and mode() == "gate" and n < int(env("MAX_STOP_BLOCKS", "3"))
    log({"event": "stop", "decision": "block" if block else ("fail" if allbad else "ok"), "stop_blocks": n,
         "checks": [c.to_json() for c in allchecks]})
    if block:
        (st / "stop_blocks").write_text(str(n + 1))
        tell("Before you finish: " + deny_message(allchecks))


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pre"
    if cmd == "init":
        print(init(Path(sys.argv[2])))
        return
    ev = json.load(sys.stdin)
    {"pre": pre, "post": post, "stop": stop}[cmd](ev)


if __name__ == "__main__":
    main()
