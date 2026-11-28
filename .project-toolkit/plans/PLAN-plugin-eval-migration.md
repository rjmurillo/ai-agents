# PLAN: Move the skill eval suite to `claude plugin eval`

Spec: `.project-toolkit/specs/SPEC-plugin-eval-migration.md` (section and item numbers below refer to it).
Date: 2026-11-28. Base commit: 2bec8b73e (main).
Status: planned, nothing implemented. Sizing is S/M/L by complexity, never time.
Steps 3, 4, 6, and 7 of the `plan` skill (milestone-planner, task-decomposer, analyst, critic) ran in this session by the same author, not as separate agents. The pre-mortem and review below are therefore one pass, not independent evidence. Run `critic` on this file before PR A starts.

## Milestones and dependency graph

```text
PR A (ADR amendments)
  |
  +--> PR B (skillopt + migration reference)  --+
  |                                              +--> PR C2 (grow 8 skills, baseline, hillclimb)
  +--> PR C1 (converter, suite, consumers)    --+
```

- A blocks B and C1: both cite the amended ADR text, and the ADR review may change the gate math they implement.
- B and C1 are file-disjoint and run in parallel. B touches `src/claude/skills/skillopt/`, `templates/skills/skillopt.SKILL.md.tmpl`, `docs/skills/skillopt.md`. C1 touches `evals/`, `scripts/eval/`, `scripts/validation/`, `tests/`, `.github/workflows/`.
- Merge order: B before C1. They build in parallel, but C1.5 makes the gate read only schema-2 receipts and B6 is their only writer, so a C1 merge first would block every skill rewrite with no way to produce evidence.
- C2 needs both. B supplies the adapter and trust checks. C1 supplies the case tree and the new gate. C1 must merge before any C2 case edit, because `_JUDGE_PATHS` in `check_skill_rewrite_evidence.py` (line 358) decides which paths count as judge-surface changes (spec item 4).
- Each PR is independently shippable: after A the ADRs are consistent; after B skillopt works on any plugin; after C1 the repo suite is converted and gated; C2 adds cases and results.
- Worktrees: `~/worktrees/ai-agents/<branch>` (`AGENTS.md` Disk row). Branches: `docs/plugin-eval-adr-amend`, `feat/skillopt-plugin-eval`, `feat/skill-cases-plugin-eval`, `feat/skill-cases-grow-hillclimb`.

Common gates for every PR: `uv run python scripts/validation/pre_pr.py` returns no BLOCKING finding; no em or en dash in added lines; conventional commit with the `Co-Authored-By` trailer; no `--no-verify`.

## PR A: ADR-057 and ADR-087 amendments

Size: M. Spec items 6 and the ADR-127 pointer (Open question 2).

| # | Task | Size | Acceptance criteria | Verification |
|---|---|---|---|---|
| A1 | Read ADR-057 (448 lines) and ADR-087 (1000 lines) amendment history and the `adr-generator` skill. Record which sections change. | S | A list of target sections for each ADR is in the PR body. | Read in session. No command. |
| A2 | Invoke `adr-generator` to amend ADR-057: runner swap, Scenario Storage path, gate math on recomputed deterministic scores, judge model pin, trust checks, $260 exception with its end event. | M | Amendment dated 2026-11-28 holds all six spec item 6 points. The Acceptance Gate numbers (`ceil(2n/3)`, 40 percent flake block, stable-base fraction, security tier 5 runs at 100 percent) keep their definitions. ADR-058 text is untouched. | `git diff --stat`, then read the diff. `grep -nP '\x{2014}\|\x{2013}' <file>` returns nothing. |
| A3 | Invoke `adr-generator` to amend ADR-087: requirements 1 to 5 re-expressed on `split.json`, tags, fingerprint, `sel_budget`, ledger key, corpus-hash refusal, conformance-test pin. | M | Each of the 5 requirements names its mechanism and its refusal condition. | Read the diff against spec item 3. |
| A4 | Add the one-line ADR-127 pointer note (if the owner accepts the default). Log it as a non-frontmatter edit. | S | The note names the ADR-057 amendment date. Frontmatter unchanged. | `git diff` shows only the note. |
| A5 | Run `adr-review` on both ADRs. Full panel if an amendment adds executable enforcement or a rules gate, else architect plus critic (`AGENTS.md` Skills row). | M | Verdict recorded for each ADR. Every P0 finding resolved or carried to the PR body with an owner. | Review output saved in the PR body. If `adr-review` cannot run, state `NOT RUN` and do not claim a verdict. |
| A6 | Run the repo gates. | S | `pre_pr.py` clean. ADR index and cross-reference checks pass. | `uv run python scripts/validation/pre_pr.py` |

Exit: both ADRs amended and reviewed, merged to main.
Rollback: revert the merge commit. No code depends on A until B and C1 merge.

## PR B: skillopt changes plus the migration reference

Size: L. Spec item 5. Depends on A.

Canonical source is `src/claude/skills/skillopt/` (hand-edited) and `templates/skills/skillopt.SKILL.md.tmpl`. Never edit `src/codex`, `src/copilot-cli`, `src/cursor` copies or `.claude/skills/skillopt/SKILL.md`. Regenerate with `uv run python build/scripts/build_all.py`.

| # | Task | Size | Acceptance criteria | Verification |
|---|---|---|---|---|
| B1 | Read every `src/claude/skills/skillopt/scripts/_skillopt_*.py`, `skillopt.py`, `references/eval-set-format.md`, `references/example-eval.json`, and `scripts/eval/_optimizer_core.py` (`split_tasks`, `split_fingerprint`). Write the module-level design (names, exit codes) in the PR body. | M | The design lists which functions of `_skillopt_runner.py` and `_skillopt_gates.py` change, and the exit-code table (0 ok, 1 logic, 2 config, 3 external, 4 auth, per `AGENTS.md`). | Read in session. |
| B2 | Add `_skillopt_plugin_eval.py`: scratch-root build (copy plugin plus cases, per `evals/ponytail-incumbent/run.py` `build_root`), `claude plugin eval --json` call, `claudeVersion` and `schemaVersion` check, aggregate parse, ledger append under a file lock, `--max-cost-usd` computation. Stdlib only. | L | Exit 3 on a schema or version mismatch. Exit 3 when cumulative plus projected cost would exceed the ceiling (spec criteria 6 to 8). A `partial` result is recorded, never averaged. Tests mock the subprocess. | `uv run pytest tests/skills/skillopt -q`, plus the new test file by name. Import check: `python3 -I -c` is not usable because `-I` drops the script dir, so run the module tests only. |
| B3 | Add `_skillopt_trust.py`: noise floor exactly as ADR-057 Amendment 2026-11-28 item 5 defines it (per-case deterministic pass fractions recomputed from `arms.with[].graders[]`, not host run scores; s from two unchanged baseline samples; floor = max(t(0.975, df) times s divided by sqrt(m), 1/m); fewer than two valid pairs refuses improvement), mechanism probe (scratch plugin minus the target skill), oracle and known-bad run, headline recompute from `graders[]`, served-model read from the trace with the pinned-model fallback, judge spot-check printer. | L | Spec criteria 9, 10, 11. Positive, negative, and edge tests: a mismatched headline fails, an oracle below 1.0 refuses later passes, a probe without a drop refuses the gate, a trace with no model field gives `served_model_verified: false`. | `uv run pytest <new trust test> -q` |
| B4 | Add `_skillopt_taxonomy.py`: classes `timeout`, `harness_or_serving`, `refusal`, `grader_error`, `genuine` from `error`, `aborted`, duration, and the trace. | M | A fixture per class. Only `genuine` feeds score deltas. Counts of every class print. | `uv run pytest <new taxonomy test> -q` |
| B5 | Extend `_skillopt_gates.py`: gate math on recomputed deterministic scores, per-case pass-to-fail block, `sel_budget` check, fingerprint check, corpus-hash refusal, `--mode cost` (quality within noise floor, cost margin, mechanism still passing). Add a conformance test pinning skillopt's fingerprint to `_optimizer_core.split_fingerprint` on one fixture. | L | Spec criteria 13 to 15. The conformance test fails when either side changes. | `uv run pytest tests/skills/skillopt -q` and the conformance test by name. |
| B6 | Extend `skillopt.py` with `run`, `trust`, `taxonomy`, `traces --split train|sel`. `traces --split sel` refuses in a proposer context (exit 2). Extend evidence output to receipt schema 2 (`_skillopt_evidence*.py`). One idea per proposed change, enforced by a required `idea` field. | L | Spec criteria 16 and the receipt fields in item 4. Each new exit code has a contract test (`.claude/rules/claude-agents.md` MUST 7). | `uv run python scripts/validation/check_skill_contract_tests.py` |
| B7 | Edit `templates/skills/skillopt.SKILL.md.tmpl` to document the new flow. Regenerate. | M | `build_all.py` leaves `git status` clean on re-run. Generated copies match. | `uv run python build/scripts/build_all.py`, then `git status --short`, then rerun and confirm no new diff. |
| B8 | Write `references/migrating-to-plugin-eval.md`: every breaking change, the mapping table (spec item 2), and the steps for a later skillopt run to convert a legacy `eval.json` plus scenario corpus. Cite `scripts/eval/convert_skill_scenarios.py` as the reference implementation once C1 lands, by name only, as a repo-only path with a `vendor-portability` declaration. | M | Spec criterion 22. The file lists each item removed or changed in B2 to B6. Dashes: none. | Read against the B2 to B6 diff. `uv run python scripts/validation/check_skill_md_portability.py` does not rise. |
| B9 | Update `docs/skills/skillopt.md` (triggers, scripts, exit codes, output paths). If not edited, add a `Docs-Reviewed: skillopt` trailer after reading the page in the same session. | S | Gate passes. | `uv run python scripts/validation/check_agent_skill_docs.py` and `uv run python scripts/validation/check_agent_skill_doc_review.py --base-ref origin/main` |
| B10 | Run the gates. | S | `pre_pr.py` clean, including `Generated Artifact Staleness` and `Rule Activation Coverage`. | `uv run python scripts/validation/pre_pr.py` |

Exit: skillopt runs a plugin-eval pass on any plugin root given `--plugin-root` and `--cases-dir`, with trust checks, in unit tests with a mocked host. No live paid pass in this PR.
Rollback: revert the merge. skillopt returns to the old runner. If C1 has merged, revert C1 first: its gate needs the receipt writer B6 adds.

## PR C1: converter, converted suite, consumer updates

Size: L. Spec items 1, 2, 4. Depends on A. Parallel with B.

| # | Task | Size | Acceptance criteria | Verification |
|---|---|---|---|---|
| C1.1 | Re-verify every N row of the spec's 37-consumer table, and classify the 17 path-join consumers and the live docs. Record the final table in the PR body. | M | Each of the 37 rows has a confirmed disposition, with the line that proves it. Counts recomputed. | `git grep -l 'tests/evals' -- 'scripts/**/*.py' 'tests/**/*.py' '.github/**/*.yml' \| wc -l` returns 37; then `git grep -n 'skill-scenarios\|-scenarios\.json' -- <file>` per N row. |
| C1.2 | Stage 0a, no spend: write `scripts/eval/convert_skill_scenarios.py` (stdlib) implementing the spec item 2 mapping, with an `--allow-contract-signals` file for reviewed contract strings. Dry-run mode prints counts and writes nothing. | L | Spec criteria 1 to 5. Tests: each mapped key, a scenario with no `expected_route`, one with `forbidden_routes`, an unknown key (fail), an `advisory-only` case count. | `uv run pytest tests/eval/test_convert_skill_scenarios.py -q` |
| C1.3 | Run the converter on the 59 files in `tests/evals/skill-scenarios/` and on the verdict corpora for skills under rewrite. Write `evals/skills/<skill>/<case-id>/`. Add `evals/skills/run.py` (thin wrapper over the skillopt scratch-root builder, or a local copy if B has not merged: duplicate only the builder, and replace it with the skillopt call in C2). | L | Case count equals 348 scenarios counted at 2bec8b73e, or each difference is listed. Every case is parsed by the host: a schema check with `claude plugin eval <scratch> --case zzz` reports no unknown-key error. | `python3 scripts/eval/convert_skill_scenarios.py --dry-run`, then a count of `evals/skills/*/*/prompt.md`. `git ls-files evals/skills \| grep -c prompt.md` |
| C1.4 | Stage 0 smoke, the first paid spend, cap $10: (a) confirm the command line carries `--no-publish` (publishing is the CLI default) and the result has no published URL, (b) oracle and known-bad case, (c) 5 route cases with the plugin, 1 run each, (d) check `scored` on an `arm: both` Skill grader, (e) read one trace for the served model, (f) compare top-level `costUsd` to the per-run sum. Create `evals/skills/ledger.jsonl` with this pass. | M | The four UNCONFIRMED items in spec Open question 4 each have an observed result or a recorded fallback. The decision rule in spec item 2 is applied to the 5 route cases. The real $ per run is in the ledger. | Ledger line present. Pass JSON kept outside git. Cumulative at or below 10.00. |
| C1.5 | Replace `check_skill_rewrite_evidence.py` and `skill_rewrite_scenarios.py` (and their helpers and tests, rows 13, 15, 30, 32, 33 of the table) with the receipt schema-2 gate. Update `_SKILL_PATH_PATTERNS` and `_JUDGE_PATHS`. `mv` `evals/skill-rewrites/skill-doctor/` to `evals/_archive/skill-rewrites-v1/skill-doctor/` after confirming nothing else reads it. | L | Spec criteria 17 to 21. Negative tests: missing `claude_version`, hash mismatch, case edit not in `retired.json`, floor below 8 or 6. The `pr-validation.yml` step name stays, or is renamed with its callers in the same PR. | `uv run pytest tests/validation/test_check_skill_rewrite_evidence.py tests/validation/test_skill_rewrite_evidence.py tests/validation/test_skill_rewrite_skills.py -q`, then `uv run python scripts/validation/check_skill_rewrite_evidence.py --help` for flags. |
| C1.6 | Port the other consumers per the confirmed table (rows 1, 3, 6, 7, 11, 12, 14, 16, 19, 26, 28, 34, 35, 36, and row 23). Delete the skill-corpus cases of `test_eval_prompt_change.py` only after their last caller moves. | L | Every changed consumer's test passes. A kept consumer is untouched (`git diff --stat` lists none of the 16 keep rows). | `uv run pytest tests/eval tests/validation tests/evals tests/commands -q` |
| C1.7 | Remove the migrated corpus from `tests/evals/skill-scenarios/` with `git mv` to `evals/_archive/skill-scenarios-v1/`, never `rm`. Update live docs that tell a reader to run `eval-prompt-change.py` for a skill. State the rollback: `git mv` back. | M | No live check reads `tests/evals/skill-scenarios/`. `git grep -n 'tests/evals/skill-scenarios' -- scripts tests .github` returns only archive or history references. | The grep in the left column. |
| C1.8 | Run the gates. | S | `pre_pr.py` clean. | `uv run python scripts/validation/pre_pr.py` |

Exit: all 59 files converted and parsed by the host, new gate live, consumers ported, ledger holds the Stage 0 pass.
Rollback: revert the merge. The corpus is archived by move, so history and the old gate return together. A paid pass already logged in the ledger stays logged: spend is not reverted.
Irreversible step: Stage 0 spend. Cap $10.

## PR C2: grow the top 8 skills, baseline, hillclimb

Size: L. Spec items 3 and 7. Depends on B and C1 (both merged).

| # | Task | Size | Acceptance criteria | Verification |
|---|---|---|---|---|
| C2.1 | Rank skills with `python3 src/claude/skills/skillopt/scripts/mine_sessions.py rank` (run without `-I`: the script imports `_mine_handoff` from its own directory). Record the top 8, the command, and the date. | S | The 8 names and their ranks are in the PR body. | The command output. If the miner finds no sessions, report `UNAVAILABLE` and ask the owner for a list (halt this branch only). |
| C2.2 | Author new cases for each of the 8 skills to reach at least 12, behavior-first (`tool_used`, `tool_order`, `file_exists`, scaffolded sandbox), with the `llm` verdict grader advisory. Sel (held-out) case bodies are written in a session separate from the one that will propose skill edits. | L | At least 12 cases per skill. A negative control per skill (a case the skill should not trigger). No case is a copy of an existing scenario. | `git ls-files evals/skills/<skill> \| grep -c prompt.md` per skill. |
| C2.3 | Write `evals/skills/<skill>/split.json` (stratified by `family`, then id hash; target 8 train and 4 sel), tags, `frozen_at`, `corpus_sha256`, `split_fingerprint`, `sel_budget`. Commit before any skill edit. | M | The tag check passes. The fingerprint recomputes. Train and sel are disjoint. | `python3 src/claude/skills/skillopt/scripts/skillopt.py` split check subcommand from B6 (name set in B1). |
| C2.4 | Stage 1 baseline, cap $60: with/without, 3 runs, on the 8 skills' cases. Run the trust block first (oracle, known-bad, mechanism probe, noise floor on sel). Ledger line per pass. | L | Trust block passes per skill, or that skill is `NOT RUN` with the reason. Receipts are not written for baseline. Cumulative at or below 70.00. | Ledger tail. `jq` over the aggregate for the headline recompute. |
| C2.5 | Stage 2 baseline of the other converted cases, ablation `none`, 3 runs, cap $100. With/without for these is `NOT RUN` unless budget remains and the owner confirmed the D2 default. | L | The report lists cases run, cases `NOT RUN`, and the reason. Cumulative at or below 110.00 plus the reserve rule. | Ledger tail. |
| C2.6 | Stage 3 hillclimb of the 8 skills, cap $75 (about 3 rounds): one idea per round, train traces only for the proposer, sel passes within `sel_budget`, de-fluff on each proposal, failure taxonomy per pass. Then run the kept candidate on every gated case (train and sel), 3 runs, inside the same cap: that whole-corpus pass is the first candidate pass the receipt hashes and the gate reads (ADR-057 item 6 run rule). Write `receipt.json` only after the trust block passes. Optional cost-hold round if budget remains. | L | A kept edit shows a gain above the noise floor, no pass-to-fail flip, and a passing mechanism probe. A rejected edit goes to the skillopt rejected-edit buffer. | Receipt per skill. `uv run python scripts/validation/check_skill_rewrite_evidence.py` passes. |
| C2.7 | Write the final report: cost by stage, the ledger total, `NOT RUN` portions, noise floors, kept and rejected edits per skill. | M | Total at or below 260.00. Every claim in the report cites a ledger line or a receipt. | `python3 -c` sum over `evals/skills/ledger.jsonl` is a code check, not a model claim. |
| C2.8 | Docs page review for skills whose `SKILL.md` changed (trailer or page edit per skill). Run the gates. | M | `check_agent_skill_doc_review.py` passes. `pre_pr.py` clean. | `uv run python scripts/validation/check_agent_skill_doc_review.py --base-ref origin/main`, then `pre_pr.py`. |

C2 may split into one PR per skill if a diff grows past review size. Skill edits keep the one-skill-per-commit rule so a revert drops one skill.
Exit: 8 skills with 12 or more cases, a committed split, a receipt, and a ledger total at or below $260.
Rollback: revert the skill edit commits per skill. The spend stays in the ledger.

## Risk register

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | D2 baseline cost (about $209 INFERRED) plus 3 climb rounds; resolved by D4 raising the ceiling to $260. | High | Medium: scope cut | Staged caps, Stage 0 measures the real rate, `NOT RUN` reporting, owner decision (spec Open question 1). |
| R2 | Stated-intent prompts never call the Skill tool, so route graders never pass. | Medium | High: the converted corpus tests nothing behavioral | C1.4 measures 5 route cases first. Decision rule in spec item 2. C2 cases are behavior-first. |
| R3 | `arm: both` does not override the Skill with-only default. | Medium | Medium: route graders go unscored | C1.4(d) reads `scored`. Fallback: gate passes use `--ablation none`. |
| R4 | The trace has no served-model field. | Medium | Low | Pinned-model fallback with `served_model_verified: false`, stated in the ADR. |
| R5 | The host schema has no public docs and changes between Claude Code versions. | Medium | High | One adapter module, version check, exit 3 on mismatch, `claudeVersion` in every receipt. |
| R6 | C2 case edits land before C1 teaches `_JUDGE_PATHS` the new path. | Low | High: the gate misses or wrongly blocks | Hard order: C1 merges first. C2.1 starts by confirming `main` contains C1. |
| R7 | ADR-087 is `proposed`, and the review may reject the amendment shape. | Medium | Medium | A5 runs before B and C1 start. |
| R8 | The 37-consumer table has N rows classified from grep counts, not a full read. | Medium | Medium: a missed consumer breaks CI | C1.1 re-verifies each N row before any edit. `pre_pr.py` and the pytest sweep in C1.6 are the net. |
| R9 | A concurrent pass double-spends the ledger. | Low | Medium | File lock on append and on the pre-pass ceiling check (B2). |
| R10 | A pass publishes the report to claude.ai (the CLI default). | Medium | Medium: case prompts and traces leave the machine | The adapter always adds `--no-publish` and refuses a command line without it; `artifact_publish` off per case; C1.4a confirms no URL. |
| R11 | The proposer author also writes sel cases and overfits. | Medium | High | C2.2 requires a separate session for sel bodies. |
| R12 | Generated copies drift after B7. | Low | Low | Rerun `build_all.py` and require a clean `git status`. |

First failure expected: R2 or R3 at C1.4. Both surface in a $10 pass.

## Deferred items (out of this plan)

- Rule, agent, and command corpora on `claude plugin eval`.
- Merging `scripts/eval/optimize-artifact.py` into skillopt.
- Hillclimbing the other 51 skills.
- `baseline` graders from stored traces.
- Deleting `eval-prompt-change.py` once its last non-skill caller moves.

## Reversibility summary

| Step | Reversible | Path |
|---|---|---|
| PR A, B, C1 merges | Yes | Revert commit. |
| Corpus move in C1.7 | Yes | `git mv` back. |
| Archive of skill-doctor v1 results | Yes | `git mv` back. |
| Paid passes | No | Ledger records the spend. Caps limit the exposure. |
| Skill edits in C2 | Yes | Revert per skill commit. |

## Not run during planning

The `milestone-planner`, `task-decomposer`, `analyst`, and `critic` agents (replaced by one author pass). `execution-plans` persistence into `plans/active/` (this file sits at the path the launching agent named). `adr-review`. Any paid `claude plugin eval` run.
