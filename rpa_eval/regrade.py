"""Re-run grade() over the stored snapshot of every trial and rewrite `failures` in place.

  python -m rpa_eval.regrade runs/*/trials.jsonl results/data/*.jsonl.gz

Infra-error rows have no snapshot and are left untouched. Prints every trial whose codes changed,
which is the list results/GRADER_CHANGES.md needs.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

from .graders import grade
from .scenarios_paraphrase import ALL_BY_ID


def read_rows(path) -> list[dict]:
    p = Path(path)
    text = gzip.open(p, "rt", encoding="utf-8").read() if p.suffix == ".gz" else p.read_text(encoding="utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def write_rows(path, rows: list[dict]) -> None:
    p = Path(path)
    body = "".join(json.dumps(r) + "\n" for r in rows)
    if p.suffix == ".gz":
        with gzip.open(p, "wt", encoding="utf-8") as f:
            f.write(body)
    else:
        p.write_text(body, encoding="utf-8")


def regrade_rows(rows: list[dict]) -> list[tuple[dict, list[str], list[str]]]:
    """Update rows in place. Returns (row, old codes, new codes) for each trial whose codes changed."""
    changed = []
    for r in rows:
        if "infra_error" in r:
            continue
        old = sorted(f["code"] for f in r["failures"])
        r["failures"] = grade(ALL_BY_ID[r["scenario"]], r["snapshot"])
        new = sorted(f["code"] for f in r["failures"])
        if old != new:
            changed.append((r, old, new))
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    for path in a.files:
        rows = read_rows(path)
        changed = regrade_rows(rows)
        write_rows(path, rows)
        print(f"{path}: {len(rows)} rows, {len(changed)} changed")
        for r, old, new in changed:
            print(f"  {r['agent']}/{r['sop']} {r['scenario']} trial {r['trial']}: {old} -> {new}")


if __name__ == "__main__":
    main()
