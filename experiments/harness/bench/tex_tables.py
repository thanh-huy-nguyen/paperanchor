"""Split a LaTeX paper into prose and an evidence folder made from its numeric tables.

Tables become CSV files with formatting stripped (bold, underline, colors, ± parts, "Ours" markers stay as text),
and row order is kept here; shuffling for the writer inputs happens in a later step.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from evw.numtrace import normalize_sci

TABULAR = re.compile(r"\\begin\{(tabular\*?|tabularx|longtable)\}.*?\\end\{\1\}", re.S)
FLOAT_TABLE = re.compile(r"\\begin\{(table\*?)\}.*?\\end\{\1\}", re.S)


def _resolve_inputs(tex: str, root: Path, depth: int = 0) -> str:
    if depth > 3:
        return tex

    def sub(m: re.Match) -> str:
        name = m.group(1).strip()
        p = (root / name) if name.endswith(".tex") else (root / f"{name}.tex")
        if p.exists():
            return _resolve_inputs(p.read_text(errors="replace"), root, depth + 1)
        return ""

    return re.sub(r"\\(?:input|include)\{([^}]*)\}", sub, tex)


def clean_cell(cell: str) -> str:
    c = re.sub(r"(?<!\\)%.*$", "", cell)
    c = normalize_sci(c.replace("\\!", "").replace("\\,", ""))
    c = re.sub(r"_\{[^{}]*\}|_\S+", "", c)  # subscripts such as 0.130$_{\pm.01}$
    for _ in range(3):
        c = re.sub(r"\\(?:textbf|textit|underline|emph|mathbf|mathrm|text|textsc|uline|bm|boldsymbol)\{([^{}]*)\}", r"\1", c)
    c = re.sub(r"\\(?:cellcolor|color|textcolor)(?:\[[^\]]*\])?\{[^}]*\}", "", c)
    c = re.sub(r"\\(?:multicolumn|multirow)\{[^}]*\}\{[^}]*\}", "", c)
    c = re.sub(r"\\(?:pm|mp)\b.*$", "", c)
    c = c.replace("$", "").replace("{", "").replace("}", "").replace("\\%", "%")
    c = re.sub(r"\\[a-zA-Z]+\*?", " ", c)
    return " ".join(c.split())


def table_rows(tab: str) -> list[list[str]]:
    body = re.sub(r"^\\begin\{[^}]*\}(\{[^}]*\})*(\[[^\]]*\])?", "", tab.strip())
    body = re.sub(r"\\end\{[^}]*\}$", "", body)
    body = re.sub(r"\\(?:toprule|midrule|bottomrule|hline|cmidrule(?:\([^)]*\))?\{[^}]*\}|cline\{[^}]*\})", "", body)
    rows = []
    for raw in re.split(r"\\\\(?:\[[^\]]*\])?", body):
        if not raw.strip():
            continue
        cells = [clean_cell(c) for c in raw.split("&")]
        if any(cells):
            rows.append(cells)
    return rows


def split_paper(main_tex: Path, out_dir: Path) -> tuple[str, int]:
    """Write evidence CSVs to out_dir/results and return (prose_tex, number_of_tables)."""
    tex = _resolve_inputs(main_tex.read_text(errors="replace"), main_tex.parent)
    res = out_dir / "results"
    res.mkdir(parents=True, exist_ok=True)
    k = 0
    floats = [(f.start(), f.end(), f.group()) for f in FLOAT_TABLE.finditer(tex)]
    for m in TABULAR.finditer(tex):
        rows = table_rows(m.group())
        if sum(bool(re.search(r"\d", c)) for r in rows for c in r) < 4:
            continue
        k += 1
        with (res / f"table_{k:02d}.csv").open("w", newline="") as f:
            csv.writer(f).writerows(rows)
        host = next((g for a, b, g in floats if a <= m.start() < b), "")
        cap = re.search(r"\\caption\{(.*?)\}\s*(?:\\label|\\end|\\centering|\\vspace|\n\s*\n|$)", host, re.S)
        if cap:
            (res / f"table_{k:02d}.csv.caption.txt").write_text(" ".join(cap.group(1).split()))
    # prose: remove whole table floats (captions included, they restate table content) and any loose tabulars
    prose = FLOAT_TABLE.sub("\n", tex)
    prose = TABULAR.sub("\n", prose)
    return prose, k
