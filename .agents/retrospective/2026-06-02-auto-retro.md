# Retrospective: 2026-06-02

Session 1873. Verify and harden Copilot CLI hook plugin-root anchoring (PR #2206,
issue #2205), extend the fix to the Claude plugin, and add an enforceable
anti-regression gate plus real-CLI end-to-end tests.

## Session Context

### Work Items

- Reviewed PR #2206 (anchor Copilot CLI hook commands to the plugin root).
- Verified the plugin-root environment-variable contract empirically against
  Copilot CLI 1.0.57 and Claude Code 2.1.159 (probe plugin, env dump, executed
  the exact generated command from a non-plugin cwd).
- Fixed the PowerShell fallback asymmetry in `_build_copilot_entry` (bash had a
  `COPILOT_PLUGIN_ROOT` to `CLAUDE_PLUGIN_ROOT` fallback; PowerShell did not).
- Replaced a self-referential string-match test with a runtime-contract test.
- Added `scripts/validation/validate_hook_anchoring.py` (covers Claude and
  Copilot) and wired it into `pre_pr.py`.
- Added `tests/e2e/test_cli_hook_e2e.py` and forced it in `.githooks/pre-push`
  on hook-path changes.

### Evidence

- Commits `ff9425fdd`, `9ec75977e`, `64506e8fa`, `8475530fe`, `ffd6f084a`,
  `9ccb95a72`, merge `90c02db0f`.
- PR #2206. Issue #2205. Follow-up issue #2223 (module-size and complexity debt).
- Serena memory `decision-copilot-cli-hook-plugin-root-contract`.

## Impact

| Area | Severity | Note |
|------|----------|------|
| Copilot CLI hooks (Windows + Linux) | High | Bare `./hooks/...` failed; anchoring plus the gate close the regression |
| Claude plugin hooks | Medium | The same trap was latent; the gate now covers `.claude/hooks/hooks.json` |
| Regression safety | High | A runtime-contract test and a forced e2e replace a string-match that proved nothing |

## What Went Well

- Empirical verification beat the documentation. The GitHub hooks reference does
  not list `COPILOT_PLUGIN_ROOT`, and one source states `CLAUDE_PLUGIN_ROOT` is
  unavailable to Copilot-format plugins. A probe hook proved both variables are
  set to the install dir. Running the tool settled a contract that reading the
  docs could not.
- The runtime-contract test executes each generated command under the measured
  contract (cwd is a non-plugin dir, the variable points at the install dir),
  with a bare-path negative control, so a regression actually trips it.
- The fix generalized to both plugins because the gate derives the Copilot
  command shape from the generator instead of hardcoding it.

## What Could Improve

- The first pass over-indexed on a PowerShell fallback before confirming the
  platform runs the PowerShell field at all. The user redirected. Confirm the
  execution path before hardening one branch of it.
- Scope grew across several prompts (Claude parity, the enforceable gate, the
  forced-local e2e). A wider first reading of "what does done mean for both CLIs,
  and how is it enforced" would have surfaced these up front.
- The change reached 20 files. It is cohesive, but a smaller core-fix PR with a
  follow-up for the gate and e2e would review more easily.

## Key Learnings

- For a runtime environment-variable contract, the only reliable check is to run
  the tool and read its environment. The docs were wrong by omission here.
  Recorded in Serena memory `decision-copilot-cli-hook-plugin-root-contract`.
- A test that asserts the literal string a generator emits proves nothing about
  runtime behavior and cannot catch a wrong variable name. Prefer a test that
  exercises the real contract, paired with a negative control.
- A static gate plus a manual proof is not a standing net. Forcing the e2e in the
  pre-push hook (skip loudly when a CLI is absent, skip rather than fail on CLI
  latency) makes the correct check the default.

## Failure Patterns

- **FM #9 Confident-incorrectness recurrence** (`.agents/governance/FAILURE-MODES.md`):
  the prior fix asserted an undocumented env-var contract from analogy and shipped
  a self-referential string-match test. Remediation: empirical verification, a
  runtime-contract test, the enforceable `validate_hook_anchoring` gate, and the
  forced e2e. This mirrors the M4 / PR #1887 canonical-source-mirror episode.
- **FM #4 False completion markers** (secondary): the string-match test and the
  placeholder retrospectives both read as "done" without substance. Remediation:
  replace the test with one that executes the contract; write real retrospectives
  (this file and `2026-06-01-auto-retro.md`).
