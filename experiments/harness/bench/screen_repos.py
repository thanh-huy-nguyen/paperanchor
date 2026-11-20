"""Screen candidate repos: does the repo's results folder actually support the paper's numbers?

For each candidate: download the arXiv LaTeX source and the repo's result files, remove tables from the paper,
and trace the prose numbers against the repo files. Keeps repos where at least --min-share of the informative prose
numbers are traced or derived.
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.fetch_arxiv import fetch_source, main_tex  # noqa: E402
from bench.tex_tables import split_paper  # noqa: E402
from evw.numtrace import EvidenceMatcher, build_evidence_index, trace  # noqa: E402


def download(repo: str, path: str, dest: Path) -> bool:
    url = f"https://raw.githubusercontent.com/{repo}/HEAD/{urllib.request.quote(path)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "evidence-writing-research/0.1"}), timeout=60) as r:
            data = r.read()
    except Exception:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidates")
    ap.add_argument("--min-share", type=float, default=0.25)
    ap.add_argument("--max-files", type=int, default=150)
    args = ap.parse_args()
    cand_path = Path(args.candidates)
    root = cand_path.parent
    rows = []
    for line in open(cand_path):
        m = json.loads(line)
        d = root / m["id"]
        if not (d / "src").exists():
            time.sleep(3)
            try:
                fetch_source(m["id"], d / "src")
            except Exception as e:
                print(m["id"], "no source:", e)
                continue
        mt = main_tex(d / "src")
        if not mt:
            print(m["id"], "no main tex")
            continue
        ev = d / "repo_results"
        if not ev.exists():
            for p in m["result_files"][: args.max_files]:
                download(m["repo"], p, ev / p)
        paper_tables = d / "paper_tables"
        prose, k = split_paper(mt, paper_tables)
        (d / "prose.tex").write_text(prose)
        rep = trace(prose, EvidenceMatcher(build_evidence_index(ev)))
        c = rep.counts
        tot = sum(c.values()) or 1
        share = (c.get("traced", 0) + c.get("derived", 0)) / tot
        # how many of the paper's own table values appear in the repo files (a second, prose-free signal)
        tab_idx = build_evidence_index(paper_tables / "results") if (paper_tables / "results").exists() else []
        repo_vals = {round(e.value, 4) for e in build_evidence_index(ev)}
        tab_hits = sum(1 for e in tab_idx if round(e.value, 4) in repo_vals or round(e.value / 100, 4) in repo_vals)
        tab_share = tab_hits / max(len(tab_idx), 1)
        m.update({"main_tex": str(mt.relative_to(root)), "prose_numbers": tot, "prose_share": round(share, 3),
                  "table_values": len(tab_idx), "table_share_in_repo": round(tab_share, 3)})
        rows.append(m)
        print(f"{m['id']:12s} {m['repo'][:40]:40s} prose {tot:4d} traced+derived {100 * share:5.1f}%  "
              f"paper-table values found in repo {100 * tab_share:5.1f}% of {len(tab_idx)}", flush=True)
    keep = [r for r in rows if r["prose_share"] >= args.min_share and r["table_share_in_repo"] >= args.min_share]
    with (root / "manifest.jsonl").open("w") as f:
        for r in keep:
            f.write(json.dumps(r) + "\n")
    print(f"kept {len(keep)} of {len(rows)}")


if __name__ == "__main__":
    main()
