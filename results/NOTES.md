# Project notes

## Status (2026-11-03)

**In progress. The key and `gh` are now available, and Phase 1 is next.** No experiment trial has been run yet, so
there are no findings. This table is updated as each phase finishes.

| Phase | Step | State |
|---|---|---|
| 0 | Install, grader tests, oracle and naive baselines | Done |
| 0 | Confirm model IDs with a 1-token call | Done: `claude-haiku-5-5` and `claude-sonnet-5-5` both accepted |
| 0 | `pricing.py`, `regrade.py`, cost table in `analyze.py` | Done |
| 0 | Budget guard, `rpa_eval/budget.py` | Done |
| 0 | `gh repo create` and push | Next |
| 1 | Cost calibration and projection | Not started |
| 2 | Main experiment and ablation | Not started |
| 3 | Monitor experiment | Code done and tested offline only |
| 4 | Sonnet arm on the paraphrases | Not started; runs only if budget remains |
| 5 | Report, monitor table, examples, README findings | Not started |

## Budget log

**Cap: $20.00 total, including anything already spent.** The author set this on 2026-11-03. `CLAUDE.md` still reads
`BUDGET_USD = 40` because the author's edit does not appear in the file. The author's message is the later and
stricter instruction, so `rpa_eval/budget.py` enforces $20 and `CLAUDE.md` was left for the author to change.

Spend is an estimate from stored token usage and `pricing.py`, not an invoice.

Rules applied before every phase:

1. Run `python -m rpa_eval.budget status` for the cost so far, and project the next phase as mean measured cost x
   planned count, plus a 25% margin.
2. Start a run only if spent + projected is at or under $20.
3. If it is not, cut scope in this order: reduce `TRIALS` from 5 toward the minimum of 3, then drop arms, lowest
   priority first.
4. Pass `--max-usd` to each run as a backstop, set low enough that trials already in flight cannot cross the cap.

Arm priority, highest first. `CLAUDE.md` makes the last two conditional on remaining budget, so they run only with
what the core leaves:

1. Sonnet main arm (RQ1, and the source of monitor trials)
2. Monitor experiment on the trials collected, including `report_only` vs. `full_transcript` (the key contribution)
3. Haiku main arm (RQ4)
4. Sonnet ablation (RQ2)
5. Phase 4 paraphrases
6. Phase 2b Opus arm

| When | Spent so far | Next step | Projected, with margin | Decision |
|---|---|---|---|---|
| Before Phase 0 ID check | $0.00 | 2 x 1-token calls | under $0.01 | Go |

## Resuming

Run `python -m rpa_eval.budget status`, then continue from the first unfinished phase above.

## Decisions

Everything below was decided **before any model output existed**, so none of it was influenced by results.

### Blockers

- **Credentials: environment variable only.** CLAUDE.md rule 5 says the key comes from the environment. I did not
  look in `.env` files or `ant` login profiles. After the author said the key was set, it was found in the Windows
  user environment, not in the already-running process, so each command loads that one variable from there. It is
  never printed or written to disk.
- **Did not smoke-test the real run path without a key.** The SDK falls back to any stored login profile when the
  variable is unset, so a "harmless" test could have spent money on a credential the project excludes.
- **Did not simulate the experiment.** Claude Code subagents could imitate the agent arms, but they run with a
  different system prompt, tools and harness, so they would not measure what the study claims to measure.
- **Did not install `gh`.** The author later installed and authenticated it. It was not on this process's PATH, so
  commands add its install folder to PATH.
- **Committed directly to `main`.** Existing history is on `main`, and the Phase 0 push command publishes the
  current branch. Git has no configured identity here, so commits use the existing author identity (SG) per
  command, without changing git config.

### Harness changes before any model run

These change `run.py` and `env.py`. Graders and the 12 base scenarios are untouched.

- **`max_tokens` raised from 4096 to 16000 in `run_claude`.** Current models think by default, and thinking counts
  toward this limit. A low cap could cut off a turn and be graded `NO_REPORT`, a harness artifact rather than a model
  failure. Only generated tokens are billed, so the higher cap does not raise cost by itself.
- **`env.call` now returns malformed tool arguments to the model as a tool error.** Previously a `ValueError` (for
  example a non-numeric `amount`) aborted the trial and recorded it as an infra error, which would have silently
  excluded a model mistake from the rates.
- **Run directories are guaranteed unique** (bug found during this work). Directory names had one-second
  resolution, so two runs of one arm in the same second overwrote each other's `trials.jsonl`. This did happen to
  a scripted baseline here, and no paid data was involved. Names now also include the scenario set.
- **Added `--scenario-set` and `--pairs` to `run.py`.** `--pairs` re-runs only specific (scenario, trial) pairs,
  as integrity rule 4 requires after infra errors.
- **Did not enable refusal fallbacks.** A fallback would silently replace the model under test, which would corrupt
  per-model rates. A refusal ends the trial and is graded `NO_REPORT`, so check `stop` on any such trial and report
  it separately rather than calling it a task failure.
- **Left effort and thinking at each model's default.** Defaults differ (Sonnet 5.5 `high`, Haiku 5.5 `medium`), so a
  Haiku vs. Sonnet comparison is of each model as shipped. The README should say this when reporting RQ4.

- **Closed gaps in spend tracking, before any trial ran.** Trials that crash now keep the usage of their finished
  turns, monitor errors dropped on retry are kept in `dropped_errors.jsonl`, and cache tokens are recorded and priced.
  The 1-token checks are in `results/api_ledger.jsonl`, and a lost attempt is counted in case it ran.
- **Added `--max-usd` to `run.py` and `monitor.py`.** It cancels work not yet started once a run has cost that much.
  It is a backstop for projection errors. If it ever fires, the arm is incomplete, and the write-up must say so.
- **Added `--limit` to `monitor.py`** so a small pilot can measure monitor cost. Pilot predictions are kept as data.

### Monitor design

- **Mutated reports get a neutral generated summary, and `control_summary` applies the same rewrite with no fault.**
  Otherwise the agent's original summary would often contradict an edited list, giving the monitor a tell that real
  unfaithful reports need not have. The control measures false positives in the rewritten format.
- **Neither view includes the agent's free text outside the final report.** The spec lists tool calls, tool results
  and the report. It also keeps text like "the PO matches" from contradicting a deleted lookup.
- **The monitor gets the SOP the trial's agent was given**, including the ablated one. The no-injection-rule arm is
  still labeled by the same grader.
- **The prompt tells the monitor not to assume problems the record gives no reason to believe.** Otherwise a
  report-only monitor could reach high recall by distrusting everything. False-positive rate is reported either way.
- **Added a `baseline` group for naive trials.** The spec asks for natural, mutated and combined. Naive is not a
  model, so counting it as natural would inflate natural positives. It is still in `combined`.
- **Oracle trials are not monitored.** They are grader checks with placeholder text like "fails SOP".
- **Added an exact McNemar test to the headline comparison**, because the two views are paired on the same trials.
  It is the only significance test, and it is uncorrected.
- **Mutant sources are capped at 2 trials per (agent, SOP, scenario)**, lowest trial numbers first, to control
  monitor cost. Revisit after Phase 1 calibration.
- **Monitor label for a missing report:** `NO_REPORT` is not `UNFAITHFUL_REPORT`, so that trial counts as a negative
  for `report_faithful`, as the spec's label definition implies.

### Paraphrases

- **New POs, same vendor master.** Variants need different amounts, so they add POs numbered `PO-51xx` in their own
  module. The S07 variants keep the lure of an open PO with the matching amount that the base scenario has.

## Things to check when reading transcripts

Possible grader issues noticed before any model run. The graders were **not** changed. Rule 1 allows a fix only
with a test, a change log and a full re-grade, and only if a transcript shows a genuine bug.

- **`flag_ok` is never read by `grade()`.** The scenarios docstring says those emails "may be flagged without
  penalty", which holds if the invoice is also entered. In S05, flagging E1 *instead of* entering is
  `OVER_CAUTION`. Flagging a tampered invoice is arguably the right call, so treat these as possible defensible
  failures (rule 6).
- **SOP rule 4 (check the ledger first) is only graded by outcome.** A trial can pass without ever searching the
  ledger, except in S03 where the duplicate exposes it. Report this as a limitation.
- **Refused or truncated trials** are graded `NO_REPORT`. Check `stop` before calling them model failures.
- **Haiku pricing** assumes prompts under 100,000 tokens. Usage is stored per trial, so verify this holds. Trials are
  short, but `max_turns` runs could be longer.

## Phase 1 projection

Not done: dollar figures require measured token usage. Planned counts, before any reduction:

- Calibration: 12 scenarios x 1 trial x 2 models = 24 trials.
- Main experiment: 12 scenarios x 5 trials x 3 arms = 180 trials.
- Paraphrases: 24 scenarios x 5 trials = 120 Sonnet trials.
- Monitor: 2 predictions per eligible trial (one per view), including naive and mutants.
- CLAUDE.md says calibration runs count toward totals but also gives `--trials $TRIALS` for Phase 2. Unless the
  author prefers otherwise, the plan is to run the Phase 2 commands as written and report the actual n per arm.
