#!/usr/bin/env python3
"""Run recipes from paper/sources.py and print the values they return (no pass/fail). Usage: run_recipe.py [key ...]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evw.sources import parse_sources, run_recipes  # noqa: E402

root = Path(".").resolve()
recipes, err = parse_sources(root / "paper" / "sources.py")
if err:
    sys.exit(err)
keys = sys.argv[1:] or sorted(recipes)
res = run_recipes(root, root / "paper" / "sources.py", {k: recipes[k].func for k in keys if k in recipes})
for k in keys:
    r = res.get(k) or res.get("__module__") or {"error": "no recipe named " + repr(k)}
    print(k, "->", r.get("value", r.get("error")), r.get("files", ""))
