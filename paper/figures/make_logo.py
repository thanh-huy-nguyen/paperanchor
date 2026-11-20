"""PaperAnchor logo: an anchor whose crown rests on a decimal point.

An anchor holds a ship to the ground below it; the tool holds every number to the data it came from.
Run: python make_logo.py   (writes logo.pdf, logo.png, logo_tile.png and logo.svg)
"""
import os

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Polygon

from style import GOLD, HERE, LAVENDER, LIGHT, PURPLE, setup

setup()
DEEP = "#3B1F66"   # shaded side of the arms


def draw(ax, cx=0.0, cy=0.0, s=1.0, lw=1.0, z=2):
    """The anchor in a box of half-size s around (cx, cy); lw scales the stroke widths."""
    T = lambda pts: np.asarray(pts, float) * s + [cx, cy]  # noqa: E731
    # arms: a thick crescent under the shank (outer and inner arcs of one circle band)
    c, r_out, r_in = np.array([0.0, 0.02]), 0.66, 0.53
    a = np.radians(np.linspace(198, 342, 60))
    outer = c + r_out * np.c_[np.cos(a), np.sin(a)]
    inner = c + r_in * np.c_[np.cos(a[::-1]), np.sin(a[::-1])]
    ax.add_patch(Polygon(T(np.r_[outer, inner]), closed=True, fc=PURPLE, ec="none", zorder=z + 1))
    half = a > np.radians(270)                                           # right half in the shaded tone
    ax.add_patch(Polygon(T(np.r_[outer[half], inner[::-1][half][::-1]]), closed=True, fc=DEEP, ec="none", zorder=z + 2))
    # flukes: arrowheads at both arm tips, pointing up and out
    for sgn in (-1, 1):
        ang = np.radians(198 if sgn < 0 else 342)
        mid = c + (r_out + r_in) / 2 * np.array([np.cos(ang), np.sin(ang)])
        tip = mid + np.array([sgn * 0.10, 0.30])
        base_l = mid + np.array([-0.15, -0.02])
        base_r = mid + np.array([0.15, -0.02])
        ax.add_patch(Polygon(T([base_l, tip, base_r]), closed=True, fc=PURPLE if sgn < 0 else DEEP, ec="none",
                             zorder=z + 2))
    # shank, from the ring down to the crown
    ax.add_patch(FancyBboxPatch(T([-0.065, -0.56]), 0.13 * s, 1.18 * s,
                                boxstyle=f"round,pad=0,rounding_size={0.05 * s}", fc=PURPLE, ec="none", zorder=z + 3))
    ax.add_patch(FancyBboxPatch(T([0.0, -0.56]), 0.065 * s, 1.18 * s,
                                boxstyle=f"round,pad=0,rounding_size={0.03 * s}", fc=DEEP, ec="none", zorder=z + 3))
    # stock: the gold crossbar
    ax.add_patch(FancyBboxPatch(T([-0.34, 0.40]), 0.68 * s, 0.13 * s,
                                boxstyle=f"round,pad=0,rounding_size={0.06 * s}", fc=GOLD, ec="none", zorder=z + 4))
    # ring
    ax.add_patch(Circle(T([0, 0.76]), 0.13 * s, fc="white", ec=PURPLE, lw=2.4 * lw, zorder=z + 4))
    (x0, y0), (x1, y1) = T([[-0.48, -0.18], [-0.40, -0.36]])
    ax.plot([x0, x1], [y0, y1], color=LIGHT, lw=1.4 * lw, solid_capstyle="round", zorder=z + 4)                   # glint
    ax.add_patch(Circle(T([0, -0.86]), 0.075 * s, fc=GOLD, ec="none", zorder=z + 4))                             # the point


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
