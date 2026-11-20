"""Recompute check: every number a writer adds or changes must name a recipe that recomputes it from the raw data.

The writer tags the number in LaTeX with a no-op macro and defines the recipe in ``paper/sources.py``::

    % preamble
    \\providecommand{\\src}[1]{}
    % text
    ... 12 frames reach 70.4\\%\\src{acc12_doubao} ...

    # paper/sources.py  (``source`` and ``load`` are provided by the checker; no imports needed for them)
    @source("acc12_doubao", means="Doubao-Seed-1.6 accuracy (%) with 12 frames")
    def acc12_doubao():
        d = load("eval_results/frames_doubao-seed-1-6.json")
        xs = [v["correct"] for v in d.values() if v["num_frames"] == 12]
        return 100 * sum(xs) / len(xs)

The checker runs each recipe in a subprocess with the repository root as working directory and accepts the number
only if (1) the recipe returns a number that rounds to the printed value at the printed precision (the checker does
the rounding, so truncation and rounding slips are caught), (2) the recipe opened at least one file of the
repository outside ``paper/``, and (3) the recipe neither hard-codes the printed value nor rounds by itself.

A recipe can still compute the wrong quantity (the right number for a different claim). ``means`` records what the
writer says it computes, so that a reader or a second model can check the claim against it; this module does not.

Two further rules close the obvious bypasses. A recipe may not read prose notes (Markdown and similar), which can be
stale, and, when a baseline snapshot of the repository is given, it may read only files that existed unchanged when
the snapshot was taken (so an agent cannot write a data file and then cite it).

Generate mode: instead of typing a number the writer may write ``\\val[d]{key}`` (``\\providecommand{\\val}[2][1]{}``
in the preamble); ``fill`` replaces it with the recipe's value rounded to ``d`` decimals, so the printed number
cannot drift from its recipe. The check only requires that the recipe runs, reads data, and does not round itself.
"""

from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from plumbline.numtrace import PaperNumber, _token_stream, extract_paper_numbers, strip_latex

MIN_INFORMATIVE = 10.0  # same rule as TraceConfig.min_informative: small bare integers are not checked
_BANNED_CALLS = {"round", "floor", "ceil", "trunc", "around", "fix", "rint", "Decimal", "quantize", "format"}
_SCALE_SUFFIX = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}
NOTE_SUFFIXES = {".md", ".markdown", ".rst", ".tex", ".org", ".adoc"}
_VAL = re.compile(r"\\val(?:\[(\d+)\])?\{([^{}]*)\}")
_SKIP_DIRS = {".git", "__pycache__", ".ipynb_checkpoints", "paper"}


def informative(n: PaperNumber) -> bool:
    return n.decimals != 0 or n.is_percent or abs(n.value) >= MIN_INFORMATIVE


# ----------------------------------------------------------------------------------------------------------------------
# Which numbers did an edit add or change
# ----------------------------------------------------------------------------------------------------------------------


def diff_numbers(old_tex: str, new_tex: str) -> list[tuple[str, PaperNumber, PaperNumber | None]]:
    """Numbers changed in place or inserted by an edit, ignoring numbers that only moved. No evidence needed."""
    old = [n for n in extract_paper_numbers(old_tex) if informative(n)]
    new = [n for n in extract_paper_numbers(new_tex) if informative(n)]
    a = _token_stream(strip_latex(old_tex), old)
    b = _token_stream(strip_latex(new_tex), new)
    sm = difflib.SequenceMatcher(None, [t for t, _ in a], [t for t, _ in b], autojunk=False)
    out: list[tuple[str, PaperNumber, PaperNumber | None]] = []
    removed: Counter = Counter()
    inserted: list[PaperNumber] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for (_, oi), (_, ni) in zip(a[i1:i2], b[j1:j2]):
                if oi >= 0 and ni >= 0 and old[oi].text != new[ni].text:
                    out.append(("changed", new[ni], old[oi]))
            continue
        removed.update(old[oi].key for _, oi in a[i1:i2] if oi >= 0)
        inserted.extend(new[ni] for _, ni in b[j1:j2] if ni >= 0)
    for n in inserted:
        if removed[n.key] > 0:  # moved with its text
            removed[n.key] -= 1
            continue
        out.append(("inserted", n, None))
    return out


# ----------------------------------------------------------------------------------------------------------------------
# Linking a paper number to its \src key
# ----------------------------------------------------------------------------------------------------------------------


def _num_pattern(text: str) -> str:
    body = re.escape(text.lstrip("+-−")).replace(",", r"\{?,\}?")
    return r"(?<![\w.])[-+−]?\$?\s*" + body


def src_key(tex: str, n: PaperNumber, siblings: list[PaperNumber]) -> str | None:
    """The key of the ``\\src{...}`` that directly follows number ``n`` on its line, if any."""
    lines = tex.splitlines()
    if not 1 <= n.line <= len(lines):
        return None
    line = lines[n.line - 1]
    pat = re.compile(_num_pattern(n.text) + r"(?![\d])[\s$}]*(?:[KMBT]\b)?[\s$}]*(?:\\%|%)?[\s$}]*(\\src\{([^}]*)\})?")
    hits = [m.group(2) for m in pat.finditer(line)]
    digits = n.text.lstrip("+-−")  # the pattern ignores the sign, so count same-digit siblings whatever their sign
    same = [s for s in siblings if s.line == n.line and s.text.lstrip("+-−") == digits]
    k = next((i for i, s in enumerate(same) if s.offset == n.offset), 0)
    if k < len(hits) and hits[k]:
        return hits[k].strip()
    keyed = [h for h in hits if h]
    return keyed[0].strip() if len(keyed) == 1 and len(hits) == 1 else None


# ----------------------------------------------------------------------------------------------------------------------
# Recipes
# ----------------------------------------------------------------------------------------------------------------------


@dataclass
class Recipe:
    key: str
    means: str
    func: str
    node: ast.FunctionDef
    module_consts: list[float] = field(default_factory=list)


def parse_sources(path: Path) -> tuple[dict[str, Recipe], str | None]:
    """Recipes keyed by name, or an error message if the file does not parse."""
    if not path.exists():
        return {}, None
    try:
        tree = ast.parse(path.read_text(), str(path))
    except SyntaxError as e:
        return {}, f"paper/sources.py does not parse: {e}"
    consts = [c.value for st in tree.body if isinstance(st, (ast.Assign, ast.AnnAssign))
              for c in ast.walk(st) if isinstance(c, ast.Constant) and isinstance(c.value, (int, float))
              and not isinstance(c.value, bool)]
    out: dict[str, Recipe] = {}
    for st in tree.body:
        if not isinstance(st, ast.FunctionDef):
            continue
        for dec in st.decorator_list:
            if (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name) and dec.func.id == "source"
                    and dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str)):
                means = next((kw.value.value for kw in dec.keywords if kw.arg == "means"
                              and isinstance(kw.value, ast.Constant)), "")
                out[dec.args[0].value] = Recipe(dec.args[0].value, str(means), st.name, st, consts)
    return out, None


def _tol(n: PaperNumber) -> float:
    return 0.5 * 10 ** (-max(n.decimals, 0)) + 1e-9


def _targets(n: PaperNumber) -> list[float]:
    """Values a recipe may return for printed number n, in the units the recipe is likely to use."""
    v = n.value
    out = [v]
    if n.text.startswith(("-", "−")) and re.search(r"--\s*\$?\s*" + re.escape(n.text.lstrip("-−")), n.context):
        out.append(abs(v))  # right end of a range "23.2--25.4" read as negative
    return out


def _scale(n: PaperNumber) -> float:
    m = re.search(re.escape(n.text.lstrip("+-−")) + r"\s*([KMBT])\b", n.context)
    return _SCALE_SUFFIX[m.group(1)] if m else 1.0


def static_problems(r: Recipe, n: PaperNumber) -> list[str]:
    probs = []
    tol = _tol(n)
    vals = [abs(t) for t in _targets(n)]
    for node in ast.walk(r.node):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""
            if name in _BANNED_CALLS:
                probs.append(f"recipe calls {name}(); return the unrounded value, the checker rounds")
    lits = [c.value for c in ast.walk(r.node) if isinstance(c, ast.Constant) and isinstance(c.value, (int, float))
            and not isinstance(c.value, bool)] + r.module_consts
    for c in lits:
        for v in vals:
            if v and any(abs(abs(c) * s - v) <= tol for s in (1.0, 100.0, 0.01)):
                probs.append(f"recipe hard-codes the printed value ({c})")
                break
    return sorted(set(probs))


_RUNNER = r'''
import json, os, sys, csv, io
root, src, keys = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])  # keys: {key: function name}
os.chdir(root)
sys.path.insert(0, root)
REG = {}
def source(key, means=""):
    def deco(f):
        REG[key] = f
        return f
    return deco
def load(path):
    p = os.path.join(root, path) if not os.path.isabs(path) else path
    with open(p) as fh:
        text = fh.read()
    if p.endswith(".json"):
        return json.loads(text)
    if p.endswith(".jsonl"):
        return [json.loads(l) for l in text.splitlines() if l.strip()]
    if p.endswith((".csv", ".tsv")):
        return list(csv.DictReader(io.StringIO(text), delimiter="\t" if p.endswith(".tsv") else ","))
    if p.endswith((".yaml", ".yml")):
        import yaml
        return yaml.safe_load(text)
    return text
opened = []
def hook(ev, args):
    if ev == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
        try:
            opened.append(os.path.realpath(os.fsdecode(args[0])))
        except Exception:
            pass
sys.addaudithook(hook)
g = {"source": source, "load": load, "__name__": "sources", "__file__": src}
out = {}
try:
    exec(compile(open(src).read(), src, "exec"), g)
except Exception as e:
    print(json.dumps({"__module__": {"error": "sources.py failed to run: " + repr(e)[:300]}}))
    sys.exit(0)
rroot = os.path.realpath(root)
paper = os.path.join(rroot, "paper") + os.sep
for k, fname in keys.items():
    # the decorator registry first; if the module redefined source(), fall back to the function's name
    f = REG.get(k) or g.get(fname)
    if not callable(f):
        out[k] = {"error": "no recipe named " + repr(k)}
        continue
    opened.clear()
    try:
        v = f()
        v = float(v)
        files = sorted({p for p in opened if p.startswith(rroot + os.sep) and not p.startswith(paper)})
        out[k] = {"value": v, "files": [os.path.relpath(p, rroot) for p in files]}
    except Exception as e:
        out[k] = {"error": "recipe raised " + repr(e)[:300]}
print(json.dumps(out))
'''


def run_recipes(root: Path, sources: Path, keys: dict[str, str], timeout: int = 300) -> dict:
    """Run recipes {key: function name} in a subprocess rooted at the repository."""
    if not keys:
        return {}
    try:
        p = subprocess.run([sys.executable, "-I", "-c", _RUNNER, str(root), str(sources), json.dumps(keys)],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"__module__": {"error": f"recipes took longer than {timeout} s"}}
    try:
        return json.loads(p.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"__module__": {"error": "recipe runner failed: " + (p.stderr or p.stdout)[-400:]}}


# ----------------------------------------------------------------------------------------------------------------------
# Which files a recipe may read
# ----------------------------------------------------------------------------------------------------------------------

_HASH_CACHE: dict[tuple[str, int, int], str] = {}


def file_hash(path: Path) -> str:
    st = path.stat()
    k = (str(path), st.st_size, st.st_mtime_ns)
    if k not in _HASH_CACHE:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        _HASH_CACHE[k] = h.hexdigest()
    return _HASH_CACHE[k]


def snapshot(root: Path) -> dict[str, str]:
    """Hashes of every repository file outside paper/ (the files recipes may read during a session)."""
    root = Path(root).resolve()
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        if rel == ".":
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        else:
            dirnames[:] = [d for d in dirnames if d not in (_SKIP_DIRS - {"paper"})]
        for fn in filenames:
            fp = Path(dirpath) / fn
            if fp.is_file():
                out[os.path.relpath(fp, root)] = file_hash(fp)
    return out


def file_problems(files: list[str], root: Path, baseline: dict[str, str] | None) -> list[str]:
    probs = []
    for f in files:
        if Path(f).suffix.lower() in NOTE_SUFFIXES:
            probs.append(f"recipe reads {f}, a prose note; notes can be stale, read the raw results instead")
        elif baseline is not None:
            if f not in baseline:
                probs.append(f"recipe reads {f}, which did not exist when the session started")
            elif file_hash(Path(root) / f) != baseline[f]:
                probs.append(f"recipe reads {f}, which was changed after the session started")
    return probs


# ----------------------------------------------------------------------------------------------------------------------
# The check
# ----------------------------------------------------------------------------------------------------------------------


@dataclass
class NumberCheck:
    kind: str  # changed | inserted | tagged | val
    number: PaperNumber
    old: PaperNumber | None
    key: str | None
    ok: bool
    reason: str
    computed: float | None = None
    files: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"kind": self.kind, "number": self.number.text, "old": self.old.text if self.old else None,
                "line": self.number.line, "context": self.number.context, "key": self.key, "ok": self.ok,
                "reason": self.reason, "computed": self.computed, "files": self.files}


def _vals(tex: str) -> list[tuple[int, str, PaperNumber]]:
    """\\val[d]{key} placeholders as (decimals, key, a stand-in PaperNumber for reporting)."""
    out = []
    for m in _VAL.finditer(tex):
        line = tex.count("\n", 0, m.start()) + 1
        ctx = tex[max(0, m.start() - 80):m.end() + 80].replace("\n", " ")
        d = int(m.group(1)) if m.group(1) is not None else 1
        out.append((d, m.group(2).strip(), PaperNumber(m.group(0), float("nan"), d, False, line, m.start(), ctx)))
    return out


def check(old_tex: str, new_tex: str, root: Path, sources: Path | None = None, *, tagged_too: bool = False,
          baseline: dict[str, str] | None = None) -> list[NumberCheck]:
    """Check numbers added or changed from old_tex to new_tex (and, with tagged_too, every number carrying \\src and
    every \\val placeholder in new_tex)."""
    root = Path(root).resolve()
    sources = Path(sources) if sources else root / "paper" / "sources.py"
    edited = diff_numbers(old_tex, new_tex)
    siblings = [n for n in extract_paper_numbers(new_tex) if informative(n)]
    keyed = [(k, n, o, src_key(new_tex, n, siblings)) for k, n, o in edited]
    if tagged_too:
        seen = {(n.line, n.offset) for _, n, _ in edited}
        for n in siblings:
            if (n.line, n.offset) not in seen:
                key = src_key(new_tex, n, siblings)
                if key:
                    keyed.append(("tagged", n, None, key))
    old_vals = Counter((d, k) for d, k, _ in _vals(old_tex))
    vals = []
    for d, k, n in _vals(new_tex):
        if not tagged_too and old_vals[(d, k)] > 0:
            old_vals[(d, k)] -= 1
            continue
        vals.append((d, k, n))
    if not keyed and not vals:
        return []
    recipes, err = parse_sources(sources)
    wanted = {key: recipes[key].func for *_, key in keyed if key and key in recipes}
    wanted.update({k: recipes[k].func for _, k, _ in vals if k in recipes})
    results = run_recipes(root, sources, wanted) if not err else {}
    mod_err = err or results.get("__module__", {}).get("error")

    def common(kind, n, o, key, number_checks: bool):
        if mod_err:
            return NumberCheck(kind, n, o, key, False, mod_err)
        if key not in recipes:
            return NumberCheck(kind, n, o, key, False, f"no recipe named {key!r} in paper/sources.py")
        res = results.get(key, {})
        if "error" in res:
            return NumberCheck(kind, n, o, key, False, res["error"])
        v, files = res.get("value"), res.get("files", [])
        probs = static_problems(recipes[key], n) if number_checks else \
            [p for p in static_problems(recipes[key], n) if "hard-codes" not in p]
        probs += file_problems(files, root, baseline)
        if probs:
            return NumberCheck(kind, n, o, key, False, "; ".join(probs), v, files)
        if not files:
            return NumberCheck(kind, n, o, key, False, "recipe read no data file of the repository", v, files)
        return NumberCheck(kind, n, o, key, True, "recomputed", v, files)

    out = []
    for kind, n, o, key in keyed:
        if key is None:
            out.append(NumberCheck(kind, n, o, None, False, "no \\src{key} after this number"))
            continue
        c = common(kind, n, o, key, True)
        if c.ok:
            s, tol = _scale(n), _tol(n)
            v = c.computed
            cands = [v / s] + ([100 * v / s] if n.is_percent else [])
            if not any(abs(x - t) <= tol for x in cands for t in _targets(n)):
                c.ok = False
                c.reason = f"recipe gives {v:.6g}, which does not round to {n.text} at the printed precision"
        out.append(c)
    for d, key, n in vals:
        out.append(common("val", n, None, key, False))
    return out


def fill(tex: str, root: Path, sources: Path | None = None) -> str:
    """Replace every \\val[d]{key} with its recipe's value rounded to d decimals. Raises if a recipe fails."""
    root = Path(root).resolve()
    sources = Path(sources) if sources else root / "paper" / "sources.py"
    vals = _vals(tex)
    if not vals:
        return tex
    recipes, err = parse_sources(sources)
    if err:
        raise ValueError(err)
    missing = sorted({k for _, k, _ in vals if k not in recipes})
    if missing:
        raise ValueError(f"no recipe for {missing}")
    res = run_recipes(root, sources, {k: recipes[k].func for _, k, _ in vals})
    if "__module__" in res:
        raise ValueError(res["__module__"]["error"])

    def rep(m):
        d = int(m.group(1)) if m.group(1) is not None else 1
        r = res[m.group(2).strip()]
        if "error" in r:
            raise ValueError(f"{m.group(2)}: {r['error']}")
        return f"{r['value']:.{d}f}"
    return _VAL.sub(rep, tex)


def deny_message(checks: list[NumberCheck], limit: int = 12) -> str:
    bad = [c for c in checks if not c.ok]
    lines = [f"{len(bad)} number(s) could not be recomputed from the repository's data:"]
    for c in bad[:limit]:
        lines.append(f"- {c.number.text} (line {c.number.line}, key {c.key or '-'}): {c.reason}. "
                     f"Context: {c.number.context[:120]}")
    if len(bad) > limit:
        lines.append(f"... and {len(bad) - limit} more.")
    lines.append("Every number you add or change needs \\src{key} right after it and a recipe "
                 "@source(\"key\", means=\"...\") in paper/sources.py that computes it from the raw results and returns "
                 "the unrounded value. `source` and `load(path)` are provided by the checker (do not define or import them); "
                 "give each recipe its own function name and write the recipe before editing the paper. Recipes must read "
                 "raw results, configs or scripts, not prose notes. When a recipe disagrees with the text, first check that "
                 "the recipe computes exactly what the sentence claims; if it does, the number in the text is what must "
                 "change. Never adjust a recipe just to reproduce a printed number.")
    return "\n".join(lines)


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="Recompute check for a paper's numbers")
    ap.add_argument("old", help="previous version, or - to check every tagged number of NEW")
    ap.add_argument("new")
    ap.add_argument("--root", default=".")
    ap.add_argument("--sources", default=None)
    ap.add_argument("--baseline", default=None, help="JSON snapshot from plumbline.sources.snapshot")
    ap.add_argument("--fill", default=None, help="write NEW with every \\val filled in to this path")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    new = Path(a.new).read_text()
    if a.fill:
        Path(a.fill).write_text(fill(new, Path(a.root), Path(a.sources) if a.sources else None))
        return
    old = "" if a.old == "-" else Path(a.old).read_text()
    base = json.loads(Path(a.baseline).read_text()) if a.baseline else None
    checks = check(old, new, Path(a.root), Path(a.sources) if a.sources else None, tagged_too=a.old == "-",
                   baseline=base)
    if a.old == "-":
        checks = [c for c in checks if c.key is not None]  # untagged numbers of an existing paper are out of scope
    if a.json:
        print(json.dumps([c.to_json() for c in checks], indent=1))
    else:
        for c in checks:
            print(("PASS " if c.ok else "FAIL ") + f"{c.kind:8s} {c.number.text:>10s} {c.key or '-':24s} {c.reason}")
        print(f"{sum(c.ok for c in checks)}/{len(checks)} recomputed")
    sys.exit(0 if all(c.ok for c in checks) else 1)


if __name__ == "__main__":
    main()
