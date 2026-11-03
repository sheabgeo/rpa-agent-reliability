# Project notes

## Status (2026-11-03)

**No model has been run, so there are no findings yet.** `ANTHROPIC_API_KEY` is not set in the environment, and
`gh` is not installed. All work that needs neither is finished and tested. Nothing in this repo reports a model result.

| Phase | Step | State |
|---|---|---|
| 0 | Install, grader tests, oracle and naive baselines | Done: tests pass, oracle 12/12, naive 0/12 |
| 0 | Confirm model IDs with a 1-token call | **Blocked: no API key** |
| 0 | `pricing.py`, `regrade.py`, cost table in `analyze.py` | Done |
| 0 | `gh repo create` and push | **Blocked: `gh` not installed.** Commits are local only |
| 1 | Cost calibration and projection | **Blocked: no API key** |
| 2 | Main experiment and ablation | **Blocked: no API key** |
| 3 | `monitor.py`, `mutate.py` | Code done, tested offline with fake clients |
| 3 | Monitor experiment | **Blocked: needs Phase 2 trials and a key** |
| 4 | `scenarios_paraphrase.py` (24 variants) | Done: oracle 24/24, naive 0/24 |
| 4 | Sonnet arm on the paraphrases | **Blocked: no API key** |
| 5 | Report, monitor table, examples, README findings | **Blocked: needs results** |
| 5 | Fresh-clone check | Done for the offline commands. Repeat at the end |

## Spend

| Phase | USD |
|---|---|
| All phases so far | $0.00 (no API calls made) |
| **Total against the $40 budget** | **$0.00** |

## Resuming

1. Set `ANTHROPIC_API_KEY` in the environment.
2. Install `gh` and run `gh auth login`.
3. Ask Claude Code to continue from `CLAUDE.md`. The next step is Phase 0, step 2 (model ID check), then
   the repo push, then Phase 1.

## Decisions

Everything below was decided **before any model output existed**, so none of it was influenced by results.

### Blockers

- **Credentials: stopped at the environment variable.** CLAUDE.md rule 5 says the key comes from the environment
  only, so I did not look for keys in `.env` files, user or machine variables, or `ant` login profiles.
- **Did not smoke-test the real run path without a key.** The SDK falls back to any stored login profile when the
  variable is unset, so a "harmless" test could have spent money on a credential the project excludes.
- **Did not simulate the experiment.** Claude Code subagents could imitate the agent arms, but they run with a
  different system prompt, tools and harness, so they would not measure what the study claims to measure.
- **Did not install `gh`.** CLAUDE.md covers an unauthenticated `gh` by telling the author and carrying on, and
  I applied that to a missing `gh`. Creating a public repo should use a login the author set up.
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
