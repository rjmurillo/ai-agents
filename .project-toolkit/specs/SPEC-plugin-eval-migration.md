# SPEC: Move the skill eval suite to `claude plugin eval`

Status: draft for owner review. Date: 2026-11-28. Base commit: 2bec8b73e (main).
Inputs: `.project-toolkit/scratch/plugin-eval-migration/recon.md`, `.../plugin-eval-schema.md`, and the claude-api guide docs `eval-audit.md`, `eval-hillclimb.md`, `cost-hillclimb.md`, `build-eval.md`.
Nothing in this spec is implemented. The next artifact is `.project-toolkit/plans/PLAN-plugin-eval-migration.md`.

## Step 0 First Principles

The requester is the repository owner. The answers below come from `recon.md`, not from a structured Q1 to Q6 interview. `recon.md` holds the owner decisions D1 to D3 and the facts, but not six verbatim answers. In auto mode that is a synthesis, so the owner should confirm them. This block lands in git history. It holds no secrets.

### Q1 Demand Reality

One present-tense requester: the repository owner (`rjmurillo`), who asked for three things on 2026-11-28: update the ADRs, update skillopt, convert the eval suite to `claude plugin eval` and run it. Paired with the Q3 blocker and the Q5 evidence below, as the gate allows.

### Q2 Status Quo

Today an author edits a skill, then runs `scripts/eval/eval-prompt-change.py` against `tests/evals/skill-scenarios/<skill>.json`. The runner puts the SKILL.md in the system prompt and asks the model to "classify your action" with one label (`eval-prompt-change.py:328`, `judge_scenario`). An LLM judge scores the label. For a rewrite, the runner writes an identity block that `check_skill_rewrite_evidence.py` reads (ADR-127 decision 9). skillopt then tunes the skill against the same corpus.

Reframing: capability invention, check: in the C1 smoke pass, at least one converted route case shows a nonzero with-versus-without delta on a `tool_used` Skill grader. Today's runner cannot observe tool use at all. `claude plugin eval` can.

### Q3 Desperate Specificity

The owner, running skillopt on the eight most-used skills. The owner cannot tell a real gain from noise, because the corpus has no held-out split and no noise floor, and the scores come from stated intent, not behavior.

### Q4 Narrowest Wedge

One skill, end to end: convert its scenario file, run an oracle and a known-bad case, run the baseline, and compute the noise floor. About 4 to 8 hours of implementation (INFERRED, not measured). This wedge is the C1 smoke pass. The full scope (PRs A, B, C1, C2) is larger than the wedge by owner decision D2.

### Q5 Observation

- Median scenarios per file is 4 (min 2, max 28), across 59 files and 348 scenarios (2bec8b73e). A median of 4 cannot carry a split or a noise estimate.
- Zero scenarios carry a split key. The only `"sel"` manifests in the repo are 6 copies of skillopt's `references/example-eval.json` (2bec8b73e).
- Grading is stated intent plus keywords. Inputs sampled in analyze, memory, ship, and review say "tell me how you would ... Do not modify any files". The sample is 4 files, so the claim is INFERRED for the other 55.

### Q6 Future-fit

At 10x skills and cases, one case directory per scenario scales, and the ledger bounds cost. The liability is the host schema. `claude plugin eval` has no public docs page. The schema was read from the binary of Claude Code 2.1.332, and four items are UNCONFIRMED (see Open questions). The design isolates the host schema behind one adapter module so a schema change touches one file.

## Step 0.5 Prior Art Block

Sources searched: `git grep` over `.serena/memories/eval/*` and `.serena/memories/decisions/*`, ADR-057, ADR-058, ADR-087, ADR-127, and the `skillopt` skill and scripts. The Hindsight bank was not queried (the memory search was `git grep`, not `memory-search`). That is a coverage gap.

Prior art found:
- ADR-057 owns the Core Pattern, the Acceptance Gate, Scenario Storage, and Cost Expectations.
- ADR-058 holds that deterministic graders gate and the LLM judge is advisory.
- ADR-087 requirements 1 to 5 define the held-out rails. `scripts/eval/optimize-artifact.py` implements them for agent, rule, and hook artifacts.
- ADR-127 decisions 7 to 9 define floors, freeze, and the evidence contract.
- `evals/ponytail-incumbent/run.py` (`build_root`) is the one in-repo precedent for `claude plugin eval` with a scratch root. Its report shows 23.62 USD over 234 runs (`evals/ponytail-incumbent/reports/2026-09-23-report.md`).

H11 note: three or more discovered entities had no match in memory (for example `claude plugin eval`, `experimental.evals`, `aggregate-result.json`). In auto mode the gate halts mechanically. Adjudication: the brief carries the owner's explicit decisions D1 to D3 and names these entities as the subject, so the work is in scope. The spec continues on the brief's authority. The owner should confirm. No risky change type lacks a record: the ADR edits go through `adr-generator` and `adr-review`.

## Problem statement

The skill eval suite grades stated intent with an LLM judge, has no held-out split, no noise floor, and a runner (`eval-prompt-change.py`) that the host tool `claude plugin eval` replaces with real tool-use traces. Move the skill corpus to `claude plugin eval`, port the hillclimb trust checks into skillopt, and replace the ADR-127 evidence contract, under a $260 spend ceiling.

## User stories

1. As the repository owner, I run one skillopt command per skill and get a baseline, a noise floor, and a verdict I can trust, so I stop accepting gains that are noise.
2. As a skill author, I edit a skill and run its train cases and its sel cases from separate commands, so the proposer never sees held-out transcripts.
3. As a reviewer, I read one receipt per rewritten skill, so I can check the evidence without rerunning it.
4. As the next skillopt user with a legacy `eval.json`, I follow `references/migrating-to-plugin-eval.md`, so I migrate without asking the owner.

## Scope decisions (the seven items)

### Item 1: Where cases live

Decision: repo-only `evals/skills/<skill>/<case-id>/` (a `prompt.md` and `graders/*.md` per case), run through a scratch root. Not `src/claude/evals/`. Not `experimental.evals`.

Reasons, each grounded in a file read:
- `src/claude/` is a shipped plugin root (`.claude/rules/plugin-self-containment.md`, "The boundary"). Cases and expected-outcome rationale are repo-only content. Both `src/claude/evals/` and an `experimental.evals` path inside `src/claude/` ship them to consumers.
- `claude plugin eval src/claude --trust-plugin --case zzz` resolves `src/claude` as the plugin root with default dir `src/claude/evals/` (`plugin-eval-schema.md`, "Target and manifest"). That confirms the shipped option works but does not make it right.
- `--eval-dir` must be relative with no `..` and no absolute path (verified, `recon.md`). A repo-only dir outside the plugin root cannot be passed directly.
- `evals/ponytail-incumbent/run.py` `build_root` already solves this: copy the plugin and the cases into a throwaway root outside the repo, run `claude plugin eval <root>`. Scratch output also lands outside `src/claude`.
- `build/scripts/binplace_manifest.py` and `templates/platforms/binplace.yaml` carry no `evals` row, so `evals/` is not generated or shipped. The `ai-agents-generation-and-release` rule `rule-generated-artifacts.md` is not triggered by `evals/`.

Layout: `evals/skills/<skill>/split.json` (the skillopt manifest), `evals/skills/<skill>/<case-id>/prompt.md`, `evals/skills/<skill>/<case-id>/graders/<name>.md`, `evals/skills/ledger.jsonl` (append-only spend ledger). Receipts live in `evals/skill-rewrites/<skill>/receipt.json` (item 4).

The generic scratch-root builder ships in skillopt (`_skillopt_plugin_eval.py`, item 5), so any skillopt user can run it with `--plugin-root` and `--cases-dir`. The repo-specific wrapper stays in `evals/skills/run.py`.

### Item 2: Mapping from scenario JSON to prompt.md plus graders

Both corpora move: the D2 corpus `tests/evals/skill-scenarios/*.json` (59 files, 348 scenarios at 2bec8b73e) and the ADR-127 verdict corpus `tests/evals/<skill>-scenarios.json` for skills under rewrite. D2 names only the first. The second is read by `check_skill_rewrite_evidence.py` (`_SKILL_PATH_PATTERNS`, `^tests/evals/(?P<n>[^/]+)-scenarios\.json$`), so leaving it would leave the old gate alive. Rule-scenario, agent-scenario, and other `tests/evals/*-scenarios.json` files (30 top-level files at 2bec8b73e, mostly agent and command corpora) stay where they are.

| Scenario key | Becomes | Rule |
|---|---|---|
| `id` | case directory name and `name` | One directory per scenario. |
| `desc` | `description` | Verbatim. |
| `input` | `prompt.md` body | Verbatim. No rewording of "tell me how you would" framing. |
| `rationale` | `expected_outcome` and the `llm` grader `criteria` | The judge reads the rationale. |
| `family` (17 files) | `tags: ["family:<value>"]` | Tag, no grader. |
| `expected_route` | `tool_used` grader, `tool: Skill`, `input_match: '"skill"\s*:\s*"(?:[\w-]+:)?<skill>"'`, `arm: both` | `arm: both` is required. Without it, a Skill `tool_used` grader is with-only and unscored (`plugin-eval-schema.md`, "Scoring"). |
| `forbidden_routes` | `tool_used` grader, same `tool`, `min: 0`, `max: 0`, `arm: both` | One grader per forbidden route. |
| `expected_gate` | `regex` grader on `last_message` only when the gate is a literal contract string (command, path, exit code, fixed label). Otherwise folded into the `llm` criteria. | Reviewed in the C1 diff. |
| `expected_signals` | Dropped as keyword regexes. A signal that is a contract string becomes a `regex` grader. Others feed the `llm` criteria text. | Pure keyword matching tests the judge's vocabulary, not behavior. |

Every case sets `allowed_tools: [Skill, Read, Glob, Grep]` (read-only, matches "do not modify any files") and `max_turns: 6`. `allowed_tools` must list `Skill`, because a scored grader with `min >= 1` needs its tool allowed. Every case gets one `llm` grader (weight 1) for the verdict. Per ADR-058, that grader is advisory: the gate recomputes from deterministic graders only (item 6). A case with no deterministic grader is `advisory-only`: it runs, it is reported, it is not gated, and the PR C1 body lists the count.

Rule: new C2 cases are authored behavior-first (`tool_used`, `tool_order`, `file_exists` in a scaffolded sandbox), not stated-intent.

Risk with a decision rule: stated-intent prompts may not make the model call the Skill tool. The C1 smoke pass runs 5 route cases with the plugin. If 0 of 5 show a Skill call in the trace, the converter drops the route graders for the stated-intent cases and keeps them for behavior-first cases only. Do not rewrite the prompts to force a tool call.

### Item 3: Splits and ADR-087

Decision: tags plus a skillopt split manifest. The manifest is the source of truth. Tags make `--tag split:train` and `--tag split:sel` runnable.

- Each case's `prompt.md` carries `tags: ["split:train"]` or `["split:sel"]`.
- `evals/skills/<skill>/split.json` is the skillopt `eval.json` v1 manifest shape (`splits`, `exposed`, `tasks`) plus `frozen_at` (base commit), `corpus_sha256`, `split_fingerprint`, and `sel_budget`.
- A check fails when a case tag disagrees with the manifest.

ADR-087 requirements 1 to 5, met as follows:

1. Split fixed before the first edit: `split.json` is committed in C2 before round 1, with `frozen_at` set. A later change to membership needs a new manifest and a new ledger key.
2. Tamper-evident: `split_fingerprint` is sha256 over the ordered `(case id, prompt.md sha256, graders sha256)` tuples per split. Every pass recomputes it and refuses on mismatch. A conformance test pins skillopt's fingerprint to `_optimizer_core.split_fingerprint` (canonical-source-mirror rank 2). skillopt is stdlib and cannot import `scripts/eval/`, so it carries its own copy and the test binds them.
3. Budgeted consultations: `sel_budget` (default 3 sel passes per skill). The ledger key is `(skill, sel membership hash, corpus_sha256)`, so reshuffling sel does not reset the budget.
4. No pass-to-fail on an aggregate gain: the gate compares per-case majority outcomes before and after, from recomputed deterministic scores. Any case that flips pass to fail blocks, whatever the mean does.
5. Corpora that disagree are refused: the manifest `corpus_sha256` must equal the hash of the case tree the aggregate result ran. Otherwise the pass is refused.

Split rule for C2: stratified by `family` where present, then by case id hash, target 8 train and 4 sel at 12 cases. Held-out (sel) case bodies come from an authoring session separate from the candidate-edit author. This keeps the author of a skill edit from writing the cases that judge it.

### Item 4: Replacement for the ADR-127 decision 9 evidence contract

Decision: replace `results.json` with a schema-2 receipt, and move the gate's data source. Breaking, per the owner's constraint. Semantics carry over unchanged: floors of 8 cases and 6 carried, scenario freeze, `retired.json`, append-only history, `_JUDGE_PATHS`.

Receipt `evals/skill-rewrites/<skill>/receipt.json` (schema 2):
`schema`, `skill`, `prompt_surface_sha256`, `cases_sha256`, `split_fingerprint`, `base_commit`, `claude_version` (from `claudeVersion`), `served_model` and `served_model_verified` (read from the trace, item 5), `ablation`, `runs`, `aggregate_sha256`, `gate` (per-case recomputed outcome, flake rate, flips), `trust` (noise floor, mechanism probe, oracle and known-bad result), `cost_usd` (sum of `costUsd` plus `judgeCostUsd`).
The raw `aggregate-result.json` is stored beside it with `tracePath` fields kept and the trace files left out of git.

Gate change: `check_skill_rewrite_evidence.py` stops calling `load_runner()` (which imports `eval-prompt-change.py` by path). It validates the receipt, recomputes `prompt_surface_sha256` and `cases_sha256` from the tree, checks the floors, the freeze, and `retired.json`, and recomputes the headline from `aggregate-result.json` instead of trusting the receipt. `_SKILL_PATH_PATTERNS` and `_JUDGE_PATHS` change to name `evals/skills/<skill>/` in place of `tests/evals/skill-scenarios/` and `tests/evals/<skill>-scenarios.json`.

Ordering: C1 must merge before any C2 case edit. `_JUDGE_PATHS` marks judge-surface files whose change forces new evidence. If C2 edits cases under `evals/skills/` before C1 teaches the gate that path, the gate either misses the change or blocks it for the wrong reason.

Legacy data: `evals/skill-rewrites/skill-doctor/results.json` (schema 1, the only skill directory under `evals/skill-rewrites/` at 2bec8b73e) moves with `mv` to `evals/_archive/skill-rewrites-v1/skill-doctor/`. The gate reads schema 2 only.

Text gap: ADR-127 decisions 7 and 9 name the old runner and identity block. Owner decision D1 limits amendments to ADR-057 and ADR-087. Recommended default: PR A also adds a one-line pointer note in ADR-127 ("evidence contract superseded in part by ADR-057 amendment 2026-11-28"), logged as a non-frontmatter edit per `AGENTS.md`. See Open questions.

#### Disposition of every `tests/evals` consumer

Pathspec: `git grep -l 'tests/evals' -- 'scripts/**/*.py' 'tests/**/*.py' '.github/**/*.yml'` returns 37 files at 2bec8b73e. A literal `git grep -l 'tests/evals'` across the whole tree returns 213 at 2bec8b73e (docs, ADRs, memories, retros, and others). Seventeen more files build the path with a path join and not a literal. The groups below cover the 37, then the rest.

Classification of files the author opened (marked R) is from the code. Others (marked N) are from `grep -c` counts of `skill-scenarios`, `rule-scenarios`, and `-scenarios.json` in each file, run at 2bec8b73e, and from the matching `tests/evals` line. The plan's C1 task 1 re-verifies every N row with `git grep -n` before editing.

| # | File | Reads | Disposition |
|---|---|---|---|
| 1 | `.github/workflows/validate-rule-activation-coverage.yml` | `skill-scenarios` (2 hits), `rule-scenarios` (1) | Port: update the `paths:` filter to include `evals/skills/**`. N |
| 2 | `scripts/eval/_eval_agent_types.py` | comment only (line 30) | Keep. N |
| 3 | `scripts/eval/eval_autoplan_routes.py` | `skill-scenarios` (2) | Port: read route fields from case graders. N |
| 4 | `scripts/eval/eval-model-sweep.py` | docstring example only (line 28) | Keep. N |
| 5 | `scripts/eval/eval-prompt-change.py` | `<skill>-scenarios.json` verdict corpus | Replace for skills: skillopt `run` takes over. The runner stays for non-skill callers until its last caller moves. R |
| 6 | `scripts/eval/eval-rule-activation.py` | `rule-scenarios` (5), `skill-scenarios` (1) | Port the one `skill-scenarios` reference. Rule path unchanged. N |
| 7 | `scripts/eval/eval-suite.py` | `rule-scenarios`, name-scenarios lookup | Port the skill lookup in the name-scenarios resolution (lines near 406). N |
| 8 | `scripts/eval/optimize-artifact.py` | comment on `rule-scenarios` (line 906) | Keep. Agent, rule, and hook kinds are out of scope. R |
| 9 | `scripts/eval/software_engineering_library_activation_ci.py` | `rule-scenarios` (10) | Keep. N |
| 10 | `scripts/validation/check_agents_write_targets.py` | `_EVAL_DATA_PREFIX = "tests/evals/"` (line 66) | Keep. The prefix still exists for the other corpora. N |
| 11 | `scripts/validation/check_route_scenario_coverage.py` | `skill-scenarios` (2) | Port: read `expected_route` graders from case dirs. N |
| 12 | `scripts/validation/check_rule_activation_coverage.py` | `rule-scenarios` (2), `skill-scenarios` (2) | Port the skill reference. N |
| 13 | `scripts/validation/check_skill_rewrite_evidence.py` | verdict corpus, runner identity | Replace: receipt schema 2. R |
| 14 | `scripts/validation/check_skill_routing_roles.py` | `skill-scenarios/{name}.json` (line 247, 312) | Port to the case tree. R |
| 15 | `scripts/validation/skill_rewrite_scenarios.py` | verdict corpus loader | Replace with a case-tree loader. R |
| 16 | `scripts/validation/testmon_data_inputs.py` | `DATA_ROOT = "tests/evals/"` (line 45) | Port: add `evals/skills/` as a data root. N |
| 17 | `tests/commands/test_spec_step0_5.py` | `spec-scenarios.json` | Keep. Not a skill-scenarios file. N |
| 18 | `tests/evals/test_hook_feedback_scenarios.py` | hook corpus | Keep. N |
| 19 | `tests/evals/test_no_unicode_dashes.py` | `tests/evals/` dash scan | Port: also scan `evals/skills/`. N |
| 20 | `tests/eval/test_capability_first_run.py` | `rule-scenarios` | Keep. N |
| 21 | `tests/eval/test_capability_first_scenarios.py` | `rule-scenarios` (11) | Keep. N |
| 22 | `tests/eval/test_eval_model_sweep_cli.py` | `Path("tests/evals/x")` fixture | Keep. N |
| 23 | `tests/eval/test_eval_prompt_change.py` | verdict corpus (33 scenario-name hits) | Delete the skill-corpus cases when the runner's last skill caller moves. Port the rest. N |
| 24 | `tests/eval/test_eval_suite_routing.py` | `rule-scenarios` (7) | Keep, with a port for any skill lookup. N |
| 25 | `tests/eval/test_optimize_artifact_cli.py` | `rule-scenarios` (3) | Keep. N |
| 26 | `tests/eval/test_skillforge_depth_scenarios.py` | `skill-scenarios` (2) | Port to read the case tree. N |
| 27 | `tests/eval/test_software_engineering_library_activation_gate.py` | `rule-scenarios` (1) | Keep. N |
| 28 | `tests/eval/test_spec_reframing_scenarios.py` | `skill-scenarios` (2) | Port to read the case tree. N |
| 29 | `tests/skills/orphan-ref-validator/test_references_and_retired_surface.py` | string `tests/evals/skills/triage-prompts.json` (line 225) | Keep. A retired-path fixture, not a read. N |
| 30 | `tests/validation/skill_rewrite_helpers.py` | verdict corpus | Replace: build receipt fixtures. N |
| 31 | `tests/validation/test_check_agents_write_targets.py` | prefix | Keep. N |
| 32 | `tests/validation/test_check_skill_rewrite_evidence.py` | verdict corpus | Replace: test schema 2. N |
| 33 | `tests/validation/test_skill_rewrite_evidence.py` | verdict corpus | Replace. N |
| 34 | `tests/validation/test_skill_rewrite_skills.py` | verdict corpus | Port. N |
| 35 | `tests/validation/test_skill_routing_report.py` | `skill-scenarios` (3) | Port. N |
| 36 | `tests/validation/test_testmon_data_inputs.py` | `rule-scenarios`, agents | Port for the new data root. N |
| 37 | `tests/validation/test_testmon_tree_scanners.py` | `profile-behavior-runtime-fixtures.json` | Keep. N |

Totals (counted from the table, 37 rows): port 14 (rows 1, 3, 6, 7, 11, 12, 14, 16, 19, 26, 28, 34, 35, 36), replace 6 (rows 5, 13, 15, 30, 32, 33), delete-and-port 1 (row 23), keep 16 (rows 2, 4, 8, 9, 10, 17, 18, 20, 21, 22, 24, 25, 27, 29, 31, 37). The plan's task 1 recomputes these after re-verifying the N rows.

Outside the 37: docs, ADR text, memories, and retros that cite `tests/evals/skill-scenarios` keep their text. History is not rewritten. Live docs that tell a reader to run `eval-prompt-change.py` for a skill get a correction in C1 (`docs/skills/skillopt.md` and any `docs/` page the plan's task 1 grep finds). The 17 path-join consumers are classified by the same task.

### Item 5: What skillopt gains

Canonical source: scripts, references, and tests live in `src/claude/skills/skillopt/` and are hand-maintained there (`.claude/rules/claude-agents.md` MUST 8). Prose source is `templates/skills/skillopt.SKILL.md.tmpl`. Copies under `src/codex`, `src/copilot-cli`, and `src/cursor` are regenerated by `uv run python build/scripts/build_all.py`. `.claude/skills/skillopt` links to the same directory (ADR-119). Never edit the generated copies.

New or changed modules in `src/claude/skills/skillopt/scripts/`, all stdlib:

| Module | Gain |
|---|---|
| `_skillopt_plugin_eval.py` (new) | The one adapter to the host schema: scratch-root build, `claude plugin eval --json` call, aggregate parse, ledger append, `--max-cost-usd` per pass. Replaces the runner contract in `_skillopt_runner.py`. |
| `_skillopt_trust.py` (new) | Noise floor, mechanism probe, oracle and known-bad run, headline recompute, judge spot-check, served-model read. |
| `_skillopt_taxonomy.py` (new) | Failure taxonomy from `error`, `aborted`, and the trace. |
| `_skillopt_gates.py` (extend) | Gate math on recomputed scores, per-case flip check, cost-hold mode. |
| `_skillopt_evidence.py`, `_skillopt_evidence_cli.py` (extend) | Receipt schema 2. |
| `skillopt.py` (extend) | New subcommands: `run`, `trust`, `taxonomy`, `traces`. The exact names and exit codes are set in PR B and covered by contract tests (`claude-agents.md` MUST 7). |

I did not open every `_skillopt_*.py` file. The plan's PR B task 1 reads them before the design is fixed. File names above are from the directory listing at 2bec8b73e.

What each gain does, with its host-schema workaround (the schema has no served-model field, no CI, no failure class, and no split):
- Noise floor. The schema reports only means, and per-run scores sit in `arms.*[].score`. skillopt reruns the sel cases of an unchanged skill once, takes the per-case paired difference, and reports the 95 percent half-width (1.96 times the standard error of the mean difference). A gain at or below the floor is noise.
- Mechanism probe. Build a scratch plugin copy without the target skill and rerun. The with-arm score must drop below the baseline by more than the floor. If it does not, the cases do not test the skill, and the pass is refused.
- Oracle and known-bad. Before the first full pass, run one case whose regex grader is trivially satisfiable (must score 1.0) and one inverted copy (must score 0.0). A harness that cannot do both is broken.
- Headline recompute. The gate sums `graders[]` (`passed`, `weight`, `scored`) and does not trust `score`. A mismatch with `aggregates.score` fails the pass.
- Failure taxonomy. Classes: `aborted` or duration at the case `timeout_seconds` is `timeout`. An `error` string matching rate, auth, 5xx, or connection patterns is `harness_or_serving`. No error, zero tool calls, and a refusal phrase in the last message is `refusal`. A judge failure or `skippedPaidGraders` is `grader_error`. Everything else with a failed deterministic grader is `genuine`. Only `genuine` runs count toward score deltas. The others are reported with counts.
- Served model. Read the assistant `model` field from the trace at `tracePath`. UNCONFIRMED that the trace carries it. Fallback: pin `model:` in the case frontmatter and record `served_model_verified: false`. The ADR text says so.
- Judge spot-check. Sample 5 baseline failures per skill and print the judge `explanation` next to the trace excerpt for a human read. Output only. No auto-decision.
- Analyzer reads train only. `skillopt traces --split train` is the only path that gives the proposer transcripts. The manifest `exposed` list records what the proposer saw. Sel traces never enter it.
- De-fluff and one idea per round. A proposed change carries one `idea` field and one diff. Each added sentence must name the failing case it addresses, or the de-fluff pass removes it.
- Cost-hold mode. The `cost-hillclimb.md` adoption gates, as `skillopt gate --mode cost`: quality within the noise floor of baseline, mean `costUsd` (plus `judgeCostUsd`) lower by a stated margin, and the mechanism probe still passing.

Relation to `scripts/eval/optimize-artifact.py`: it is the repo-only optimizer for agent, rule, and hook kinds, with its own ADR-087 rails (`_optimizer_core.py` holds `split_tasks` and `split_fingerprint`). skillopt owns skills. This change does not touch it, and the two optimizers stay separate. Merging them is deferred.

Migration reference: `src/claude/skills/skillopt/references/migrating-to-plugin-eval.md`. It lists every breaking change (old `eval.json` and scenario JSON go away, the runner contract changes, the receipt is schema 2, the ledger moves), the mapping table from item 2, and the steps a later skillopt run follows to convert a legacy corpus. This meets the owner's instruction to add a migration reference. It cites the repo converter `scripts/eval/convert_skill_scenarios.py` as the reference implementation of the mapping.

Docs: PR B edits `docs/skills/skillopt.md` (`.claude/rules/agent-skill-docs.md` MUST 2), or carries a `Docs-Reviewed: skillopt` trailer only after reading the page in the same session.

### Item 6: ADR-057 and ADR-087 amendment content

Both go through `adr-generator`, then `adr-review`. ADR-087 is `proposed`. Amending a proposed ADR is allowed, and `adr-review` decides the verdict.

ADR-057 amendment (dated 2026-11-28), as revised after the full panel's first round:

1. Runner swap. `claude plugin eval` is the Core Pattern runner for skill cases. `eval-prompt-change.py` stays for non-skill corpora until their callers move.
2. Scenario Storage. Skill cases live in `evals/skills/<skill>/<case-id>/`. Retire the old skill corpus only at C1, after porting every consumer.
3. Gate math. Reproduce the host headline over all scored graders; gate separately on the deterministic with-skill arm. A run passes only when all scored deterministic graders pass. Freeze gated membership from the expected deterministic graders; advisory-only cases count toward no floor. Preserve `ceil(2n/3)`, the 40 percent flake block, the stable-base fraction over gated cases, and flip blocking against the frozen baseline. Distinguish unscored infrastructure or grader errors from refusals, which fail on either side. Require sufficient after-side scored runs; the security tier requires 5 scored runs at 100 percent and no advisory-only cases. The hillclimb decision reads sel; repository evidence covers the whole gated corpus, including the 8-case and 6-carried floors. Require at least 3 gated sel cases.
4. Pin the judge model per pass; compare only compatible host and model identities.
5. Trust checks. Separate host-headline verification from deterministic gate scoring. Measure the noise floor from deterministic paired differences, using the t critical value and a nonzero minimum of one case divided by the number of cases being compared. Use a mechanism probe that excludes route-only signals, oracle and known-bad, failure taxonomy, served-model check and a train-only judge spot-check. An improvement must exceed the floor; an ordinary no-regression acceptance need not improve. Store the aggregates needed to recompute the gate. The detailed definitions and limits in ADR-057 Amendment 2026-11-28 govern where earlier items of this spec differ.
6. Cost exception. Keep the `$50 per month, reassess` line. A one-time exception allows $260 total (D4, 2026-11-28), with the five owner-approved stage caps. Reserve projected spend against remaining stage and total balances before each pass and settle on completion. Release larger stages only after owner approval of measured affordability and gated-case coverage. The pass cap is the smaller of remaining stage and total balances, allowing for in-flight overshoot. Record stage, skill and pass kind. Use one checkout for paid passes. End the exception when C2 closes (the last PR if split). Do not apply this repository's ceiling as a permanent skillopt default.

ADR-087 amendment (dated 2026-11-28): restate Decision Requirements 1 to 5 for the skill path. The split manifest adds `seed`, `sel_ratio`, and `tier`. `split_fingerprint` uses the canonical `_optimizer_core.split_fingerprint` algorithm (case ids, seed and ratios); the conformance test pins the stdlib copy. `corpus_sha256` binds split membership and case content as specified in the amendment; it equals receipt `cases_sha256`. Refuse a mismatch. Key `sel_budget` on skill and selection membership; changing corpus content alone does not reset the budget. Charge a candidate consultation before it starts, including partial or failed consultations. Pre-candidate fixed trust controls do not charge candidate consultations if they disclose no selection results to the proposer. The ledger also records the corpus identity, membership digest, and pass kind. The same-user boundary is procedural, and ADR-087 remains proposed. These revised definitions supersede earlier inconsistent gate, split and run-protocol details in this spec.

### Item 7: Run protocol under a $260 ceiling

Rates are INFERRED, not measured: about $0.10 per run, from 23.62 USD over 234 runs in the ponytail report. The first smoke pass measures the real rate and the plan rescales every later stage from it.

Conflict to surface: decision D2 asks for a with/without baseline on all cases at 3 runs. The existing corpus is 348 scenarios (2bec8b73e). 348 cases times 3 runs times 2 arms is 2,088 runs. At about $0.10 per run that is about $209 for generation alone, before judge cost and before the C2 growth cases. That exceeds D3's $150. The owner decides. Default below. Resolved by owner decision D4 (2026-11-28): the ceiling rises to $260, so the D2 baseline runs as asked: every case at 3 runs, with/without on the 8 hillclimb skills and ablation `none` elsewhere, plus about 3 hillclimb rounds.

Ledger: `evals/skills/ledger.jsonl`, append-only, one line per pass: pass id, UTC time, command, `corpus_sha256`, runs, ablation, sum of per-run `costUsd` plus `judgeCostUsd`, `partial` and `partialReason`, cumulative total. Per-run sums are used because top-level `costUsd` may exclude judge cost (UNCONFIRMED).

Before every pass: cumulative plus the pass's projected cost must not exceed 260. The pass runs with `--max-cost-usd min(stage cap, 260 - cumulative)`. A pass that stops with `partialReason: cost_ceiling` is recorded and its unrun cases are reported `NOT RUN`.

Stages and caps (default, rescaled after Stage 0):

| Stage | Content | Cap |
|---|---|---|
| 0 | Smoke and oracle: `--help` flag check, oracle and known-bad case, 5 route cases with the plugin, one skill end to end. 1 run per case. | $10 |
| 1 | With/without baseline, 3 runs, on the cases of the 8 hillclimb skills (up to 96 cases at 12 each). | $60 |
| 2 | Baseline of the other converted cases, ablation `none`, 3 runs. With/without for these is `NOT RUN` unless budget remains. | $100 |
| 3 | Hillclimb, 8 skills: train passes with `--tag split:train`, sel passes within `sel_budget`. Ablation `none`. | $75 (about 3 rounds) |
| reserve | Noise-floor repeats and one retry per stage. | $15 |

Every pass runs from the scratch root, so output lands outside `src/claude`. `claude plugin eval` publishes the HTML report to claude.ai by default when the account supports it (`--help`: `--no-publish` "Keep the HTML report local only", `--publish-report` "already the default"). Every pass passes `--no-publish`, the adapter refuses to build a command line without it, and every case sets `artifact_publish` off. A pass that publishes anything is a defect.

Every hillclimb pass writes `evals/skill-rewrites/<skill>/receipt.json` only after the trust block passes.

## Ontology

- Case: one directory, a `prompt.md` and graders. Replaces Scenario.
- Grader: deterministic (`regex`, `tool_used`, `tool_order`, `file_exists`) or advisory (`llm`, `baseline`).
- Split: `train` or `sel`, recorded in the manifest and as a tag.
- Pass: one `claude plugin eval` invocation, recorded as one ledger line.
- Receipt: the schema-2 evidence file for one skill rewrite.
- Scratch root: a throwaway copy of the plugin plus the cases, outside the repo.
- Bounded contexts: the host tool (`claude plugin eval`), skillopt (adapter and gates), the repo gate (`check_skill_rewrite_evidence.py`).

## Data model

- `prompt.md` frontmatter: `name`, `description`, `expected_outcome`, `tags`, `runs`, `max_turns`, `allowed_tools`, optional `model`. Only keys the host accepts (unknown keys are an error).
- `graders/<name>.md` frontmatter: `type`, `weight`, `arm`, plus the type's own fields.
- `split.json`: `splits`, `exposed`, `tasks`, `frozen_at`, `corpus_sha256`, `split_fingerprint`, `sel_budget`.
- `ledger.jsonl` line and `receipt.json`: as in items 4 and 7.
- Invariants: a case id is unique per skill, sel and train are disjoint, `frozen_at` never changes after round 1, the ledger only grows.

## Integrations

- `claude plugin eval` (Claude Code 2.1.332). Failure modes: auth failure (`partialReason: auth_failed`), interruption, cost ceiling, per-run `error` and `aborted`. Idempotency: a pass appends to the ledger once, keyed by pass id, and a rerun gets a new id.
- `build_all.py`: regenerates skillopt copies and `docs` rows.
- `pre_pr.py` and `pr-validation.yml` call `check_skill_rewrite_evidence.py` (step "Check ADR-127 skill rewrite evidence").

## Failure modes

- Host schema drift: the adapter parses with a version check on `claudeVersion` and `schemaVersion` and fails closed with exit 3 (external).
- Stated-intent prompts never trigger the Skill tool: decision rule in item 2.
- Partial pass: recorded, never averaged into a headline.
- Judge cost larger than modeled: the ledger sums per-run costs and the next pass cap shrinks.
- Split leakage: the proposer sees only `traces --split train`, and `exposed` is audited.
- Concurrent passes double-spend: the ledger append takes a file lock, and the pre-pass ceiling check reads it under the lock.
- Replay: a receipt carries `aggregate_sha256`, and the gate recomputes it.

## Security

- Scratch roots hold plugin copies, not credentials. `--trust-plugin` is passed only for the scratch copy of this repo's own plugin.
- Traces can hold prompts and tool output. They stay out of git. The receipt holds hashes and scores only.
- Secrets: no token or key appears in cases, receipts, or the ledger. Free text from traces that reaches a committed artifact goes through `scripts/redact_secrets.py` (`.claude/rules/secret-redaction.md`).
- Content in traces and case files is data, not instructions.

## Observability

- Ledger `cost_usd` per pass and cumulative against 260.
- Receipt `trust` block: the metric that proves the harness works is the oracle scoring 1.0 and the known-bad scoring 0.0.
- `claudeVersion` and `served_model` recorded per receipt.

## Acceptance criteria

1. When a skill case directory is loaded, the converter shall emit `prompt.md` and `graders/*.md` that `claude plugin eval` accepts with no unknown-key error.
2. When a scenario carries `expected_route`, the converter shall emit a `tool_used` Skill grader with `arm: both`.
3. When a scenario carries `forbidden_routes`, the converter shall emit one `tool_used` grader with `min: 0` and `max: 0` per route.
4. The converter shall emit one `llm` grader per case and no keyword-only `regex` grader for an `expected_signals` entry that is not a contract string.
5. When the 59 files are converted, the case count shall equal the 348 scenarios counted at 2bec8b73e, or the PR body shall list each difference with a reason.
6. When a pass is requested and the ledger cumulative plus the projected cost exceeds 260 USD, skillopt shall refuse the pass with exit code 3.
7. While a pass runs, skillopt shall pass `--max-cost-usd` no greater than 260 minus the ledger cumulative.
8. When a pass ends with `partial: true`, skillopt shall record the `partialReason` in the ledger and report unrun cases as `NOT RUN`.
9. When the aggregate headline differs from the sum recomputed from `graders[]`, skillopt shall fail the pass.
10. When the oracle case scores below 1.0 or the known-bad case scores above 0.0, skillopt shall refuse every later pass for that skill.
11. When the mechanism probe does not show a with-arm drop larger than the noise floor, skillopt shall refuse the skill's gate result.
12. When a case tag disagrees with `split.json`, the split check shall fail.
13. When the recomputed `split_fingerprint` differs from the manifest, skillopt shall refuse the pass.
14. When a sel pass would exceed `sel_budget`, skillopt shall refuse it.
15. When any case flips from pass to fail between the baseline and a candidate, the gate shall block the candidate, whatever the mean change.
16. When `skillopt traces --split sel` is invoked in a proposer context, skillopt shall refuse.
17. When a skill rewrite PR changes a skill under `src/claude/skills/<skill>/`, `check_skill_rewrite_evidence.py` shall require a schema-2 receipt whose `prompt_surface_sha256` and `cases_sha256` match the tree.
18. The receipt shall carry no scenario count below the floor of 8 cases and 6 carried.
19. When a case is edited in the same PR as its skill rewrite and the case is not in `retired.json`, the gate shall fail.
20. When the receipt `claude_version` is missing, the gate shall fail.
21. When `evals/skill-rewrites/skill-doctor/results.json` (schema 1) is the only evidence, the gate shall report it as unreadable, and the archived copy shall sit under `evals/_archive/skill-rewrites-v1/skill-doctor/`.
22. When PR B lands, `references/migrating-to-plugin-eval.md` shall exist and list every breaking change in item 5.
23. When PR A lands, `adr-review` shall return a verdict for both amendments, and the ADR-057 amendment shall name the $260 exception.
24. When PR C2 closes, the ledger cumulative shall be at or below 260.00 USD, and each of the 8 skills shall have at least 12 cases with a committed `split.json`.
25. No authored file in these PRs shall contain an em dash or an en dash.

## Out of scope

- Rule scenarios (`tests/evals/rule-scenarios/`, 40 files), agent scenarios, command scenarios, and `eval-rule-activation.py`.
- Merging `optimize-artifact.py` into skillopt.
- Hillclimbing the other 51 skills (they get a baseline only).
- Any change to the host tool.
- A new ADR (owner decision D1).

## Deferred

- Move rule and agent corpora to `claude plugin eval`. Owner: repository owner. Trigger: after C2 shows the noise floor on skills.
- Unify the two optimizers. Owner: repository owner.
- Trim the `llm` grader to `baseline` graders once trace baselines exist.

## Open questions

1. RESOLVED (D4, 2026-11-28): ceiling raised to $260; stage caps $10, $60, $100, $75, reserve $15.
2. ADR-127 pointer note in PR A, beyond D1's two ADRs. Recommended default: yes, one line, logged. Owner: repository owner.
3. End date of the $260 exception. Recommended default: closes when PR C2 closes. Owner: repository owner.
4. UNCONFIRMED host items, each with a smoke check and a fallback. (a) `arm: both` overrides the Skill with-only default. Check: read `scored` in a smoke result. Fallback: gate passes use `--ablation none`. (b) The trace carries the served model. Check: read one trace. Fallback: pin `model:` and record `served_model_verified: false`. (c) Top-level `costUsd` includes judge cost. Check: compare to the per-run sum. Fallback: sum per-run. (d) A publish or no-publish flag exists. Check: `claude plugin eval --help`. Fallback: `artifact_publish` off per case.
5. Step 0 and H11 gate notes above need owner confirmation. Owner: repository owner.

## CVA summary

- Common: one case shape, one adapter, one receipt, one ledger for every skill.
- Varies: per-skill graders, split membership, floors (security tier at 5 runs).
- Relationships: case to split (tag plus manifest), split to ledger (key), pass to receipt (hash chain).

## Buy-vs-build decision

Classification: runner is context, gates are core. Alternatives: keep `eval-prompt-change.py`; adopt only the claude-api guide docs (they are docs, with no runnable code); buy the host runner and build the gates. Recommendation: buy the runner, build the adapter and gates. Rationale: the host runner records real tool traces, which the old runner cannot, and the gates are repo policy that no vendor tool provides.

## Complexity classification

Engineering tier 4 (ADR amendments, a gate replacement, 37 consumers). Problem domain: Complicated (known mechanics, several unknowns that a smoke pass resolves). Methodology: plan, four PRs, Stage 0 smoke before spend.

## ADR cross-reference

ADR-057 and ADR-087 are amended in PR A. ADR-058 is unchanged and constrains item 2. ADR-127 decisions 7 and 9 are superseded in part (Open question 2).

## Not run during this spec

`mine_sessions.py rank` (the top-8 list is chosen in PR C2 task 1). `adr-review`. Any paid `claude plugin eval` run. A Hindsight search. The full spec-generator REQ, DESIGN, TASK split.
