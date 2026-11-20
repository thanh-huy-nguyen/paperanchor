"""Shared colors, fonts and drawing helpers for every figure of the PaperAnchor report.

Figure text is set in Source Serif 4, titles in Cormorant Garamond (both SIL Open Font License, in fonts/).
Coordinates of the helper functions are in the units of the axes they draw into (we use inches).
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyArrowPatch
from matplotlib.path import Path
from matplotlib.patches import PathPatch

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")
FONT_FAMILY = "Source Serif 4"
DISPLAY = "Cormorant Garamond"
DISPLAY_SCALE = 1.28                # Cormorant has a small x-height; scale it to sit with Source Serif

# ---------------------------------------------------------------- colors
# A dark, high-contrast academic palette: Northwestern purple for PaperAnchor, deep muted inks for everything else
# (brass, walnut, navy, hunter green, oxblood), parchment panels, and near-black warm text.
PURPLE = "#4E2A84"       # PaperAnchor (ours)
PURPLE_DK = "#2E1A52"    # darkest purple (generate mode, header bars)
PURPLE_MID = "#6C50A2"   # mid purple (feedback mode)
LIGHT = "#A898C6"        # purple companion: light fills and outlines
LAVENDER = "#ECE8F2"; LAV_EDGE = "#8F7DB3"
ARROW = "#2B2530"        # flow arrows: near-black ink
INK = "#1E1A17"; MUTED = "#4B443D"; GRID = "#D9D2C5"
PARCH = "#F5F0E6"; PARCH_EDGE = "#A99A7C"   # parchment panel
SKIN = "#E8C7A6"
AMBER = "#9A6A1F"; AMBER_TXT = "#7A5214"; AMBER_FILL = "#F4EBD8"; AMBER_EDGE = "#B8955A"     # brass: offered tool
TEAL = "#2F5D62"; TEAL_TXT = "#24494D"; TEAL_FILL = "#E3ECEB"; TEAL_EDGE = "#7E9FA1"         # deep teal: passes
ROSE = "#8E2332"; ROSE_TXT = "#7A1D2A"; ROSE_FILL = "#F4E6E4"; ROSE_EDGE = "#B98A8C"         # oxblood: errors
BLUE = "#2D4B73"; BLUE_TXT = "#253F61"; BLUE_FILL = "#E4E8EE"; BLUE_EDGE = "#8797AF"         # navy: audit agents
GREEN = "#3D6B3F"; GREEN_TXT = "#2F5531"                                                     # hunter green
BROWN = "#7A5233"; BROWN_TXT = "#5F3F27"                                                     # walnut: placebo
SLATE = "#4F5D6B"; SLATE_FILL = "#E8E9EA"; SLATE_EDGE = "#97A0A9"                             # reviewer
ERROR_TXT = "#A3202B"    # a wrong number
GOLD = "#A9823A"


def setup():
    from matplotlib import font_manager
    for f in sorted(os.listdir(FONT_DIR)):
        if f.endswith((".ttf", ".otf")):
            font_manager.fontManager.addfont(os.path.join(FONT_DIR, f))
    plt.rcParams.update({
        "font.family": FONT_FAMILY, "font.serif": [FONT_FAMILY], "mathtext.fontset": "custom",
        "mathtext.rm": FONT_FAMILY, "mathtext.it": f"{FONT_FAMILY}:italic", "axes.unicode_minus": True,
        "font.weight": "normal", "font.size": 7, "axes.titleweight": "normal", "axes.labelweight": "normal",
        "axes.labelsize": 7, "xtick.labelsize": 6.5, "ytick.labelsize": 6.5, "legend.fontsize": 6.5,
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "xtick.major.size": 2.5, "ytick.major.size": 2.5, "axes.spines.top": False, "axes.spines.right": False,
        "pdf.fonttype": 42, "ps.fonttype": 42, "savefig.dpi": 300, "mathtext.default": "regular",
        "axes.edgecolor": INK, "xtick.color": INK, "ytick.color": INK, "axes.labelcolor": INK, "text.color": INK,
    })


def number(ax, x, y, k, r=0.075, fc=PURPLE, fs=6.5, z=6):
    """Numbered step badge."""
    ax.add_patch(Circle((x, y), r, fc=fc, ec="none", zorder=z))
    ax.text(x, y - 0.004, str(k), ha="center", va="center", color="white", fontsize=fs, weight=600, zorder=z + 1)


def arrow(ax, p0, p1, color=ARROW, lw=1.3, rad=0.0, z=5, head=None, ls="-"):
    """Straight (or gently curved) flow arrow: a thin shaft and a slim, sharp head scaled to the line width.
    `head` is accepted for old call sites and ignored, so every arrow of the report has the same proportions."""
    a = FancyArrowPatch(p0, p1, arrowstyle="-|>,head_length=0.62,head_width=0.3",
                        connectionstyle=f"arc3,rad={rad}", color=color, lw=lw, capstyle="butt",
                        joinstyle="miter", shrinkA=0, shrinkB=0, zorder=z, mutation_scale=5.5 + 2.6 * lw, linestyle=ls)
    ax.add_patch(a)
    return a


def path_arrow(ax, pts, color=ARROW, lw=1.3, r=0.08, z=5, head=None, ls="-"):
    """Polyline with rounded corners and an arrowhead at the end."""
    pts = [np.asarray(p, float) for p in pts]
    verts, codes = [pts[0]], [Path.MOVETO]
    for a, b, c in zip(pts[:-2], pts[1:-1], pts[2:]):
        u, v = (a - b) / np.linalg.norm(a - b), (c - b) / np.linalg.norm(c - b)
        rr = min(r, 0.45 * np.linalg.norm(a - b), 0.45 * np.linalg.norm(c - b))
        verts += [b + u * rr, b, b + v * rr]
        codes += [Path.LINETO, Path.CURVE3, Path.CURVE3]
    d = (pts[-1] - pts[-2]) / np.linalg.norm(pts[-1] - pts[-2])
    stop = pts[-1] - d * 0.06
    verts.append(stop); codes.append(Path.LINETO)
    ax.add_patch(PathPatch(Path(verts, codes), fc="none", ec=color, lw=lw, capstyle="butt", joinstyle="round",
                           zorder=z, linestyle=ls))
    arrow(ax, stop - d * 0.01, pts[-1], color=color, lw=lw, z=z, head=head)
