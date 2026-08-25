---
id: ADR-035
status: accepted
date: 2025-12-30
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-035: Exit Code Standardization

<!-- # taste-lint: ignore file-size (long-form ADR; the 500-line code-cohesion limit does not apply to prose ADRs, cf. ADR-013 at 597, ADR-022 at 604, ADR-037 at 593, all accepted over the limit) -->

**Status**: Accepted
**Date**: 2025-12-30
**Deciders**: User, Architect Agent, ADR Review Protocol
**Context**: Issue #536 - Standardize exit codes across PowerShell scripts

---

## Context and Problem Statement

PowerShell scripts across the repository use inconsistent exit codes. Analysis of 50+ scripts reveals:

1. **Inconsistent semantics**: `exit 1` means "validation failed" in one script, "merged" in another
2. **Undocumented codes**: Scripts use exit codes 0-7 without documentation
3. **Cross-language contract risk**: Bash callers interpret exit codes; inconsistency causes bugs
4. **Test confusion**: Test assertions check exit codes but meanings vary by script

**Key Question**: What exit code standard should all PowerShell scripts follow?

---

## Decision Drivers

1. **Cross-Platform Contract**: PowerShell scripts called from bash/GitHub Actions must have predictable exit semantics
2. **Testability**: Pester tests need clear expectations for exit code assertions
3. **Debugging**: Operators need to interpret exit codes without reading source
4. **Consistency**: ADR-005 standardized language; this standardizes exit semantics
5. **Industry Practice**: Exit code conventions from POSIX, sysexits.h, PowerShell best practices

---

## Considered Options

### Option 1: POSIX-Style Standard (CHOSEN)

Standard exit code ranges with documented semantics:

| Code | Meaning | Examples |
|------|---------|----------|
| 0 | Success | Operation completed, idempotent skip |
| 1 | General error / Validation failure | Logic error, assertion failed |
| 2 | Usage/configuration error | Missing required param, invalid argument, not in git repo |
| 3 | External service error | GitHub API failure, network error |
| 4 | Authentication/authorization error | Token expired, permission denied |
| 5-99 | Reserved for future standard use | |
| 100+ | Script-specific errors | Must be documented in script header |

**Pros**:

- Aligns with POSIX/sysexits conventions (familiar to operators)
- Clear separation: 1=logic, 2=config, 3=external, 4=auth
- Reserved range prevents collision
- Extensible via 100+ range

**Cons**:

- Requires updating existing scripts (migration effort)
- More granular than some scripts need

### Option 2: Binary Success/Failure

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Any failure |

**Pros**:

- Simple
- Already common in some scripts

**Cons**:

- No diagnostic value (caller cannot distinguish failure types)
- Debugging requires log inspection
- Cannot implement conditional retry logic

### Option 3: HTTP-Style Codes

| Code | Meaning |
|------|---------|
| 0 | Success (200-299 equivalent) |
| 4 | Client error (400-499 equivalent) |
| 5 | Server error (500-599 equivalent) |

**Pros**:

- Familiar to web developers

**Cons**:

- Awkward mapping (exit codes are not HTTP codes)
- Loses granularity (many error types map to 4 or 5)
- Not conventional for CLI tools

### Option 4: No Standard (Status Quo)

**Pros**:

- No migration effort

**Cons**:

- Continued inconsistency
- Cross-language bugs persist
- Test reliability issues continue
- Debugging remains difficult

---

## Decision Outcome

**Chosen option: Option 1 - POSIX-Style Standard**

### Exit Code Reference

| Code | Category | Semantic Meaning | When to Use |
|------|----------|------------------|-------------|
| 0 | Success | Operation completed successfully | All success paths, including idempotent no-ops |
| 1 | Logic Error | General failure, validation failed | Business logic failures, assertion violations |
| 2 | Config Error | Usage, configuration, or environment error | Missing params, invalid args, missing dependencies |
| 3 | External Error | External service or API error | GitHub API failures, network errors, timeouts |
| 4 | Auth Error | Authentication or authorization failure | Token expired, permission denied, rate limited |
| 5-99 | Reserved | Future standard use | Do not use until standardized |
| 100+ | Script-Specific | Custom error codes | Document in script header comment |

### When to Use Script-Specific Codes (100+)

**Use standard codes (0-4) when:**

- The error maps cleanly to an existing category
- CI/CD pipelines need to implement conditional logic (retry on 3, fail fast on 2)
- The script is called by multiple consumers who need consistent semantics
- The failure mode is common across many scripts (validation, auth, API errors)

**Use script-specific codes (100+) when:**

- The script has domain-specific states that consumers need to distinguish
- Multiple distinct success or failure modes exist that callers act on differently
- The standard categories (0-4) lose important diagnostic information
- The script serves as a specialized tool where callers need granular control flow

**Examples of script-specific codes:**

```powershell
# Test-PRMerged.ps1 - Callers need to distinguish merge states
# EXIT CODES:
# 0   - Success: PR is open (can proceed with merge)
# 100 - Info: PR already merged (idempotent success)
# 101 - Info: PR was closed without merge (requires intervention)
# 1   - Error: Validation failed
# 3   - Error: GitHub API error

# Get-PRChecks.ps1 - Callers need to know check status
# EXIT CODES:
# 0   - Success: All checks passed
# 100 - Pending: Checks still running (retry later)
# 101 - Failed: One or more checks failed
# 3   - Error: GitHub API error
```

**Decision Framework:**

| Question | If Yes | If No |
|----------|--------|-------|
| Does the caller need to distinguish multiple non-error states? | Use 100+ | Use 0 |
| Does the caller retry based on the exit code? | Use standard (0-4) | Consider 100+ |
| Is this a reusable utility called by many scripts? | Prefer standard (0-4) | 100+ acceptable |
| Would 0 vs 1 lose important caller context? | Use 100+ | Use standard |

### Documentation Requirement

All scripts MUST include exit code documentation in the script header:

```powershell
<#
.SYNOPSIS
    Brief description

.NOTES
    EXIT CODES:
    0  - Success: Operation completed
    1  - Error: Validation failed (specify conditions)
    2  - Error: Missing required parameter
    3  - Error: GitHub API returned error
    4  - Error: Authentication failed

    When called from bash/CI:
    - Exit 0 = success ($? equals 0)
    - Exit non-zero = failure ($? non-zero)
#>
```

### Deviation from Original Proposal (Issue #536)

Issue #536 proposed a simpler 0-5 exit code range. This ADR adopts a POSIX-aligned approach instead:

| Issue #536 Proposal | This ADR | Rationale for Change |
|---------------------|----------|----------------------|
| 1 (invalid params) | 2 (config error) | Align with POSIX convention (exit 2 = usage error) |
| 2 (auth failure) | 4 (auth error) | Reserve 2 for config; align auth with sysexits EX_NOUSER (67→4) |
| 3 (API error) | 3 (external error) | No change (aligned) |
| 4 (not found) | 3 (external error) | Consolidate into external service category |
| 5 (permission denied) | 4 (auth error) | Consolidate into authentication/authorization category |
| N/A | 1 (logic error) | Add general error category for validation failures |
| N/A | 5-99 (reserved) | Future-proof the standard |
| N/A | 100+ (script-specific) | Allow documented custom codes |

**Rationale for POSIX alignment**: Cross-language consistency with bash/Python/Ruby conventions reduces operator cognitive load and enables intelligent retry logic in CI workflows. The reserved range (5-99) future-proofs the standard without risking collision with script-specific codes.

### Rationale

1. **Industry Alignment**: POSIX exit codes and sysexits.h provide proven conventions
2. **Diagnostic Value**: Operators can triage without logs (2=fix config, 3=check GitHub, 4=renew token)
3. **Retry Logic**: CI can implement intelligent retry (retry on 3, fail fast on 2)
4. **Test Clarity**: Pester tests assert specific codes, improving test documentation

### Enforcement

1. **This ADR**: Canonical reference
2. **Code Review**: Verify exit code documentation and compliance
3. **Pester Tests**: Include exit code assertions with semantic checks
4. **PSScriptAnalyzer**: Future custom rule for undocumented exit statements

---

## Migration Plan

Implementation will be tracked via GitHub epic with 3 sub-tasks (see PR comment for issue creation request).

### Phase 1: Document Current State (Low Risk)

**GitHub Issue**: TBD (epic sub-task 1)

1. Add exit code documentation to existing scripts without changing behavior
2. Update scripts that already comply to reference this ADR

**Scope**: All scripts in `.claude/skills/`, `.github/scripts/`, `scripts/`

### Phase 2: Fix Inconsistencies (Medium Risk)

**GitHub Issue**: TBD (epic sub-task 2)

Priority fixes for semantic confusion:

| Script | Current | Issue | Fix |
|--------|---------|-------|-----|
| `Test-PRMerged.ps1` | exit 1 = merged | Success case exits with error code | Change to exit 0 with output property |
| Scripts using exit 1 for API errors | exit 1 | Should be exit 3 | Update to exit 3 |

**Testing**: Pester tests MUST be updated before changing exit codes to verify no regressions.

### Phase 3: Update Callers (Medium Risk)

**GitHub Issue**: TBD (epic sub-task 3)

Update bash/workflow callers to handle new exit codes appropriately.

**Scope**: GitHub Actions workflows in `.github/workflows/` that invoke PowerShell scripts.

---

## Current State Analysis

### Exit Code Usage Before Standardization

| Exit Code | Count | Current Usage |
|-----------|-------|---------------|
| 0 | 30+ | Success (consistent) |
| 1 | 15+ | Mixed: validation, API error, generic failure |
| 2 | 12+ | Config/dependency error (mostly consistent) |
| 3 | 8+ | API error (consistent in newer scripts) |
| 7 | 1 | Timeout (Get-PRChecks.ps1) |

### Notable Inconsistencies

1. **`Test-PRMerged.ps1`**: Uses `exit 1` for "PR is merged" which is a successful state determination
2. **`collect-metrics.ps1`**: Uses `exit 1` for both path-not-found and not-a-git-repo (should be exit 2)
3. **Timeout handling**: Only one script uses exit 7; others use exit 1 or exit 3

---

## Consequences

### Positive

1. **Predictable Cross-Language Behavior**: Bash callers can reliably interpret exit codes
2. **Improved Debugging**: Exit code alone provides diagnostic category
3. **Better Test Coverage**: Pester tests can assert semantic correctness
4. **Consistent Documentation**: All scripts document their exit codes
5. **Retry Intelligence**: CI can implement category-based retry logic

### Negative

1. **Migration Effort**: Existing scripts need updates (30+ files)
   - **Mitigation**: Phase over multiple PRs; prioritize high-impact scripts
2. **Breaking Changes**: Callers expecting specific codes may break
   - **Mitigation**: Phase 3 updates callers; document in PR

### Neutral

1. **Learning Curve**: Developers must learn standard
   - This ADR serves as reference

---

## Implementation Notes

### Helper Function Pattern

Consider adding a shared helper for consistent error exit:

```powershell
function Write-ErrorAndExit {
    param(
        [string]$Message,
        [ValidateRange(1,255)][int]$ExitCode = 1
    )
    Write-Error $Message
    exit $ExitCode
}
```

### Testing Pattern

```powershell
Describe "Exit Codes" {
    It "Should exit 0 on success" {
        $result = & $script -ValidParams
        $LASTEXITCODE | Should -Be 0
    }

    It "Should exit 2 on missing required parameter" {
        $result = & $script 2>&1
        $LASTEXITCODE | Should -Be 2
    }

    It "Should exit 3 on API error" {
        Mock gh { throw "API error" }
        $result = & $script -ValidParams 2>&1
        $LASTEXITCODE | Should -Be 3
    }
}
```

---

## Claude Code Hook Exit Codes

Claude Code hooks have predefined exit code semantics defined by Claude Code itself. Hook scripts under `.claude/hooks/**/*.py` (Python per ADR-042) are exempt from this ADR's POSIX exit-code table because Claude interprets these codes specially. They are NOT exempt from the blocking discipline below. A hook that blocks the wrong thing is worse than a script that returns the wrong number: it can wedge the agent loop (issue #3247).

### Hook Exit Code Reference

Exit code semantics vary by hook event. Exit 2 blocks for some events and not others.

**Blocking events** (exit 2 blocks the action): PreToolUse, PermissionRequest, UserPromptSubmit, Stop, SubagentStop.

**Non-blocking events** (exit 2 is an error, not a block): PostToolUse, PostToolUseFailure, Notification, SubagentStart, SessionStart, SessionEnd, PreCompact.

| Exit Code | Blocking events | Non-blocking events |
|-----------|-----------------|---------------------|
| 0 | Allow action, stdout injected as context | Success, stdout injected as context |
| 1 | Hook error; Claude lets the tool proceed | Hook error, stderr shown in verbose mode |
| 2 | Block action immediately | Error only (no block), stderr shown, stdout context dropped |

This table is Claude's mechanical interpretation of the exit code. Two things layer on top:

- Policy (ADR-071 binding; ADR-066 accepted) requires a hook to surface a loud stderr note on its own error rather than a silent success. On a blocking event a gate that must fail closed does so with exit 2 and stderr, not exit 1: exit 1 lets the tool proceed on Claude.
- Copilot diverges. Its preToolUse denies on any non-zero exit (see Cross-Harness). Exit 1 as a proceed-anyway lane is a Claude-only mechanic, not a portable one.

### PreToolUse deny: nested shape at exit 0, or exit 2

A PreToolUse hook has two ways to deny. They are mutually exclusive; pick one per hook.

**Exit 0 with a nested JSON decision (Claude only):**

```python
import json, sys
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "Blocked: no session log for this branch. Run session-init first.",
    }
}))
sys.exit(0)  # the nested permissionDecision carries the block at exit 0
```

Claude honors ONLY the nested form. Top-level `{"decision": "deny"}` is invalid for PreToolUse and is silently ignored: the tool proceeds. Top-level `decision` is not a PreToolUse shape. This is not theoretical: issue #2521 shipped a security gate that emitted top-level `{"decision":"deny"}` at exit 0, the harness ignored it, and the gate never blocked until it was rewritten to exit 2 (commit 3e5d8495).

**Exit 2 (portable, both harnesses):**

Exit 2 blocks on Claude and forces deny on Copilot. Put the reason on stderr. Claude processes hook stdout JSON only at exit 0; at exit 2 any JSON the hook prints is ignored, so the two paths do not combine. Do not emit a nested `permissionDecision` and also exit 2 expecting richer UX: at exit 2 the JSON is inert and renders nothing. Some existing gates print a top-level `{"decision":"block"}` next to their exit 2; that JSON is vestigial, and the block comes from exit 2 alone.

Because the exit-0 JSON shape is harness-specific (see Cross-Harness) and neither harness accepts the other's, exit 2 is the tested, portable block. Use exit 2 for any gate that must block on both harnesses. Use the nested exit-0 form only for a Claude-only gate that wants the richer reason surfaced to the model.

### Hook Blocking Discipline (STRICT)

Binding on every hook under `.claude/hooks/`. These rules override any convenience default.

**Do not wedge the loop.** A hook MUST NOT block, by exit 2 or by a JSON deny, a core agentic-loop tool for an advisory concern (token efficiency, a preferred alternative, style). One false positive on a core tool halts the whole loop. Issue #3247 illustrates the class: a preToolUse deny landed on the Task tool and stalled the agent (that deny came from a harness-global default, not a repo hook, but the failure mode is the one this rule guards against). The LSP runtime-enforcement family (Read, Grep, Glob, Task guards) was retired for the same availability cost (#3232, ADR-062). The rule is strongest for the read-only navigation tools, where a block leaves the agent unable to even look; for mutation tools a narrow, certain, hard-to-reverse action may still block per the bar below.

**Core tools and "broad Bash."** Core agentic-loop tools are Read, Grep, Glob, Task, Agent, Write, Edit, and broad Bash. "Broad Bash" means matching the Bash tool as a whole. Matching a specific dangerous command inside Bash (a push to `main`, a commit on a protected branch) is narrow, and a narrow match on a certain, hard-to-reverse action may block. A blocking Bash gate MUST detect that specific command in its own body and allow everything else.

**Block bar.** A hook may block only when ALL hold:

1. The event is a blocking event (exit 2 blocks it).
2. The gated action is not a core navigation tool, OR the specific action is both certain and irreversible-or-high-cost-to-reverse.
3. The prevented harm is concrete and named: a secret commit, a force-push to `main`, a push to a protected branch, a destructive irreversible operation, or another action that is hard to undo once it lands.

If you cannot name the harm and show it is hard to reverse, the hook does not qualify to block. Make it advisory: exit 0 with a stderr or stdout note.

| Is the harm hard to reverse AND detection certain? | Path |
|----------------------------------------------------|------|
| Yes | May block. Use `exit 2` with the reason on stderr (portable). |
| No | Advisory only. Exit 0 with a stderr/stdout note. Never a deny. |

**Fail-mode by hook class (ADR-071 binding; ADR-066 D4).** [ADR-071](./ADR-071-plugin-hook-runtime-contract-verification.md) (Accepted) binds the rule: hooks fail closed and loud, never silent success. [ADR-066](./ADR-066-hook-fail-open-reconciliation.md) (Accepted) D4 classifies hooks into three failure modes; apply the one that fits what the hook does, not a blanket runtime default.

- **Class 1, invariant / policy gate** (denies a specific dangerous action). On its OWN internal error it MUST fail closed and loud: exit 2 with actionable stderr naming the hook, the unproven invariant, and the recovery path. This matches Copilot, whose preToolUse already denies on crash or non-zero exit. Do not swallow the error into a silent exit 0.
- **Class 2, integration point** (a user-facing call where a reduced response is meaningful to the caller). Graceful degradation is allowed, scoped to the caller. Rare among governance hooks.
- **Class 3, advisory / steering / precondition** (injects context, nudges a preference, checks a soft precondition; does NOT block a specific dangerous action). It MUST fail open: catch its runtime errors, exit 0, and surface the error on stderr loudly. A false block from a class-3 hook wedges the loop with no safety benefit (the #3247 and #3232 lesson). A silent `exit 0` or `except: pass` is still forbidden (ADR-066 D1); the exit 0 MUST carry the D6 class-3 marker and a loud stderr note. Wrapping `main()` covers runtime errors only: a launch-level failure (bad shebang, import error, syntax error) exits non-zero before any handler runs, and on Copilot that denies. ADR-066's prevention layer (`validate_hook_anchoring.py`, runtime-contract tests, pre-push and CI) is the control for that class, not the exit code.

Do not cite ADR-066 as a blanket warrant for fail-open: fail-open is correct only for class-3 hooks, and only with the D6 marker. For class-1 gates the mandate is the opposite.

**Non-blocking events cannot block, but still fail loud.** Hooks on non-blocking events (PostToolUse, PostToolUseFailure, Notification, SubagentStart, SessionStart, SessionEnd, PreCompact) cannot deny an action; exit 2 there does not block, it only shows a hook error and drops the hook's own stdout context. Choose the exit by hook class, not by the event. A class-3 advisory non-blocking hook (most of them: context injectors, nudges) fails open on its own error, exit 0 with the D6 marker and a loud stderr note, so its context path stays clean. A non-blocking hook that asserts an invariant (class-1) exits non-zero and loud on a bootstrap or config failure; the host ignores the non-zero (it cannot block), so per ADR-066 D2 the repository treats the hook as failed and relies on pre-push, CI, and runtime-contract tests to catch the broken artifact. Neither class emits a spurious exit 2 to fake a block.

**Do not collide with the POSIX helper.** Inside a blocking-event hook, exit 2 means BLOCK. Do not reuse a generic `exit 2 = config error` helper there: on Claude it silently blocks the tool, and on Copilot it denies. Route a blocking hook's internal-config errors through the fail-mode rule above, not through the POSIX table.

**Declare intent.** Every hook SHOULD carry a header docstring naming its event, its blocking mechanism, and the named harm that justifies any block. Conformance of exit-2 gates is verified by a test that scans exit-2 hooks for the docstring and the block bar, not by a hand-maintained list of filenames. A hook that blocks with no named hard-to-reverse harm is non-conformant; downgrade it to advisory.

### Exit-2 gate criteria

Exit 2 (immediate block) is permitted only when the block bar above holds: a blocking event; an action that is not a core navigation tool (or a specific action that is certain and hard-to-reverse); and a named harm that is hard to undo after it lands. The conforming gates are not enumerated here. A hand-maintained filename list goes stale on the next gate added or renamed and silently condemns every omitted exit-2 gate, of which this repo already has more than a dozen under `.claude/hooks/PreToolUse/`. Enforcement is the docstring-and-criteria scan applied to whatever exit-2 hooks exist. Issue #2521 is the record of why exit 2, not an exit-0 top-level `decision`, is the reliable block for these gates.

### Hook header docstring template (Python, ADR-042)

```python
"""Claude Code PreToolUse hook: session-log gate.

Event:        PreToolUse (blocking)
Blocks tool:  Bash (git commit) only; core tools pass through untouched
Mechanism:    exit 2 with reason on stderr (portable block). At exit 2 any
              stdout JSON is inert, so do not also emit permissionDecision.
Fail-mode:    blocking gate; own error fails closed and loud (exit 2 +
              actionable stderr), per ADR-066. Not fail-open.
Blocks to prevent: an irreversible loss of change provenance (a commit with
              no session log)

Exit codes (Claude hook semantics, exempt from the POSIX table above):
    0  Allow, OR a nested JSON permissionDecision
    2  Immediate block (must meet the block bar)
"""
```

### Cross-Harness Hook Idiosyncrasies (Claude Code vs Copilot CLI)

Hooks in this repo run on both Claude Code and GitHub Copilot CLI. The contracts differ enough that a hook correct on one can silently fail on the other.

| Axis | Claude Code | Copilot CLI |
|------|-------------|-------------|
| PreToolUse deny JSON | Nested: `hookSpecificOutput.permissionDecision:"deny"` | Top-level: `permissionDecision:"deny"` |
| Accepts the other's shape? | No (top-level `decision` invalid for PreToolUse) | No (rejects nested wrapper for preToolUse) |
| Exit 2 on PreToolUse | Blocks | Forces deny even if stdout JSON says allow |
| PreToolUse fail mode on hook error | Fails open (tool proceeds) | Fails closed on crash/non-zero/malformed JSON (denies); open only on timeout |
| Matcher | Always honored | Honored on 1.0.62+ (this repo pins 1.0.63, honored); older pins ignore it |
| Event set | Aligned lifecycle events (PreToolUse, PostToolUse, UserPromptSubmit, SessionStart, Stop, SubagentStop, PreCompact, PermissionRequest, plus postToolUseFailure and notification) | Same aligned set |
| Cloud reach | N/A | Copilot only: default-branch `.github/hooks/*.json` also runs in Copilot's cloud agent (ADR-071) |

Consequences for authoring:

1. **Exit 2 is the only cross-harness-portable block.** The structured-JSON deny path is harness-specific and neither harness accepts the other's shape. Block via exit 2 with the reason on stderr.
2. **Self-gate; do not rely on the matcher for containment.** This repo routes all hooks through one consolidated dispatcher (ADR-068) that matches in-process, and per-hook `matcher` honoring is version-dependent in Copilot besides. A blocking hook MUST detect its target tool or command in its own body and allow otherwise, independent of matcher support.
3. **Fail by hook class** (see the fail-mode rule). A crashing allow-hook wedges Copilot preToolUse; a blocking gate that crashes fails closed and loud on both harnesses.

### Cross-Reference

- [ADR-033: Routing-Level Enforcement Gates](./ADR-033-routing-level-enforcement-gates.md) - uses Claude hooks for enforcement
- [ADR-062: Conditional LSP-First Navigation Enforcement](./ADR-062-conditional-lsp-first-enforcement.md) - the LSP runtime guard family retired by its amendment (#3214), deleted in #3232
- [ADR-071: Plugin Hook Runtime-Contract Verification](./ADR-071-plugin-hook-runtime-contract-verification.md) - Accepted; the binding fail-closed-and-loud rule (Decision item 5)
- [ADR-066: Hook Fail-Open Reconciliation](./ADR-066-hook-fail-open-reconciliation.md) - Accepted; the D4 three-class failure-mode model and the exit-code table
- [ADR-084: Vendored-Hook ROI Bar](./ADR-084-vendored-hook-roi-bar.md) - the value-vs-cost bar a hook must clear to exist
- [ADR-068: Consolidated Hook Dispatcher](./ADR-068-consolidated-hook-dispatcher.md) - the in-process matcher dispatch this section references
- [Issue #3247](https://github.com/rjmurillo/ai-agents/issues/3247) - core-tool deny wedges the harness
- [Issue #2521](https://github.com/rjmurillo/ai-agents/issues/2521) - harness ignored top-level `decision:deny` at exit 0 for a safety gate
- [Claude Code Hooks Documentation](https://code.claude.com/docs/en/hooks) - official reference
- [GitHub Copilot CLI Hooks Reference](https://docs.github.com/en/copilot/reference/hooks-reference) - official reference

---

## Related Decisions

- [ADR-005: PowerShell-Only Scripting](./ADR-005-powershell-only-scripting.md) - Language standardization
- [ADR-006: Thin Workflows, Testable Modules](./ADR-006-thin-workflows-testable-modules.md) - Module patterns
- **Memory**: `bash-integration-exit-codes` - Cross-language contract documentation

---

## References

- [POSIX Exit Codes](https://pubs.opengroup.org/onlinepubs/9699919799/utilities/V3_chap02.html#tag_18_08_02)
- [sysexits.h](https://man.freebsd.org/cgi/man.cgi?query=sysexits) - BSD exit code conventions
- [PowerShell Exit Codes Best Practices](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_automatic_variables#lastexitcode)
- [Issue #536](https://github.com/rjmurillo/ai-agents/issues/536) - Original request

---

## Validation

Before accepting this ADR:

- [ ] Review exit code assignments align with project needs
- [ ] Confirm migration plan is feasible
- [ ] Verify no critical workflows depend on current inconsistent codes

After implementation:

- [ ] All scripts document exit codes in header
- [ ] High-priority inconsistencies resolved
- [ ] Pester tests include exit code assertions
- [ ] This ADR referenced in relevant code reviews

---

**Supersedes**: None (new decision)
**Amended by**: None
