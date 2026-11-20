"""Plumbline logo: a plumb bob on its line, its tip resting on a decimal point.

A plumb line tells a builder whether a wall is true; the tool tells a writer whether a number is.
Run: python make_logo.py   (writes logo.pdf, logo.png, logo_tile.png and logo.svg)
"""
import os

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon

from style import GOLD, HERE, LAVENDER, LIGHT, PURPLE, setup

setup()
DEEP = "#3B1F66"   # shaded facet of the bob


def bob_outline(top=0.30, shoulder=0.02, tip=-0.80, half=0.36, n=40):
    """Right half of the bob: a short rounded shoulder, then a slightly convex taper to the tip."""
    t = np.linspace(0, 1, n)
    sx = 0.16 + (half - 0.16) * np.sin(t * np.pi / 2)            # shoulder widens from the neck
    sy = top - (top - shoulder) * (1 - np.cos(t * np.pi / 2))
    tx = half * (1 - t) ** 0.82                                   # taper
    ty = shoulder + (tip - shoulder) * t
    return np.r_[np.c_[sx, sy], np.c_[tx, ty]]


def draw(ax, cx=0.0, cy=0.0, s=1.0, lw=1.0, z=2):
    """The bob with its line, in a box of half-size s around (cx, cy); lw scales the stroke widths."""
    T = lambda pts: np.asarray(pts, float) * s + [cx, cy]  # noqa: E731
    right = bob_outline()
    left = right * [-1, 1]
    (x0, y0), (x1, y1) = T([[0, 0.42], [0, 0.9]])
    ax.plot([x0, x1], [y0, y1], color=PURPLE, lw=2.2 * lw, solid_capstyle="round", zorder=z)                     # line
    ax.add_patch(Circle(T([0, 0.9]), 0.075 * s, fc="white", ec=PURPLE, lw=1.8 * lw, zorder=z + 1))               # eye
    ax.add_patch(Polygon(T(np.r_[left, right[::-1]]), closed=True, fc=PURPLE, ec="none", zorder=z + 1))
    ax.add_patch(Polygon(T(np.r_[[[0, 0.30]], right, [[0, -0.80]]]), closed=True, fc=DEEP, ec="none", zorder=z + 2))
    cap = T([-0.17, 0.29])
    ax.add_patch(FancyBboxPatch(cap, 0.34 * s, 0.15 * s, boxstyle=f"round,pad=0,rounding_size={0.05 * s}", fc=GOLD,
                                ec="none", zorder=z + 3))                                                        # cap
    (x0, y0), (x1, y1) = T([[-0.2, -0.02], [-0.07, -0.34]])
    ax.plot([x0, x1], [y0, y1], color=LIGHT, lw=1.6 * lw, solid_capstyle="round", zorder=z + 3)                   # glint
    ax.add_patch(Circle(T([0, -0.9]), 0.07 * s, fc=GOLD, ec="none", zorder=z + 3))                               # the point


def main():
    for name, tile in (("logo", False), ("logo_tile", True)):
        fig = plt.figure(figsize=(1, 1))
        ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(-1, 1); ax.set_ylim(-1, 1); ax.axis("off"); ax.set_aspect("equal")
        if tile:  # rounded lavender tile for the repository avatar and README
            ax.add_patch(FancyBboxPatch((-0.96, -0.96), 1.92, 1.92, boxstyle="round,pad=0,rounding_size=0.4",
                                        fc=LAVENDER, ec="none", zorder=0))
            draw(ax, s=0.76, lw=1.0)
        else:
            draw(ax)
            fig.savefig(os.path.join(HERE, f"{name}.pdf"), transparent=True)
            fig.savefig(os.path.join(HERE, f"{name}.svg"), transparent=True)
        fig.savefig(os.path.join(HERE, f"{name}.png"), dpi=512, transparent=True)
        plt.close(fig)


if __name__ == "__main__":
    main()
