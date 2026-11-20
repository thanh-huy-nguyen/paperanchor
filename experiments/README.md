# AnchorBench: the experiments behind the paper

This folder holds what is needed to inspect and rerun the studies of the technical report: the harness as it was run,
the analysis plans that were fixed in advance, the identifiers of the papers and repositories, and the per-session
outcomes. The third-party papers and repositories are listed by arXiv identifier and are not redistributed, and the
texts of the model reviews of those papers are left out; their scores are included.

| Paper section | Script (`harness/bench/`) | Plan (`plans/`) | Results (`results/`) |
|---|---|---|---|
| Reviewers name the wrong number but keep the score | `fetch_arxiv.py`, `killa_reviewers.py` | `reviewer_study.md` | `reviewers/` |
| Agents compute their new numbers; recompute, lookup and audit agents compared | `writing_loop_pressure.py`, `replay_recipes.py`, `killc_audit.py`, `human_score.py` | | `checkers/` |
| A check works when it runs by itself at the edit | `exh4.py` (uses `rlive.py`, `rlive_tempt.py`) | `placement_study.md` | `placement/`, `pilot_placement/`, `pilot_flattering/` |
| A writer told to protect its results; other writer sizes | `exh5.py` | `extensions.md` | `extensions/` |

The plans use the working names of the project: kill test A is the reviewer study, Exhibit 4 the placement study, and
Exhibit 5 its extensions.

## Layout

- `harness/` is the research code as run: `bench/` (one script per study), `evw/` (the checker and the model-call
  wrapper), `hooks/evidence_gate.py` (the hook, including the random-denial placebo mode), `bin/run_recipe.py`.
  The released tool in `paperanchor/` at the repository root is the same checker and hook, packaged, with three later
  fixes to how typeset numbers are read (`1{,}559`, `$-$6.0`, and the same digits with two signs on one line).
- `plans/` are the analysis plans, unchanged since they were written.
- `manifests/` list the 60 arXiv papers of the reviewer study, the 10 repositories of the writing study and the 8 of
  the placement study.
- `results/` holds one JSON line per session (`summary.jsonl`) and the analysis output (`analysis.json`) for each
  study.

## Rerunning

The harness calls models through the Claude Code command line (`claude -p`) and writes to a `pilot/` folder next to
`harness/`. A rerun fetches the papers and repositories named in `manifests/` first. For example, the placement study:

```bash
cd harness
python3 bench/exh4.py run --arms none,tool,feedback,gate,generate,audit --seeds 0,1,2
python3 bench/exh4.py run --arms random --seeds 0,1,2      # after gate: uses its denial rate
python3 bench/exh4.py analyze
```

Each row of `results/placement/summary.jsonl` is one paper under one placement: the outcome of every planted error
(corrected, deleted, laundered, left, other, for flattering and neutral errors), the numbers the agent added, its
turns, and the hook's denials and messages.
