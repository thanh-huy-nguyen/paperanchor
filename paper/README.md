# Paper

`plumbline.pdf` is the technical report. To rebuild it from source:

```bash
tectonic -X compile main.tex        # or: latexmk -xelatex main.tex
```

The figure scripts in `figures/` need matplotlib and read the experiment outputs under `pilot/` at the
root of the working tree in which the experiments were run (see `experiments/README.md`); the summaries
they need for the placement figures are in `experiments/results/`. The rendered PDFs are included, so the
paper builds without rerunning them. Figure text is set in Source Serif 4 and Cormorant Garamond
(`figures/fonts/`, SIL Open Font License); code is set in DejaVu Sans Mono (`fonts/`).
