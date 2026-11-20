"""Figure 1 (teaser) of the PaperAnchor report: one writing session, checked by a reviewer vs. recomputed at the edit.

A schematic: the scores (31 -> 30 of 100) are illustrative, not measured; the measured version is fig2_reviewers.
Icons are drawn here (agent terminal card, paper page, reviewer, recipe card, run badge) so all report diagrams match.
Coordinates are inches on a single axes that covers the figure.

Run: python make_concept.py   (writes fig1_teaser.pdf and fig1_teaser.png)
"""
import os
import sys

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from make_figures import MIN_FS, TEXT_W, contrast, ctext, save  # noqa: E402  (also runs the shared font setup)
from style import (ARROW, DISPLAY, DISPLAY_SCALE, ERROR_TXT, INK, LAV_EDGE, LAVENDER, LIGHT, MUTED, PARCH,  # noqa: E402
                   PARCH_EDGE, PURPLE, ROSE, ROSE_TXT, SKIN, SLATE, TEAL, arrow, number)

W, H = TEXT_W, 2.6
ROSE_FILL, ROSE_EDGE = PARCH, PARCH_EDGE      # reviewer row: parchment panel, oxblood title
LINE = "#D3CBBE"                              # placeholder text lines on pages and cards
DARK = "#2B2530"                              # terminal title bar
CARD_BG = "#FBF9F5"                           # recipe card


# ---------------------------------------------------------------- measuring and small helpers
def _w(ax, s, fs, **kw):
    t = ax.text(0, 0, s, fontsize=fs, **kw)
    w = t.get_window_extent(renderer=ax.figure.canvas.get_renderer()).width / ax.figure.dpi
    t.remove()
    return w


def text_w(ax, s, fs, **kw):
    """Advance width of a text in inches, counting leading and trailing spaces (the bounding box drops them)."""
    return _w(ax, "|" + s + "|", fs, **kw) - _w(ax, "||", fs, **kw)


def box(ax, x0, y0, w, h, fc="white", ec=INK, lw=0.8, r=0.05, z=3):
    ax.add_patch(FancyBboxPatch((x0, y0), w, h, boxstyle=f"round,pad=0,rounding_size={r}", fc=fc, ec=ec, lw=lw,
                                zorder=z))


def pill(ax, cx, cy, s, color, fc="white", ec=None, fs=MIN_FS, h=0.15, z=9, style="normal"):
    w = text_w(ax, s, fs, style=style) + 0.14
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle=f"round,pad=0,rounding_size={h / 2}",
                                fc=fc, ec=ec or color, lw=0.8, zorder=z))
    ctext(ax, cx, cy - 0.005, s, color=color, bg=fc, fs=fs, ha="center", va="center", zorder=z + 1, style=style)


def runs(ax, x, y, parts, fs=MIN_FS, bg="white", z=8, ha="left"):
    """A line of text made of (string, color) runs, starting at x (or centered on x)."""
    sp = 0.012 * fs / MIN_FS  # a little extra at run boundaries that are spaces (Source Serif spaces are narrow)
    widths = [text_w(ax, s, fs) + (sp if s.endswith(" ") else 0) for s, _ in parts]
    if ha == "center":
        x -= sum(widths) / 2
    for (s, c), w in zip(parts, widths):
        ctext(ax, x, y, s, color=c, bg=bg, fs=fs, ha="left", va="center", zorder=z)
        x += w
    return x


def stage(ax, cx, y, k, s, fc, bg):
    """Numbered circle and a short label, centered on cx as a unit."""
    r, gap = 0.072, 0.05
    w = text_w(ax, s, 7)
    x0 = cx - (2 * r + gap + w) / 2
    number(ax, x0 + r, y, k, r=r, fc=fc)
    ctext(ax, x0 + 2 * r + gap, y, s, color=INK, bg=bg, fs=7, ha="left", va="center", zorder=7)


def row_title(ax, x, y, s, color, bg):
    assert contrast(color, bg) >= 4.5
    ax.text(x, y, s, fontsize=7.4 * DISPLAY_SCALE, family=DISPLAY, weight=600, color=color, ha="left", va="center")


# ---------------------------------------------------------------- icon set
def agent(ax, cx, cy, w=0.5, h=0.4, z=4):
    """Coding agent: a terminal card with a title bar, a prompt chevron and a cursor block."""
    box(ax, cx - w / 2, cy - h / 2, w, h, fc="white", ec=DARK, lw=0.9, r=0.05, z=z)
    bar = 0.095
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy + h / 2 - bar), w, bar, boxstyle="round,pad=0,rounding_size=0.05",
                                fc=DARK, ec=DARK, lw=0.9, zorder=z + 1))
    ax.add_patch(plt.Rectangle((cx - w / 2, cy + h / 2 - bar), w, bar / 2, fc=DARK, ec="none", zorder=z + 1))
    for i in range(3):
        ax.add_patch(Circle((cx - w / 2 + 0.06 + i * 0.045, cy + h / 2 - bar / 2), 0.014, fc="white", ec="none",
                            zorder=z + 2))
    yb = cy - bar / 2
    ax.plot([cx - 0.15, cx - 0.08, cx - 0.15], [yb + 0.06, yb, yb - 0.06], color=PURPLE, lw=1.6,
            solid_capstyle="round", solid_joinstyle="round", zorder=z + 2)
    ax.add_patch(plt.Rectangle((cx - 0.04, yb - 0.055), 0.07, 0.03, fc=INK, ec="none", zorder=z + 2))
    # a small spark: this terminal is an agent
    sx, sy, s = cx + w / 2 - 0.08, cy - h / 2 + 0.08, 0.045
    star = [(sx, sy + s), (sx + 0.25 * s, sy + 0.25 * s), (sx + s, sy), (sx + 0.25 * s, sy - 0.25 * s), (sx, sy - s),
            (sx - 0.25 * s, sy - 0.25 * s), (sx - s, sy), (sx - 0.25 * s, sy + 0.25 * s)]
    ax.add_patch(Polygon(star, closed=True, fc=LIGHT, ec="none", zorder=z + 2))


def page(ax, x0, y0, w, h, z=4, ec=MUTED):
    """Paper page with a folded corner and placeholder lines; returns the inner text box (x0, x1)."""
    f = 0.1
    pts = [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h - f), (x0 + w - f, y0 + h), (x0, y0 + h)]
    ax.add_patch(Polygon(pts, closed=True, fc="white", ec=ec, lw=0.8, joinstyle="round", zorder=z))
    ax.add_patch(Polygon([(x0 + w - f, y0 + h), (x0 + w - f, y0 + h - f), (x0 + w, y0 + h - f)], closed=True,
                         fc="#E7E0D3", ec=ec, lw=0.8, joinstyle="round", zorder=z + 1))
    return x0 + 0.07, x0 + w - 0.07


def lines(ax, x0, x1, ys, z=5, frac=None):
    for i, y in enumerate(ys):
        e = x1 if frac is None else x0 + (x1 - x0) * frac[i % len(frac)]
        ax.plot([x0, e], [y, y], color=LINE, lw=1.3, solid_capstyle="round", zorder=z)


def reviewer(ax, cx, cy, s=0.36, z=6):
    """Reviewer: head and shoulders in a white disc, with a pen."""
    ax.add_patch(Circle((cx, cy), 0.5 * s, fc="white", ec=SLATE, lw=0.9, zorder=z - 1))
    ax.add_patch(FancyBboxPatch((cx - 0.27 * s, cy - 0.36 * s), 0.54 * s, 0.3 * s, boxstyle=f"round,pad={0.07 * s}",
                                fc=SLATE, ec="none", zorder=z))
    ax.add_patch(Circle((cx, cy + 0.15 * s), 0.15 * s, fc=SKIN, ec="none", zorder=z + 1))
    ax.plot([cx - 0.09 * s, cx + 0.09 * s], [cy + 0.17 * s, cy + 0.17 * s], color=INK, lw=0.6, zorder=z + 2)  # glasses
    for dx in (-0.055, 0.055):
        ax.add_patch(Circle((cx + dx * s, cy + 0.165 * s), 0.04 * s, fc="none", ec=INK, lw=0.6, zorder=z + 2))


def check_badge(ax, cx, cy, r=0.085, fc=TEAL, z=10):
    ax.add_patch(Circle((cx, cy), r, fc=fc, ec="white", lw=1.0, zorder=z))
    ax.plot([cx - 0.42 * r, cx - 0.1 * r, cx + 0.45 * r], [cy + 0.0 * r, cy - 0.33 * r, cy + 0.38 * r], color="white",
            lw=1.4, solid_capstyle="round", solid_joinstyle="round", zorder=z + 1)


def cross_badge(ax, cx, cy, r=0.085, fc=ROSE_TXT, z=10):
    ax.add_patch(Circle((cx, cy), r, fc=fc, ec="white", lw=1.0, zorder=z))
    for sg in (-1, 1):
        ax.plot([cx - 0.38 * r, cx + 0.38 * r], [cy - sg * 0.38 * r, cy + sg * 0.38 * r], color="white", lw=1.4,
                solid_capstyle="round", zorder=z + 1)


def run_badge(ax, cx, cy, r=0.13, z=8):
    """The hook: a purple disc with a play triangle (it runs the recipe)."""
    ax.add_patch(Circle((cx, cy), r, fc=PURPLE, ec="white", lw=1.0, zorder=z))
    s = 0.5 * r
    ax.add_patch(Polygon([(cx - 0.35 * s, cy - 0.6 * s), (cx - 0.35 * s, cy + 0.6 * s), (cx + 0.7 * s, cy)],
                         closed=True, fc="white", ec="white", lw=0.8, joinstyle="round", zorder=z + 1))


def strike(ax, x0, x1, y, color, z=9):
    ax.plot([x0, x1], [y, y], color=color, lw=0.8, zorder=z)


# ---------------------------------------------------------------- figure
def main():
    fig = plt.figure(figsize=(W, H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    fig.canvas.draw()

    PX0, PX1 = 0.04, W - 0.04
    rows = [(H - 0.04, ROSE_FILL, ROSE_EDGE), (H / 2 - 0.03, LAVENDER, LAV_EDGE)]
    RH = H / 2 - 0.07
    for top, fc, ec in rows:
        box(ax, PX0, top - RH, PX1 - PX0, RH, fc=fc, ec=ec, lw=0.9, r=0.09, z=0)

    # shared layout (inches): agent | page | (recipe card) | reviewer or hook + its card | outcome
    XA = 0.5                      # agent center
    PG0, PW, PH = 1.02, 0.86, 0.6  # first page
    BX = 3.7                      # reviewer / hook badge center
    CX0, CW = 3.92, 0.94          # review / hook message card
    XD = 5.8                      # outcome column center

    # ======================= top row: the reviewer is the check
    top, bg = rows[0][0], ROSE_FILL
    row_title(ax, 0.16, top - 0.15, "Reviewer as the check", ROSE_TXT, bg)
    ctext(ax, PX1 - 0.12, top - 0.15, "Schematic, illustrative scores", color=MUTED, bg=bg, ha="right", va="center",
          style="italic")
    cy = top - 0.57
    ys = top - 1.0  # stage labels
    agent(ax, XA, cy)
    stage(ax, XA, ys, 1, "Agent edits", ROSE_TXT, bg)
    arrow(ax, (XA + 0.31, cy), (PG0 - 0.06, cy))

    tx0, tx1 = page(ax, PG0, cy - PH / 2, PW, PH)
    lines(ax, tx0, tx1, [cy + 0.19, cy + 0.11], frac=[1.0, 0.8])
    lines(ax, tx0, tx1, [cy - 0.13, cy - 0.21], frac=[0.9, 0.55])
    runs(ax, tx0, cy - 0.01, [("accuracy ", INK), ("84.8%", ERROR_TXT)])
    stage(ax, PG0 + PW / 2, ys, 2, "Wrong number", ROSE_TXT, bg)

    # long arrow: the reviewer reads the paper only after drafting
    a0, a1 = PG0 + PW + 0.08, BX - 0.26
    arrow(ax, (a0, cy), (a1, cy), ls=(0, (3.0, 2.2)))   # dashed: time passes before the review
    ctext(ax, (a0 + a1) / 2, cy + 0.08, "after the draft is done", color=MUTED, bg=bg, ha="center", va="bottom",
          style="italic")

    reviewer(ax, BX, cy, s=0.36)
    chh = 0.5
    box(ax, CX0, cy - chh / 2, CW, chh, fc="white", ec=SLATE, lw=0.8, r=0.05, z=4)
    ctext(ax, CX0 + 0.07, cy + 0.15, "Weakness", color=MUTED, ha="left", va="center", zorder=6, style="italic")
    runs(ax, CX0 + 0.07, cy + 0.0, [("84.8% ", ERROR_TXT), ("contradicts", INK)])
    ctext(ax, CX0 + 0.07, cy - 0.14, "Table 2", color=INK, ha="left", va="center", zorder=6)
    stage(ax, (BX - 0.18 + CX0 + CW) / 2, ys, 3, "Review flags it", ROSE_TXT, bg)
    arrow(ax, (CX0 + CW + 0.06, cy), (XD - 0.46, cy))

    runs(ax, XD, cy + 0.06, [("31", INK), (" → ", MUTED), ("30", INK)], fs=12, bg=bg, ha="center")
    ctext(ax, XD, cy - 0.15, "score out of 100", color=MUTED, bg=bg, ha="center", va="center")
    cross_badge(ax, XD + 0.5, cy + 0.07)
    stage(ax, XD, ys, 4, "Score barely moves", ROSE_TXT, bg)

    # ======================= bottom row: recompute at the edit
    top, bg = rows[1][0], LAVENDER
    row_title(ax, 0.16, top - 0.15, "Recompute at the edit", PURPLE, bg)
    ctext(ax, PX1 - 0.12, top - 0.15, "PaperAnchor", color=PURPLE, bg=bg, ha="right", va="center", style="italic")
    cy = top - 0.57
    ys = top - 1.0
    agent(ax, XA, cy)
    stage(ax, XA, ys, 1, "Agent edits", PURPLE, bg)
    arrow(ax, (XA + 0.31, cy), (PG0 - 0.06, cy))

    # page with the tagged number, and its recipe card
    tx0, tx1 = page(ax, PG0, cy - PH / 2, PW, PH)
    lines(ax, tx0, tx1, [cy + 0.19, cy + 0.11], frac=[1.0, 0.8])
    lines(ax, tx0, tx1, [cy - 0.21], frac=[0.55])
    runs(ax, tx0, cy + 0.0, [("accuracy ", INK), ("84.8%", ERROR_TXT)])
    ctext(ax, tx0, cy - 0.11, r"\src{acc}", color=PURPLE, ha="left", va="center", zorder=8)
    code = ["def acc():", '  load("eval/results.json")', "  ...", "  return acc"]
    rw = max(text_w(ax, s, MIN_FS) for s in code) + 0.14
    rx0, rh = PG0 + PW + 0.04, 0.5
    ry0 = cy - rh / 2
    box(ax, rx0, ry0, rw, rh, fc=CARD_BG, ec=PURPLE, lw=0.9, r=0.05, z=6)
    for i, s in enumerate(code):
        ctext(ax, rx0 + 0.07, ry0 + rh - 0.095 - i * 0.104, s, color=INK, bg=CARD_BG, ha="left", va="center",
              zorder=7)
    stage(ax, (PG0 + rx0 + rw) / 2, ys, 2, "Number and recipe", PURPLE, bg)

    # the hook runs the recipe at the edit
    arrow(ax, (rx0 + rw + 0.06, cy), (BX - 0.19, cy))
    run_badge(ax, BX, cy)
    mh = 0.27
    box(ax, CX0, cy - 0.02, CW, mh, fc="white", ec=PURPLE, lw=0.8, r=0.05, z=4)
    runs(ax, CX0 + 0.07, cy + 0.17, [("recipe gives ", INK), ("81.84", PURPLE), (",", INK)])
    runs(ax, CX0 + 0.07, cy + 0.06, [("printed ", INK), ("84.8", ERROR_TXT)])
    pill(ax, CX0 + CW / 2, cy - 0.17, "Feedback or deny", PURPLE)
    stage(ax, (BX - 0.13 + CX0 + CW) / 2, ys, 3, "Hook recomputes", PURPLE, bg)
    arrow(ax, (CX0 + CW + 0.06, cy), (XD - 0.55, cy))

    # fixed page
    fw = 0.86
    fx0 = XD - fw / 2 - 0.06
    tx0, tx1 = page(ax, fx0, cy - PH / 2, fw, PH)
    lines(ax, tx0, tx1, [cy + 0.19, cy + 0.11], frac=[1.0, 0.8])
    lines(ax, tx0, tx1, [cy - 0.13, cy - 0.21], frac=[0.9, 0.55])
    runs(ax, tx0, cy - 0.01, [("accuracy ", INK), ("81.8%", PURPLE)])
    check_badge(ax, fx0 + fw + 0.03, cy + 0.07)
    stage(ax, fx0 + fw / 2, ys, 4, "Agent fixes it", PURPLE, bg)

    save(fig, "fig1_teaser")


if __name__ == "__main__":
    main()
