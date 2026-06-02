# Retrospective: Copilot CLI preToolUse Hook Payload Mismatch

## Session Info
- **Date**: 2026-06-02
- **Agents**: Claude Opus 4.6 (orchestrator, analyst, implementer)
- **Task Type**: Bug
- **Outcome**: Partial (payload fix shipped; hook timeout issue separate, unresolved)

## Phase 0: Data Gathering

### 4-Step Debrief

#### Step 1: Observe (Facts Only)
- Tool calls: Probe plugin installed, stdin captured for both PascalCase and camelCase event names; generate_hooks.py edited; 49 hooks regenerated; 120 tests run (all pass); PR #2293 opened
- Outputs: Fixed hooks.json (PascalCase event keys), dual-format shim in all 49 generated hook scripts, 3 new test cases, empirical payload format proof via probe plugin
- Errors: First fix attempt ("use `gh copilot-cli plugin install`") was hallucinated CLI invocation; probe plugin captured correct payload on second attempt; hook timeout (exit 143) discovered after payload fix
- Duration: ~3 hours

#### Step 2: Respond (Reactions)
- Pivots: Initial assumed fix (payload format only) proved insufficient; second pivot to investigate exit code 143; third pivot confirmed timeout is a separate issue
- Retries: Copilot CLI test ran 3 times (bash tool worked, Read tool failed even after fix)
- Escalations: User explicitly rejected results twice ("both of those command lines are hallucinated"; "It's still broken")
- Blocks: LSP guard blocked multiple Read/Edit calls; ctx_execute sandbox ran in temp dir without repo context

#### Step 3: Analyze (Interpretations)
- Patterns: All three failures in this session (payload mismatch, hallucinated CLI commands, timeout) trace to unverified assumptions about the Copilot CLI runtime contract
- Anomalies: Exit code 143 (SIGTERM) is structurally different from payload crash (exit 2); same symptom ("hook errored") masked a different root cause
- Correlations: ADR-063 verification gap and the hallucinated CLI commands both originate from "analogy to similar systems" reasoning instead of empirical measurement

#### Step 4: Apply (Actions)
- Skills to update: generate_hooks observations (copilot-hooks-observations.md), ADR-063
- Process changes: Add stdin payload format to runtime contract probe; instrument probe to capture stdin in addition to env vars
- Context to preserve: Copilot CLI 1.0.58 sends snake_case when PascalCase event key; toolArgs is a JSON string in camelCase mode

### Execution Trace

| Time | Agent | Action | Outcome | Energy |
|------|-------|--------|---------|--------|
| T+0 | analyst | Read issue #2290 via ctx_execute | Got error message and related issue | High |
| T+1 | analyst | Read .claude/hooks/hooks.json and copilot-cli hooks.json | Got hook structure; found _shim_should_fire | High |
| T+2 | analyst | Read ADR-063, decision memory, generate_hooks.py | Identified eventRemap config | High |
| T+3 | analyst | Fetched Copilot CLI hooks reference | Discovered PascalCase vs camelCase payload contract | High |
| T+4 | implementer | Edited copilot-cli.yaml, generate_hooks.py, 4 test files | PascalCase eventRemap, dual-format shim | High |
| T+5 | implementer | Regenerated hooks, ran 120 tests | All pass | High |
| T+6 | implementer | Hallucinated Copilot CLI install commands | User rejected | Blocked |
| T+7 | implementer | Discovered correct `copilot plugin install ./src/copilot-cli` | Plugin installed | Medium |
| T+8 | analyst | Installed probe plugin, ran `echo hello` | Captured payload: tool_name snake_case confirmed | High |
| T+9 | analyst | Ran `read README.md`, saw "still broken" | Exit code 143, not payload error | Medium |
| T+10 | analyst | Checked process log | Identified SIGTERM timeout as separate issue | Medium |
| T+11 | implementer | Committed, pushed, opened PR #2293 | Done | High |

### Outcome Classification

| Category | Item |
|----------|------|
| Glad | Probe methodology proved format empirically; 120 tests all pass; PR shipped |
| Glad | Dual-format shim is defensive insurance against future config changes |
| Sad | ADR-063 never verified stdin payload format; gap shipped with original fix |
| Sad | Exit code 143 is a separate P0-class issue, still unresolved |
| Mad | Hallucinated CLI install command wasted user trust and time |

## Phase 1: Insights Generated

### Five Whys: Primary Failure

**Failure**: Every Copilot CLI tool call blocked with "hook errored"

1. Why? Hook exited 2. Copilot CLI is fail-closed on non-zero hook exit.
2. Why exit 2? `_shim_should_fire` raised `ValueError`: `payload.get("tool_name")` returned None.
3. Why was `tool_name` missing? Copilot CLI sent `toolName` (camelCase), not `tool_name`. Payload field names depend on event key casing.
4. Why camelCase event key? `eventRemap` mapped `PreToolUse -> preToolUse`. The generator used camelCase because that was the original Copilot-side convention, copied from the first time the mapping was written.
5. Why wasn't it caught? ADR-063 verified env vars and cwd empirically but did NOT capture stdin. The test `test_shim_reads_snake_case_wire_format` proved the shim reads `tool_name` correctly but constructed its own payload, proving internal consistency, not runtime correctness. Self-referential test anti-pattern.

### Five Whys: Hallucinated CLI Commands

**Failure**: Proposed `gh copilot-cli plugin install` and `copilot plugin install --from` without verifying these commands exist.

1. Why? Guessed CLI syntax by analogy to other package managers without running `copilot --help`.
2. Why? Did not apply "Search Before Building" / "Boil the Lake" discipline to CLI command discovery.
3. Why? Treated well-known tool names (`gh`, `copilot`) as sufficient signal to construct valid subcommands.
4. Why? No forcing function to verify CLIs before proposing commands; it only fails when the user tests.
5. Prevention: Always verify CLI commands via `--help` or `help` before proposing. Never guess subcommands.

### Learning Matrix

| Quadrant | Item |
|----------|------|
| Known/Worked | Dual-format shim pattern; probe plugin methodology |
| Known/Failed | ADR-063 verification scope was too narrow |
| Unknown/Discovered | Copilot CLI payload format is casing-dependent; toolArgs is a JSON string in camelCase mode |
| Unknown/Remaining | Hook timeout root cause on Windows; optimal hook count for perf |

## Phase 2: Diagnosis

### Successes (Tag: helpful)

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Probe plugin for empirical contract verification | Captured exact stdin payloads for both casing modes from live CLI | 10 | 92% |
| Dual-format shim (snake + camelCase fallback) | Zero cost; survives future eventRemap config changes | 8 | 88% |
| JSON string parsing for camelCase toolArgs | toolArgs is a raw string in camelCase mode; parsing enables glob matching | 9 | 90% |

### Failures (Tag: harmful)

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Assumed PascalCase/camelCase payload format without verification | Contract mismatch | ADR-063 scope covered env vars, not stdin | Add stdin payload capture to runtime contract probe | 95% |
| Hallucinated Copilot CLI plugin install commands | Confidence error | Guessed subcommands by analogy, no `--help` verification | Always run `<cmd> --help` before proposing a CLI command | 90% |
| Stopped investigation after payload fix | Incomplete diagnosis | Exit code 143 looks like same symptom as exit 2 | Treat same-symptom/different-exit-code as a distinct failure | 82% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Test_generate_hooks_runtime_contract always fails on Windows | Verified pre-existing by running on original code; excluded from CI scope | Windows bash env var pass-through is a separate test infrastructure gap |
| Unrelated `docs/retros/INDEX.md` change staged alongside fix | Caught before commit | Check `git status` before staging; exclude noise files |

## Phase 3: Decisions

### Action Classification

| Item | Classification | Rationale |
|------|---------------|-----------|
| Keep dual-format shim | Keep | Zero cost, high resilience |
| Keep PascalCase eventRemap | Keep | Matches Copilot CLI VS Code-compatible format spec |
| ADR-063: add stdin payload section | Add | Gap in runtime contract documentation |
| Probe: capture stdin payload in test | Add | Closes self-referential test anti-pattern for payload format |
| Hook timeout P0 issue | Add | Exit code 143 is a separate blocking issue |
| CLI command verification rule | Add | Prevents hallucinated subcommands |

### SMART Validation

| Learning | Specific | Measurable | Achievable | Relevant | Time-bound |
|----------|----------|------------|------------|----------|------------|
| "Use PascalCase event names in eventRemap" | Yes: specific config key | Yes: verifiable in hooks.json | Yes: 1-line change | Yes: P0 fix | Yes: now |
| "Verify stdin payload with probe before writing shim" | Yes: probe = stdin dump | Yes: payload fields visible | Yes: 15-min probe | Yes: prevents recurrence | Yes: before next hook change |
| "Never guess CLI subcommands; run --help first" | Yes: --help check | Yes: observable behavior | Yes: 10 seconds | Yes: eliminates hallucination | Yes: every CLI use |

### Action Sequence

1. **Amend ADR-063** to add stdin payload format verification to the contract (depends on: PR #2293 merged)
2. **Add probe-based stdin test** to `tests/build_scripts/test_generate_hooks_runtime_contract.py` (depends on: ADR-063 amendment)
3. **File P0 issue** for hook timeout (exit 143) on Windows (depends on: PR #2293 merged)
4. **Update FAILURE-MODES.md** with FM-CONTRACT: producer/consumer wire format mismatch pattern (standalone)

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Copilot CLI payload field names depend on hook event key casing.
- **Atomicity Score**: 95%
- **Evidence**: Probe plugin captured `toolName` (camelCase event) and `tool_name` (PascalCase event) from Copilot CLI 1.0.58 live session, 2026-06-02
- **Skill Operation**: ADD
- **Target Skill ID**: copilot-hooks-payload-casing

### Learning 2
- **Statement**: Runtime contract tests must capture stdin payload, not only env vars.
- **Atomicity Score**: 90%
- **Evidence**: ADR-063 probe captured env vars and cwd but missed payload field names; mismatch shipped undetected
- **Skill Operation**: ADD
- **Target Skill ID**: runtime-contract-probe-scope

### Learning 3
- **Statement**: camelCase Copilot events send toolArgs as a JSON string, not a parsed dict.
- **Atomicity Score**: 92%
- **Evidence**: Probe dump: `"toolArgs": "{\"command\":\"echo hello\",\"description\":\"Echo hello\"}"` vs PascalCase `"tool_input": {"command": "echo hello"}`
- **Skill Operation**: ADD
- **Target Skill ID**: copilot-hooks-toolargs-format

### Learning 4
- **Statement**: Exit code 143 from a hook is SIGTERM (timeout), not a payload crash.
- **Atomicity Score**: 88%
- **Evidence**: Process log `HookExitCodeError: Hook command failed with code 143`; code 143 = 128+SIGTERM; shim uses exit 2 for payload errors
- **Skill Operation**: ADD
- **Target Skill ID**: hook-exit-code-taxonomy

### Learning 5
- **Statement**: Never propose a CLI subcommand without running `--help` first.
- **Atomicity Score**: 85%
- **Evidence**: Proposed `gh copilot-cli plugin install` and `copilot plugin install --from`; both invalid; user rejected as hallucinated
- **Skill Operation**: ADD
- **Target Skill ID**: cli-command-verification

### Learning 6
- **Statement**: Self-referential shim tests prove internal consistency, not runtime correctness.
- **Atomicity Score**: 91%
- **Evidence**: `test_shim_reads_snake_case_wire_format` passed for months; never caught payload mismatch because it constructed its own `tool_name` payload instead of using a real Copilot CLI capture
- **Skill Operation**: ADD
- **Target Skill ID**: runtime-contract-test-self-referential

## Skillbook Updates

### ADD

```json
{
  "skill_id": "copilot-hooks-payload-casing",
  "statement": "Copilot CLI hook payload field names are determined by event key casing: camelCase sends toolName/toolArgs, PascalCase sends tool_name/tool_input.",
  "context": "When writing or generating Copilot CLI hook configurations and shims.",
  "evidence": "Probe plugin dump from Copilot CLI 1.0.58, 2026-06-02. PR #2293.",
  "atomicity": 95
}
```

```json
{
  "skill_id": "runtime-contract-probe-scope",
  "statement": "Hook runtime contract probes must capture stdin payload field names, not only env vars and cwd.",
  "context": "When verifying or amending runtime contract documentation (ADR-063 and successors).",
  "evidence": "ADR-063 gap: session 1873 proved env vars but not stdin; payload mismatch shipped as a result. PR #2293.",
  "atomicity": 90
}
```

```json
{
  "skill_id": "copilot-hooks-toolargs-format",
  "statement": "In camelCase Copilot hook payloads, toolArgs is a raw JSON string; parse with json.loads before processing.",
  "context": "When the matcher shim extracts tool arguments for glob matching with camelCase event names.",
  "evidence": "Probe dump 2026-06-02: toolArgs = '{\"command\":\"echo hello\"}' (string, not dict). PR #2293.",
  "atomicity": 92
}
```

```json
{
  "skill_id": "hook-exit-code-taxonomy",
  "statement": "Hook exit code 143 = SIGTERM timeout; exit 2 = config/payload error; exit 1 = logic error. Same symptom, different root cause.",
  "context": "When diagnosing Copilot CLI hook failures from process logs.",
  "evidence": "Process log 2026-06-02: code 143 after payload fix confirmed second issue was timeout, not payload.",
  "atomicity": 88
}
```

```json
{
  "skill_id": "cli-command-verification",
  "statement": "Verify any CLI subcommand exists via --help before proposing it. Never guess from analogy.",
  "context": "Any time a shell command involving a subcommand (plugin install, pr create, etc.) is proposed to a user.",
  "evidence": "Hallucinated 'gh copilot-cli plugin install' and 'copilot plugin install --from' in session 2026-06-02. User rejected both.",
  "atomicity": 85
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| generate_hooks-observations | Not found | New sidecar at .serena/memories/copilot-hooks-observations.md | ADR-063 gap, payload format, exit codes all belong here |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| copilot-hooks-payload-casing | p0-blocker | All tools denied until fixed | Critical |
| runtime-contract-probe-scope | adr-063-gap | Probe scope defined in ADR-063 | High |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| (none) | | |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| copilot-hooks-payload-casing | decision-copilot-cli-hook-plugin-root-contract | Same domain; that memory covers env vars; this covers payload format | ADD (distinct) |
| runtime-contract-probe-scope | generated-artifacts rule | Generated-artifacts covers path resolution; this covers payload wire format | ADD (distinct) |
| cli-command-verification | search-before-building rule | Search-before-building is design-level; this is CLI-specific | ADD (distinct) |

---

## Closing

### +/Delta

| + (Keep) | Delta (Change) |
|----------|---------------|
| Probe plugin methodology for empirical contract verification | ADR-063 must explicitly include stdin payload capture |
| Dual-format defensive shim pattern | Hook timeout P0 needs its own issue and fix |
| Running `--help` before CLI proposals | Self-referential contract tests need runtime capture partner |

### ROTI (Return on Time Invested)

**Score**: 4/5. The payload mismatch is fully fixed and proven. The timeout issue was identified but not resolved. Time investment: ~3 hours. Value: P0 Copilot CLI usability restored.

### Helped / Hindered / Hypothesis

- **Helped**: Fetching the live Copilot CLI hooks reference via ctx_fetch_and_index revealed the exact payload casing rule. Probe plugin gave irrefutable evidence.
- **Hindered**: LSP guard blocked multiple Read calls mid-investigation. ctx_execute sandbox ran in a temp dir without repo files. Both added friction.
- **Hypothesis**: Hook execution performance (timeout) is the next blocking issue for Copilot CLI users. 30+ sequential Python process startups on Windows will exceed timeout budgets for any non-trivial tool use.

## Failure Mode Classification

**FM-CONTRACT**: Producer/consumer wire format mismatch. A generator produced a contract (eventRemap) that was never tested against the real runtime's payload. The canonical source for this pattern: this retrospective and PR #2293.

Reference: `.agents/governance/FAILURE-MODES.md`

## Remediation Tracker

| Action | Owner | Status | Issue |
|--------|-------|--------|-------|
| PascalCase event names + dual-format shim | session | Done | PR #2293 |
| Empirical payload evidence in decision memory | session | Done | .serena/memories/copilot-hooks-observations.md |
| ADR-063 amendment: add stdin payload section | follow-up | TODO | TBD |
| Probe-based stdin payload test | follow-up | TODO | TBD |
| Hook timeout P0 issue | follow-up | TODO | TBD |
| FAILURE-MODES.md: add FM-CONTRACT pattern | follow-up | TODO | TBD |
