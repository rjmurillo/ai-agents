# Retrospective: PR #2205 - Customer Environment Wedge Incident

> **Status**: INCIDENT RETROSPECTIVE - PRODUCTION IMPACT
> **Date**: 2026-06-02
> **Severity**: P0 - Customer-facing, environment-wedging
> **Failure Modes**: FM #9 (Confident-Incorrectness Recurrence), FM #4 (False Completion Markers), FM #11 (proposed, see below)
> **Issues**: #2205 (fix), #2223 (follow-up debt)
> **PRs**: #2206 (session 1872 fix), session 1873 hardening commits
> **Supersedes**: Shallow auto-retros `2026-05-31-auto-retro.md`, `2026-06-01-auto-retro.md`, `2026-06-02-auto-retro.md`
> **No blame**: This retro critiques processes and artifacts, not individuals.

---

## Impact Table

| Area | Severity | Description |
|------|----------|-------------|
| Customer plugin usability | **Critical** | Every plugin hook failed at launch with "No such file or directory" across all 5 hook events |
| Blast radius | **Critical** | Every customer who installed the project-toolkit Copilot CLI plugin (versions 0.3.0 through 0.5.6) on any Copilot CLI version was affected |
| Failure mode | **Critical** | Hook failure happened at the launcher level, BEFORE any in-script fail-open handler could execute |
| Recovery path | **Severe** | Customers were forced to UNINSTALL the plugin to restore their Copilot CLI environment |
| Duration | **High** | 33 days: bare-path form introduced 2026-04-29, first fix landed 2026-06-01 |
| Fix quality (session 1872) | **High** | First fix introduced three new defects: unverified env var name, self-referential test, PowerShell asymmetry |
| Trust erosion | **High** | Environment-wedging failures destroy trust; forced uninstall is the hardest customer recovery path |
| Versions shipped broken | **Medium** | v0.3.0 through v0.5.6 inclusive (6 minor versions across 33 days) |

---

## Evidence Links

- First broken commit: `01e76615a` (2026-04-29) - "Inaugural M5 generation." Created `src/copilot-cli/hooks/hooks.json` with bare `./hooks/...` paths
- Broken form persisted through: `26d917ea0` (v0.4.1, 2026-05-25), `50f1eef06` (v0.4.1, 2026-05-29), `96aafb4fa` (v0.5.6, 2026-06-01)
- Session 1872 first fix (Copilot-authored agent): commit `0bfb90713`, PR #2206, 2026-06-01, bumped to v0.5.7
- Session 1873 hardening: commits `ff9425fdd`, `9ec75977e`, `64506e8fa`, `8475530fe`, `ffd6f084a`, `9ccb95a72`, merge `90c02db0f`
- Issue: https://github.com/rjmurillo/ai-agents/issues/2205
- Follow-up debt: https://github.com/rjmurillo/ai-agents/issues/2223
- Serena memory: `decision-copilot-cli-hook-plugin-root-contract`

---

## Verified Timeline

| Date | Event | Evidence |
|------|-------|----------|
| 2026-04-29 | `01e76615a`: Inaugural M5 generation. `src/copilot-cli/hooks/hooks.json` created with `python3 -u "./hooks/<event>/<script>.py"` and `"cwd": "."` - the bare path form that starts the incident. Plugin at v0.3.0. | `git show 01e76615a:src/copilot-cli/hooks/hooks.json` |
| 2026-04-30 | `c00a32e5f`: Merged REQ-003 build system. Plugin bumped to v0.4.0. Broken hooks.json ships to all customers. | Plugin version history |
| 2026-05-05 | `66ffd8433`: Pre-push validation framework ships. The `validate-plugin-manifests` CI gate validates JSON schema and `command` field presence, but never checks hook path anchoring or path resolvability under a foreign cwd. The gate that should have caught this did not. | `build/scripts/validate_plugin_manifests.py:_validate_hook_event_entries` |
| 2026-05-24 to 2026-05-29 | Multiple hook regenerations (`26d917ea0`, `50f1eef06`, etc.) add new hooks. Each regeneration faithfully reproduces the broken bare-path form. Plugin advances from v0.4.1 to v0.5.x. Tests exist for the generator but test only the JSON structure and matcher logic, never the path-resolution semantics under the Copilot CLI runtime contract. | `git log --all --oneline -- src/copilot-cli/hooks/hooks.json` |
| 2026-06-01 (session 1872, Copilot SWE agent) | `0bfb90713`: First fix. The Copilot-authored agent diagnosed correctly that `cwd` is the user's working directory. Changed `_build_copilot_entry` to use `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}` (bash) and `$env:COPILOT_PLUGIN_ROOT` (powershell). Three defects: (1) env var name `COPILOT_PLUGIN_ROOT` assumed by analogy to `CLAUDE_PLUGIN_ROOT`, not empirically verified; (2) regression test (`test_generate_hooks_plugin_root.py`) only string-matched the generator's own output - self-referential and thus cannot catch drift; (3) PowerShell lacked fallback - if `COPILOT_PLUGIN_ROOT` unset, path expanded to `/hooks/...` (absolute failure). Plugin bumped to v0.5.7. | `git show 0bfb90713`, `tests/build_scripts/test_generate_hooks_plugin_root.py` |
| 2026-06-01 (session 1873) | `ff9425fdd` + subsequent: Empirically verified env var contract against Copilot CLI 1.0.57 and Claude Code 2.1.159. Fixed PowerShell fallback asymmetry (`if ($env:COPILOT_PLUGIN_ROOT) {...} else {...}`). Replaced self-referential test with runtime-contract test. Added `scripts/validation/validate_hook_anchoring.py` wired into `pre_pr.py`. Added `tests/e2e/test_cli_hook_e2e.py` behind `RUN_CLI_E2E=1`. Plugin bumped to v0.5.12. | Commits `ff9425fdd` through `9ccb95a72` |

---

## Phase 0: Data Gathering

### 4-Step Debrief

**Step 1: Observe (Facts Only)**

- `src/copilot-cli/hooks/hooks.json` was generated by `build/scripts/generate_hooks.py:_build_copilot_entry` with `rel = f"./hooks/{target_event}/{script_name}"` - a cwd-relative path
- The entry also set `"cwd": "."` - the current working directory, which Copilot CLI resolves to the USER'S working directory
- Copilot CLI 1.0.57 (and all tested versions) sets `COPILOT_PLUGIN_ROOT` to the plugin install directory for hook subprocess invocations; it does NOT set `cwd` to the plugin root
- `python3 -u "./hooks/preToolUse/invoke_routing_gates__Bash.py"` executed from the user's home directory (`~/`) resolved to `~/hooks/preToolUse/...`, which does not exist
- Python exits with code 2 ("can't open file: No such file or directory") before any Python code runs
- The fail-open shim wraps the Python BODY in a try/except - but the shim is inside the Python file itself. A launch-level failure (Python can't open the file) is fatal before the shim executes
- 5 hook events affected: preToolUse, postToolUse, sessionStart, sessionEnd, userPromptSubmitted
- All customers on all platforms (Linux, macOS, Windows) were affected; Windows customers saw it as `C:\Users\<user>\hooks\...`
- Duration: 33 days (2026-04-29 to 2026-06-01)
- Versions shipped broken: v0.3.0 through v0.5.6

**Step 2: Respond (Reactions)**

- Pivots: The original generator function had NO documentation about the Copilot CLI runtime cwd behavior. The cwd contract was discovered only when a customer reported the failure via issue #2205.
- Retries: Session 1872 (first fix) introduced three new defects in the fix itself - canonical-source-mirror anti-pattern, PowerShell asymmetry, unverified env var name. Session 1873 was required to catch and correct these.
- Escalations: The fix required empirical verification against the actual CLI (not inferable from docs, which do not document the env vars). Session 1873 ran the CLI and did an env dump.
- Blocks: No nightly or release smoke test existed. The CI gate (`validate-plugin-manifests`) validated JSON schema and `command` field presence, but not path resolvability.

**Step 3: Analyze (Interpretations)**

- The generator was designed and tested purely for structural correctness (valid JSON, correct event names, matcher logic). Runtime behavior under Copilot CLI was never part of the test contract.
- The in-script fail-open shim was treated as an adequate protection layer. It is not: launcher-level failures happen before the shim can execute.
- The manifest validation gate was designed to prevent schema regressions (like PR #1795 - "Invalid input" on plugin install). It has no concept of "does this hook path resolve from the runtime cwd?"
- The self-referential test added in session 1872 is the canonical-source-mirror anti-pattern: it asserts that the generator produces the string the test author believes the generator should produce, which means the test passes when the generator is consistently wrong.

**Step 4: Apply (Actions)**

- Generator tests must include a runtime-contract layer: execute the generated command from a non-plugin cwd and verify the hook script resolves and runs
- The launcher-level failure mode (Python can't open the file) must be addressed at the command string level, not in the script body
- The manifest validation gate must grow a path-anchoring check
- A new failure mode (FM #11) is warranted for customer-facing generated artifacts shipped without runtime verification

### Outcome Classification

| Category | Events |
|----------|--------|
| Mad (Blocked/Failed) | Hook launched from user's cwd, script not found, Python exits code 2 before any code runs, fail-open shim never executes, customer environment wedged |
| Mad | First fix (session 1872) re-introduced confident-incorrectness: env var name assumed not verified, test self-referential, PowerShell fallback missing |
| Sad (Suboptimal) | 33-day detection window: no customer-facing runtime verification existed to catch the failure before customers did |
| Sad | The existing CI gate validated the wrong property (JSON schema valid, `command` present) rather than the right one (command resolves under runtime cwd) |
| Glad (Success) | Session 1873 empirically verified the env var contract, fixed PowerShell asymmetry, replaced self-referential test, added both a fast gate and an e2e test |
| Glad | The launcher path bug is now prevented at the command string level (anchoring) and caught by the runtime-contract gate before release; the in-script handler was never the right place to catch a launcher failure |

---

## Phase 1: Five Whys - TRUE Root Causes

### Five Whys: Why Did Customers' Environments Get Wedged?

**Problem**: Every Copilot CLI plugin hook failed at launch with "No such file or directory," requiring plugin uninstall to recover.

**Q1: Why did every hook fail at launch?**
The generated `hooks.json` invoked scripts via `python3 -u "./hooks/<event>/<script>.py"` with `"cwd": "."`. Copilot CLI runs hooks with `cwd` set to the user's working directory. The relative path `./hooks/...` resolves under the user's home/project directory, not the plugin install directory. The file does not exist there. Python exits code 2 before any Python executes.

**Q2: Why did the fail-open shim not protect customers?**
The fail-open shim is Python code INSIDE the hook script. A launcher-level failure (`python3: can't open file`) means the Python interpreter exits before reading a single byte of the script. The shim is unreachable. The architecture assumed failures would be in-script (caught by try/except), not at the Python launcher (caught by resolving the file path). This is an architectural blind spot: the fail-open contract was written at the wrong level of the stack.

**Q3: Why did the wrong cwd behavior ship?**
The generator function `_build_copilot_entry` was designed to produce structurally correct JSON (valid event names, command strings, timeout values). Its docstring at the time of the incident contained no reference to the Copilot CLI runtime cwd contract. No one reading the function would know that `cwd: "."` meant "user's directory, not plugin directory." The Copilot CLI documentation does not prominently document this; it was discoverable only by running the CLI or reading other plugins' source.

**Q4: Why did no test catch this before it shipped to customers?**
Three layers of tests existed and all missed it:
- Generator unit tests: tested that the generator produces structurally valid JSON; never tested that the command resolves from a non-plugin cwd
- Manifest validation CI gate (`validate-plugin-manifests`): validated `command` field is a string; never validated the command is a resolvable path
- Pre-push validation: caught drift between source hooks and generated hooks; never tested runtime path resolution

None of these tests exercised the actual Copilot CLI runtime contract: spawn `python3 -u "<command>"` from a working directory that is NOT the plugin install directory.

**Q5: Why did no gate exist to test the runtime contract?**
The generator and its tests were built to satisfy structural requirements (REQ-003 multi-tool artifact build system). The runtime environment contract for Copilot CLI (cwd, env vars, process setup) was undocumented internal behavior. Testing it requires either: (a) running the real CLI (requires auth, credits, CLI install - not feasible in PR CI), or (b) writing a contract simulation that emulates the CLI's invocation behavior without the CLI itself. Neither existed. No one made "can the hook actually be invoked from a realistic cwd?" a specification requirement or a test gate.

**Root Cause 1**: Customer-facing generated artifacts were shipped without any test that verified their behavior under the target runtime's actual invocation contract. Structural validation (schema, command field presence) was treated as sufficient. Runtime validation (does the command resolve from the runtime cwd?) was not defined as a requirement.

**Root Cause 2**: The protection against a broken hook was implemented at the wrong architectural layer. In-script try/except catches Python exceptions; it cannot catch Python launcher failures (file not found, file not executable). A hook command whose path is wrong wedges the environment with no recovery except uninstall. The fix is to prevent the bad command path at generation time and verify it before release (RC1 remediation), not to add a launcher-level fail-open that would silently disable the hook.

### Five Whys: Why Did the First Fix (Session 1872) Introduce New Defects?

**Problem**: Session 1872 fixed the path form but shipped three new defects.

**Q1: Why did session 1872 use an unverified env var name?**
The session 1872 work log states: "Real-world Copilot CLI plugins anchor hook commands with `${COPILOT_PLUGIN_ROOT}`; GitHub docs confirm Copilot exposes `${COPILOT_PLUGIN_DATA}` with `${CLAUDE_PLUGIN_DATA}` alias." The agent inferred `COPILOT_PLUGIN_ROOT` by analogy to `CLAUDE_PLUGIN_ROOT` and by reading other plugins' source. It did not execute the CLI and dump the environment to confirm the variable was actually set. This is FM #9 (confident-incorrectness): a name inferred from pattern-matching without empirical verification.

**Q2: Why was the regression test self-referential?**
`test_generator_anchors_script_path_to_plugin_root` calls `generate_hooks.generate_hooks(cfg, tmp_path)` and then asserts `"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/hooks/" in entry["bash"]`. This asserts that the generator produces the string the author expected the generator to produce. It does not simulate what happens when the Copilot CLI executes the command from a foreign cwd. It would pass whether or not the hook actually resolves at runtime. This is the canonical-source-mirror anti-pattern: the test mirrors the generator's own output, making it a tautology.

**Q3: Why did PowerShell lack the fallback?**
The bash form used parameter-expansion fallback (`${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}`). PowerShell has no equivalent syntax. Session 1872 used `$env:COPILOT_PLUGIN_ROOT` with no fallback. If `COPILOT_PLUGIN_ROOT` is unset on Windows (hypothetical), the path expands to `/hooks/...` which is an absolute path failure. The asymmetry was not caught because the regression test did not test the PowerShell command form for path-resolution correctness.

**Q4: Why was the fix Copilot-only (identical risk on Claude plugin ignored)?**
Issue #2205 was filed against the Copilot plugin. Session 1872 diagnosed and fixed the Copilot plugin only. The Claude plugin (`/.claude/hooks/hooks.json`) uses a different mechanism and already anchors to `${CLAUDE_PLUGIN_ROOT}`. But the risk analysis was scoped to the reporter's context (Copilot CLI), not to the whole class of customer-facing plugin hook artifacts. The fix was incident-scoped, not class-scoped.

**Root Cause 3**: Session 1872 operated under FM #9 (confident-incorrectness): it diagnosed the symptom correctly, inferred a fix from analogy (not verification), wrote a self-referential test that confirmed the fix looked right without testing it behaved right, and shipped. The pattern is: partial signal, premature conclusion, confident delivery.

---

## Phase 2: Failure Mode Classification

### Primary: FM #9 - Confident-Incorrectness Recurrence

Both the original generator and the session 1872 fix exhibit this pattern:
- **Original generator**: `cwd: "."` is structurally correct (the JSON field is valid). The author was confident in the structural form without knowing (or testing) the runtime semantics.
- **Session 1872 fix**: env var name inferred from analogy, test self-referential, PowerShell form unvalidated. Confident delivery of a fix with unverified critical properties.

### Secondary: FM #4 - False Completion Markers

Session 1872 created and committed artifacts (hooks.json, regression test) that signaled the fix was complete. The test passed. The plugin was bumped. The completion markers (passing test, bumped version) were present but the underlying failure (unverified env var, no runtime simulation, PowerShell asymmetry) remained. Observers would see "test passed, version bumped" and conclude the fix was complete.

### Proposed New: FM #11 - Customer-Facing Generated Artifact Shipped Without Runtime Verification

**Description**: A generated artifact that is shipped to customers and executed in a specific runtime environment (OS, CLI, working directory) is validated only for structural correctness (schema, syntax, field presence). It is never executed against a simulation of the target runtime before shipping. The structural test passes. The runtime behavior is never exercised. The artifact wedges customer environments.

**Distinguishing characteristics**:
1. The artifact is machine-generated from a template/generator
2. The artifact is customer-facing (shipped as part of a release or install)
3. Testing validates the generator's output structure, not the artifact's behavior under the target runtime contract
4. The target runtime has behavioral properties (cwd, env vars, user context, process setup) that are not discoverable from the artifact's schema alone
5. When the behavioral property is wrong, the failure is unrecoverable without uninstall (environment-wedging)

**Trigger**: A generator is extended or a new artifact type is introduced. Tests are written against the generator's output. The runtime contract (how the target system invokes the artifact) is not tested.

**Detection signals**:
- A generated file that will be executed by an external CLI or runtime has no test that executes a simulation of the runtime invocation from a realistic cwd/env
- The only tests for the generated artifact call the generator and assert on the output string
- No gate in pre-PR or CI simulates the target runtime contract

**Enforcement pattern**:
- Generated artifacts MUST have a runtime-contract test that simulates the target runtime's invocation semantics (cwd, env vars, PATH)
- The runtime contract must be documented in the generator's docstring with a citation to where it was verified (CLI version, env dump, empirical test)
- A mandatory gate in pre-PR validation must check that every command in a plugin hook file can be resolved from a non-plugin cwd under the expected env vars

**Evidence**: Issue #2205, commits `01e76615a` through `ff9425fdd`, this retrospective.

**Related**: FM #9 (confident-incorrectness), FM #4 (false completion markers)

---

## Phase 3: What Went Wrong - Fishbone Analysis

### Problem: Customer environments wedged by plugin hooks that fail at launch

**Category: Prompt / Specification**
- REQ-003 (multi-tool artifact build system) specified structural requirements for `hooks.json` (valid JSON, correct event shape, script-per-matcher generation). It did not specify runtime path-resolution requirements.
- No acceptance criterion stated: "hook commands MUST be executable from a working directory that is not the plugin install directory."
- The generator docstring for `_build_copilot_entry` contained zero information about the Copilot CLI runtime cwd contract at the time of incident.

**Category: Tools / Generation**
- `generate_hooks.py:_build_copilot_entry` used `rel = f"./hooks/{target_event}/{script_name}"` (cwd-relative) with no knowledge of the runtime cwd contract
- `"cwd": "."` was set, making the runtime cwd explicit - but what "." means in the Copilot runtime context was not documented or tested
- The fail-open shim was placed at the wrong architectural layer (in-script, not at the command string)

**Category: Context / Knowledge Gap**
- The Copilot CLI documentation does not prominently document that hooks run with cwd set to the user's working directory, not the plugin directory
- The env vars `COPILOT_PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` are not in the public documentation; they were inferred from reading other plugins' source code
- No memory entry, ADR, or steering document captured the Copilot CLI runtime hook invocation contract

**Category: Testing**
- Generator tests: tested structural output only; no test executed a hook command from a non-plugin cwd
- CI gate: validated JSON schema validity; no check for path anchoring
- Pre-push validation: checked hook drift (source vs generated match); did not check runtime resolution
- No e2e test existed that installed the plugin and ran a hook from a realistic cwd

**Category: Release Process**
- Plugin versions were bumped and `hooks.json` was regenerated as a mechanical build step
- No release gate simulated the customer installation and invocation flow
- No smoke test ran as part of the release pipeline to verify that hooks resolve before the version was published

**Category: Architecture**
- The fail-open protection was designed for in-script failures (Python exceptions), not launcher failures (Python can't open the file)
- There is no graceful degradation at the hook command level: if `python3 -u "bad-path.py"` returns non-zero, the hook fails, and depending on the hook event and the CLI, this can wedge the environment

---

## Phase 4: Systemic Remediation Plan

This section maps each root cause to a durable artifact change. Items requiring ADR review or governance consensus are flagged.

### RC1 Remediation: Runtime Contract Test Requirement for Generated Artifacts

**Root cause addressed**: RC1 (no runtime verification for generated artifacts)

**Target artifact**: `.claude/rules/generated-artifacts.md` (NEW FILE)

**Change intent**: New rule binding any generator that produces a customer-facing artifact to include a runtime-contract test. The test must:
1. Simulate the target runtime's invocation semantics (cwd set to non-artifact directory, expected env vars set)
2. Execute a representative generated command (not just assert on its string form)
3. Verify the command resolves and runs successfully
4. Include a negative control (bare-path or wrong-cwd form must fail)

The rule must also require the generator function's docstring to cite the runtime contract verbatim (which CLI version, which env vars, empirically verified).

**ADR review**: Not required (new rule under the existing rule governance, not an architecture decision). Recommend human review of the rule before merge.

**Example text for the rule**:
```
A generator that produces a file executed by an external runtime (CLI, IDE, agent
harness) MUST include a runtime-contract test that:
1. Documents the runtime contract in the generator function docstring (env vars,
   cwd, process setup), citing the CLI version and how it was verified.
2. Executes a representative generated command from a cwd that is NOT the
   artifact directory.
3. Asserts the command resolves and runs successfully.
4. Includes a negative control (the broken form must fail).
Self-referential tests (assert that the generator produces the string the test
expects) do not satisfy this requirement.
```

---

**Target artifact**: `AGENTS.md` (addition to Boundaries section)

**Change intent**: Add two lines to the Always section:
- "Generated artifacts shipped to customers MUST have a runtime-contract test; structural/schema tests are necessary but not sufficient."
- "Hook commands in plugin artifacts MUST be verified resolvable from a non-plugin cwd before release."

**ADR review**: Not required (editorial addition to Boundaries).

---

### RC2 Remediation: Prevent the Bad Launcher, Fail Loud If One Escapes

**Root cause addressed**: RC2 (protection implemented at the wrong architectural layer)

**Target artifact**: `build/scripts/generate_hooks.py:_build_copilot_entry`

**Change intent**: Fix the failure at its source. The launcher command shape is
fixed at generation time (anchor every path to the plugin root, RC1 remediation)
and verified before release by the runtime-contract gate and the real-CLI smoke.
A path bug is caught before it ships, not papered over at runtime.

**Rejected alternative: launcher-level fail-open.** An earlier proposal added a
launcher wrapper that tests file existence and exits 0 with a warning when the
script is missing. This is rejected. Exiting 0 on a broken launcher converts a
loud, learnable failure into a silently disabled hook: the customer's hook
protection is gone and no one finds out. That is the silent-failure anti-pattern.
The correct posture for a hook is fail closed and loud: prevent the bad launcher
from shipping, and if a novel launcher failure still escapes, surface it so it is
detected and fixed rather than masked. Tracked and closed on this basis as issue
#2230 (addressed-by-prevention).

**ADR review**: The runtime-contract verification decision is recorded in
ADR-063. No launcher fail-open principle is adopted.

---

### RC3 Remediation: Pre-PR Gate for Hook Path Anchoring

**Root cause addressed**: RC1 (no gate caught the bare path form before customers)

**Target artifact**: `scripts/validation/validate_hook_anchoring.py` (EXISTS, added in session 1873)

**Status**: Gate already added and wired into `pre_pr.py`. This item is complete. Document it here as a remediation rather than a new action.

**Verification**: Session 1873 added `validate_hook_anchoring.py` that checks both `src/copilot-cli/hooks/hooks.json` and `.claude/hooks/hooks.json` for anchored paths. It is wired into `pre_pr.py`. A bare-path form will now fail the pre-PR gate before merge.

---

### RC4 Remediation: Canonical-Source-Mirror Rule Enforcement on Generator Tests

**Root cause addressed**: RC3 (session 1872 self-referential test)

**Target artifact**: `.claude/rules/canonical-source-mirror.md` (EXISTS)

**Change intent**: Add an explicit example of the self-referential test anti-pattern to the rule. Current rule says "quote the contract verbatim." Add: "A test that calls the generator and asserts on the generator's own output is a self-referential test and does NOT satisfy this rule. The test must simulate the runtime contract independently."

**ADR review**: Not required (editorial addition to existing rule).

---

### RC5 Remediation: Failure Mode Document Update

**Root cause addressed**: Need institutional memory of this failure class

**Target artifact**: `.agents/governance/FAILURE-MODES.md`

**Change intent**: Add FM #11 (Customer-Facing Generated Artifact Shipped Without Runtime Verification) as defined in Phase 2 above. The entry follows the same structure as FM #9 and FM #10.

**ADR review**: Not required (adding to existing document, does not change existing rules). Recommend human approval per governance.md MUST #1 (governance changes require human approval).

---

### RC6 Remediation: Release Smoke Test Proposal

**Root cause addressed**: RC1 (no release-time verification)

**Target artifact**: `.github/workflows/` (new workflow) + `tests/e2e/test_cli_hook_e2e.py` (EXISTS)

**Status**: `tests/e2e/test_cli_hook_e2e.py` was added in session 1873 and is gated by `RUN_CLI_E2E=1`. The pre-push hook forces it on hook-path changes.

**Remaining gap**: No nightly or release pipeline runs the e2e test. Proposal:

Create a new workflow `.github/workflows/plugin-release-smoke.yml` that:
1. Triggers on: `push` to `main` when `src/copilot-cli/hooks/hooks.json` changes, and on `workflow_dispatch`
2. Requires secrets (CLI auth token) - this workflow is NOT in the PR CI path; it is a post-merge gate
3. Uses a matrix to test on Ubuntu, Windows (pwsh), and macOS runners
4. Runs `RUN_CLI_E2E=1 uv run pytest tests/e2e/test_cli_hook_e2e.py -v`
5. On failure, alerts via a GitHub issue or Slack notification

**No-auth contract simulation alternative**: For PR CI (no secrets), add a "contract simulation" test that does NOT call the real CLI but instead:
- Sets `COPILOT_PLUGIN_ROOT=/tmp/fake-plugin-root` and `cwd=/tmp/fake-user-home`
- Runs the generated `bash` command in a subprocess
- Verifies the Python hook script executes (writes a marker file) and exits 0

This is the pattern used by `tests/build_scripts/test_generate_hooks_runtime_contract.py` added in session 1873.

**ADR review**: The nightly workflow requires a decision about secrets management in CI. This is an architecture/governance decision. FLAG for human review before implementing.

---

### RC7 Remediation: Document the Copilot CLI Runtime Contract

**Root cause addressed**: RC1 (undocumented runtime contract was the root of the original failure)

**Target artifact**: `.agents/architecture/` - consider an ADR documenting the empirically verified Copilot CLI and Claude Code hook runtime contracts

**Change intent**: Create `ADR-063-plugin-hook-runtime-contract.md` documenting:
- Copilot CLI 1.0.57: hook subprocess has `cwd` = user's working directory; env includes `COPILOT_PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` pointing to the install dir
- Claude Code 2.1.159: hook subprocess has `cwd` = user's working directory; env includes `CLAUDE_PLUGIN_ROOT` pointing to the install dir
- Both CLIs set both variables (Copilot sets both; Claude sets at least `CLAUDE_PLUGIN_ROOT`)
- Verified empirically via probe plugin + env dump (session 1873)
- References: `decision-copilot-cli-hook-plugin-root-contract` Serena memory, `tests/e2e/test_cli_hook_e2e.py`

**ADR review**: YES - BLOCKING. Any `ADR-*.md` creation fires the adr-review skill. Do not create this file without completing the adr-review flow.

---

### RC8 Remediation: New Serena Memories

**Root cause addressed**: Institutional knowledge preservation

Create or confirm the following memories (session 1873 may have already created some):

1. `feedback-generated-artifact-runtime-verification` (NEW): "Generated artifacts shipped to customers (hooks.json, etc.) MUST have a runtime-contract test. Structural/schema tests are not sufficient. The runtime contract (cwd, env vars, process setup) must be documented in the generator docstring citing CLI version and empirical verification. Evidence: issue #2205, 33-day customer-wedge incident."

2. (No separate fail-open memory.) The launcher-layer lesson is captured as a binding principle in `.claude/rules/generated-artifacts.md` and ADR-063: prevent the bad launcher at generation time, fail closed and loud if one escapes, never add a launcher fail-open that silently disables the hook. The earlier `feedback-hook-fail-open-architectural-layer` memory is removed as superseded by this prevention-first position (issue #2230, closed addressed-by-prevention).

3. `feedback-self-referential-test-anti-pattern` (UPDATE existing feedback-canonical-source-first): "A test that calls a generator and asserts on the generator's own output is self-referential - it confirms the generator is internally consistent but does NOT verify behavior against the target runtime. This is the canonical-source-mirror anti-pattern at the test level. Evidence: session 1872 `test_generate_hooks_plugin_root.py`, issue #2205."

---

## Phase 5: Ordered Remediation Action List

The table below is ordered by: (a) ability to prevent recurrence immediately, (b) dependency order. Items requiring ADR review or human governance are flagged.

| # | Action | Target Artifact | Intent | Gate Required | Status |
|---|--------|----------------|--------|--------------|--------|
| 1 | Wire `validate_hook_anchoring.py` into `pre_pr.py` | `scripts/validation/pre_pr.py` | Enforce anchored paths before merge | None | DONE (session 1873) |
| 2 | Add runtime-contract test to `tests/build_scripts/` | `tests/build_scripts/test_generate_hooks_runtime_contract.py` | Replace self-referential test with real simulation | None | DONE (session 1873) |
| 3 | Fix PowerShell fallback asymmetry | `build/scripts/generate_hooks.py:_build_copilot_entry` | Both shells use same fallback order | None | DONE (session 1873) |
| 4 | Add FM #11 to FAILURE-MODES.md | `.agents/governance/FAILURE-MODES.md` | Institutional memory of this failure class | Human approval (governance.md MUST #1) | PENDING |
| 5 | Create `generated-artifacts.md` rule | `.claude/rules/generated-artifacts.md` | Binding rule: generated artifacts need runtime-contract tests | Human review recommended | PENDING |
| 6 | Add two lines to AGENTS.md Boundaries | `AGENTS.md` | "Generated artifacts MUST have runtime-contract test; Hook commands MUST be verified from non-plugin cwd before release" | None | PENDING |
| 7 | Reject launcher-level fail-open; prevent at generation, fail loud if escaped | `build/scripts/generate_hooks.py:_build_copilot_entry` | No silent exit-0 wrapper; anchoring + runtime-contract gate prevent the bug; a novel launcher failure fails loud | Closed addressed-by-prevention (#2230) | REJECTED |
| 8 | Add self-referential test anti-pattern example to canonical-source-mirror rule | `.claude/rules/canonical-source-mirror.md` | Prevent reoccurrence of the session 1872 self-referential test | None | PENDING |
| 9 | Create ADR-063 for plugin hook runtime contract | `.agents/architecture/ADR-063-plugin-hook-runtime-contract.md` | Document the empirically verified Copilot CLI + Claude Code hook invocation contract | ADR review BLOCKING - do not create without adr-review | PENDING |
| 10 | Create or update Serena memories (3 memories) | `.serena/memories/` | Institutional knowledge persistence | None | PENDING |
| 11 | Propose nightly plugin-release-smoke workflow | `.github/workflows/plugin-release-smoke.yml` | Real-CLI e2e on post-merge, secrets-gated | Human review + secrets governance | PENDING |

---

## Phase 6: Close - +/Delta

### + Keep

- The session 1873 three-layer defense (fast gate + runtime-contract test + e2e) is the right pattern for generated artifacts
- Empirical verification against the actual CLI before shipping is the right standard
- The in-script handler covers in-script errors; a launcher path bug is prevented at generation and verified before release, not masked by a launcher fail-open

### Delta Change

- Generator functions that produce customer-facing artifacts need a "runtime contract" section in their docstring from day one, not after a customer incident
- Release process needs a gate that distinguishes "structurally valid" from "behaviorally correct under the target runtime"
- Session 1872 shows that a Copilot-authored agent can produce a confidently-wrong fix faster than a human would catch it; the self-referential test is the evidence. The canonical-source-mirror rule must be extended to cover tests, not just production code.

### ROTI Assessment

- **Score**: 4 (Exceptional)
- **Benefits**: FM #11 proposed, three RC items are complete, five more are precisely specified for immediate execution, the incident duration (33 days) is documented as a forcing function for the rule changes
- **Time invested**: ~4 hours of evidence gathering and analysis
- **Verdict**: Extract this pattern into guidance for future generated-artifact PRs

### Helped, Hindered, Hypothesis

**Helped**: Git history with descriptive commit messages made the 33-day timeline reconstructable in minutes. The session 1873 commit messages were precise enough to verify every claim.

**Hindered**: The Copilot CLI documentation gap (env vars not documented publicly) means this incident was only discoverable by running the CLI. No amount of reading the docs would have revealed the risk.

**Hypothesis**: If the `generate_hooks.py` generator had a mandatory "runtime-contract" checklist block in its function template (analogous to the `--fail-open` pattern in the shim template), engineers would have been prompted to document and test the runtime contract at generation time rather than after a customer report.

---

## Notes on Superseded Auto-Retros

The following auto-retros were generated by the `invoke_auto_retrospective.py` Stop hook and were unfilled at the time of this retrospective:

- `2026-05-31-auto-retro.md`: Session adding the Serena re-assertion UserPromptSubmit hook. Not related to this incident. Content placeholder only.
- `2026-06-01-auto-retro.md`: Session 1872 first fix. The session-level auto-retro captures the work log but not the systemic analysis. THIS retrospective supersedes it for incident purposes.
- `2026-06-02-auto-retro.md`: Session 1873 hardening. The session-level auto-retro captures the work log but not the systemic analysis. THIS retrospective supersedes it for incident purposes.

Those files remain in `.agents/retrospective/` as session artifacts. For the authoritative post-incident analysis, reference this document.
