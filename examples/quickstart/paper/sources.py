"""Recipes for the numbers in this paper. Each returns the unrounded value printed next to \\src{key}.

`source` and `load(path)` are provided by the checker; do not import or define them. Paths are relative to the
repository root. Read raw results, configs or scripts, never Markdown notes.
"""


@source("acc", means="test accuracy (%) of our model: correct / total")
def acc():
    d = load("results/metrics.json")["ours"]
    return 100 * d["correct"] / d["total"]


@source("gain", means="accuracy gain (points) of our model over the baseline")
def gain():
    d = load("results/metrics.json")
    return 100 * (d["ours"]["correct"] / d["ours"]["total"] - d["baseline"]["correct"] / d["baseline"]["total"])


@source("n_test", means="number of test examples")
def n_test():
    return load("results/metrics.json")["ours"]["total"]
