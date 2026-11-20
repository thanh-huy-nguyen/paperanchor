"""Placement-study figures of the Plumbline report.

fig5_study:   the full placement study, paper by paper (left) and cost against outcome (right).
fig6_extend:  the two extensions: a writer told to protect its results, and other writer sizes.

Reads pilot/exh4/summary.jsonl and pilot/exh5/summary.jsonl.
Run: python make_placement.py
"""
import json
import os
from collections import defaultdict

import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, to_hex
from matplotlib.patches import FancyBboxPatch, Patch

from make_figures import (DELETED, FEEDBACK, FEEDBACK_TXT, GRAY_NOCHECK, GRAY_TXT, MIN_FS, PROJ, TEXT_W, contrast,
                          ctext, on, save, style_axis, title)
from style import (AMBER, AMBER_TXT, BLUE, BLUE_TXT, BROWN, BROWN_TXT, GRID, INK, LIGHT, MUTED, PURPLE, ROSE_TXT, TEAL,
                   TEAL_TXT)

GENERATE, GENERATE_TXT = "#7A4FB3", "#5E3A93"
# arm, label, color, label color (gray is reserved for "no check")
ARMS = [("none", "No check", GRAY_NOCHECK, GRAY_TXT), ("tool", "Tool in the prompt", AMBER, AMBER_TXT),
        ("random", "Random denial (placebo)", BROWN, BROWN_TXT), ("audit", "Opus audit at the end", BLUE, BLUE_TXT),
        ("feedback", "Feedback (ours)", FEEDBACK, FEEDBACK_TXT), ("gate", "Gate (ours)", PURPLE, PURPLE),
        ("generate", "Generate (ours)", GENERATE, GENERATE_TXT)]
LEFT_KEYS = [f"{k}_{o}" for k in ("flatter", "digit") for o in ("left", "laundered", "other")]
ROSES = LinearSegmentedColormap.from_list("roses", ["#F9DDE5", ROSE_TXT])


def rows(name):
    f = os.path.join(PROJ, "pilot", name, "summary.jsonl")
    return [json.loads(x) for x in open(f)] if os.path.exists(f) else []


def left_of(r, kinds=("flatter", "digit")):
    return sum(r[f"{k}_{o}"] for k in kinds for o in ("left", "laundered", "other"))


def fig5_study():
    R = {(r["repo"], r["seed"], r["arm"]): r for r in rows("exh4")}
    repos = sorted({k[0] for k in R})
    seeds = sorted({k[1] for k in R})
    W, H = TEXT_W, 2.3
    fig = plt.figure(figsize=(W, H))
    # ---- left: one cell per paper
    cell, rgap = 0.118, 0.055
    gx0, gy0 = 1.5, 0.36
    gw = len(repos) * (len(seeds) * cell + rgap) - rgap
    rowh = 0.235
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(0, H); ax.axis("off")
    for i, (arm, lab, col, tc) in enumerate(ARMS):
        y = gy0 + (len(ARMS) - 1 - i) * rowh
        ctext(ax, gx0 - 0.1, y + cell / 2, lab, color=tc, fs=7, ha="right", va="center")
        tot = n = 0
        for j, repo in enumerate(repos):
            for s in seeds:
                r = R.get((repo, s, arm))
                if r is None:
                    continue
                k = left_of(r)
                tot += k; n += 1
                x = gx0 + j * (len(seeds) * cell + rgap) + s * cell
                fc = "white" if k == 0 else to_hex(ROSES((k - 1) / 5))
                ax.add_patch(FancyBboxPatch((x + 0.008, y + 0.008), cell - 0.016, cell + 0.05 - 0.016,
                                            boxstyle="round,pad=0,rounding_size=0.018", fc=fc,
                                            ec=LIGHT if k == 0 else fc, lw=0.5, zorder=2))
                if k:
                    ax.text(x + cell / 2, y + (cell + 0.05) / 2 - 0.003, str(k), fontsize=5.6, ha="center", va="center",
                            color=on(fc), zorder=3)
        ctext(ax, gx0 + gw + 0.3, y + cell / 2 + 0.02, f"{tot / n:.2f}", fs=7, ha="center", va="center",
              color=tc, weight=600)
    for j, _ in enumerate(repos):
        x = gx0 + j * (len(seeds) * cell + rgap) + len(seeds) * cell / 2
        ctext(ax, x, gy0 - 0.1, f"R{j + 1}", ha="center", va="center", color=MUTED)
    ctext(ax, gx0 + gw / 2, gy0 - 0.26, "Repository (three seeds each)", ha="center", va="center")
    ctext(ax, gx0 + gw + 0.3, gy0 - 0.1, "Mean", ha="center", va="center", color=MUTED)
    title(ax, gx0 / W, (gy0 + len(ARMS) * rowh + 0.08) / H, "Planted errors left in each paper, of six")
    # ---- right: cost, as agent turns per paper, on the same rows
    bx0 = gx0 + gw + 0.78
    bmax = W - bx0 - 0.42
    turns = {}
    for i, (arm, lab, col, tc) in enumerate(ARMS):
        y = gy0 + (len(ARMS) - 1 - i) * rowh
        rs = [r for (_, _, a), r in R.items() if a == arm]
        turns[arm] = sum(r["turns"] for r in rs) / len(rs)
        w = bmax * turns[arm] / 24
        ax.add_patch(FancyBboxPatch((bx0, y + 0.012), w, cell + 0.05 - 0.024, boxstyle="round,pad=0,rounding_size=0.03",
                                    fc=col, ec="none", zorder=2))
        ctext(ax, bx0 + w + 0.06, y + cell / 2 + 0.02, f"{turns[arm]:.1f}", fs=7, ha="left", va="center", color=tc,
              weight=600)
    title(ax, bx0 / W, (gy0 + len(ARMS) * rowh + 0.08) / H, "Turns per paper")
    ax.plot([bx0, bx0], [gy0 - 0.02, gy0 + len(ARMS) * rowh - 0.04], color=INK, lw=0.6, zorder=3)
    pts = turns
    save(fig, "fig5_study")
    return pts


OUT_COL = {"corrected": None, "deleted": DELETED, "laundered": TEAL, "left": ROSE_TXT, "other": "white"}


def fig6_extend():
    R = {(r["repo"], r["seed"], r["arm"]): r for r in rows("exh5")}
    for r in rows("exh4"):
        if r["arm"] in ("tool", "feedback", "gate"):
            R[(r["repo"], r["seed"], r["arm"])] = r
    if not any(a.endswith("_defend") for _, _, a in R):
        print("fig6: no exh5 rows yet")
        return
    W, H = TEXT_W, 2.5
    fig = plt.figure(figsize=(W, H))
    panels = [("A writer told to protect its results: flattering errors", ("flatter",),
               [("tool", "Tool", AMBER, AMBER_TXT), ("tool_defend", "Tool, told to protect", AMBER, AMBER_TXT),
                ("feedback", "Feedback", FEEDBACK, FEEDBACK_TXT),
                ("feedback_defend", "Feedback, told to protect", FEEDBACK, FEEDBACK_TXT),
                ("gate", "Gate", PURPLE, PURPLE), ("gate_defend", "Gate, told to protect", PURPLE, PURPLE)]),
              ("Other writers: all planted errors", ("flatter", "digit"),
               [("tool_haiku", "Haiku, tool", AMBER, AMBER_TXT), ("feedback_haiku", "Haiku, feedback", FEEDBACK, FEEDBACK_TXT),
                ("tool", "Sonnet, tool", AMBER, AMBER_TXT), ("feedback", "Sonnet, feedback", FEEDBACK, FEEDBACK_TXT),
                ("tool_opus", "Opus, tool", AMBER, AMBER_TXT), ("feedback_opus", "Opus, feedback", FEEDBACK, FEEDBACK_TXT)])]
    lft, gap, rgt, top, bot = 1.42, 1.18, 0.12, 0.5, 0.36
    pw = (W - 2 * lft - rgt + (lft - gap) - 0.0) / 2
    pw = (W - lft - gap - rgt) / 2
    stats = {}
    for i, (ttl, kinds, arms) in enumerate(panels):
        ax = fig.add_axes([(lft + i * (pw + gap)) / W, bot / H, pw / W, (H - top - bot) / H])
        ys = list(range(len(arms)))[::-1]
        for y, (arm, lab, col, tc) in zip(ys, arms):
            rs = [r for (_, _, a), r in R.items() if a == arm]
            if not rs:
                continue
            n = sum(r[f"n_{k}"] for r in rs for k in kinds)
            x = 0
            stats[(i, arm)] = {}
            for o in ("corrected", "deleted", "laundered", "left", "other"):
                v = sum(r[f"{k}_{o}"] for r in rs for k in kinds)
                stats[(i, arm)][o] = v
                if not v:
                    continue
                fc = col if o == "corrected" else OUT_COL[o]
                share = 100 * v / n
                ax.barh(y, share, 0.66, left=x, color=fc, ec=INK if o == "other" else "white",
                        lw=0.6 if o == "other" else 0.8, hatch="////" if o == "other" else None, zorder=2)
                if share >= 7 and o != "other":
                    ctext(ax, x + share / 2, y, str(v), color=on(fc), bg=fc, ha="center", va="center")
                x += share
            stats[(i, arm)]["n"] = n
        ax.set_xlim(0, 100); ax.set_ylim(-0.5, len(arms) - 0.5)
        ax.set_yticks(ys); ax.set_yticklabels([a[1] for a in arms], fontsize=7)
        for t, a in zip(ax.get_yticklabels(), arms):
            t.set_color(a[3])
        ax.tick_params(axis="y", length=0, pad=4)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_xlabel("Planted errors (%)", fontsize=MIN_FS, labelpad=2)
        style_axis(ax); ax.spines["left"].set_visible(False)
        title(ax, 0.0, 1.03, ttl) if False else ax.text(-lft / pw + 0.02, 1.04, ttl, transform=ax.transAxes,
                                                        fontsize=7.2 * 1.28, family="Cormorant Garamond", weight=600,
                                                        color=INK, ha="left", va="bottom")
    seen = {o for v in stats.values() for o in v if o != "n" and v[o]}   # outcomes that never occur get no legend entry
    handles = [Patch(fc=PURPLE, ec="none", label="Corrected (arm color)"), Patch(fc=DELETED, ec="none", label="Deleted")]
    handles += [Patch(fc=TEAL, ec="none", label="Laundered")] if "laundered" in seen else []
    handles += [Patch(fc=ROSE_TXT, ec="none", label="Left wrong")]
    handles += [Patch(fc="white", ec=INK, lw=0.6, hatch="////", label="Third value")] if "other" in seen else []
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=5, frameon=False, fontsize=MIN_FS,
               handlelength=1.3, handletextpad=0.4, columnspacing=1.4, borderpad=0.25)
    save(fig, "fig6_extend")
    return stats


if __name__ == "__main__":
    print(fig5_study())
    print(fig6_extend())
