import json
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evw.sources import check, fill, snapshot  # noqa: E402

PRE = "\\documentclass{article}\n\\providecommand{\\src}[1]{}\n\\begin{document}\n"
END = "\n\\end{document}\n"

RECIPES = '''
@source("acc12", means="accuracy (%) at 12 frames")
def r_a():
    d = load("results/frames.json")
    xs = [v["correct"] for v in d if v["n"] == 12]
    return 100 * sum(xs) / len(xs)

@source("acc12_frac", means="accuracy at 12 frames as a fraction")
def r_b():
    d = load("results/frames.json")
    xs = [v["correct"] for v in d if v["n"] == 12]
    return sum(xs) / len(xs)

@source("gap", means="worst gain")
def r_c():
    return load("results/gain.json")["worst"]

@source("hard", means="hard-coded")
def r_d():
    load("results/gain.json")
    return 66.67

@source("rounded", means="rounds itself")
def r_e():
    return round(load("results/gain.json")["worst"], 1) * 1.0

@source("nofile", means="reads nothing")
def r_f():
    return 2 * 33.335

@source("params", means="encoder parameters")
def r_g():
    return load("results/gain.json")["params"]

@source("from_note", means="reads a prose note")
def r_h():
    return float(load("NOTES.md").split()[-1])

@source("from_new", means="reads a file written later")
def r_i():
    return load("results/late.json")["v"]

@source("gap_val", means="worst gain, filled in")
def r_j():
    return load("results/gain.json")["worst"]
'''


class SourcesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "results").mkdir()
        (root / "paper").mkdir()
        rows = [{"n": 12, "correct": c} for c in [1, 1, 0]] + [{"n": 8, "correct": 1}]
        (root / "results" / "frames.json").write_text(json.dumps(rows))
        (root / "results" / "gain.json").write_text(json.dumps({"worst": -3.0516, "params": 676.6e6}))
        (root / "paper" / "sources.py").write_text(textwrap.dedent(RECIPES))
        self.root = root
        self.old = PRE + "We test four models with 8 frames.\n" + END

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, sentence):
        return check(self.old, PRE + "We test four models with 8 frames. " + sentence + END, self.root)

    def test_correct_percent_passes(self):
        (c,) = self.run_check("With more frames accuracy is 66.7\\%\\src{acc12}.")
        self.assertTrue(c.ok, c.reason)

    def test_fraction_recipe_for_percent_passes(self):
        (c,) = self.run_check("With more frames accuracy is 66.7\\%\\src{acc12_frac}.")
        self.assertTrue(c.ok, c.reason)

    def test_rounding_slip_fails(self):
        (c,) = self.run_check("The worst case loses $-3.0$\\%\\src{gap}.")
        self.assertFalse(c.ok)
        (c,) = self.run_check("The worst case loses $-3.1$\\%\\src{gap}.")
        self.assertTrue(c.ok, c.reason)

    def test_missing_src_fails(self):
        (c,) = self.run_check("With more frames accuracy is 66.7\\%.")
        self.assertFalse(c.ok)
        self.assertIn("no \\src", c.reason)

    def test_hard_coded_and_self_rounded_fail(self):
        (c,) = self.run_check("Accuracy is 66.67\\src{hard}.")
        self.assertFalse(c.ok)
        self.assertIn("hard-codes", c.reason)
        (c,) = self.run_check("The worst case loses $-3.1$\\%\\src{rounded}.")
        self.assertFalse(c.ok)
        self.assertIn("round", c.reason)

    def test_recipe_must_read_data(self):
        (c,) = self.run_check("A value of 66.67\\src{nofile}.")
        self.assertFalse(c.ok)
        self.assertIn("read no data", c.reason)

    def test_suffix_and_unchanged_numbers(self):
        (c,) = self.run_check("The encoder has 676.6M\\src{params} parameters.")
        self.assertTrue(c.ok, c.reason)
        self.assertEqual(check(self.old, self.old, self.root), [])

    def test_key_digits_are_not_numbers(self):
        checks = self.run_check("Accuracy is 66.7\\%\\src{acc12}.")
        self.assertEqual([c.number.text for c in checks], ["66.7"])

    def test_notes_and_new_files_rejected(self):
        (self.root / "NOTES.md").write_text("accuracy 66.7")
        (c,) = self.run_check("Accuracy is 66.7\\%\\src{from_note}.")
        self.assertFalse(c.ok)
        self.assertIn("prose note", c.reason)
        base = snapshot(self.root)
        (self.root / "results" / "late.json").write_text('{"v": 66.7}')
        new = PRE + "We test four models with 8 frames. Accuracy is 66.7\\%\\src{from_new}." + END
        (c,) = check(self.old, new, self.root, baseline=base)
        self.assertFalse(c.ok)
        self.assertIn("did not exist", c.reason)
        (c,) = check(self.old, PRE + "We test four models with 8 frames. Accuracy is 66.7\\%\\src{acc12}." + END,
                     self.root, baseline=base)
        self.assertTrue(c.ok, c.reason)

    def test_tagged_too_rechecks_unchanged_numbers(self):
        tex = PRE + "We test four models with 8 frames. The worst case loses $-3.0$\\%\\src{gap}." + END
        self.assertEqual(check(tex, tex, self.root), [])
        (c,) = check(tex, tex, self.root, tagged_too=True)
        self.assertEqual(c.kind, "tagged")
        self.assertFalse(c.ok)

    def test_val_generate_mode(self):
        tex = PRE + "We test four models with 8 frames. The worst case loses $\\val[1]{gap_val}$\\%." + END
        (c,) = check(self.old, tex, self.root)
        self.assertEqual(c.kind, "val")
        self.assertTrue(c.ok, c.reason)
        self.assertIn("$-3.1$", fill(tex, self.root))
        (c,) = check(self.old, tex.replace("gap_val", "rounded"), self.root)
        self.assertFalse(c.ok)


if __name__ == "__main__":
    unittest.main()
