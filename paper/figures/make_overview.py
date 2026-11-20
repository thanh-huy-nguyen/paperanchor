"""Figure 2 (overview) of the PaperAnchor report: one edit, checked at the edit, and the six places a check can sit.

Top row: a writing agent changes a number (lane 1), the hook reruns the number's recipe on the repository's raw data
(lane 2), and the verdict returns to the agent in the same turn (lane 3). The edit, the recipe and the message are
shown as cards with their actual content. Bottom row: the six placements we compare, in session order, each with the
measured number of planted errors left per paper (of 6) from the placement study.

The dots are read from pilot/exh4/analysis.json when it is present and fall back to the published values.
Coordinates are inches on a single axes that covers the figure.

Run: python make_overview.py   (writes fig_overview.pdf and fig_overview.png)
"""
import json
import os

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon, Rectangle, Wedge

from make_figures import MIN_FS, PROJ, TEXT_W, contrast, ctext, save  # noqa: F401  (also runs the font setup)
from make_concept import (agent, box, check_badge, cross_badge, lines, page, pill, reviewer, run_badge, runs,
                          text_w)
from make_logo import draw as bob
from style import (AMBER, AMBER_EDGE, AMBER_FILL, AMBER_TXT, ARROW, BLUE, BLUE_EDGE, BLUE_FILL, BLUE_TXT, DISPLAY,
                   DISPLAY_SCALE, ERROR_TXT, GOLD, INK, LAV_EDGE, LAVENDER, LIGHT, MUTED, PURPLE, ROSE, ROSE_EDGE,
                   ROSE_FILL, ROSE_TXT, SLATE, SLATE_EDGE, SLATE_FILL, TEAL, TEAL_EDGE, TEAL_FILL, TEAL_TXT, arrow,
                   number, path_arrow)

W, H = TEXT_W, 5.0
MONO = "DejaVu Sans Mono"
MFS = 6.0                      # code size (pt); DejaVu Sans Mono advances 0.602 em
CW = 0.602 * MFS / 72          # width of one code character (in)
DARK = "#3A3247"
CODE_BG = "#FBFAFD"
DEL_BG, ADD_BG = "#FBE3E4", "#E2F3E4"
GREEN_TXT = "#2E7D32"
PUBLISHED = {"generate": 0.0, "gate": 0.0, "feedback": 0.0, "tool": 2.96, "audit": 0.12}


def errors_left():
    f = os.path.join(PROJ, "pilot", "exh4", "analysis.json")
    if os.path.exists(f):
        per = json.load(open(f))["per_arm"]
        return {k: per[k]["planted_left_per_paper"] for k in PUBLISHED}
    return PUBLISHED


# ---------------------------------------------------------------- helpers
def mono(ax, x, y, parts, z=8, fs=MFS, weight="normal"):
    """A line of code made of (string, color) runs; monospaced, so runs are placed by character count."""
    if isinstance(parts, str):
        parts = [(parts, INK)]
    for s, c in parts:
        ax.text(x, y, s, family=MONO, fontsize=fs, color=c, ha="left", va="center", zorder=z, weight=weight)
        x += len(s) * CW * fs / MFS
    return x


def card(ax, x0, y0, w, h, head, head_fc, fc=CODE_BG, ec=None, z=4, head_h=0.17, mono_head=True):
    """Content card with a colored header bar (the header is clipped to the card's rounded top)."""
    ec = ec or head_fc
    body = FancyBboxPatch((x0, y0), w, h, boxstyle="round,pad=0,rounding_size=0.05", fc=fc, ec=ec, lw=0.9, zorder=z)
    ax.add_patch(body)
    bar = Rectangle((x0, y0 + h - head_h), w, head_h, fc=head_fc, ec="none", zorder=z + 1)
    ax.add_patch(bar)
    bar.set_clip_path(body)
    ax.add_patch(FancyBboxPatch((x0, y0), w, h, boxstyle="round,pad=0,rounding_size=0.05", fc="none", ec=ec, lw=0.9,
                                zorder=z + 2))
    if mono_head:
        ax.text(x0 + 0.07, y0 + h - head_h / 2 - 0.004, head, family=MONO, fontsize=MFS, color="white", ha="left",
                va="center", zorder=z + 3)
    else:
        ax.text(x0 + 0.07, y0 + h - head_h / 2 - 0.004, head, fontsize=MIN_FS, color="white", ha="left", va="center",
                zorder=z + 3, weight=600)
    return y0 + h - head_h


def lane(ax, x0, y0, w, h, fc, ec, k, title, badge=PURPLE):
    box(ax, x0, y0, w, h, fc=fc, ec=ec, lw=1.0, r=0.1, z=0)
    r = 0.085
    number(ax, x0 + 0.2, y0 + h - 0.2, k, r=r, fc=badge, fs=7)
    ax.text(x0 + 0.2 + r + 0.06, y0 + h - 0.2, title, fontsize=7.6 * DISPLAY_SCALE, family=DISPLAY, weight=700,
            color=INK, ha="left", va="center", zorder=7)


def label(ax, x, y, s, bg, color=INK, **kw):
    kw.setdefault("ha", "center"); kw.setdefault("va", "center")
    ctext(ax, x, y, s, color=color, bg=bg, zorder=8, **kw)


def tile(ax, cx, cy, s, color, w=0.74, h=0.3, fs=10):
    box(ax, cx - w / 2, cy - h / 2, w, h, fc="white", ec=color, lw=1.1, r=0.06, z=5)
    ax.text(cx, cy - 0.006, s, fontsize=fs, color=color, ha="center", va="center", zorder=7, weight=600)


def lock(ax, cx, cy, s=0.1, color=TEAL_TXT, z=9):
    """Padlock: the snapshot of the data cannot change during the session."""
    ax.add_patch(Circle((cx, cy), s * 1.05, fc="white", ec=color, lw=0.7, zorder=z))
    t = np.linspace(0, np.pi, 20)
    ax.plot(cx + 0.36 * s * np.cos(t), cy + 0.12 * s + 0.36 * s * np.sin(t), color=color, lw=0.9, zorder=z + 1)
    ax.add_patch(FancyBboxPatch((cx - 0.5 * s, cy - 0.55 * s), s, 0.68 * s, boxstyle=f"round,pad=0,rounding_size={0.1 * s}",
                                fc=color, ec="none", zorder=z + 2))


def data_stack(ax, cx, cy, w=0.42, h=0.5, z=4):
    """Raw result files: three stacked sheets with rows of cells."""
    for i, d in enumerate((0.07, 0.035, 0.0)):
        x0, y0 = cx - w / 2 + d, cy - h / 2 + d
        ax.add_patch(FancyBboxPatch((x0, y0), w, h, boxstyle="round,pad=0,rounding_size=0.03", fc="white", ec=TEAL,
                                    lw=0.8, zorder=z + i))
    x0, y0 = cx - w / 2, cy - h / 2
    ax.add_patch(Rectangle((x0 + 0.04, y0 + h - 0.12), w - 0.08, 0.07, fc=TEAL, ec="none", zorder=z + 3))
    for r in range(4):
        for c in range(3):
            ax.add_patch(Rectangle((x0 + 0.04 + c * (w - 0.08) / 3 + 0.008, y0 + 0.05 + r * 0.075), (w - 0.08) / 3 - 0.016,
                                   0.05, fc=TEAL_FILL, ec="none", zorder=z + 3))


def neq_badge(ax, cx, cy, r=0.11, z=8):
    ax.add_patch(Circle((cx, cy), r, fc=ROSE_TXT, ec="white", lw=1.0, zorder=z))
    for dy in (-0.3, 0.3):
        ax.plot([cx - 0.45 * r, cx + 0.45 * r], [cy + dy * r, cy + dy * r], color="white", lw=1.3,
                solid_capstyle="round", zorder=z + 1)
    ax.plot([cx - 0.25 * r, cx + 0.25 * r], [cy - 0.62 * r, cy + 0.62 * r], color="white", lw=1.1,
            solid_capstyle="round", zorder=z + 1)


def status(ax, x, y, s, ok, bg):
    """Rule pill with a check or a cross badge at its left end; returns the x after it."""
    color, fill, edge = (TEAL_TXT, "white", TEAL) if ok else (ROSE_TXT, "white", ROSE)
    h = 0.17
    w = text_w(ax, s, MIN_FS) + 0.3
    ax.add_patch(FancyBboxPatch((x, y - h / 2), w, h, boxstyle=f"round,pad=0,rounding_size={h / 2}", fc=fill, ec=edge,
                                lw=0.9, zorder=6))
    (check_badge if ok else cross_badge)(ax, x + 0.1, y, r=0.058, fc=TEAL_TXT if ok else ROSE_TXT, z=7)
    ctext(ax, x + 0.2, y - 0.004, s, color=color, bg=fill, ha="left", va="center", zorder=8)
    return x + w


def chip(ax, x, y, s, color, fill, edge, h=0.16):
    w = text_w(ax, s, MIN_FS) + 0.14
    ax.add_patch(FancyBboxPatch((x, y - h / 2), w, h, boxstyle=f"round,pad=0,rounding_size={h / 2}", fc=fill, ec=edge,
                                lw=0.8, zorder=6))
    ctext(ax, x + 0.07, y - 0.004, s, color=color, bg=fill, ha="left", va="center", zorder=8)
    return x + w


# ---------------------------------------------------------------- placement icons (bottom row), centered on (cx, cy)
def ic_generate(ax, cx, cy):
    """A placeholder chip that the build turns into a number."""
    box(ax, cx - 0.36, cy - 0.085, 0.3, 0.17, fc="white", ec=PURPLE, lw=0.9, r=0.04, z=5)
    ax.text(cx - 0.21, cy - 0.004, "\\val", family=MONO, fontsize=MFS, color=PURPLE, ha="center", va="center", zorder=7)
    arrow(ax, (cx - 0.03, cy), (cx + 0.1, cy), color=PURPLE, lw=1.4, head=3.2)
    box(ax, cx + 0.12, cy - 0.085, 0.26, 0.17, fc=PURPLE, ec=PURPLE, lw=0.9, r=0.04, z=5)
    ax.text(cx + 0.25, cy - 0.004, "81.8", fontsize=MIN_FS, color="white", ha="center", va="center", zorder=7, weight=600)


def ic_gate(ax, cx, cy):
    """A barrier across the edit's path."""
    ax.plot([cx - 0.3, cx - 0.06], [cy, cy], color=ARROW, lw=1.6, solid_capstyle="round", zorder=5)
    ax.add_patch(Polygon([(cx - 0.08, cy + 0.045), (cx - 0.08, cy - 0.045), (cx - 0.01, cy)], closed=True, fc=ARROW,
                         ec="none", zorder=5))
    ax.add_patch(FancyBboxPatch((cx + 0.03, cy - 0.16), 0.07, 0.32, boxstyle="round,pad=0,rounding_size=0.02", fc=PURPLE,
                                ec="none", zorder=6))
    for i in range(3):  # hazard stripes
        ax.add_patch(Rectangle((cx + 0.03, cy - 0.12 + i * 0.105), 0.07, 0.04, fc=GOLD, ec="none", zorder=7))
    cross_badge(ax, cx + 0.24, cy, r=0.07, fc=PURPLE)


def ic_feedback(ax, cx, cy):
    """A speech bubble from the hook."""
    w, h = 0.46, 0.24
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2 + 0.03), w, h, boxstyle="round,pad=0,rounding_size=0.07",
                                fc=PURPLE, ec="none", zorder=5))
    ax.add_patch(Polygon([(cx - 0.12, cy - h / 2 + 0.04), (cx - 0.16, cy - h / 2 - 0.05), (cx - 0.03, cy - h / 2 + 0.04)],
                         closed=True, fc=PURPLE, ec="none", zorder=5))
    for i, f in enumerate((1.0, 0.62)):
        ax.plot([cx - 0.15, cx - 0.15 + 0.3 * f], [cy + 0.085 - i * 0.085, cy + 0.085 - i * 0.085], color="white", lw=1.5,
                solid_capstyle="round", zorder=6)


def ic_tool(ax, cx, cy):
    """A command the agent may run: dashed, because nothing runs unless it asks."""
    w, h = 0.56, 0.2
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle="round,pad=0,rounding_size=0.05", fc="white",
                                ec=AMBER_TXT, lw=0.9, ls=(0, (2.5, 1.6)), zorder=5))
    ax.text(cx, cy - 0.004, "$ check", family=MONO, fontsize=MFS, color=AMBER_TXT, ha="center", va="center", zorder=7)


def ic_audit(ax, cx, cy):
    """A magnifier over the finished paper."""
    tx0, tx1 = page(ax, cx - 0.2, cy - 0.17, 0.28, 0.34, z=4, ec=BLUE_TXT)
    lines(ax, tx0 - 0.02, tx1 + 0.02, [cy + 0.07, cy + 0.0, cy - 0.07], z=5, frac=[0.9, 1.0, 0.6])
    ax.add_patch(Circle((cx + 0.12, cy - 0.02), 0.095, fc="white", ec=BLUE_TXT, lw=1.4, zorder=7, alpha=0.95))
    ax.plot([cx + 0.19, cx + 0.27], [cy - 0.09, cy - 0.17], color=BLUE_TXT, lw=2.0, solid_capstyle="round", zorder=7)


def ic_reviewer(ax, cx, cy):
    reviewer(ax, cx, cy, s=0.34)


def dots(ax, cx, cy, left, bg, n=6, r=0.043, gap=0.115):
    """Six planted errors per paper: filled = still wrong at the end (rounded mean), hollow = removed."""
    k = int(round(left))
    x0 = cx - gap * (n - 1) / 2
    for i in range(n):
        if i < k:
            ax.add_patch(Circle((x0 + i * gap, cy), r, fc=ERROR_TXT, ec=ERROR_TXT, lw=0.8, zorder=6))
        else:
            ax.add_patch(Circle((x0 + i * gap, cy), r, fc="white", ec=LIGHT, lw=0.8, zorder=6))


# ---------------------------------------------------------------- figure
def main():
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    fig.canvas.draw()
    left = errors_left()

    # ======================= top row: three lanes
    LY0, LY1 = 2.06, H - 0.04
    LH = LY1 - LY0
    L1, L2, L3 = (0.04, 1.80), (1.92, 4.72), (4.84, W - 0.04)
    lane(ax, L1[0], LY0, L1[1] - L1[0], LH, BLUE_FILL, BLUE_EDGE, 1, "The agent edits a number")
    lane(ax, L2[0], LY0, L2[1] - L2[0], LH, LAVENDER, LAV_EDGE, 2, "The hook reruns its recipe")
    lane(ax, L3[0], LY0, L3[1] - L3[0], LH, TEAL_FILL, TEAL_EDGE, 3, "The verdict returns")

    # ----- lane 1: reviewer pushes, the agent edits
    bg = BLUE_FILL
    ya = 4.27
    XA, XR = 0.62, 1.45
    agent(ax, XA, ya, w=0.48, h=0.38)
    reviewer(ax, XR, ya, s=0.36)
    arrow(ax, (XR - 0.23, ya), (XA + 0.3, ya), color=ROSE, lw=2.0, head=4.2)
    label(ax, (XA + XR) / 2 + 0.03, ya + 0.1, "Review", bg, color=ROSE_TXT, style="italic", va="bottom")
    label(ax, XA, ya - 0.3, "Writing agent", bg)
    label(ax, XR, ya - 0.3, "Reviewer", bg)

    EX0, EW = 0.26, 1.36
    EY0, EH = 2.92, 0.72
    arrow(ax, (XA, ya - 0.4), (XA, EY0 + EH + 0.03), color=ARROW, lw=2.2, head=4.5)
    top = card(ax, EX0, EY0, EW, EH, "Edit paper/main.tex", DARK)
    for i, (sign, fc_, num, col) in enumerate((("-", DEL_BG, "81.8", INK), ("+", ADD_BG, "84.8", ERROR_TXT))):
        y = top - 0.12 - i * 0.15
        ax.add_patch(Rectangle((EX0 + 0.012, y - 0.07), EW - 0.024, 0.14, fc=fc_, ec="none", zorder=5))
        mono(ax, EX0 + 0.06, y, [(sign + " hits ", INK), (num, col), ("\\%", INK), ("\\src{acc12}", PURPLE)],
             weight="bold" if False else "normal")
    label(ax, EX0 + 0.06, EY0 + 0.115, "The tag names its recipe", CODE_BG, color=MUTED, ha="left",
          style="italic")

    # typical slips (what goes wrong in practice)
    label(ax, EX0, 2.62, "Slips we found in real sessions", bg, color=MUTED, ha="left", style="italic")
    x = EX0
    for s in ("Rounding", "Wrong unit"):
        x = chip(ax, x, 2.42, s, AMBER_TXT, "white", AMBER_EDGE) + 0.05
    x = EX0
    for s in ("Stale note", "Denominator"):
        x = chip(ax, x, 2.22, s, AMBER_TXT, "white", AMBER_EDGE) + 0.05

    # ----- the hook, on the border between lanes 1 and 2
    HX, HY = (L1[1] + L2[0]) / 2, EY0 + EH / 2
    ax.add_patch(Circle((HX, HY), 0.2, fc="white", ec=PURPLE, lw=1.4, zorder=9))
    bob(ax, HX, HY + 0.005, s=0.165, lw=0.55, z=10)
    pill(ax, HX, HY - 0.3, "Hook", PURPLE, fc="white", z=10)

    # ----- lane 2: recipe card, raw data, run, compare, rules
    bg = LAVENDER
    code = [[("@source", PURPLE), ("(", INK), ('"acc12"', TEAL_TXT), (",", INK)],
            [("  means=", INK), ('"accuracy, 12 frames"', TEAL_TXT), (")", INK)],
            [("def ", PURPLE), ("acc12():", INK)],
            [("  d = load(", INK), ('"eval/frames.json"', TEAL_TXT), (")", INK)],
            [("  return ", PURPLE), ("100 * mean(d[", INK), ('"ok"', TEAL_TXT), ("])", INK)]]
    RX0 = L2[0] + 0.32
    RW = max(sum(len(s) for s, _ in ln) for ln in code) * CW + 0.14
    RH = 0.17 + len(code) * 0.135 + 0.1
    RY0 = 4.56 - RH
    top = card(ax, RX0, RY0, RW, RH, "paper/sources.py", PURPLE)
    for i, ln in enumerate(code):
        mono(ax, RX0 + 0.07, top - 0.115 - i * 0.135, ln)
    path_arrow(ax, [(HX + 0.21, HY), (RX0 - 0.13, HY), (RX0 - 0.13, RY0 + 0.3), (RX0 - 0.02, RY0 + 0.3)], color=ARROW,
               lw=2.2, r=0.07, head=4.0)

    # raw data, locked in a snapshot
    DX = (RX0 + RW + L2[1]) / 2 + 0.02
    DY = RY0 + RH - 0.42
    data_stack(ax, DX, DY)
    lock(ax, DX + 0.2, DY - 0.2)
    yl = top - 0.115 - 3 * 0.135
    arrow(ax, (DX - 0.26, yl), (RX0 + RW + 0.03, yl), color=TEAL, lw=1.6, head=3.6, ls=(0, (2.2, 1.4)))
    label(ax, DX, DY - 0.4, "Raw data,", bg, color=TEAL_TXT)
    label(ax, DX, DY - 0.51, "snapshot", bg, color=TEAL_TXT)

    # run, value, compare
    CY = 2.98
    BX = RX0 + 0.14
    arrow(ax, (BX, RY0 - 0.02), (BX, CY + 0.16), color=ARROW, lw=2.2, head=4.0)
    run_badge(ax, BX, CY, r=0.13)
    TA, TB = BX + 0.7, L2[1] - 0.5
    arrow(ax, (BX + 0.16, CY), (TA - 0.4, CY), color=ARROW, lw=2.2, head=4.0)
    tile(ax, TA, CY, "81.8421", PURPLE)
    tile(ax, TB, CY, "84.8", ERROR_TXT)
    neq_badge(ax, (TA + TB) / 2, CY)
    label(ax, TA, CY + 0.235, "Recipe returns", bg)
    label(ax, TB, CY + 0.235, "Paper prints", bg)
    label(ax, (TA + TB) / 2, CY - 0.24, "compared at the printed precision", bg, color=MUTED, style="italic")

    # the three rules
    x = L2[0] + 0.18
    for s, ok in (("Value follows", False), ("Reads raw data", True)):
        x = status(ax, x, 2.47, s, ok, bg) + 0.07
    x = status(ax, L2[0] + 0.18, 2.25, "No typed constant", True, bg) + 0.07
    chip(ax, x, 2.25, "No model call", MUTED, "white", LAV_EDGE, h=0.17)

    # ----- lane 3: the message and the fix
    bg = TEAL_FILL
    MX0, MW = L3[0] + 0.13, L3[1] - L3[0] - 0.26
    msg = [[("84.8", ERROR_TXT), (" (key", INK), ("  acc12", PURPLE), ("): recipe", INK)],
           [("gives", INK), ("  81.8421", PURPLE), (", which does", INK)],
           [("not round to", INK), ("  84.8", ERROR_TXT), (".", INK)],
           [("If the recipe is right,", INK)], [("change the number.", INK)]]
    MH = 0.17 + len(msg) * 0.13 + 0.1
    MY0 = 4.56 - MH
    top = card(ax, MX0, MY0, MW, MH, "Hook to agent", PURPLE, fc="white", mono_head=False)
    for i, ln in enumerate(msg):
        runs(ax, MX0 + 0.08, top - 0.115 - i * 0.13, ln)
    # from the comparison (lane 2) up into the message
    path_arrow(ax, [(TB + 0.39, CY), (L3[0] + 0.02, CY), (L3[0] + 0.02, MY0 + 0.3), (MX0 - 0.02, MY0 + 0.3)],
               color=ARROW, lw=2.2, r=0.07, head=4.0)

    PW, PH = 0.92, 0.6
    PX0 = (L3[0] + L3[1]) / 2 - PW / 2 + 0.06
    PY0 = 2.8
    arrow(ax, (PX0 + PW / 2, MY0 - 0.02), (PX0 + PW / 2, PY0 + PH + 0.04), color=ARROW, lw=2.2, head=4.0)
    tx0, tx1 = page(ax, PX0, PY0, PW, PH)
    yc = PY0 + PH / 2
    lines(ax, tx0, tx1, [yc + 0.19, yc + 0.11], frac=[1.0, 0.8])
    lines(ax, tx0, tx1, [yc - 0.13, yc - 0.21], frac=[0.9, 0.55])
    runs(ax, tx0, yc - 0.01, [("accuracy ", INK), ("81.8%", PURPLE)])
    check_badge(ax, PX0 + PW + 0.02, yc + 0.08, fc=TEAL_TXT)
    label(ax, PX0 + PW / 2, PY0 - 0.13, "The agent fixes it", bg)
    pill(ax, PX0 + PW / 2 - 0.06, 2.42, "No planted error left", TEAL_TXT, fc="white", h=0.17, z=9)
    label(ax, PX0 + PW / 2 - 0.06, 2.26, "in any of 24 papers", bg, color=TEAL_TXT)

    # return to the agent, in the same turn
    yret = 1.93
    xin = 0.13
    path_arrow(ax, [(PX0 + PW + 0.03, yc - 0.16), (L3[1] - 0.12, yc - 0.16), (L3[1] - 0.12, yret), (xin, yret), (xin, ya),
                    (XA - 0.27, ya)],
               color=PURPLE, lw=2.4, r=0.1, head=4.6, z=3)
    pill(ax, 3.3, yret, "The fix lands in the same turn, before the reviewer reads anything", PURPLE, fc="white",
         h=0.17, z=9)

    # ======================= bottom row: six placements
    BY0, BH = 0.04, 1.72
    box(ax, 0.04, BY0, W - 0.08, BH, fc="#FAF8F3", ec="#E0D8C6", lw=1.0, r=0.1, z=0)
    cream = "#FAF8F3"
    ax.text(0.2, BY0 + BH - 0.19, "Where the check can sit", fontsize=7.6 * DISPLAY_SCALE, family=DISPLAY, weight=700,
            color=INK, ha="left", va="center", zorder=7)
    # legend for the dots
    lx = W - 0.2
    label(ax, lx, BY0 + BH - 0.19, "planted error left in the paper (of 6, mean per paper)", cream, color=MUTED,
          ha="right", style="italic")
    wl = text_w(ax, "planted error left in the paper (of 6, mean per paper)", MIN_FS, style="italic")
    ax.add_patch(Circle((lx - wl - 0.1, BY0 + BH - 0.187), 0.043, fc=ERROR_TXT, ec=ERROR_TXT, lw=0.8, zorder=6))

    cards = [("Generate", "The build types it", ic_generate, LAVENDER, LAV_EDGE, PURPLE, left["generate"]),
             ("Gate", "The edit is refused", ic_gate, LAVENDER, LAV_EDGE, PURPLE, left["gate"]),
             ("Feedback", "Told after the edit", ic_feedback, LAVENDER, LAV_EDGE, PURPLE, left["feedback"]),
             ("Tool", "The agent may call it", ic_tool, AMBER_FILL, AMBER_EDGE, AMBER_TXT, left["tool"]),
             ("Audit agent", "Rereads the paper", ic_audit, BLUE_FILL, BLUE_EDGE, BLUE_TXT, left["audit"]),
             ("Reviewer", "Scores the paper", ic_reviewer, SLATE_FILL, SLATE_EDGE, "#465A6E", None)]
    n, gap = len(cards), 0.07
    cw = (W - 0.08 - 0.24 - gap * (n - 1)) / n
    cy0, ch = BY0 + 0.36, 1.02
    xs = [0.04 + 0.12 + i * (cw + gap) for i in range(n)]
    for x0, (name, sub, icon, fc_, ec_, tc, k) in zip(xs, cards):
        box(ax, x0, cy0, cw, ch, fc=fc_, ec=ec_, lw=0.9, r=0.07, z=2)
        cx = x0 + cw / 2
        icon(ax, cx, cy0 + ch - 0.24)
        assert contrast(tc, fc_) >= 4.5, (name, contrast(tc, fc_))
        ax.text(cx, cy0 + ch - 0.52, name, fontsize=7.2, color=tc, ha="center", va="center", zorder=7, weight=600)
        assert text_w(ax, sub, MIN_FS, style="italic") < cw - 0.04, (sub, text_w(ax, sub, MIN_FS, style="italic"), cw)
        label(ax, cx, cy0 + ch - 0.66, sub, fc_, color=MUTED, style="italic")
        if k is not None:
            dots(ax, cx, cy0 + 0.22, k, fc_)
            label(ax, cx, cy0 + 0.09, f"{k:.1f} left" if 0 < k < 10 and round(k, 1) != int(k) else f"{k:.0f} left",
                  fc_)
        else:  # the reviewer names the error but its score moves by about 3 of 100 points
            bw = cw - 0.3
            ax.add_patch(FancyBboxPatch((cx - bw / 2, cy0 + 0.195), bw, 0.05, boxstyle="round,pad=0,rounding_size=0.025",
                                        fc="white", ec=SLATE, lw=0.7, zorder=6))
            ax.add_patch(Rectangle((cx + bw / 2 - 0.03 * bw - 0.01, cy0 + 0.195), 0.03 * bw, 0.05, fc=ERROR_TXT,
                                   ec="none", zorder=7))
            label(ax, cx, cy0 + 0.09, "score moves 3 of 100", fc_)

    # groups in session order
    yb = BY0 + 0.27
    groups = [(0, 2, "At the edit, without being asked", PURPLE), (3, 3, "On request", AMBER_TXT),
              (4, 5, "After the session", SLATE)]
    for a, b, s, c in groups:
        x0, x1 = xs[a] + 0.03, xs[b] + cw - 0.03
        ax.plot([x0, x1], [yb, yb], color=c, lw=1.6, solid_capstyle="round", zorder=5)
        label(ax, (x0 + x1) / 2, yb - 0.12, s, cream, color=c, weight=600)

    save(fig, "fig_overview")


if __name__ == "__main__":
    main()
