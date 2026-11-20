# Kill test A: analysis plan, fixed before any review is run (2026-11-18)

The question is whether LLM reviewers treat a wrong number any worse than a missing one. If a reviewer scores a paper
with five numbers that contradict its own tables the same as the paper with those five numbers deleted, it is pricing
the presence of evidence and not its correctness. The pilot (notes/07, 0-100 scale) suggested this for Opus on 10
papers. This run decides it on about 60.

## Papers

arXiv papers in cs.LG, cs.CV and cs.CL posted from 2026-09-01, after the reviewers' training cutoff, with at least
two numeric tables (`bench/fetch_arxiv.py`). A paper is eligible if it has an experiments or results section followed
by a conclusion, discussion or limitations section, and at least 5 prose numbers that report a measured result (one
Haiku call labels candidates; settings and counts are excluded) and also appear in a table. Eligibility is decided
by `bench/killa_reviewers.py build` before any review; we take papers in manifest order until 60 are eligible.

## Versions

- clean: the paper as posted, minus comments and bibliography.
- vis5: five such prose numbers shifted (by 2 to 4 points, or about 6% for small values) so they contradict the
  table that still holds the true value. One target per sentence.
- vis1: the first of those five shifts only.
- del5: the same five sentences, rewritten by Haiku without the number and with every other number kept; if three
  rewrites fail that check, the sentence is dropped. The rewrites are stored in each paper's `meta.json`.
- posctrl2: the experiments section and every table removed (positive control).

## Reviews

Haiku, Sonnet and Opus, each in a fresh stateless call with the reviewer prompt of `bench/reviewer_pilot.py`
(0-100 percentile, 50 a typical submission, 75 a likely accept). Every eligible paper gets clean twice and each other
version once. The first 20 eligible papers get clean, vis5 and del5 three times. Scores are averaged within a paper
and version before any contrast.

## Primary endpoint and decision rule

For each reviewer, the paper-level difference d = score(vis5) - score(del5), averaged over papers, with a 90%
bootstrap interval over papers (10,000 resamples; two one-sided tests at alpha 0.05).

- Margin: 3 points on the 0-100 scale, about the test-retest noise of Opus in the pilot (2.7).
- A reviewer is equivalent (wrong numbers priced like missing ones) if the whole 90% interval lies inside
  (-3, +3).
- A reviewer is informative only if its positive control registers: clean - posctrl2 has a mean of at least 10
  points and a 95% interval above zero. An uninformative reviewer cannot pass or fail.
- Kill test A passes if Opus and at least one other informative reviewer are equivalent. If it fails, Exhibit 2
  reports what reviewers do see and shrinks to a paragraph.

## Secondary

clean - vis5, clean - vis1 and clean - del5 with 95% intervals; test-retest noise (mean absolute difference of the
two clean reviews); the share of vis1 and vis5 reviews whose summary, weaknesses or questions quote a planted value,
as a direct measure of detection. All are reported whatever their direction.
