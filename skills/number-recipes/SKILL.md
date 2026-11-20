---
name: number-recipes
description: Use when writing or revising numbers in a LaTeX paper (paper/*.tex) inside a repository that has paper/sources.py, or when the user asks to make a paper's numbers checkable against the repository's data. Explains the \src tag and recipe convention that the Plumbline hooks check.
---

# Numbers that recompute from the data

In this repository every number in `paper/*.tex` is tied to a recipe that recomputes it from raw data. Hooks run the
recipes at each edit and report (or, in gate mode, refuse) any number that does not follow at its printed precision.

## Adding or changing a number

1. Find the raw source first: a results JSON/CSV, a log, a config, or the script that sets the value. Markdown,
   READMEs and notes are not evidence.
2. Write the recipe in `paper/sources.py` before editing the paper:

   ```python
   @source("acc12", means="test accuracy (%) of our model with 12 frames, mean over seeds")
   def acc12():
       d = load("eval_results/frames.json")      # relative to the repository root
       xs = [v["correct"] for v in d.values() if v["num_frames"] == 12]
       return 100 * sum(xs) / len(xs)             # unrounded; the checker rounds
   ```

   `source` and `load` are provided; do not import or define them. One function per key. No rounding and no
   hard-coded printed values inside a recipe.
3. Print the number with its tag right after it (after `\%` if present): `70.4\%\src{acc12}`. Or write
   `\val[1]{acc12}` and let `plumbline fill` insert the value.
4. Check: `plumbline check`. To see values: `plumbline run acc12`.

The paper's preamble needs `\providecommand{\src}[1]{}` and `\providecommand{\val}[2][1]{}`.

## When a number fails

The message gives the recipe's value and the printed one. First make sure the recipe computes exactly the quantity the
sentence claims (same split, metric, unit, aggregation). If it does, the text is wrong: change the number. Never edit a
recipe just so it reproduces a printed number; if the data cannot support a claim, reword or remove the claim.

## Setting up a new paper

Run `plumbline init` at the repository root. It creates `paper/sources.py` (which turns the hooks on for this project)
and snapshots the repository so recipes can only read files that existed before the session.
