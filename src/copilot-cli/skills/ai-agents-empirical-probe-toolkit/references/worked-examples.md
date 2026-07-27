# Empirical Probe Toolkit: Worked Examples

The war stories behind each recipe in `../SKILL.md`. Each incident is why the recipe exists. Consult when you want the concrete repo history; the operative When-to-use, Steps, and What-invalidates stay inline in SKILL.md.

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths (.agents/, .claude/, scripts/, build/) because its audience is repo contributors, not plugin consumers (issue #2050) -->

## Recipe 1: Runtime-Contract Probe

**Worked example (session 1873, the #2205 fix)**: Copilot CLI ran plugin hooks with cwd = the user's directory, so generated `./hooks/...` paths broke every customer install for 33 days. The first fix (session 1872, commit `0bfb90713`) diagnosed the cwd correctly but then ASSUMED the env var name `COPILOT_PLUGIN_ROOT` by analogy to `CLAUDE_PLUGIN_ROOT`, shipped a self-referential test, and left PowerShell without a fallback: three new defects in one fix (`.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md:49`). Session 1873 then did it right: installed a probe plugin under GitHub Copilot CLI 1.0.57, dumped the hook environment from cwd=/tmp, and found the docs were wrong by omission: `COPILOT_PLUGIN_ROOT`, `CLAUDE_PLUGIN_ROOT`, and bare `PLUGIN_ROOT` are all set to the install dir, none documented (`.serena/memories/decision-copilot-cli-hook-plugin-root-contract.md`). Artifacts: `scripts/validation/validate_hook_anchoring.py`, `tests/build_scripts/test_generate_hooks_runtime_contract.py`, `.claude/rules/generated-artifacts.md`.

**Second worked example (#2290, the day after)**: the #2205 probe captured env vars and cwd but NOT stdin. Payload field names turned out to depend on event-key casing: camelCase event keys send `toolName`/`toolArgs` (with `toolArgs` a JSON string), PascalCase keys send `tool_name`/`tool_input`. Found only when the probe was re-instrumented to capture stdin under Copilot CLI 1.0.58 (`.agents/retrospective/2026-06-02-issue-2290-copilot-hook-payload-format.md:47`). Lesson: a probe verifies only the dimensions it captures. Enumerate dimensions (cwd, env, stdin, exit/signal, timeout) explicitly.

## Recipe 2: Guard and Threshold Calibration

**Worked example (#1989 M4)**: the rework-warning detector shipped with threshold 6. Replayed against its own PR: `--diff-filter=R` semantics were wrong (returned 0 files reworked) and the maximum file-edit count on the branch was 4. The detector could NEVER fire on ordinary work in this repo (`.agents/retrospective/2026-05-10-pr-1989-recursive-failure.md:70`). Recalibrated recommendation: threshold 2 or 3, or a relative measure.

**Worked example (#1887 Phase-6 audit)**: the guard framework took 69 commits and 254 review conversations to land. The Phase 6 evidence audit then asked the calibration question retroactively: would the as-shipped guards have prevented the PR's own 35 fix commits? Answer: 0 of 35 (`.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md:199` and the total at line 230). Calibrate BEFORE the 69 commits, not after.

## Recipe 3: Behavioral A/B via Eval Harness

**Worked example**: scenario files for 10+ agents exist under `tests/evals/` (`analyst-scenarios.json`, `security-scenarios.json`, ...) with the JSON shape documented in the `eval-prompt-change.py` module docstring (id, input, `expected_verdict`, `verdict_options`, `expected_reason_contains`). Spike fixtures live under `evals/<name>-spike/`.

## Recipe 4: Docs-vs-Reality Audit

**Worked example (the dead pwsh commands)**: `CONTRIBUTING.md:155` said `build/Generate-Agents.ps1` PowerShell invocation until PR #2871 repointed it to `python3 build/generate_agents.py`; zero `.ps1` files exist in the repo outside `.venv` (ADR-042 Python migration; verify: `find . -name '*.ps1' -not -path './.venv/*'`). The real commands are `python3 build/generate_agents.py` and `python3 build/scripts/build_all.py`. Anyone who transcribed the old CONTRIBUTING.md shipped a dead runbook. This skill library was itself written under this recipe: every command above was executed before being written down.

**Worked example (the imagined contract)**: PR #1887's M4 guard was designed against an imagined contract instead of the canonical `scripts/validate_session_json.py` regex; aligning it took 7 fix commits (`.claude/rules/canonical-source-mirror.md`, citing the #1887 retro).

## Recipe 5: Reproduce-on-Main Discriminator

**Worked example (PR #1361)**: a CI failure was nearly misattributed to PR code when the failure pre-existed on main. The rule was captured as a standing correction: "When a CI job fails on a PR, check if the failure exists on main before debugging PR code" (`.serena/memories/ci-infrastructure-observations.md:8`, 2026-03-04).

## Recipe 6: Negative-Control Test Design

**Worked example**: `tests/build_scripts/test_generate_hooks_runtime_contract.py` is the exemplar. It generates hooks, then resolves and executes each emitted command via a real bash subprocess from a `userland/` cwd that is not the plugin root, with `COPILOT_PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT` set explicitly. `test_negative_control_bare_relative_path_fails` proves the bare `./hooks/...` form fails the same harness ("so the guard has teeth", per its module docstring), and `test_anchor_is_load_bearing_when_no_plugin_root_var_set` proves the env var is doing the work. The docstring pins the contract to Copilot CLI 1.0.57, measured by probe. Run it: `uv run pytest tests/build_scripts/test_generate_hooks_runtime_contract.py -q` (6 passed in about 2s as of 2026-07-03). Contrast with `tests/build_scripts/test_generate_hooks_plugin_root.py`, which string-matches generator output and is retained only as a literal-output pin.
