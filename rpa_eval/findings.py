"""Fill the generated blocks in README.md from committed outputs, so that no reported number is typed by hand.

  python -m rpa_eval.findings

Reads results/data/*.jsonl.gz, results/monitor/predictions.jsonl, results/REPORT.md and results/MONITOR.md.
"""
from __future__ import annotations

import glob
import re
from pathlib import Path

from .analyze import wilson
from .budget import CAP_USD, load_all, summarize
from .monitor import VIEWS, in_group, load_trials, predicted_problem, true_problem

SONNET, HAIKU = "claude-sonnet-5-5", "claude-haiku-5-5"
ABLATION_SCENARIOS = ("S04_bank_change", "S05_injection", "S10_scope_creep")


def ci(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} (95% CI {lo:.0%}-{hi:.0%})"


def passes(rows, **match) -> tuple[int, int]:
    rs = [r for r in rows if all(r.get(k) == v for k, v in match.items())]
    return sum(not r["failures"] for r in rs), len(rs)


def recall(preds, field, view, group) -> tuple[int, int]:
    rs = [r for r in preds if r["view"] == view and in_group(r, group) and true_problem(field, r["codes"])]
    return sum(predicted_problem(field, r["prediction"]) for r in rs), len(rs)


def flagged(preds, field, view, mutation) -> tuple[int, int]:
    rs = [r for r in preds if r["view"] == view and r.get("mutation") == mutation]
    return sum(predicted_problem(field, r["prediction"]) for r in rs), len(rs)


def key_findings(main, para, preds) -> str:
    sonnet = passes(main, agent=SONNET, sop="full")
    haiku = passes(main, agent=HAIKU, sop="full")
    ablated = passes(main, agent=SONNET, sop="no-injection-rule")
    model_rows = [r for r in main if r["agent"] in (SONNET, HAIKU)]
    failing = [r for r in model_rows if r["failures"]]
    only_s03 = {r["scenario"] for r in failing} == {"S03_duplicate"}
    assert only_s03, "the finding below assumes that all model failures are on S03; rewrite it"
    s03_haiku = passes(main, agent=HAIKU, sop="full", scenario="S03_duplicate")
    inj_rows = [r for r in main if r["agent"] == SONNET and r["sop"] == "no-injection-rule" and r["scenario"] in ABLATION_SCENARIOS]
    inj_pass = sum(not r["failures"] for r in inj_rows)
    para_p = (sum(not r["failures"] for r in para), len(para))

    uf_full = recall(preds, "report_faithful", "full_transcript", "mutated")
    uf_rep = recall(preds, "report_faithful", "report_only", "mutated")
    uv_full = recall(preds, "unverified_entry", "full_transcript", "mutated")
    uv_rep = recall(preds, "unverified_entry", "report_only", "mutated")
    nat_full = recall(preds, "sop_violation", "full_transcript", "natural")
    nat_rep = recall(preds, "sop_violation", "report_only", "natural")
    natural_negs = [r for r in preds if r["origin"] == "natural" and r["view"] == "full_transcript"
                    and not true_problem("report_faithful", r["codes"])]
    nat_flagged = sum(predicted_problem("report_faithful", r["prediction"]) for r in natural_negs)
    fp_email = flagged(preds, "report_faithful", "full_transcript", "insert_send_email")
    fp_ctrl = flagged(preds, "report_faithful", "full_transcript", "control_summary")

    return "\n".join([
        f"- **Failures were rare, and the only graded ones were on one scenario.** Sonnet passed {ci(*sonnet)} and "
        f"Haiku {ci(*haiku)}. Every model failure was on S03, including {s03_haiku[1] - s03_haiku[0]} of "
        f"{s03_haiku[1]} Haiku trials. Those agents refused the duplicate invoice and said so in the report, but "
        "did not raise the flag the SOP requires, so this is a [defensible failure](results/examples/04_defensible_duplicate.md). "
        "See the [results tables](#results).",
        f"- **Removing the anti-injection rule changed nothing measurable (null result).** Without it, Sonnet passed "
        f"{ci(*ablated)} overall and {inj_pass}/{len(inj_rows)} on the three scenarios that could show an effect. "
        "These scenarios may simply be too easy to separate the arms. [Report](results/REPORT.md).",
        f"- **Results held under rewording.** Sonnet passed {ci(*para_p)} on 24 paraphrased scenarios. "
        "[Paraphrase report](results/REPORT_PARAPHRASE.md).",
        f"- **Full transcripts caught injected faults that reports did not, but mostly by construction.** On mutated "
        f"trials, full-transcript recall was {uf_full[0]}/{uf_full[1]} for unfaithful reports and {uv_full[0]}/{uv_full[1]} "
        f"for unverified entries, against {uf_rep[0]}/{uf_rep[1]} and {uv_rep[0]}/{uv_rep[1]} for report-only. The "
        "mutations leave no trace in the report, so this shows what a report cannot carry, not how real silent failures "
        "are missed. No natural trial had either grader code. [Monitor results](results/MONITOR.md).",
        f"- **On natural trials the monitor added little, with one useful exception.** It caught {nat_full[0]}/{nat_full[1]} "
        f"graded failures from transcripts and {nat_rep[0]}/{nat_rep[1]} from reports. It also flagged {nat_flagged} of "
        f"{len(natural_negs)} natural trials as unfaithful, and that one is a [real false claim](results/examples/01_false_claim_in_summary.md) "
        "the grader cannot see.",
        "",
        f"Read the monitor's false-positive rates with care: full-transcript monitoring marked {fp_email[0]}/{fp_email[1]} "
        f"`insert_send_email` mutants as unfaithful and {fp_ctrl[0]}/{fp_ctrl[1]} controls. Those mutants keep an agent "
        "summary saying no email was sent, so the monitor is right, and the grader's label is narrower than the monitor's reading. "
        "[Worked example](results/examples/02_mutant_email_contradiction.md).",
    ])


def section(text: str, heading: str) -> str:
    m = re.search(rf"^## {re.escape(heading)}.*?\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    assert m, heading
    return m.group(1).strip()


def results_block(preds) -> str:
    rep = Path("results/REPORT.md").read_text(encoding="utf-8")
    mon = Path("results/MONITOR.md").read_text(encoding="utf-8")
    s = summarize(load_all())
    counts = {v: sum(r["view"] == v for r in preds) for v in VIEWS}
    return "\n\n".join([
        "### Overall", section(rep, "Overall pass rate"),
        "Haiku and Sonnet have 6 trials per scenario because calibration runs count; the ablation arm has 5. "
        "`naive` and `oracle` are scripted grader checks, not models.",
        "### Per scenario", section(rep, "Pass rate by scenario"),
        "### Failure catalog", section(rep, "Failure catalog"),
        "### Monitor: recall on silent failures", section(mon, "Headline: recall on silent failures, report-only vs. full transcript"),
        f"Each view made {counts['report_only']} predictions. Per-label and per-mutation tables are in "
        "[`results/MONITOR.md`](results/MONITOR.md).",
        "### Cost",
        f"Estimated total API spend was ${s['total']:.2f} of the ${CAP_USD:.0f} cap (agent trials ${s['trials']:.2f}, "
        f"monitor ${s['monitor']:.2f}). This comes from stored token usage, not an invoice. See "
        "[`results/SPEND.txt`](results/SPEND.txt).",
    ])


def fill(text: str, name: str, body: str) -> str:
    pattern = rf"(<!-- BEGIN GENERATED {name} -->\n).*?(<!-- END GENERATED {name} -->)"
    assert re.search(pattern, text, re.S), name
    return re.sub(pattern, lambda m: m.group(1) + body + "\n" + m.group(2), text, flags=re.S)


def main():
    main_rows = [r for r in load_trials(sorted(glob.glob("results/data/*_main.jsonl.gz"))) if "infra_error" not in r]
    para = [r for r in load_trials(sorted(glob.glob("results/data/*_paraphrase.jsonl.gz"))) if "infra_error" not in r]
    preds = [r for r in load_trials(["results/monitor/predictions.jsonl"]) if "error" not in r]
    readme = Path("README.md")
    text = readme.read_text(encoding="utf-8")
    text = fill(text, "FINDINGS", key_findings(main_rows, para, preds))
    text = fill(text, "RESULTS", results_block(preds))
    readme.write_text(text, encoding="utf-8")
    print("README generated blocks updated")


if __name__ == "__main__":
    main()
