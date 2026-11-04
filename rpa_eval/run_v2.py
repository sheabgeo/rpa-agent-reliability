"""Run the v2 scenarios under one condition and grade every trial.

  python -m rpa_eval.run_v2 --agent oracle --trials 1
  python -m rpa_eval.run_v2 --model claude-haiku-5-5 --phase pilot --condition pressure --trials 3 --max-usd 1
  python -m rpa_eval.run_v2 --model claude-haiku-5-5 --phase confirm --condition neutral --trials 15 \
      --scenarios V01_erp_outage,V07_currency_trap

Rows are kept in `runs/`, in the same format as v1, with `scenario_set`, `condition` and `phase` added.
"""
from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .env_v2 import EnvV2
from .graders_v2 import grade_v2
from .pricing import PRICES_PER_MTOK, cost_usd
from .run import SOP_VARIANTS, new_run_dir, run_claude
from .scenarios_v2 import KICKOFFS, V2_SCENARIOS

MAX_TURNS_V2 = 80  # the ten-invoice batch needs more turns than any v1 scenario


def run_trial_v2(scn: dict, trial: int, agent: str, model: str, condition: str, phase: str, client) -> dict:
    env = EnvV2.from_seed(scn["seed"])
    t0 = time.time()
    if agent == "claude":
        meta = run_claude(env, model, SOP_VARIANTS["full"], client, kickoff=KICKOFFS[condition], max_turns=MAX_TURNS_V2)
    else:
        from agents.scripted import AGENTS
        from agents.scripted_v2 import oracle_v2
        {"oracle": oracle_v2, "naive": AGENTS["naive"]}[agent](env, scn)
        meta = {"transcript": env.calls, "usage": {}, "stop": "scripted"}
    snap = env.snapshot()
    return {"scenario": scn["id"], "trial": trial, "agent": agent if agent != "claude" else model, "sop": "full",
            "scenario_set": "v2", "condition": condition, "phase": phase,
            "failures": grade_v2(scn, snap), "snapshot": snap,
            "tool_calls": [{"tool": c["tool"], "args": c["args"]} for c in env.calls],
            "seconds": round(time.time() - t0, 1), **meta}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="claude", help="claude | oracle | naive")
    ap.add_argument("--model", default="claude-haiku-5-5")
    ap.add_argument("--condition", default="pressure", choices=sorted(KICKOFFS))
    ap.add_argument("--phase", default="pilot", choices=["pilot", "confirm", "check"])
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--scenarios", default="all", help="comma-separated ids or 'all'")
    ap.add_argument("--pairs", default="", help="re-run only these pairs after infra errors, e.g. V01_erp_outage:0")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default="runs")
    ap.add_argument("--max-usd", type=float, help="backstop: cancel trials not yet started once this run has cost this much")
    a = ap.parse_args()

    scns = V2_SCENARIOS if a.scenarios == "all" else [s for s in V2_SCENARIOS if s["id"] in a.scenarios.split(",")]
    client = None
    if a.agent == "claude":
        if a.max_usd is not None and a.model not in PRICES_PER_MTOK:
            ap.error(f"--max-usd needs a known price for {a.model}")
        import anthropic
        client = anthropic.Anthropic(max_retries=6)

    label = a.model if a.agent == "claude" else a.agent
    out = new_run_dir(Path(a.out), f"{time.strftime('%Y%m%d-%H%M%S')}_{label}_{a.condition}_v2{a.phase}")
    jobs = [(s, t) for s in scns for t in range(a.trials)]
    if a.pairs:
        wanted = {tuple(p.rsplit(":", 1)) for p in a.pairs.split(",")}
        jobs = [(s, int(t)) for s in V2_SCENARIOS for sid, t in sorted(wanted) if s["id"] == sid]
    n_pass = n_cancelled = 0
    run_cost = 0.0
    with ThreadPoolExecutor(max_workers=a.workers) as pool, open(out / "trials.jsonl", "w") as f:
        futs = {pool.submit(run_trial_v2, s, t, a.agent, a.model, a.condition, a.phase, client): (s["id"], t) for s, t in jobs}
        for fut in as_completed(futs):
            sid, t = futs[fut]
            if fut.cancelled():
                n_cancelled += 1
                continue
            try:
                r = fut.result()
            except Exception as exc:  # keep the batch alive; record infra errors separately
                r = {"scenario": sid, "trial": t, "agent": label, "sop": "full", "scenario_set": "v2", "condition": a.condition,
                     "phase": a.phase, "infra_error": repr(exc), "usage": getattr(exc, "partial_usage", {})}
            f.write(json.dumps(r) + "\n")
            f.flush()
            ok = "infra_error" not in r and not r["failures"]
            n_pass += ok
            if a.phase != "confirm":  # confirmatory outcomes stay out of the console until the author's labels are committed
                codes = ",".join(x["code"] for x in r.get("failures", [])) or ("INFRA" if "infra_error" in r else "")
                print(f"{sid:26s} trial {t}  {'PASS' if ok else 'FAIL'}  {codes}")
            run_cost += cost_usd(r["agent"], r.get("usage")) or 0
            if a.max_usd is not None and run_cost >= a.max_usd:
                for other in futs:
                    other.cancel()
    if n_cancelled:
        print(f"\nSTOPPED AT BUDGET BACKSTOP: {n_cancelled} trials not started after ${run_cost:.4f}.")
    done = len(jobs) - n_cancelled
    print(f"\n{done} trials, ${run_cost:.4f}." + ("" if a.phase == "confirm" else f" {n_pass}/{done} passed.") + f" Results: {out / 'trials.jsonl'}")


if __name__ == "__main__":
    main()
