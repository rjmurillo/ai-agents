---
name: ai-agents-empirical-probe-toolkit
description: Prove-it methods for this repo. Six recipes for runtime-contract probes, guard and threshold calibration, eval A/B, docs-vs-reality audits, reproduce-on-main CI triage, and negative-control test design, each with a worked example from repo history. Use when you say `probe the runtime contract`, `calibrate this guard`, `prove it empirically`. Do NOT use for the portability battle plan (use `ai-agents-portability-campaign`) or evidence standards (use `ai-agents-validation-and-qa`).
version: 1.0.0
---

# AI Agents Empirical Probe Toolkit

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->
This skill is the method library for replacing assumption with measurement. Every recipe exists because an assumption shipped here and became an incident. The house rule, from the #2290 payload-format incident: the cost of a probe is 15 minutes; the cost of assumption is a P0 (`.serena/memories/copilot-hooks-observations.md`).

Two terms used throughout:

- **Probe**: a minimal disposable artifact (a hook that dumps its environment, a script that captures stdin) run against the real pinned tool to observe what the tool actually does, instead of what its docs say.
- **Negative control**: a deliberately broken input run through the same harness as the passing case, proving the test or probe CAN fail. A check that cannot fail proves nothing.

## Triggers

- `probe the runtime contract`
- `calibrate this guard`
- `prove it empirically`
- `add a negative control`
- `docs versus reality audit`

## Recipe Selector

| Situation | Recipe | Related skill |
|-----------|--------|---------------|
| You are about to rely on undocumented tool behavior (cwd, env vars, stdin format) | 1. Runtime-contract probe | `agent-harness-reference` for settled contracts |
| You are shipping a detector, guard, or numeric threshold | 2. Guard/threshold calibration | `guard-maturity` for post-ship monitoring |
| You changed a prompt, rule, or agent and claim it behaves better | 3. Behavioral A/B via eval harness | `benchmark-models` for cross-model comparison |
| You are about to write a command, path, or "matches X" claim into a doc or docstring | 4. Docs-vs-reality audit | `doc-accuracy` for full doc audits |
| A CI job failed on your PR | 5. Reproduce-on-main discriminator | `ai-agents-debugging-playbook` for symptom triage |
| You are writing a test for a generated artifact or contract | 6. Negative-control test design | `ai-agents-validation-and-qa` for the evidence bar |

## Process

Pick the recipe from the selector table. Each recipe states when to use it, the steps, a worked example with real repo paths, and what invalidates the result.

### Recipe 1: Runtime-Contract Probe

**When to use**: before writing any code that depends on how an external tool invokes yours: working directory, environment variables, stdin payload shape, signal/timeout behavior. Mandatory when the vendor docs are silent, because this repo's docs-say vs reality gap has produced two P0s (#2205, #2290).

**Steps**:

1. Write the hypothesis with exact strings: "Copilot CLI sets `COPILOT_PLUGIN_ROOT` for hook subprocesses", not "there is probably an env var".
2. Pin the tool version and record it (`copilot --version`, `claude --version`). A contract without a version is not a contract.
3. Build the minimal probe: a plugin/hook whose only job is to dump `os.environ`, `os.getcwd()`, and raw stdin to a file.
4. Run under a FOREIGN cwd and clean env. The #2205 probe ran with cwd=/tmp, not from the plugin directory. Running from the plugin dir masks exactly the bug you are hunting.
5. Include a negative control: the form you believe is broken must fail under the same harness (bare `./hooks/...` resolved NO; anchored path resolved YES in the #2205 probe).
6. Record the result in a decision memory: `.serena/memories/decision-<slug>.md` with Question, Conventional answer (docs, cited), First-principles position (measured), Evidence, Decision. Exemplar: `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md`.
7. Freeze the contract into a runtime-contract test (Recipe 6) so it survives you.

**Worked example (session 1873, the #2205 fix)**: Copilot CLI ran plugin hooks with cwd = the user's directory, so generated `./hooks/...` paths broke every customer install for 33 days. The first fix (session 1872, commit `0bfb90713`) diagnosed the cwd correctly but then ASSUMED the env var name `COPILOT_PLUGIN_ROOT` by analogy to `CLAUDE_PLUGIN_ROOT`, shipped a self-referential test, and left PowerShell without a fallback: three new defects in one fix (`.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md:49`). Session 1873 then did it right: installed a probe plugin under GitHub Copilot CLI 1.0.57, dumped the hook environment from cwd=/tmp, and found the docs were wrong by omission: `COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`, and bare `PLUGIN_ROOT` are all set to the install dir, none documented (`.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md`). Artifacts: `scripts/validation/validate_hook_anchoring.py`, `tests/build_scripts/test_generate_hooks_runtime_contract.py`, `.claude/rules/generated-artifacts.md`.

**Second worked example (#2290, the day after)**: the #2205 probe captured env vars and cwd but NOT stdin. Payload field names turned out to depend on event-key casing: camelCase event keys send `toolName`/`toolArgs` (with `toolArgs` a JSON string), PascalCase keys send `tool_name`/`tool_input`. Found only when the probe was re-instrumented to capture stdin under Copilot CLI 1.0.58 (`.agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md:47`). Lesson: a probe verifies only the dimensions it captures. Enumerate dimensions (cwd, env, stdin, exit/signal, timeout) explicitly.

**What invalidates the result**: unpinned tool version; probe run from the artifact's own directory; env inherited from your dev shell instead of controlled; no negative control; extrapolating to a dimension the probe did not capture; inferring a name "by analogy" to a sibling tool.

### Recipe 2: Guard and Threshold Calibration

**When to use**: before shipping ANY detector, guard, or numeric threshold (file counts, thread counts, rework counts, similarity percentages). This repo's rule: a detector that cannot fire on the last 5 real PRs is not calibrated (`.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md:153`).

**Steps**:

1. Take the last ~5 merged PRs as the sample. Real PRs, not synthetic fixtures.
2. Replay the detector against each and record the measured metric per PR.
3. Build the calibration table: threshold | PR | measured value | would it fire? Include the expected firing rate.
4. Run the guard on its own branch. A guard that never runs against the PR that ships it is unproven (#1989 M5 failure).
5. If the detector fires on zero of five, the threshold is wrong or the metric is wrong. Fix before commit, and put the table in the PR description.
6. After shipping, watch its tier via `guard-maturity` (EVENT= telemetry consumers).

**Worked example (#1989 M4)**: the rework-warning detector shipped with threshold 6. Replayed against its own PR: `--diff-filter=R` semantics were wrong (returned 0 files reworked) and the maximum file-edit count on the branch was 4. The detector could NEVER fire on ordinary work in this repo (`.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md:70`). Recalibrated recommendation: threshold 2 or 3, or a relative measure.

**Worked example (#1887 Phase-6 audit)**: the guard framework took 69 commits and 254 review conversations to land. The Phase 6 evidence audit then asked the calibration question retroactively: would the as-shipped guards have prevented the PR's own 35 fix commits? Answer: 0 of 35 (`.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md:199` and the total at line 230). Calibrate BEFORE the 69 commits, not after.

**What invalidates the result**: calibrating against synthetic or hand-picked PRs; changing the metric definition after building the table; sample PRs authored specifically to trip the guard; skipping the run-on-own-branch step.

### Recipe 3: Behavioral A/B via Eval Harness

**When to use**: any claim that a prompt, rule, or agent change improves behavior. "Reads better" is not evidence. ADR-057 (`.agents/architecture/ADR-057-prompt-behavioral-evaluation.md`) defines the acceptance gate; the harness lives in `scripts/eval/`.

**Steps**:

1. Write down predicted numbers BEFORE running: which scenarios flip, expected pass-rate delta. If you cannot predict, you do not yet have a hypothesis, you have a hope. The #1989 M1 mitigation was built on a premise nobody had checked; prediction-first would have exposed it (see `ai-agents-research-methodology`).
2. Dry-run first to validate inputs at zero API spend. This is the only no-spend path; there is no `--mock`:

   ```bash
   python3 scripts/eval/eval-prompt-change.py \
     --prompt templates/agents/analyst.shared.md \
     --scenarios tests/evals/analyst-scenarios.json \
     --base-ref main --dry-run
   ```

3. Run the real before/after comparison (same command without `--dry-run`; `ANTHROPIC_API_KEY` from env or `.env`). Security-critical prompts add `--security-critical` (5 runs, 100% pass required, per ADR-057).
4. For agent-vs-baseline comparisons:

   ```bash
   python3 scripts/eval/eval-agent-vs-baseline.py \
     --agent analyst --fixtures evals/analyst-spike/fixtures \
     --n-runs 3 --model claude-sonnet-4-6 --dry-run
   ```

5. Compare actuals to predictions. A surprise in EITHER direction is a finding: record it in a memory.

**Worked example**: scenario files for 10+ agents exist under `tests/evals/` (`analyst-scenarios.json`, `security-scenarios.json`, ...) with the JSON shape documented in the `eval-prompt-change.py` module docstring (id, input, `expected_verdict`, `verdict_options`, `expected_reason_contains`). Spike fixtures live under `evals/<name>-spike/`.

**What invalidates the result**: predictions written after seeing results; comparing runs across different models or scenario files; single-run verdicts on flaky scenarios (ADR-057 has a flakiness protocol; use it); editing scenarios and the prompt in the same experiment.

### Recipe 4: Docs-vs-Reality Audit

**When to use**: before writing any command, flag, path, or "matches/mirrors X" claim into documentation, a docstring, or a skill. Also when consuming docs: treat vendor and repo docs as hypotheses, not facts. FM-9 in `.agents/governance/FAILURE-MODES.md` (confident-incorrectness) is the failure mode this recipe prevents.

**Steps**:

1. For every command you write: run it (read-only or `--help`) or verify the file exists first. Never transcribe from another doc.
2. For every "matches", "mirrors", "aligned with", or "same as" claim: apply `.claude/rules/canonical-source-mirror.md`. Cite the canonical path verbatim, quote the contract character-for-character (the regex, the exit codes, the schema), and document any intentional divergence, all in the SAME commit that introduces the claim.
3. For vendor docs: remember they were wrong by omission twice here (#2205 env vars, #2290 payload casing). If the behavior is load-bearing, escalate to Recipe 1.
4. When you find stale docs, fix on contact or flag with path:line; do not silently work around them.

**Worked example (the dead pwsh commands)**: `CONTRIBUTING.md:155` said `build/Generate-Agents.ps1` PowerShell invocation until PR #2871 repointed it to `python3 build/generate_agents.py`; zero `.ps1` files exist in the repo outside `.venv` (ADR-042 Python migration; verify: `find . -name '*.ps1' -not -path './.venv/*'`). The real commands are `python3 build/generate_agents.py` and `python3 build/scripts/build_all.py`. Anyone who transcribed the old CONTRIBUTING.md shipped a dead runbook. This skill library was itself written under this recipe: every command above was executed before being written down.

**Worked example (the imagined contract)**: PR #1887's M4 guard was designed against an imagined contract instead of the canonical `scripts/validate_session_json.py` regex; aligning it took 7 fix commits (`.claude/rules/canonical-source-mirror.md`, citing the #1887 retro).

**What invalidates the result**: verifying existence but not behavior ("the file is there" does not mean "the flag works"); quoting a paraphrase instead of the verbatim contract; auditing the copy instead of the canonical source (ask which tree is source of truth; see the 2025-12-15 drift-direction story in `ai-agents-failure-archaeology`).

### Recipe 5: Reproduce-on-Main Discriminator

**When to use**: any CI failure on your PR, before you spend a minute debugging your diff.

**Steps**:

1. Check whether the identical failure exists on main: look at recent runs of the same workflow on main, or re-run the workflow against main. Use the `github` skill scripts (raw `gh` is blocked by the skill-first guard).
2. If it fails on main too: pre-existing bug. File an issue, link it in the PR, and stop debugging your diff.
3. If it fails only on the PR: the discriminating experiment is now cheap. Bisect your diff (revert half the changes locally, re-run the failing check via `python3 scripts/validation/pre_pr.py` or the specific validator).
4. Record misattribution near-misses in a memory; they compound.

**Worked example (PR #1361)**: a CI failure was nearly misattributed to PR code when the failure pre-existed on main. The rule was captured as a standing correction: "When a CI job fails on a PR, check if the failure exists on main before debugging PR code" (`.serena/memories/ci-infrastructure-observations.md:8`, 2026-03-04).

**What invalidates the result**: comparing against a stale main (fetch first); a workflow whose behavior depends on PR context (file-set-sensitive coverage pins, see `ai-agents-debugging-playbook`), where "passes on main" does not imply "your diff broke it".

### Recipe 6: Negative-Control Test Design

**When to use**: every runtime-contract test, and any test guarding a generated artifact (FM-11). A test suite with no case that fails when the contract breaks is decoration.

**Steps**:

1. Ban the self-referential form: a test that asserts the generator emits the string the test author copied FROM the generator passes when the generator is consistently wrong. This shipped two P0-adjacent defects here (#2205 first fix; #2290's `test_shim_reads_snake_case_wire_format` constructed its own payload, proving internal consistency, not runtime correctness).
2. Simulate the target runtime, do not restate the source: foreign cwd, contract env vars set explicitly, real subprocess execution.
3. Add at least one negative control: run the known-broken form through the same harness and assert it FAILS.
4. Add a load-bearing check: strip the contract precondition (unset the env var) and assert the passing case now fails, proving the anchor matters.
5. Cite the empirical contract (tool name + version + date) in the test module docstring, per `.claude/rules/generated-artifacts.md`.

**Worked example**: `tests/build_scripts/test_generate_hooks_runtime_contract.py` is the exemplar. It generates hooks, then resolves and executes each emitted command via a real bash subprocess from a `userland/` cwd that is not the plugin root, with `COPILOT_PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT` set explicitly. `test_negative_control_bare_relative_path_fails` proves the bare `./hooks/...` form fails the same harness ("so the guard has teeth", per its module docstring), and `test_anchor_is_load_bearing_when_no_plugin_root_var_set` proves the env var is doing the work. The docstring pins the contract to Copilot CLI 1.0.57, measured by probe. Run it: `uv run pytest tests/build_scripts/test_generate_hooks_runtime_contract.py -q` (6 passed in about 2s as of 2026-07-03). Contrast with `tests/build_scripts/test_generate_hooks_plugin_root.py`, which string-matches generator output and is retained only as a literal-output pin.

**What invalidates the result**: negative control that fails for an unrelated reason (assert on the SPECIFIC failure); mocking the subprocess boundary you are supposed to be exercising; a "contract" docstring with no tool version.

## Anti-Patterns

| Anti-pattern | Why it burned us | Evidence |
|--------------|------------------|----------|
| Assuming a name or behavior by analogy to a sibling tool | First #2205 fix invented `COPILOT_PLUGIN_ROOT` by analogy; happened to exist, was unverified for a full release | `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md:49` |
| Self-referential tests (test asserts the author's own output) | Passed while every customer install was wedged | same retro, `:83` |
| Shipping thresholds chosen by intuition | M4 threshold 6 vs repo max 4: could never fire | `2026-05-10-pr-1989-recursive-failure.md:70` |
| Building guards without asking "would this have caught real history?" | #1887 guards: 0/35 of their own fix commits prevented | `2026-05-05-pr-1887-iteration-paradox.md:199` |
| Trusting vendor docs for load-bearing behavior | Docs omitted the plugin-root env vars AND the payload casing rule | `decision-copilot-cli-hook-plugin-root-contract.md` |
| Probing one dimension, claiming the whole contract | #2205 probe captured env+cwd; stdin casing bug shipped anyway | `2026-06-02-issue-2290-copilot-hook-payload-format.md:71` |
| Predicting results after seeing them | Post-hoc "as expected" is unfalsifiable; see the eval gate | ADR-057 |
| Debugging PR code for a failure that exists on main | Time burned on misattributed pre-existing bugs | `.serena/memories/ci-infrastructure-observations.md:8` |

## Verification

Before claiming a probe, calibration, or eval result:

- [ ] Tool version pinned and recorded next to the result (probe without a version is folklore).
- [ ] Negative control ran through the same harness and failed for the specific expected reason.
- [ ] For thresholds: calibration table from the last ~5 real merged PRs is in the PR description, and the guard ran on its own branch.
- [ ] For evals: predicted numbers were written down before the run; `--dry-run` validated inputs first.
- [ ] Result recorded where it survives the session: decision memory (`.serena/memories/decision-<slug>.md`) or a runtime-contract test, not just chat.
- [ ] Every command in your write-up was executed, not transcribed.

## Provenance and Maintenance

Verified 2026-07-03 against the working tree. Sources and re-verification one-liners:

| Fact | Source | Re-verify |
|------|--------|-----------|
| #2205 probe story, first-fix defects | `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md:49-50` | `grep -n "session 1873" .agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md` |
| Plugin-root env contract, Copilot CLI 1.0.57 | `.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` | `cat .serena/memories/decision-copilot-cli-hook-plugin-root-contract.md` |
| Payload casing contract, CLI 1.0.58 | `.agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md:33,47,71` | `grep -n "toolArgs" .agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md` |
| M4 threshold 6 vs max 4; last-5-PRs rule | `.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md:70-73,153` | `grep -n "Threshold = 6" .agents/retrospective/2026-05-10-pr-1989-recursive-failure.md` |
| #1887 Phase-6 audit 0/35 | `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md:199,230` | `grep -n "Total preventable" .agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md` |
| Eval commands and flags | `scripts/eval/eval-prompt-change.py:1-60`, `scripts/eval/eval-agent-vs-baseline.py:447-475` | `python3 scripts/eval/eval-prompt-change.py --help` |
| Scenario/fixture locations | `tests/evals/`, `evals/` | `ls tests/evals/ evals/` |
| Verbatim-quote rule (7 fix commits) | `.claude/rules/canonical-source-mirror.md` | `sed -n '1,30p' .claude/rules/canonical-source-mirror.md` |
| CONTRIBUTING pwsh commands are dead | `CONTRIBUTING.md:155`; no `.ps1` outside `.venv` | `find . -name '*.ps1' -not -path './.venv/*'` |
| Reproduce-on-main rule (PR #1361) | `.serena/memories/ci-infrastructure-observations.md:8` | `sed -n '8p' .serena/memories/ci-infrastructure-observations.md` |
| Runtime-contract exemplar passes (6 tests) | `tests/build_scripts/test_generate_hooks_runtime_contract.py` | `uv run pytest tests/build_scripts/test_generate_hooks_runtime_contract.py -q` |
| FM-9, FM-11 catalog rows | `.agents/governance/FAILURE-MODES.md:14-27` | `sed -n '14,28p' .agents/governance/FAILURE-MODES.md` |

Volatile facts to re-check when touching this skill: Copilot CLI version pins (1.0.57/1.0.58 were the measured versions, not the current ones), the `tests/evals/` scenario inventory, and whether ADR-057's flakiness protocol has been amended.
