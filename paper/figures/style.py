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
PURPLE = "#4E2A84"       # PaperAnchor (ours)
LIGHT = "#B6ACD1"        # purple companion: light fills
LAVENDER = "#ECE6F6"; LAV_EDGE = "#BDB0DC"
ARROW = "#5E5482"        # flow arrows
INK = "#17121C"; MUTED = "#4A4352"; GRID = "#DCD6E4"
SKIN = "#F1D2B6"
AMBER = "#D98200"; AMBER_TXT = "#9A5800"; AMBER_FILL = "#FFF1D6"; AMBER_EDGE = "#F2C46B"
TEAL = "#119184"; TEAL_TXT = "#0B6B62"; TEAL_FILL = "#E2F4F1"; TEAL_EDGE = "#8FCFC6"
ROSE = "#D2457A"; ROSE_TXT = "#B02E5C"; ROSE_FILL = "#FCEFF3"; ROSE_EDGE = "#EBB8CB"
BLUE = "#3B72C4"; BLUE_TXT = "#2F62AA"; BLUE_FILL = "#E8EFFA"; BLUE_EDGE = "#A9C1E8"
GREEN = "#5A9A2E"; GREEN_TXT = "#3F7F24"
BROWN = "#A8683A"; BROWN_TXT = "#8A5A33"
SLATE = "#5D7389"; SLATE_FILL = "#EBF0F4"; SLATE_EDGE = "#B9C6D3"
ERROR_TXT = "#C8320C"    # a wrong number
GOLD = "#C9A045"


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


def arrow(ax, p0, p1, color=ARROW, lw=2.4, rad=0.0, z=5, head=5.0, ls="-"):
    a = FancyArrowPatch(p0, p1, arrowstyle=f"-|>,head_length={head * 0.11},head_width={head * 0.08}",
                        connectionstyle=f"arc3,rad={rad}", color=color, lw=lw, capstyle="round",
                        joinstyle="round", shrinkA=0, shrinkB=0, zorder=z, mutation_scale=10, linestyle=ls)
    ax.add_patch(a)
    return a


def path_arrow(ax, pts, color=PURPLE, lw=2.6, r=0.12, z=5, head=5.0, ls="-"):
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
    ax.add_patch(PathPatch(Path(verts, codes), fc="none", ec=color, lw=lw, capstyle="round", joinstyle="round",
                           zorder=z, linestyle=ls))
    arrow(ax, stop - d * 0.01, pts[-1], color=color, lw=lw, z=z, head=head)
