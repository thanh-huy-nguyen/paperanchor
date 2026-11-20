"""plumbline: recompute every tagged number of a paper from the repository's data.

    plumbline init            create paper/sources.py (opts this project in) and snapshot the repository
    plumbline check [FILE]    check every tagged number and \\val in paper/*.tex (or FILE); exit 1 if any fails
    plumbline run [KEY ...]   print what each recipe returns (no pass/fail)
    plumbline fill IN OUT     write IN with every \\val[d]{key} replaced by its recipe's value
    plumbline git-hook        install a git pre-commit hook that runs `plumbline check` on staged paper/*.tex

Run from the repository root (the directory that contains paper/).
"""
import json
import os
import shutil
import stat
import sys
from pathlib import Path

from plumbline import gate
from plumbline.sources import check, fill, parse_sources, run_recipes

WRAPPER = Path(__file__).resolve().parents[1] / "bin" / "plumbline"   # present when run from the plugin folder

SKELETON = '''"""Recipes for the numbers in this paper. Each returns the unrounded value printed next to \\\\src{key}.

`source` and `load(path)` are provided by the checker; do not import or define them. Paths are relative to the
repository root. Read raw results, configs or scripts, never Markdown notes.
"""

# @source("example_key", means="what this number is, in one line")
# def example_key():
#     d = load("results/metrics.json")
#     return 100 * d["test"]["accuracy"]
'''

PREAMBLE = "\\providecommand{\\src}[1]{}\n\\providecommand{\\val}[2][1]{}"


def root() -> Path:
    r = Path.cwd()
    for d in [r, *r.parents]:
        if (d / "paper").is_dir():
            return d
    sys.exit("plumbline: no paper/ folder here or above; run from the repository root")


def cmd_init() -> None:
    r = Path.cwd()
    (r / "paper").mkdir(exist_ok=True)
    s = r / "paper" / "sources.py"
    if not s.exists():
        s.write_text(SKELETON)
        print(f"created {s}")
    st = gate.init(r)
    print(f"snapshot of the repository saved in {st}")
    print("Add to the preamble of your paper if missing:\n" + PREAMBLE)


def cmd_check(args: list[str]) -> None:
    r = root()
    files = [Path(a) for a in args] or sorted((r / "paper").glob("*.tex"))
    bad = 0
    for f in files:
        checks = [c for c in check("", f.read_text(), r, tagged_too=True) if c.key is not None]
        for c in checks:
            if not c.ok:
                bad += 1
                print(f"FAIL {f.name}:{c.number.line} {c.number.text} [{c.key}] {c.reason}")
        print(f"{f.name}: {sum(c.ok for c in checks)}/{len(checks)} tagged numbers recompute")
    sys.exit(1 if bad else 0)


def cmd_run(keys: list[str]) -> None:
    r = root()
    recipes, err = parse_sources(r / "paper" / "sources.py")
    if err:
        sys.exit(err)
    keys = keys or sorted(recipes)
    res = run_recipes(r, r / "paper" / "sources.py", {k: recipes[k].func for k in keys if k in recipes})
    for k in keys:
        x = res.get(k) or res.get("__module__") or {"error": "no recipe named " + repr(k)}
        print(k, "->", x.get("value", x.get("error")), x.get("files", ""))


def cmd_fill(a: list[str]) -> None:
    if len(a) != 2:
        sys.exit("usage: plumbline fill IN.tex OUT.tex")
    Path(a[1]).write_text(fill(Path(a[0]).read_text(), root()))
    print(f"wrote {a[1]}")


def cmd_git_hook() -> None:
    r = root()
    git = r / ".git"
    if not git.is_dir():
        sys.exit("plumbline: not a git repository root")
    h = git / "hooks" / "pre-commit"
    run = f"{sys.executable} {WRAPPER}" if WRAPPER.exists() else f"{sys.executable} -m plumbline.cli"
    if h.exists():
        sys.exit(f"plumbline: {h} exists; add `{run} check` to it yourself")
    h.write_text(f"#!/bin/sh\nif git diff --cached --name-only | grep -qE '(^|/)paper/[^/]+\\.tex$'; then\n"
                 f"  {run} check || {{ echo 'plumbline: fix the numbers or their "
                 f"recipes before committing' >&2; exit 1; }}\nfi\n")
    h.chmod(h.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"installed {h}")


def main() -> None:
    a = sys.argv[1:]
    if not a or a[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    {"init": lambda: cmd_init(), "check": lambda: cmd_check(a[1:]), "run": lambda: cmd_run(a[1:]),
     "fill": lambda: cmd_fill(a[1:]), "git-hook": lambda: cmd_git_hook()}.get(
        a[0], lambda: sys.exit(f"unknown command {a[0]!r}; see plumbline --help"))()


if __name__ == "__main__":
    main()
