"""Deterministic number trace: link every number in a LaTeX manuscript to a value in a results folder.

No LLM and no network.

Matching is anchored. A number in the paper is linked to an evidence value only if (a) the values agree at the
precision shown, allowing a x100 / /100 rescale, and (b) the evidence value's labels (table row and column names,
JSON keys, or the words on its log line) share a word with the sentence around the number. Without (b), dense
result tables would let almost any number match some cell by chance.

Status of a paper number:
  traced    anchored match to an evidence value
  derived   anchored match to a difference, relative change, ratio, or column mean of evidence values
  weak      matches some value only without an anchor (reported, never trusted by the gate)
  untraced  no match

The gate compares two versions of a manuscript. A number that keeps its place in the text but changes value must
still match one of the evidence values the old number was linked to. A newly inserted number must be traced or
derived. Text that merely moves is allowed.
"""

from __future__ import annotations

import bisect
import csv
import difflib
import io
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

EVIDENCE_SUFFIXES = {".csv", ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".txt", ".log", ".md", ".out"}
_NUM_IN_TEXT = re.compile(r"(?<![\w.])[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w])")
_NUM_IN_PAPER = re.compile(
    r"(?<![\w.])[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?(?=[KMBT]\b|(?![\w]))"
)
_STOP = set(
    "the a an of and or in on for to with by from at as is are was were be been this that these those our we its it "
    "than vs versus all each per over under into using use used based model models method methods results result "
    "table tab figure fig set sets mean avg average std score scores value values total best".split()
)

# ----------------------------------------------------------------------------------------------------------------------
# Parsing helpers
# ----------------------------------------------------------------------------------------------------------------------

_LATEX_SCI = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:\\!\s*)*(?:\\times|\\cdot|x|×)\s*(?:\\!\s*)*10\s*\^\s*\{?\s*([-−+]?\s*\d+)\s*\}?"
)


def normalize_sci(text: str) -> str:
    """Rewrite 5.45\\times 10^{-5} (and the bare 10^{-14}) as 5.45e-5 / 1e-14 so they parse as one number."""
    text = _LATEX_SCI.sub(lambda m: f"{m.group(1)}e{m.group(2).replace('−', '-').replace(' ', '')}", text)
    return re.sub(r"(?<![\d.e])10\s*\^\s*\{?\s*([-−+]?\d+)\s*\}?", lambda m: f"1e{m.group(1).replace('−', '-')}", text)


def _parse_number(text: str) -> tuple[float, int] | None:
    t = text.strip().replace("−", "-").replace(",", "")
    if not t:
        return None
    try:
        v = float(t)
    except ValueError:
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    if "e" in t.lower():
        # 2.4e-7 is written to 8 decimals (one in the mantissa, seven in the exponent); large exponents stay unknown
        mant, _, exp = t.lower().partition("e")
        md = len(mant.split(".", 1)[1]) if "." in mant else 0
        try:
            d = md - int(exp)
        except ValueError:
            d = -1
        decimals = d if d >= 0 else -1
    elif "." in t:
        decimals = len(t.split(".", 1)[1])
    else:
        decimals = 0
    return v, decimals


def _cell_number(cell: str) -> tuple[float, int] | None:
    """The leading number of a table cell, ignoring %, ±, bold markers and subscripts."""
    c = normalize_sci(cell.replace("\\!", "").replace("\\,", ""))
    c = c.split("±")[0].split("+/-")[0]
    m = re.match(r"\s*[*_(\[]*\s*([-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?)", c)
    return _parse_number(m.group(1)) if m else None


# common abbreviations in config files and log keys, expanded so they can anchor to prose
_ALIASES = {
    "lr": "learning rate", "bs": "batch size", "wd": "weight decay", "ep": "epochs", "acc": "accuracy",
    "auc": "auroc", "params": "parameters", "dsc": "dice", "iou": "jaccard", "ft": "fine tuning",
    "seq": "sequence", "len": "length", "dim": "dimension", "temp": "temperature", "lat": "latency",
}


def tokens(text: str) -> frozenset[str]:
    """Lower-case content words used as anchors. 'CIFAR-10' yields 'cifar' and 'cifar10'."""
    text = re.sub(r"\\[a-zA-Z]+", " ", text)
    out = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9]*(?:[-_][A-Za-z0-9]+)*", text):
        lw = w.lower()
        parts = [p for p in re.split(r"[-_]", lw) if p]
        for p in parts + ["".join(parts)]:
            if len(p) >= 2 and p not in _STOP and not p.isdigit():
                out.add(p)
                if p in _ALIASES:
                    out.update(_ALIASES[p].split())
    return frozenset(out)


def anchor_score(evidence_anchors: frozenset[str], context: frozenset[str]) -> int:
    """Number of evidence label words found in the context. 'acc' counts for 'accuracy' (prefix of 3+ letters)."""
    score = 0
    for e in evidence_anchors:
        if e in context or (len(e) >= 3 and any(len(c) >= 3 and (c.startswith(e) or e.startswith(c)) for c in context)):
            score += 1
    return score


# ----------------------------------------------------------------------------------------------------------------------
# Evidence index
# ----------------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceValue:
    value: float
    decimals: int  # digits after the decimal point as written (-1 if unknown, e.g. JSON floats)
    source: str  # file path relative to the evidence root
    locator: str  # row/column, JSON path, or line number
    group: str  # values in the same group can be combined into derived values
    anchors: frozenset[str] = frozenset()

    @property
    def id(self) -> str:
        return f"{self.source}#{self.locator}"


def _file_anchors(rel: str, root: Path | None = None) -> frozenset[str]:
    """Folder and file names, plus a caption sidecar (<file>.caption.txt) when one exists."""
    p = Path(rel)
    words = " ".join(list(p.parent.parts) + [re.sub(r"^table_\d+$", "", p.stem)])
    anchors = tokens(words)
    if root is not None:
        cap = (root / rel).with_name(p.name + ".caption.txt")
        if cap.exists():
            anchors |= tokens(cap.read_text(errors="replace"))
    return anchors


def _index_table(rows: list[list[str]], rel: str, out: list[EvidenceValue], file_anchor: frozenset[str] = frozenset()) -> None:
    if not rows:
        return
    width = max(len(r) for r in rows)
    n_header = 0
    for r in rows[:3]:  # leading rows that are mostly text are header rows (group header + sub header)
        nonempty = [c for c in r if c.strip()]
        if nonempty and sum(_cell_number(c) is not None for c in nonempty) < max(1, len(nonempty) // 2):
            n_header += 1
        else:
            break
    names = []
    for j in range(width):
        parts = []
        for r in rows[:n_header]:
            if j < len(r) and r[j].strip():
                parts.append(r[j].strip())
            elif j < len(r) and not r[j].strip() and parts == [] and j > 0:
                # a spanning group header leaves blanks; inherit the nearest label to the left in that header row
                left = next((r[k].strip() for k in range(j - 1, -1, -1) if k < len(r) and r[k].strip()), "")
                if left:
                    parts.append(left)
        names.append(" / ".join(parts) or f"col{j}")
    for i, row in enumerate(rows[n_header:]):
        label = " ".join(c for c in row if c and _cell_number(c) is None)
        row_anchor = tokens(label)
        for j, cell in enumerate(row):
            parsed = _cell_number(cell)
            if parsed is None:
                continue
            col = names[j]
            out.append(
                EvidenceValue(
                    parsed[0],
                    parsed[1],
                    rel,
                    f"row {i + 1} ({label[:40]}), col {col!r}",
                    f"{rel}::col::{col}",
                    row_anchor | tokens(col) | file_anchor,
                )
            )


def _index_json(obj, rel: str, path: str, out: list[EvidenceValue]) -> None:
    if isinstance(obj, bool):
        return
    key = re.sub(r"\[\d+\]", "[]", path).split(".")[-1] or path
    anchors = tokens(path.replace(".", " ").replace("[", " ").replace("]", " ")) | _file_anchors(rel)
    if isinstance(obj, (int, float)):
        decimals = 0 if isinstance(obj, int) else -1
        out.append(EvidenceValue(float(obj), decimals, rel, path or "$", f"{rel}::key::{key}", anchors))
    elif isinstance(obj, str):
        parsed = _parse_number(obj)
        if parsed is not None:
            out.append(EvidenceValue(parsed[0], parsed[1], rel, path or "$", f"{rel}::key::{key}", anchors))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            _index_json(v, rel, f"{path}.{k}" if path else str(k), out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _index_json(v, rel, f"{path}[{i}]", out)


def _index_text(text: str, rel: str, out: list[EvidenceValue], file_anchor: frozenset[str] = frozenset()) -> None:
    lines = normalize_sci(text).splitlines()
    table: list[list[str]] = []  # Markdown pipe tables are indexed as tables so columns form groups
    for ln, line in enumerate(lines, 1):
        if line.strip().startswith("|") and line.count("|") >= 2:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                table.append(cells)
            continue
        if table:
            _index_table(table, rel, out, file_anchor)
            table = []
        anchors = tokens(line) | file_anchor
        for m in _NUM_IN_TEXT.finditer(line):
            parsed = _parse_number(m.group())
            if parsed is not None:
                out.append(EvidenceValue(parsed[0], parsed[1], rel, f"line {ln}", f"{rel}::text", anchors))
    if table:
        _index_table(table, rel, out, file_anchor)


def build_evidence_index(evidence_dir: str | Path) -> list[EvidenceValue]:
    root = Path(evidence_dir)
    files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
    out: list[EvidenceValue] = []
    for p in files:
        if p.suffix.lower() not in EVIDENCE_SUFFIXES or p.name.endswith(".caption.txt"):
            continue
        rel = str(p.relative_to(root.parent if root.is_file() else root))
        try:
            text = p.read_text(errors="replace")
        except OSError:
            continue
        suf = p.suffix.lower()
        fa = _file_anchors(rel, root if root.is_dir() else root.parent)
        if suf in {".csv", ".tsv"}:
            _index_table(list(csv.reader(io.StringIO(text), delimiter="\t" if suf == ".tsv" else ",")), rel, out, fa)
        elif suf == ".json":
            try:
                _index_json(json.loads(text), rel, "", out)
            except json.JSONDecodeError:
                _index_text(text, rel, out, fa)
        elif suf == ".jsonl":
            for i, line in enumerate(text.splitlines()):
                try:
                    _index_json(json.loads(line), rel, f"[{i}]", out)
                except json.JSONDecodeError:
                    continue
        else:
            _index_text(text, rel, out, fa)
    return out


# ----------------------------------------------------------------------------------------------------------------------
# Manuscript numbers
# ----------------------------------------------------------------------------------------------------------------------

_DROP_COMMANDS = (
    r"src|val|cite[tp]?\*?|citeauthor|citeyear|ref|eqref|cref|Cref|autoref|label|url|href|includegraphics|input|include|"
    r"usepackage|documentclass|bibliography|bibliographystyle|vspace\*?|hspace\*?|setlength|addtolength|"
    r"resizebox|scalebox|rule|multicolumn|multirow|cline|cmidrule|arraystretch|tabcolsep|definecolor|"
    r"color|textcolor|cellcolor|rowcolor|fontsize|newcommand|renewcommand|footnotesize|linewidth|textwidth"
)
_CMD_WITH_ARGS = re.compile(r"\\(?:" + _DROP_COMMANDS + r")(?:\s*\[[^\]]*\])*(?:\s*\{[^{}]*\})*")
_STRUCTURAL_REF = re.compile(
    r"(?:Section|Sec\.|Sections|Table|Tab\.|Tables|Figure|Fig\.|Figures|Eq\.|Equation|Eqs\.|Appendix|App\.|Algorithm|"
    r"Alg\.|Line|Lines|Theorem|Lemma|Definition|Proposition|Corollary|Step|Stage|Chapter|Part)\s*~?\s*$",
    re.IGNORECASE,
)
_YEAR = re.compile(r"^(19|20)\d{2}$")


@dataclass
class PaperNumber:
    text: str
    value: float
    decimals: int
    is_percent: bool
    line: int
    offset: int  # character offset in the stripped body, used to align two versions
    context: str
    ctx_tokens: frozenset[str] = field(default_factory=frozenset, repr=False)
    status: str = "untraced"
    evidence: list[dict] = field(default_factory=list)
    links: set[str] = field(default_factory=set, repr=False)  # ids of anchored evidence (direct or derived)
    specific: bool = False  # the match beats nearby decoy values (see EvidenceMatcher.classify)

    @property
    def key(self) -> tuple[str, bool]:
        return (self.text, self.is_percent)


def strip_latex(tex: str) -> str:
    """Keep line structure so reported line numbers stay valid. Drops comments, preamble, and non-claim commands."""
    body = "\n".join(re.sub(r"(?<!\\)%.*$", "", line) for line in tex.splitlines())
    start = body.find(r"\begin{document}")
    if start >= 0:
        body = "\n" * body[:start].count("\n") + body[start:]
    # bibliography entries are references, not claims
    body = re.sub(r"\\begin\{thebibliography\}.*?\\end\{thebibliography\}",
                  lambda m: "\n" * m.group().count("\n"), body, flags=re.S)
    body = re.sub(r"(?:arXiv|arxiv|doi|DOI)\s*[:.]?\s*\S+", " ", body)
    end = body.find(r"\end{document}")
    if end >= 0:
        body = body[:end]
    for _ in range(3):  # nested arguments
        body = _CMD_WITH_ARGS.sub(lambda m: "\n" * m.group().count("\n"), body)
    body = re.sub(r"\\(?:begin|end)\{[^}]*\}(?:\{[^}]*\})?(?:\[[^\]]*\])?", " ", body)
    body = re.sub(r"(?<=\d)\{,\}(?=\d{3}(?!\d))", ",", body)                   # 1{,}559 is one number
    body = re.sub(r"\$\s*[-−]\s*\$(?=\d)|\\textminus\s*(?:\{\})?(?=\d)", "-", body)  # $-$6.0 is negative
    body = normalize_sci(body.replace("\\!", "").replace("\\,", ""))
    body = re.sub(r"\d*\.?\d+\s*\\(?:linewidth|textwidth|columnwidth|hsize)", " ", body)
    body = re.sub(r"\d*\.?\d+\s*(?:pt|em|ex|cm|mm|in)\b", " ", body)
    return body


def _sentence_window(body: str, start: int, end: int) -> str:
    """The sentence holding the number plus the one before it, capped at 400 characters on each side."""

    def prev_break(pos: int) -> int:
        return max(body.rfind(". ", 0, pos), body.rfind("\n\n", 0, pos))

    lo = prev_break(start)
    lo = prev_break(lo) if lo > 0 else lo
    lo = max(lo, start - 400, 0)
    his = [x for x in (body.find(". ", end), body.find("\n\n", end)) if x >= 0]
    hi = min(min(his) if his else len(body), end + 400)
    return body[lo:hi]


def extract_paper_numbers(tex: str) -> list[PaperNumber]:
    body = strip_latex(tex)
    out: list[PaperNumber] = []
    line_starts = [0] + [i + 1 for i, ch in enumerate(body) if ch == "\n"]
    for m in _NUM_IN_PAPER.finditer(body):
        raw = m.group()
        parsed = _parse_number(raw)
        if parsed is None:
            continue
        value, decimals = parsed
        ls = body.rfind("\n", 0, m.start()) + 1
        le = body.find("\n", m.end())
        line_text = body[ls : le if le >= 0 else len(body)]
        before = body[ls : m.start()]
        after = body[m.end() : le if le >= 0 else len(body)]
        if _STRUCTURAL_REF.search(before):
            continue
        if decimals == 0 and _YEAR.match(raw.lstrip("+-−")):
            continue
        if re.search(r"[A-Za-z]-?$", before) or re.match(r"[A-Za-z]{2}", after.lstrip("\\")):
            # part of a name such as ResNet50, GPT4o, CIFAR-10 or 3D; not a claim
            if not re.match(r"\s*(?:\\?%|x\b|\\times)", after):
                continue
        is_percent = bool(re.match(r"\s*(?:\\%|%|percent)", after))
        window = _sentence_window(body, m.start(), m.end())
        ctx = re.sub(r"\s+", " ", line_text[max(0, m.start() - ls - 80) : m.end() - ls + 80]).strip()
        out.append(
            PaperNumber(
                raw,
                value,
                decimals,
                is_percent,
                bisect.bisect_right(line_starts, m.start()),
                m.start(),
                ctx,
                tokens(window),
            )
        )
    return out


# ----------------------------------------------------------------------------------------------------------------------
# Matching
# ----------------------------------------------------------------------------------------------------------------------


def _tol(decimals_paper: int, decimals_ev: int) -> float:
    d = [x for x in (decimals_paper, decimals_ev) if x >= 0]
    # half a unit of the coarser precision, so 81.2 in the paper matches 81.23 in a log and vice versa
    return 0.5 * 10 ** (-min(d)) + 1e-9 if d else 1e-9


@dataclass(frozen=True)
class Derived:
    value: float
    decimals: int
    kind: str
    description: str
    id: str
    anchors: frozenset[str]


@dataclass
class TraceConfig:
    allow_rescale: bool = True  # 0.812 <-> 81.2 (fraction <-> percent)
    allow_derived: bool = True  # differences, relative changes, ratios, column means within one column or key
    min_informative: float = 10.0  # integers below this without a % sign are too common to trace and are skipped
    max_group_size: int = 60  # derived pairs only within groups of this size or smaller
    decoy_offsets: tuple[int, ...] = (-13, -7, -3, 3, 7, 13)  # in units of the paper's last digit
    check_specific: bool = False  # compute n.specific with decoy values (7x slower)
    require_specific: bool = False  # traced/derived also need a match that beats every decoy value


_SCALES = ((1.0, "as written"), (0.01, "paper value is a percent of the evidence"), (100.0, "evidence is a percent"))


class EvidenceMatcher:
    def __init__(self, index: list[EvidenceValue], cfg: TraceConfig | None = None):
        self.cfg = cfg or TraceConfig()
        self.index = sorted(index, key=lambda e: e.value)
        self._vals = [e.value for e in self.index]
        self.derived: list[Derived] = []
        if self.cfg.allow_derived:
            self._build_derived()
        self.derived.sort(key=lambda d: d.value)
        self._dvals = [d.value for d in self.derived]
        # candidates depend only on (value, decimals, context words); writing loops retrace near-identical versions
        self._cand_cache: dict[tuple, list] = {}
        self._trace_cache: dict[str, "TraceReport"] = {}

    def _build_derived(self) -> None:
        groups: dict[str, list[EvidenceValue]] = defaultdict(list)
        for e in self.index:
            groups[e.group].append(e)
        for g, vals in groups.items():
            if len(vals) < 2 or len(vals) > self.cfg.max_group_size:
                continue
            if "::col::" in g:
                mean = sum(v.value for v in vals) / len(vals)
                anchors = frozenset().union(*(v.anchors for v in vals))
                self.derived.append(Derived(mean, -1, "mean", f"mean of {g.split('::col::')[1]!r}", f"{g}#mean", anchors))
            for a in vals:
                for b in vals:
                    if a is b or a.value <= b.value:
                        continue
                    anchors = a.anchors | b.anchors
                    pid = f"{a.id}|{b.id}"
                    dec = max(a.decimals, b.decimals) if min(a.decimals, b.decimals) >= 0 else -1
                    desc = f"{a.locator} vs {b.locator} in {a.source}"
                    self.derived.append(Derived(a.value - b.value, dec, "difference", desc, pid + "#diff", anchors))
                    if b.value > 0:
                        rel = 100.0 * (a.value - b.value) / b.value
                        self.derived.append(Derived(rel, -1, "relative change %", desc, pid + "#rel", anchors))
                        self.derived.append(Derived(a.value / b.value, -1, "ratio", desc, pid + "#ratio", anchors))

    @staticmethod
    def _window(sorted_vals: list[float], lo: float, hi: float) -> range:
        return range(bisect.bisect_left(sorted_vals, lo), bisect.bisect_right(sorted_vals, hi))

    def candidates(self, n: PaperNumber) -> list[tuple[str, str, float, int, str]]:
        """All tolerance matches: (id, kind, value, anchor score, description)."""
        key = (n.value, n.decimals, n.ctx_tokens)
        hit = self._cand_cache.get(key)
        if hit is not None:
            return hit
        hit = self._candidates(n)
        if len(self._cand_cache) > 200_000:
            self._cand_cache.clear()
        self._cand_cache[key] = hit
        return hit

    def _candidates(self, n: PaperNumber) -> list[tuple[str, str, float, int, str]]:
        x = abs(n.value)
        out = []
        for scale, how in _SCALES if self.cfg.allow_rescale else _SCALES[:1]:
            t = x * scale
            for k in self._window(self._vals, t - scale, t + scale):
                e = self.index[k]
                tol = _tol(n.decimals, e.decimals) if scale == 1.0 else _tol(n.decimals, n.decimals) * scale
                if abs(abs(e.value) - t) <= tol:
                    out.append((e.id, "direct", e.value, anchor_score(e.anchors, n.ctx_tokens), f"{e.source}: {e.locator} ({how})"))
            if not self.cfg.allow_derived:
                continue
            for k in self._window(self._dvals, t - scale, t + scale):
                d = self.derived[k]
                if d.kind in ("relative change %", "ratio") and scale != 1.0:
                    continue  # already a percentage or a unitless ratio
                tol = _tol(n.decimals, d.decimals) if scale == 1.0 else _tol(n.decimals, n.decimals) * scale
                if abs(d.value - t) <= tol:
                    out.append((d.id, d.kind, d.value, anchor_score(d.anchors, n.ctx_tokens), d.description))
        return out

    def classify(self, n: PaperNumber) -> None:
        cands = self.candidates(n)
        anchored_c = [c for c in cands if c[3]]
        direct = [c for c in anchored_c if c[1] == "direct"]
        if direct:
            n.status = "traced"
        elif anchored_c:
            n.status = "derived"
        elif cands:
            n.status = "weak"
        else:
            n.status = "untraced"
        # links are the best-anchored matches only, and direct matches win over derived ones, so a later edit
        # cannot slide to some other value that merely shares a word with the sentence
        pool = direct or anchored_c
        top = max((c[3] for c in pool), default=0)
        n.links = {c[0] for c in pool if c[3] == top}
        # specificity: with large evidence sets some label word is shared by chance with values near any number.
        # A match is specific only if the true value anchors strictly better than every nearby decoy value.
        if pool and (self.cfg.check_specific or self.cfg.require_specific):
            unit = 10.0 ** -max(n.decimals, 0)
            decoy = 0
            for k in self.cfg.decoy_offsets:
                v = n.value + k * unit
                dn = replace(n, value=v, text=f"{v:.{max(n.decimals, 0)}f}")
                decoy = max([decoy] + [c[3] for c in self.candidates(dn)])
            n.specific = top > decoy
            if self.cfg.require_specific and not n.specific:
                n.status = "weak"
        shown = sorted(direct or anchored_c or cands, key=lambda c: -c[3])
        n.evidence = [{"id": c[0], "kind": c[1], "value": c[2], "anchor_score": c[3], "where": c[4]} for c in shown[:5]]

    def matches_any(self, n: PaperNumber, ids: set[str]) -> bool:
        return any(c[0] in ids for c in self.candidates(n))

    def informative(self, n: PaperNumber) -> bool:
        return n.decimals != 0 or n.is_percent or abs(n.value) >= self.cfg.min_informative


# ----------------------------------------------------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------------------------------------------------


@dataclass
class TraceReport:
    numbers: list[PaperNumber]

    @property
    def counts(self) -> dict[str, int]:
        return dict(Counter(n.status for n in self.numbers))

    def untraced(self) -> list[PaperNumber]:
        return [n for n in self.numbers if n.status in ("untraced", "weak")]

    def to_json(self) -> dict:
        nums = []
        for n in self.numbers:
            d = asdict(n)
            d.pop("ctx_tokens", None)
            d["links"] = sorted(n.links)
            nums.append(d)
        return {"counts": self.counts, "numbers": nums}


def trace(tex: str, matcher: EvidenceMatcher) -> TraceReport:
    hit = matcher._trace_cache.get(tex)
    if hit is not None:
        return hit
    nums = [n for n in extract_paper_numbers(tex) if matcher.informative(n)]
    for n in nums:
        matcher.classify(n)
    if len(matcher._trace_cache) > 64:
        matcher._trace_cache.clear()
    matcher._trace_cache[tex] = TraceReport(nums)
    return matcher._trace_cache[tex]


@dataclass
class GateDecision:
    allow: bool
    violations: list[tuple[str, PaperNumber, PaperNumber | None]]  # (kind, new number, old number if changed in place)

    def reason(self) -> str:
        if self.allow:
            return "All new or changed numbers trace to the results files."
        out = ["This edit introduces numbers that the results files do not support:"]
        for kind, n, o in self.violations[:10]:
            pct = "%" if n.is_percent else ""
            if kind == "changed":
                out.append(f"  - line {n.line}: {o.text} was changed to {n.text}{pct}, which no longer matches "
                           f"{(o.evidence[0]['where'] if o.evidence else 'its source')}. Context: ...{n.context}...")
            else:
                out.append(f"  - line {n.line}: new number {n.text}{pct} matches no labeled value in the results. "
                           f"Context: ...{n.context}...")
        out.append("Use the exact values from the results files, or remove the claim.")
        return "\n".join(out)


def _token_stream(body: str, nums: list[PaperNumber]) -> list[tuple[str, int]]:
    """Words and number placeholders in order. A placeholder carries the index of its PaperNumber."""
    by_offset = {n.offset: i for i, n in enumerate(nums)}
    stream: list[tuple[str, int]] = []
    for m in re.finditer(r"[A-Za-z]+|" + _NUM_IN_PAPER.pattern, body):
        if m.start() in by_offset:
            stream.append(("<NUM>", by_offset[m.start()]))
        elif m.group()[0].isalpha():
            stream.append((m.group().lower(), -1))
    return stream


def edited_numbers(old_tex: str, new_tex: str, matcher: EvidenceMatcher) -> list[tuple[str, PaperNumber, PaperNumber | None, bool]]:
    """Every number an edit changed in place or inserted, ignoring numbers that only moved with their text.

    Returns (kind, new number, old number or None, anchored) where kind is "changed" or "inserted" and anchored is
    True when the edit-time identity check accepts the number: a changed number still matches the evidence its
    predecessor was linked to (or, with no predecessor link, traces on its own); an inserted number traces.
    """
    old = trace(old_tex, matcher).numbers
    new = trace(new_tex, matcher).numbers
    a = _token_stream(strip_latex(old_tex), old)
    b = _token_stream(strip_latex(new_tex), new)
    sm = difflib.SequenceMatcher(None, [t for t, _ in a], [t for t, _ in b], autojunk=False)
    out: list[tuple[str, PaperNumber, PaperNumber | None, bool]] = []
    removed: Counter = Counter()
    inserted: list[PaperNumber] = []
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for (_, oi), (_, ni) in zip(a[i1:i2], b[j1:j2]):
                if oi < 0 or ni < 0:
                    continue
                o, n = old[oi], new[ni]
                if o.text == n.text:
                    continue
                if any(m.key == n.key and (m.links & n.links or not m.links) for m in old):
                    continue  # the same number with the same evidence moved here (clauses were reordered)
                ok = matcher.matches_any(n, o.links) if o.links else n.status in ("traced", "derived")
                out.append(("changed", n, o, ok))
            continue
        removed.update(old[oi].key for _, oi in a[i1:i2] if oi >= 0)
        inserted.extend(new[ni] for _, ni in b[j1:j2] if ni >= 0)
    for n in inserted:
        if removed[n.key] > 0:  # the same number moved with its text
            removed[n.key] -= 1
            continue
        out.append(("inserted", n, None, n.status in ("traced", "derived")))
    return out


def gate(old_tex: str, new_tex: str, matcher: EvidenceMatcher) -> GateDecision:
    """Lookup gate: blocks edited numbers that the identity check cannot anchor (see edited_numbers)."""
    violations = [(k, n, o) for k, n, o, ok in edited_numbers(old_tex, new_tex, matcher) if not ok]
    return GateDecision(allow=not violations, violations=violations)
