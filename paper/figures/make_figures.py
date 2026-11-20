"""Plots for the PaperAnchor technical report (fig2_reviewers, fig3_checkers, fig4_placement).

Every number is read from the pilot result files, except fig3, whose counts come from a hand-labeled table in
notes/07_pilot_log.md (hard-coded below with a pointer to the section).

  fig2_reviewers  pilot/killa/analysis.json (score contrasts, 95% bootstrap CIs, retest noise) and
                  pilot/killa/reviews.jsonl + pilot/killa/versions/<paper>/meta.json (planted-value quotes, recomputed here)
  fig3_checkers   notes/07_pilot_log.md, "At a matched alarm rate, an Opus audit agent matches recompute"
  fig4_placement  pilot/rlive_tempt/<repo>/<arm>/result.json (per planted number: kind and outcome)

Run: python make_figures.py   (writes <name>.pdf and <name>.png next to this file)
"""
import glob
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.abspath(os.path.join(HERE, "..", ".."))  # evidence_writing/
# shared palette, fonts and drawing helpers (style.py; Source Serif 4 + Cormorant Garamond)
sys.path.insert(0, HERE)
from style import (AMBER, AMBER_TXT, BLUE, BLUE_TXT, BROWN, DISPLAY, DISPLAY_SCALE, GOLD, GREEN, INK, LIGHT,  # noqa: E402
                   MUTED, PURPLE, PURPLE_DK, PURPLE_MID, ROSE, ROSE_TXT, SLATE, TEAL, setup)

setup()
TEXT_W = 6.5
GRAY_NOCHECK = "#6E6A64"     # warm gray is reserved for "no check"
GRAY_TXT = "#55514B"
ROSE_LIGHT = "#C4868D"       # 1 wrong number (light companion of oxblood = 5 wrong numbers)
BLUE_LIGHT = "#A9B6C9"       # Opus audit at the strict cutoff (light companion of navy)
FEEDBACK = PURPLE_MID        # mid purple: PaperAnchor feedback mode
FEEDBACK_TXT = PURPLE_MID
GENERATE = PURPLE_DK         # darkest purple: PaperAnchor generate mode
DELETED = "#CDBFA0"          # deleted numbers (tan, not a method color)
CORRECTED = TEAL             # planted error corrected (deep teal, the same in every outcome chart)
OTHER = GOLD                 # planted number changed to a third value
LEFT = ROSE                  # wrong number left in the paper (oxblood)
MIN_FS = 6.5


# ---------------------------------------------------------------- helpers
def _lum(c):
    r, g, b = matplotlib.colors.to_rgb(c)
    f = lambda u: u / 12.92 if u <= 0.03928 else ((u + 0.055) / 1.055) ** 2.4  # noqa: E731
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(fg, bg="white"):
    a, b = sorted([_lum(fg), _lum(bg)], reverse=True)
    return (a + 0.05) / (b + 0.05)


def ctext(ax, x, y, s, color=INK, bg="white", fs=MIN_FS, **kw):
    """Text that refuses colors below WCAG 4.5 on its background and sizes below the print minimum."""
    assert contrast(color, bg) >= 4.5, (s, color, bg, round(contrast(color, bg), 2))
    assert fs >= MIN_FS - 1e-6, (s, fs)
    return ax.text(x, y, s, color=color, fontsize=fs, **kw)


def on(fill):
    """White or ink, whichever reads better on a filled bar segment."""
    return "white" if contrast("white", fill) >= 4.5 else INK


def title(ax, x, y, s, color=INK, fs=7.2, **kw):
    """Panel title in Cormorant Garamond SemiBold, scaled to sit with Source Serif (never used for digits)."""
    assert not re.search(r"\d", s), s
    assert contrast(color) >= 4.5
    kw.setdefault("ha", "left"); kw.setdefault("va", "bottom")
    return ax.text(x, y, s, fontsize=fs * DISPLAY_SCALE, family=DISPLAY, weight=600, color=color,
                   transform=ax.transAxes, **kw)


def wilson(k, n, z=1.96):
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def save(fig, name):
    for ext in ("pdf", "png"):
        fig.savefig(os.path.join(HERE, f"{name}.{ext}"), dpi=300 if ext == "png" else None)
    plt.close(fig)


def style_axis(ax):
    ax.tick_params(labelsize=MIN_FS)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(INK)


# ---------------------------------------------------------------- fig2: reviewers see the wrong number, score barely moves
REVIEWERS = [("haiku", "Haiku"), ("sonnet", "Sonnet"), ("opus", "Opus")]
CONDS = [("clean_minus_vis1", "1 wrong number", ROSE_LIGHT), ("clean_minus_vis5", "5 wrong numbers", ROSE),
         ("clean_minus_del5", "5 numbers deleted", GOLD), ("clean_minus_posctrl2", "No evidence", SLATE)]
# a planted value counts as quoted if it appears as a whole number: no digit or decimal point before it, and no digit
# or decimal-point-plus-digit after it (a sentence-ending period after the value still counts)
QUOTE_RE = r"(?<![\d.]){}(?!\d|\.\d)"


def quote_rates():
    root = os.path.join(PROJ, "pilot", "killa")
    meta = {}
    for f in glob.glob(os.path.join(root, "versions", "*", "meta.json")):
        m = json.load(open(f))
        if m.get("eligible"):
            meta[m["paper"]] = m
    cnt = defaultdict(lambda: [0, 0])
    for line in open(os.path.join(root, "reviews.jsonl")):
        r = json.loads(line)
        rv = r.get("review") or {}
        try:
            float(rv.get("overall"))  # same inclusion rule as the score analysis: parsed reviews with a score
        except (TypeError, ValueError):
            continue
        txt = json.dumps({x: rv.get(x) for x in ("weaknesses", "questions")})
        hit = lambda k: any(re.search(QUOTE_RE.format(re.escape(t["new"])), txt)  # noqa: E731
                            for t in meta[r["paper"]]["targets"][:k])
        v = r["version"]
        if v in ("vis1", "vis5"):
            k = 1 if v == "vis1" else 5
            c = cnt[(r["model"], v)]
            c[0] += hit(k); c[1] += 1
        elif v == "clean":  # coincidence baseline: the would-be planted values, searched in reviews of the clean paper
            for k, tag in ((1, "clean1"), (5, "clean5")):
                c = cnt[(r["model"], tag)]
                c[0] += hit(k); c[1] += 1
    return {k: tuple(v) for k, v in cnt.items()}


def fig2():
    A = json.load(open(os.path.join(PROJ, "pilot", "killa", "analysis.json")))
    Q = quote_rates()
    W, H = TEXT_W, 2.5
    fig = plt.figure(figsize=(W, H))
    lw_, top, bot = 0.56, 0.48, 0.3
    wl, gap, wr = 3.0, 0.66, W - 0.56 - 3.0 - 0.66 - 0.06
    ax = fig.add_axes([lw_ / W, bot / H, wl / W, (H - top - bot) / H])
    bw = 0.19
    for i, (m, _) in enumerate(REVIEWERS):
        for j, (key, _, col) in enumerate(CONDS):
            d = A[m][key]
            x = i + (j - 1.5) * (bw + 0.02)
            lo, hi = d["ci95"]
            ax.bar(x, d["mean"], bw, color=col, ec="none", zorder=2)
            ax.errorbar(x, d["mean"], yerr=[[d["mean"] - lo], [hi - d["mean"]]], fmt="none", ecolor=INK, elinewidth=0.7,
                        capsize=1.6, capthick=0.7, zorder=3)
            # the mean as a short mark, so a bar near zero is still visible, and its value above the interval
            ax.plot([x - bw / 2, x + bw / 2], [d["mean"]] * 2, color=INK, lw=0.9, zorder=4, solid_capstyle="butt")
            mv = round(d["mean"], 1) + 0.0
            ctext(ax, x, hi + 0.22, f"{mv:.1f}".replace("-", "−"), ha="center", va="bottom", fs=MIN_FS, zorder=6,
                  bbox=dict(fc="white", ec="none", pad=1.6))
        rt = A[m]["retest_abs_diff"]
        ax.plot([i - 0.47, i + 0.47], [rt, rt], color=MUTED, lw=1.0, ls=(0, (3, 1.6)), zorder=1.5,
                solid_capstyle="butt")
    ax.axhline(0, color=INK, lw=0.6, zorder=1)
    ax.set_xlim(-0.55, 2.55)
    ax.set_ylim(-2.2, 9.9)
    ax.set_yticks([-2, 0, 2, 4, 6, 8])
    ax.set_yticklabels(["−2", "0", "2", "4", "6", "8"])
    ax.set_xticks(range(3)); ax.set_xticklabels([n for _, n in REVIEWERS], fontsize=7)
    ax.tick_params(axis="x", length=0, pad=4)
    ax.spines["bottom"].set_visible(False)
    ax.set_ylabel("Score drop vs. clean paper\n(points out of 100)", fontsize=MIN_FS, labelpad=3, linespacing=1.15)
    style_axis(ax)
    title(ax, 0.0, 1.02, "The score barely moves")

    # right panel: share of reviews that quote a planted wrong value in their weaknesses or questions
    ax2 = fig.add_axes([(lw_ + wl + gap) / W, bot / H, wr / W, (H - top - bot) / H])
    bw2 = 0.36
    stats = {}
    for i, (m, _) in enumerate(REVIEWERS):
        for j, (v, cl, col) in enumerate([("vis1", "clean1", ROSE_LIGHT), ("vis5", "clean5", ROSE)]):
            k, n = Q[(m, v)]
            kb, nb = Q[(m, cl)]
            stats[(m, v)] = (k, n, kb, nb)
            x = i + (j - 0.5) * (bw2 + 0.04)
            p = 100 * k / n
            lo, hi = (100 * u for u in wilson(k, n))
            ax2.bar(x, p, bw2, color=col, ec="none", zorder=2)
            ax2.errorbar(x, p, yerr=[[p - lo], [hi - p]], fmt="none", ecolor=INK, elinewidth=0.7, capsize=1.6,
                         capthick=0.7, zorder=3)
            ax2.plot(x, 100 * kb / nb, marker="D", ms=3.6, mfc="white", mec=INK, mew=0.6, zorder=5, lw=0, clip_on=False)
            ctext(ax2, x, hi + 2.5, f"{k}/{n}", ha="center", va="bottom", fs=MIN_FS)
    ax2.set_xlim(-0.55, 2.55)
    ax2.set_ylim(0, 112)
    ax2.set_yticks([0, 25, 50, 75, 100])
    ax2.set_xticks(range(3)); ax2.set_xticklabels([n for _, n in REVIEWERS], fontsize=7)
    ax2.tick_params(axis="x", length=0, pad=4)
    ax2.set_ylabel("Reviews quoting a\nwrong value (%)", fontsize=MIN_FS, labelpad=3, linespacing=1.15)
    style_axis(ax2)
    title(ax2, 0.0, 1.02, "Yet the review names it")

    handles = [Patch(fc=c, ec="none", label=lab) for _, lab, c in CONDS]
    handles += [Line2D([], [], color=MUTED, lw=1.0, ls=(0, (3, 1.6)), label="Re-review noise"),
                Line2D([], [], marker="D", ms=3.6, mfc="white", mec=INK, mew=0.6, lw=0, label="Chance quote, clean paper")]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, 1.0), ncol=6, frameon=False, fontsize=MIN_FS,
               handlelength=1.3, handletextpad=0.4, columnspacing=1.1, borderpad=0.25)
    save(fig, "fig2_reviewers")
    return stats


# ---------------------------------------------------------------- fig3: recompute vs. audit agents
# Hard-coded from notes/07_pilot_log.md, section "At a matched alarm rate, an Opus audit agent matches recompute"
# (table columns "Human errors caught (A, B overrides)" of 16 and "Human false alarms"). Matched = audit cutoff set so it
# flags no more correct numbers than recompute (Sonnet p >= 4%, Opus p >= 6%).
CHECKERS = [  # label, errors caught of 16, false alarms (None = not reported), fill, edge, hatch
    ("Recompute", 14, 27, PURPLE, PURPLE, None),
    ("Sonnet audit,\nmatched alarm rate", 9, 10, GREEN, GREEN, None),
    ("Opus audit,\nmatched alarm rate", 12, 10, BLUE, BLUE, None),
    ("Opus audit, p ≥ 50%", 9, 3, BLUE_LIGHT, BLUE, None),
    ("Recompute or\nOpus audit", 16, 31, PURPLE, LIGHT, "////"),
]
N_ERR = 16


def fig3():
    W, H = TEXT_W, 2.3
    fig = plt.figure(figsize=(W, H))
    lft, top, bot, gap = 1.22, 0.36, 0.36, 0.42
    w1 = 2.55
    w2 = W - lft - w1 - gap - 0.12
    h = H - top - bot
    ax1 = fig.add_axes([lft / W, bot / H, w1 / W, h / H])
    ax2 = fig.add_axes([(lft + w1 + gap) / W, bot / H, w2 / W, h / H])
    ys = list(range(len(CHECKERS)))[::-1]
    bh = 0.62
    plt.rcParams["hatch.linewidth"] = 1.4
    for y, (lab, caught, fa, fc, ec, hatch) in zip(ys, CHECKERS):
        for ax, v in ((ax1, caught), (ax2, fa)):
            if v is None:
                ctext(ax, 0.6, y, "not reported", color=MUTED, ha="left", va="center", style="italic")
                continue
            ax.barh(y, v, bh, color=fc, ec=ec, lw=0.9 if hatch or fc != ec else 0, hatch=hatch, zorder=2)
            ctext(ax, v + (0.3 if ax is ax1 else 0.5), y, str(v), ha="left", va="center")
    ax1.axvline(N_ERR, color=INK, lw=0.7, ls=(0, (3, 2)), zorder=1)
    ctext(ax1, N_ERR + 0.3, ys[2], "all\nerrors", ha="left", va="center", color=MUTED, linespacing=1.1)
    for ax, xmax, ticks in ((ax1, 19.5, [0, 4, 8, 12, 16]), (ax2, 35, [0, 10, 20, 30])):
        ax.set_xlim(0, xmax); ax.set_xticks(ticks)
        ax.set_ylim(-0.55, len(CHECKERS) - 0.45)
        ax.set_yticks(ys)
        ax.tick_params(axis="y", length=0, pad=4)
        style_axis(ax)
    ax1.set_yticklabels([c[0] for c in CHECKERS], fontsize=MIN_FS, linespacing=1.1)
    ax2.set_yticklabels([])
    ax1.set_xlabel("Errors caught (of 16)", fontsize=MIN_FS, labelpad=2)
    ax2.set_xlabel("False alarms (count)", fontsize=MIN_FS, labelpad=2)
    title(ax1, 0.0, 1.03, "Errors caught, of those found by human checkers")
    title(ax2, 0.0, 1.03, "False alarms on human-checked rows")
    save(fig, "fig3_checkers")


# ---------------------------------------------------------------- fig4: where the check sits decides what the agent does
ARMS = [("none", "No check", GRAY_NOCHECK, GRAY_TXT), ("log", "Rule in prompt", AMBER, AMBER_TXT),
        ("feedback", "Feedback", FEEDBACK, FEEDBACK_TXT), ("gate", "Gate", PURPLE, PURPLE)]
OUT_FILL = {"corrected": CORRECTED, "deleted": DELETED, "left": LEFT, "other": OTHER}
OUT_LABEL = {"corrected": "Corrected", "deleted": "Deleted", "left": "Left wrong", "other": "Changed to a third value"}
OUTCOMES = ["corrected", "deleted", "left", "other"]  # laundered never occurred; asserted below
KINDS = [("flatter", "Flattering errors"), ("digit", "Neutral slips")]


def placement_counts():
    c = defaultdict(Counter)
    repos = set()
    for f in sorted(glob.glob(os.path.join(PROJ, "pilot", "rlive_tempt", "*", "*", "result.json"))):
        repo, arm = f.split(os.sep)[-3:-1]
        repos.add(repo)
        v2 = f.replace("result.json", "result_v2.json")  # re-scored with tag-free alignment (bench/rlive.py)
        for p in json.load(open(v2 if os.path.exists(v2) else f))["planted"]:
            c[(arm, p["kind"])][p["outcome"]] += 1
    assert all(c[k]["laundered"] == 0 for k in c), "laundered outcomes present: add a segment"
    return c, sorted(repos)


def fig4():
    C, repos = placement_counts()
    W, H = TEXT_W, 2.25
    fig = plt.figure(figsize=(W, H))
    lft, top, bot, gap, rgt = 0.98, 0.5, 0.36, 0.3, 0.1
    n = {k: sum(C[("none", k)].values()) for k, _ in KINDS}
    unit = (W - lft - gap - rgt) / (n["flatter"] + n["digit"])  # same length per planted number in both panels
    h = H - top - bot
    x0 = lft
    axes = []
    for kind, ktitle in KINDS:
        w = unit * n[kind]
        ax = fig.add_axes([x0 / W, bot / H, w / W, h / H])
        axes.append(ax)
        x0 += w + gap
        ys = list(range(len(ARMS)))[::-1]
        for y, (arm, _, col, _) in zip(ys, ARMS):
            cnt = C[(arm, kind)]
            assert sum(cnt.values()) == n[kind], (arm, kind, cnt)
            left = 0
            for o in OUTCOMES:
                v = cnt[o]
                if not v:
                    continue
                fc = OUT_FILL[o]
                ax.barh(y, v, 0.66, left=left, color=fc, ec="white", lw=0.8, zorder=2)
                ctext(ax, left + v / 2, y, str(v), color=on(fc), bg=fc, ha="center", va="center")
                left += v
        ax.set_xlim(0, n[kind])
        ax.set_ylim(-0.5, len(ARMS) - 0.5)
        ax.set_yticks(ys)
        ax.tick_params(axis="y", length=0, pad=4)
        step = 6 if n[kind] > 12 else 3
        ax.set_xticks(range(0, n[kind] + 1, step))
        ax.set_xlabel(f"Planted numbers (of {n[kind]})", fontsize=MIN_FS, labelpad=2)
        style_axis(ax)
        ax.spines["left"].set_visible(False)
        title(ax, 0.0, 1.03, ktitle)
    axes[0].set_yticklabels([a[1] for a in ARMS], fontsize=7)
    for t, (_, _, _, tc) in zip(axes[0].get_yticklabels(), ARMS):
        assert contrast(tc) >= 4.5
        t.set_color(tc)
    axes[1].set_yticklabels([])
    seen = {o for k in C for o, v in C[k].items() if v}
    handles = [Patch(fc=OUT_FILL[o], ec="none", label=OUT_LABEL[o]) for o in OUTCOMES if o in seen]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5 + (lft - rgt) / W / 2, 1.0), ncol=4,
               frameon=False, fontsize=MIN_FS, handlelength=1.3, handletextpad=0.4, columnspacing=1.4, borderpad=0.25)
    save(fig, "fig4_placement")
    return C, repos


if __name__ == "__main__":
    s2 = fig2()
    print("fig2 quote rates (weaknesses + questions):")
    for (m, v), (k, n_, kb, nb) in sorted(s2.items()):
        print(f"  {m:7s} {v}: {k}/{n_} = {100 * k / n_:.1f}%   clean baseline {kb}/{nb} = {100 * kb / nb:.1f}%")
    fig3()
    C, repos = fig4()
    print("fig4 outcomes over", len(repos), "repos:")
    for arm, *_ in ARMS:
        for kind, _ in KINDS:
            print(f"  {arm:8s} {kind:7s} {dict(C[(arm, kind)])}")
