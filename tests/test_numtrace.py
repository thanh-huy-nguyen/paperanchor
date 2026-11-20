import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from paperanchor.numtrace import EvidenceMatcher, build_evidence_index, extract_paper_numbers, gate, trace  # noqa: E402

PAPER = r"""
\documentclass{article}
\usepackage{booktabs}
\begin{document}
\section{Results}
As shown in Table~2 and Fig.~3, our method reaches 81.2\% accuracy on CIFAR-10, compared with 78.9\% for ResNet50
\cite{he2016}. This is a gain of 2.3 points. We train for 200 epochs with a learning rate of 0.001 (Section 4.1).
Our model has 12.5M parameters and was published in 2024.
% 99.9 is a commented-out number and must be ignored
\begin{tabular}{lc}
Ours & 81.2 \\
Baseline & 78.9 \\
\end{tabular}
\end{document}
"""


def _evidence(tmp: Path) -> Path:
    ev = tmp / "results"
    ev.mkdir()
    (ev / "main.csv").write_text("method,acc\nours,0.8123\nresnet50,0.7891\n")
    (ev / "config.json").write_text(json.dumps({"epochs": 200, "lr": 0.001, "params_m": 12.5}))
    return ev


class NumTraceTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.matcher = EvidenceMatcher(build_evidence_index(_evidence(self.tmp)))

    def test_extraction_skips_refs_years_comments_and_names(self):
        texts = [n.text for n in extract_paper_numbers(PAPER)]
        for skipped in ["2", "3", "4.1", "2024", "99.9", "50", "10"]:
            self.assertNotIn(skipped, texts, skipped)
        for kept in ["81.2", "78.9", "2.3", "200", "0.001", "12.5"]:
            self.assertIn(kept, texts, kept)

    def test_trace_rescale_and_derived(self):
        rep = trace(PAPER, self.matcher)
        status = {n.text: n.status for n in rep.numbers}
        self.assertEqual(status["81.2"], "traced")  # 0.8123 x 100, rounded to one decimal
        self.assertEqual(status["0.001"], "traced")
        self.assertEqual(status["2.3"], "derived")  # 81.23 - 78.91 = 2.32
        self.assertEqual(rep.counts.get("untraced", 0), 0, [n.text for n in rep.untraced()])

    def test_gate_blocks_inflated_number_and_allows_rewording(self):
        inflated = PAPER.replace("reaches 81.2\\%", "reaches 83.5\\%")
        d = gate(PAPER, inflated, self.matcher)
        self.assertFalse(d.allow)
        self.assertEqual([v[1].text for v in d.violations], ["83.5"])
        reworded = PAPER.replace("our method reaches", "the proposed model attains")
        self.assertTrue(gate(PAPER, reworded, self.matcher).allow)

    def test_gate_allows_reordered_clauses(self):
        a = "Ours reaches 81.2\\% accuracy, while ResNet50 reaches 78.9\\% accuracy."
        b = "ResNet50 reaches 78.9\\% accuracy, while ours reaches 81.2\\% accuracy."
        self.assertTrue(gate(PAPER.replace("This is a gain", a + " This is a gain"),
                             PAPER.replace("This is a gain", b + " This is a gain"), self.matcher).allow)

    def test_bibliography_ignored(self):
        bib = "\\begin{thebibliography}{9}\\bibitem{a} A. B. Title. \\emph{arXiv:2302.13861}, 2023.\\end{thebibliography}"
        self.assertTrue(gate(PAPER, PAPER.replace("\\end{document}", bib + "\n\\end{document}"), self.matcher).allow)

    def test_gate_tolerates_preexisting_untraced(self):
        base = PAPER.replace("2.3 points", "4.7 points")  # already untraced before the edit
        edited = base.replace("We train", "In all runs we train")
        self.assertTrue(gate(base, edited, self.matcher).allow)


class SciNotationTest(unittest.TestCase):
    def test_latex_scientific_notation(self):
        from paperanchor.numtrace import normalize_sci

        self.assertEqual(normalize_sci("5.45\\times 10^{-5}"), "5.45e-5")
        self.assertEqual(normalize_sci("order of $10^{-14}$"), "order of $1e-14$")
        self.assertEqual(normalize_sci("1.94 \\times 10^{-15}"), "1.94e-15")


if __name__ == "__main__":
    unittest.main()
