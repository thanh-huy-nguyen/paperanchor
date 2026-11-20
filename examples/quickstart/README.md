# Quickstart: a paper whose numbers recompute

This folder is a tiny project in the layout PaperAnchor expects: raw results in `results/`, the paper in `paper/`, and
one recipe per number in `paper/sources.py`.

```bash
cd examples/quickstart
paperanchor check        # main.tex: 3/3 tagged numbers recompute
paperanchor run          # what each recipe returns, and the files it read
```

Now break a number. Change `81.8\%` to `84.8\%` in `paper/main.tex` and run the check again:

```text
FAIL main.tex:8 84.8 [acc] recipe gives 81.84, which does not round to 84.8 at the printed precision
main.tex: 2/3 tagged numbers recompute
```

Inside Claude Code with the plugin loaded, the same message reaches the agent right after its edit (feedback mode),
or the edit is refused (gate mode). Try it:

```bash
claude --plugin-dir ../..        # from this folder
> In paper/main.tex, add a sentence giving the baseline's accuracy and the spread of our model over seeds.
```

The agent writes a recipe for each new number in `paper/sources.py` before it types the number, and the hook reruns
the recipes on every edit.
