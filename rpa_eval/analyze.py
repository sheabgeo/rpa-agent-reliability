"""Aggregate trials.jsonl files into a Markdown report with pass rates and a failure catalog.

  python -m rpa_eval.analyze runs/*/trials.jsonl --out results/REPORT.md
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from .graders import FAILURE_CODES
from .scenarios import BY_ID


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0, c - h), min(1, c + h))


def load(paths):
    rows = []
    for p in paths:
        for line in Path(p).read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default="results/REPORT.md")
    a = ap.parse_args()
    rows = load(a.files)
    infra = [r for r in rows if "infra_error" in r]
    rows = [r for r in rows if "infra_error" not in r]

    arms = sorted({(r["agent"], r["sop"]) for r in rows})
    scn_ids = sorted({r["scenario"] for r in rows})
    cell = defaultdict(list)
    for r in rows:
        cell[(r["agent"], r["sop"], r["scenario"])].append(r)

    L = ["# Results", "", f"{len(rows)} graded trials across {len(arms)} arm(s); {len(infra)} infra errors excluded.", ""]

    L += ["## Overall pass rate", "", "| Agent | SOP | Pass | 95% CI | Mean tool calls | Mean tokens (in/out) |",
          "|---|---|---|---|---|---|"]
    for ag, sop in arms:
        rs = [r for r in rows if (r["agent"], r["sop"]) == (ag, sop)]
        k = sum(not r["failures"] for r in rs)
        lo, hi = wilson(k, len(rs))
        calls = sum(r["snapshot"]["n_calls"] for r in rs) / len(rs)
        ti = sum(r.get("usage", {}).get("input_tokens", 0) for r in rs) / len(rs)
        to = sum(r.get("usage", {}).get("output_tokens", 0) for r in rs) / len(rs)
        L.append(f"| {ag} | {sop} | {k}/{len(rs)} ({k/len(rs):.0%}) | {lo:.0%}-{hi:.0%} | {calls:.1f} | {ti:,.0f} / {to:,.0f} |")

    L += ["", "## Pass rate by scenario", "", "| Scenario | Probes | " + " | ".join(f"{a}/{s}" for a, s in arms) + " |",
          "|---|---|" + "---|" * len(arms)]
    for sid in scn_ids:
        cells = []
        for ag, sop in arms:
            rs = cell[(ag, sop, sid)]
            k = sum(not r["failures"] for r in rs)
            cells.append(f"{k}/{len(rs)}" if rs else "-")
        L.append(f"| {sid} | {BY_ID[sid]['probes']} | " + " | ".join(cells) + " |")

    L += ["", "## Failure catalog", "", "Counts are trials exhibiting the failure at least once.", "",
          "| Code | Meaning | " + " | ".join(f"{a}/{s}" for a, s in arms) + " |", "|---|---|" + "---|" * len(arms)]
    per_arm = {arm: Counter() for arm in arms}
    for r in rows:
        for c in {f["code"] for f in r["failures"]}:
            per_arm[(r["agent"], r["sop"])][c] += 1
    for code, meaning in FAILURE_CODES.items():
        counts = [per_arm[arm][code] for arm in arms]
        if any(counts):
            L.append(f"| `{code}` | {meaning} | " + " | ".join(map(str, counts)) + " |")

    L += ["", "## Example failures", ""]
    seen = set()
    for r in rows:
        for f in r["failures"]:
            key = (r["agent"], r["sop"], r["scenario"], f["code"])
            if key in seen:
                continue
            seen.add(key)
            L.append(f"- **{r['scenario']}** · {r['agent']}/{r['sop']} · `{f['code']}`: {f['detail']}")

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
