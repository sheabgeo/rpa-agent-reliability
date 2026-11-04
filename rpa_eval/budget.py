"""Budget guard: what has been spent, and whether the next phase fits under the cap.

  python -m rpa_eval.budget status
  python -m rpa_eval.budget project claude-sonnet-5-5:60 claude-haiku-5-5:60 --monitor 400

Spend is estimated from stored token usage and `pricing.py`. It covers every trial file, including partial usage from
infra errors, monitor predictions, monitor errors dropped on resume, and calls logged in `results/api_ledger.jsonl`.
It is an estimate, not an invoice. Requests that were billed but never returned a response cannot be seen here.
"""
from __future__ import annotations

import argparse
import glob
import sys
from collections import defaultdict
from pathlib import Path

from .monitor import load_trials, trial_key
from .pricing import cost_usd

CAP_USD = 30.0  # v1 ran under $20; the author raised the total to $30 for v2 on 2026-11-04
MARGIN = 0.25  # added to projections, because trial costs vary and calibration n is small
TRIAL_GLOBS = ("runs/*/trials.jsonl", "results/data/*.jsonl.gz", "results/data_v2/*.jsonl.gz")
MONITOR_GLOBS = ("results/monitor/predictions*.jsonl", "results/monitor/dropped_errors.jsonl",
                 "results/monitor_v2/predictions*.jsonl", "results/monitor_v2/dropped_errors.jsonl")
LEDGER = "results/api_ledger.jsonl"


def expand(patterns, root=".") -> list[Path]:
    return sorted({Path(p) for pat in patterns for p in glob.glob(str(Path(root) / pat))})


def load_all(root=".") -> dict:
    """Billable rows by source. A trial in both runs/ and results/data/ counts once, and mutants never count."""
    trials = {}
    for row in load_trials(expand(TRIAL_GLOBS, root)):
        if row.get("origin") != "mutated":
            trials[trial_key(row)] = row
    monitor = load_trials(expand(MONITOR_GLOBS, root))
    ledger_path = Path(root) / LEDGER
    ledger = load_trials([ledger_path]) if ledger_path.exists() else []
    return {"trials": list(trials.values()), "monitor": monitor, "ledger": ledger}


def priced(model: str, usage: dict | None) -> float:
    cost = cost_usd(model, usage)
    if cost is None:
        raise ValueError(f"no price for model {model}; add it to pricing.py before spending on it")
    return cost


def summarize(data: dict) -> dict:
    per_model = defaultdict(list)
    for r in data["trials"]:
        if r.get("usage"):
            per_model[r["agent"]].append(priced(r["agent"], r["usage"]))
    trials = sum(sum(v) for v in per_model.values())
    monitor_costs = [priced(r["model"], r.get("usage")) for r in data["monitor"]]
    ledger = sum(priced(r["model"], r) for r in data["ledger"])
    biggest_prompt = max((r.get("usage", {}).get("max_prompt_tokens", 0) for r in data["trials"]), default=0)
    return {"trials": trials, "monitor": sum(monitor_costs), "ledger": ledger,
            "total": trials + sum(monitor_costs) + ledger, "per_model": dict(per_model),
            "monitor_costs": monitor_costs, "biggest_prompt": biggest_prompt,
            "infra_errors": sum("infra_error" in r for r in data["trials"])}


def project(s: dict, plan: dict[str, int], monitor_preds: int, cap: float = CAP_USD) -> dict:
    """Mean measured cost x planned count, plus MARGIN. Raises if a planned item has no measurements to project from."""
    base = 0.0
    for model, n in plan.items():
        costs = s["per_model"].get(model)
        if not costs:
            raise ValueError(f"no measured trials for {model}")
        base += n * sum(costs) / len(costs)
    if monitor_preds:
        if not s["monitor_costs"]:
            raise ValueError("no measured monitor predictions; run a pilot with --limit first")
        base += monitor_preds * sum(s["monitor_costs"]) / len(s["monitor_costs"])
    with_margin = base * (1 + MARGIN)
    return {"base": base, "with_margin": with_margin, "spent": s["total"], "total": s["total"] + with_margin,
            "go": s["total"] + with_margin <= cap}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("project")
    p.add_argument("plan", nargs="*", help="model:trials")
    p.add_argument("--monitor", type=int, default=0, help="planned monitor predictions")
    a = ap.parse_args()
    s = summarize(load_all())
    print(f"Spent: ${s['total']:.4f} of ${CAP_USD:.2f} (trials ${s['trials']:.4f}, monitor ${s['monitor']:.4f}, "
          f"other ${s['ledger']:.4f}). Infra errors: {s['infra_errors']}. Largest prompt: {s['biggest_prompt']:,} tokens.")
    for model, costs in sorted(s["per_model"].items()):
        print(f"  {model}: {len(costs)} trials, mean ${sum(costs)/len(costs):.4f}, max ${max(costs):.4f}")
    if s["monitor_costs"]:
        mc = s["monitor_costs"]
        print(f"  monitor: {len(mc)} predictions, mean ${sum(mc)/len(mc):.4f}, max ${max(mc):.4f}")
    if a.cmd == "project":
        plan = {m: int(n) for m, n in (x.rsplit(":", 1) for x in a.plan)}
        r = project(s, plan, a.monitor)
        print(f"Projected next: ${r['base']:.4f}, or ${r['with_margin']:.4f} with {MARGIN:.0%} margin. "
              f"Spent + projected: ${r['total']:.4f}. {'GO' if r['go'] else 'NO-GO'}.")
        sys.exit(0 if r["go"] else 1)


if __name__ == "__main__":
    main()
