---
type: design
id: DESIGN-005
title: Bundle Dedicated Skills into Lifecycle Commands
status: draft
priority: P1
related:
  - REQ-005
adr: []
author: spec-agent
created: 2026-05-03
updated: 2026-05-05
---

# DESIGN-005: Bundle Dedicated Skills into Lifecycle Commands

## Requirements Addressed

- REQ-005 AC-1 through AC-14: all fourteen acceptance criteria are satisfied by edits to seven command files plus two supporting artifacts (test file and pre_pr.py check).

## Design Overview

Seven markdown command files are edited in place to add `Skill(skill="<name>")` invocations at defined phases. No runtime code is generated. A flat BundleRegistry table (below) is the authoritative record of what fires where. Two supporting artifacts enforce the registry at test time and at PR gate time.

## Source

This design is derived from `.agents/analysis/command-skill-bundling-2026-05-03.md` (2026-05-03), which identified all gaps and proposed the fix for each command.

---

## BundleRegistry

The registry is the canonical mapping. Every `Skill(skill="...")` call added by this spec appears here. AC-14 (`pre_pr.py`) and the test file both validate against this table.

| Command file | Skill name | Gate type | Phase | Presence marker | AC# |
|---|---|---|---|---|---|
| `spec.md` | `session-init` | presence | preflight | `.agents/SESSION-PROTOCOL.md` | AC-1 |
| `ship.md` | `session-end` | presence | postflight | `.agents/SESSION-PROTOCOL.md` | AC-2 |
| `ship.md` | `reflect` | always | postflight | (none) | AC-2 |
| `plan.md` | `pre-mortem` | always | step-6 | (none) | AC-3 |
| `plan.md` | `decision-critic` | always | step-7 | (none) | AC-4 |
| `build.md` | `context-gather` | always | preflight | (none) | AC-5 |
| `build.md` | `steering-matcher` | always | preflight | (none) | AC-5 |
| `build.md` | `chestertons-fence` | presence | preflight | diff contains file with last commit > 6 months old | AC-5 |
| `test.md` | `threat-modeling` | conditional | gate-3 | complexity tier >= 3 | AC-6 |
| `test.md` | `slo-designer` | always | gate-6 | (none) | AC-7 |
| `test.md` | `observability` | always | gate-6 | (none) | AC-7 |
| `review.md` | `doc-accuracy` | always | axis-6 | (none) | AC-8 |
| `review.md` | `chestertons-fence` | presence | axis-1 | diff touches file with last commit > 6 months old | AC-8 |
| `pr-review.md` | `merge-resolver` | presence | step-2 | `gh pr view --json mergeable -q '.mergeable'` returns `CONFLICTING` or `UNKNOWN` | AC-9 |
| `research.md` | `context-gather` | always | preflight | (none) | AC-10 |

**Gate types**:
- `always`: unconditional; fires every invocation.
- `presence`: fires only when a marker file or condition is met; emits `skipped:no-marker` otherwise.
- `conditional`: fires when a computed condition holds (e.g., complexity tier from a prior step).

---

## Presence-Marker Table

| Skill | Command | Marker | Check method |
|---|---|---|---|
| `session-init` | `spec.md` | `.agents/SESSION-PROTOCOL.md` | `Read` or `Bash(test -f ...)` |
| `session-end` | `ship.md` | `.agents/SESSION-PROTOCOL.md` | `Read` or `Bash(test -f ...)` |
| `chestertons-fence` | `build.md` | diff contains file with last commit > 6 months old | `Bash(git log --format=%at -1 -- "<file>")` — quote path to prevent CWE-78 |
| `chestertons-fence` | `review.md` | diff touches file with last commit > 6 months old | same as above |
| `merge-resolver` | `pr-review.md` | `gh pr view --json mergeable -q '.mergeable'` returns `CONFLICTING` or `UNKNOWN` | `gh pr view $PR --json mergeable -q '.mergeable'` |

Security note: presence checks MUST use `Read` or `Bash(test -f <literal-path>)`. User-supplied input MUST NOT be interpolated into any shell command (CWE-78 prevention).

---

## BUNDLE Marker Format

Every bundled invocation has a parseable marker in the command markdown adjacent to the `Skill(...)` call. This is a **static contract** (the marker exists in the file text for test verification), not runtime stdout.

Format:

```
BUNDLE: <command> -> <skill> (<status>)
```

Where:
- `<command>` is the slash-command name (e.g., `spec`, `ship`, `build`).
- `<skill>` is the exact skill name passed to `Skill(skill="...")`.
- `<status>` is one of:
  - `invoked`: the skill was called.
  - `skipped:no-marker`: the presence marker was absent.
  - `failed:<reason>`: the skill returned an error; `<reason>` is a short string, no PII, no secrets.

Example inline pattern:

```markdown
Emit `BUNDLE: spec -> session-init (invoked)`, then invoke `Skill(skill="session-init")`.
```

The test file parses command files for both the `Skill(skill="...")` call and the adjacent `BUNDLE:` text. This is a markdown-text-search, not a runtime output capture.

---

## Per-Command Edit Specifications

### spec.md

**Phase**: preflight (before Step 1 "Clarify the problem")

**Before** (current Step 1 heading):
```markdown
## Process

1. Clarify the problem (what, who, why, constraints)
```

**After**:
```markdown
## Process

0. **Session init** (presence-gated): If `.agents/SESSION-PROTOCOL.md` exists, invoke `Skill(skill="session-init")` and emit `BUNDLE: spec -> session-init (invoked)`. Otherwise emit `BUNDLE: spec -> session-init (skipped:no-marker)` and continue.
1. Clarify the problem (what, who, why, constraints)
```

Satisfies: AC-1, AC-11, AC-12.

---

### ship.md

**Phase**: postflight (after Step 4 "Create PR")

**Before** (current Step 5):
```markdown
5. Report: what shipped, PR link, any warnings
```

**After**:
```markdown
5. **Post-ship learnings**: After PR creation succeeds:
   - Emit `BUNDLE: ship -> session-end (invoked)` or `BUNDLE: ship -> session-end (skipped:no-marker)` based on presence of `.agents/SESSION-PROTOCOL.md`, then invoke `Skill(skill="session-end")` if marker present.
   - Emit `BUNDLE: ship -> reflect (invoked)`, then invoke `Skill(skill="reflect")` unconditionally.
   - If either skill returns an error, emit `BUNDLE: ship -> <skill> (failed:<reason>)` and continue.
6. Report: what shipped, PR link, any warnings
```

Satisfies: AC-2, AC-11, AC-12, AC-13.

---

### plan.md

**Phase**: steps 6 and 7 (currently inline agent prompts)

**Before** (current Steps 6-7):
```markdown
6. Task(subagent_type="analyst"): You are a risk analyst. Run a pre-mortem on this plan. What fails first? What dependencies are fragile? What assumptions are untested?
7. Task(subagent_type="critic"): You are a plan reviewer. Validate: is scope complete? Can tasks execute in the stated sequence? Are estimates credible? Is anything missing?
```

**After**:
```markdown
6. **Pre-mortem**: Emit `BUNDLE: plan -> pre-mortem (invoked)`, then invoke `Skill(skill="pre-mortem")` on the plan produced in step 5. If the skill fails, emit `BUNDLE: plan -> pre-mortem (failed:<reason>)` and continue.
7. **Decision critic**: Emit `BUNDLE: plan -> decision-critic (invoked)`, then invoke `Skill(skill="decision-critic")` to challenge plan assumptions. If the skill fails, emit `BUNDLE: plan -> decision-critic (failed:<reason>)` and continue.
```

Satisfies: AC-3, AC-4, AC-11, AC-13.

---

### build.md

**Phase**: preflight (before "Complexity Assessment")

**Before** (current opening after frontmatter):
```markdown
## Complexity Assessment

Before implementation, Task(subagent_type="analyst"):...
```

**After**:
```markdown
## Preflight

Before any implementation work, run in order:

1. Emit `BUNDLE: build -> context-gather (invoked)`, then invoke `Skill(skill="context-gather")` to load Forgetful, Serena, Context7, and DeepWiki context for the current task.
2. Emit `BUNDLE: build -> steering-matcher (invoked)`, then invoke `Skill(skill="steering-matcher")` to load path-based rules from `.claude/rules/` for files in scope.
3. **Chesterton's Fence (conditional)**: Run `git log --format=%at -1 -- "<file>"` for each file in scope (paths MUST be quoted to prevent CWE-78 shell injection). If any file's last commit timestamp is older than six months, emit `BUNDLE: build -> chestertons-fence (invoked)` and invoke `Skill(skill="chestertons-fence")`. Otherwise emit `BUNDLE: build -> chestertons-fence (skipped:no-marker)`.

Each preflight skill has a 120-second timeout. On timeout: emit `BUNDLE: build -> <skill> (failed:timeout)` and continue.

If any preflight skill fails, emit `BUNDLE: build -> <skill> (failed:<reason>)` and continue.

## Complexity Assessment

Before implementation, Task(subagent_type="analyst"):...
```

Satisfies: AC-5, AC-11, AC-12, AC-13.

---

### test.md

**Gate 3 addition** (Security Testing, after existing `security-scan` invocation):

**Before**:
```markdown
## Gate 3: Security Testing

Invoke Skill(skill="security-scan") for CWE pattern detection.

Task(subagent_type="security"):...
```

**After**:
```markdown
## Gate 3: Security Testing

Invoke Skill(skill="security-scan") for CWE pattern detection.

**Threat modeling (conditional)**: If the complexity tier from Step 0 is 3 or higher, emit `BUNDLE: test -> threat-modeling (invoked)` and invoke `Skill(skill="threat-modeling")`. Otherwise emit `BUNDLE: test -> threat-modeling (skipped:no-marker)`.

Task(subagent_type="security"):...
```

**Gate 6 addition** (Observability, before existing architect agent):

**Before**:
```markdown
## Gate 6: Observability and Monitoring

Task(subagent_type="architect"):...
```

**After**:
```markdown
## Gate 6: Observability and Monitoring

Emit `BUNDLE: test -> slo-designer (invoked)`, then invoke `Skill(skill="slo-designer")` to assess SLI/SLO definitions for new features.
Emit `BUNDLE: test -> observability (invoked)`, then invoke `Skill(skill="observability")` to assess structured logging, metrics, and tracing gaps.
If either skill fails, emit `BUNDLE: test -> <skill> (failed:<reason>)` and continue.

Task(subagent_type="architect"):...
```

Satisfies: AC-6, AC-7, AC-11, AC-13.

---

### review.md

**Axis 1 addition** (Architecture, conditional chestertons-fence):

**Before** (Axis 1 close):
```markdown
- Follows existing patterns? Clean boundaries? Right abstraction level?
- Coupling intentional? Cohesion strong?
- ADR conformance? Any decisions that need a new ADR?
```

**After**:
```markdown
- Follows existing patterns? Clean boundaries? Right abstraction level?
- Coupling intentional? Cohesion strong?
- ADR conformance? Any decisions that need a new ADR?
- **Chesterton's Fence (conditional)**: If the diff touches a file whose last commit is older than six months (via `git log --format=%at -1 -- "<file>"`), emit `BUNDLE: review -> chestertons-fence (invoked)` and invoke `Skill(skill="chestertons-fence")`. Otherwise emit `BUNDLE: review -> chestertons-fence (skipped:no-marker)`.
```

**Axis 6 addition** (new axis, after Axis 5 Standards):

**Before** (Principles section):
```markdown
## Principles
```

**After**:
```markdown
## Axis 6: Documentation

Emit `BUNDLE: review -> doc-accuracy (invoked)`, then invoke `Skill(skill="doc-accuracy")` to detect documentation drift, inaccurate inline comments, and missing doc coverage for changed public surface.
If the skill fails, emit `BUNDLE: review -> doc-accuracy (failed:<reason>)` and continue.

Include the doc-accuracy verdict in the final synthesis table with a `Documentation` row.

## Principles
```

Update the synthesis step (Step 8) to include Axis 6 in the findings table.

Satisfies: AC-8, AC-11, AC-12, AC-13.

---

### pr-review.md

**Step 2 addition** (Comprehensive PR Status Check, merge-resolver):

**Before** (Step 2 close):
```markdown
### Step 2: Comprehensive PR Status Check

Before addressing comments, gather full context:

1. **Review ALL comments**: ...
2. **Check merge eligibility**: Verify `mergeable=MERGEABLE` and no conflicts.
3. **Review failing checks**: ...
```

**After**:
```markdown
### Step 2: Comprehensive PR Status Check

Before addressing comments, gather full context:

1. **Review ALL comments**: ...
2. **Check merge eligibility**: Run `gh pr view $PR --json mergeable -q '.mergeable'`. If the result is `CONFLICTING`, emit `BUNDLE: pr-review -> merge-resolver (invoked)` and invoke `Skill(skill="merge-resolver")`. If the result is `UNKNOWN`, prompt the user for guidance before proceeding. Otherwise emit `BUNDLE: pr-review -> merge-resolver (skipped:no-marker)`. If the skill fails, emit `BUNDLE: pr-review -> merge-resolver (failed:<reason>)` and continue.
3. **Review failing checks**: ...
```

Satisfies: AC-9, AC-11, AC-12, AC-13.

---

### research.md

**Preflight addition** (before any web fetch):

**Before** (current opening process step):
```markdown
Respond to the research request: $ARGUMENTS
```

**After**:
```markdown
Respond to the research request: $ARGUMENTS

## Preflight

Before any web fetch or memory write, emit `BUNDLE: research -> context-gather (invoked)` and invoke `Skill(skill="context-gather")` to load repo-local context. If the skill fails, emit `BUNDLE: research -> context-gather (failed:<reason>)` and continue.
```

Satisfies: AC-10, AC-11, AC-13.

---

## Technology Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Artifact type | Markdown hand-edits | No template generator for commands; verified `templates/commands/` does not exist. Direct edits match existing conventions. |
| Skill invocation syntax | `Skill(skill="<name>")` | Matches existing pattern in `spec.md:16,23,30`, `ship.md:17-21`, `review.md:24-26,39,49,63`. |
| BUNDLE marker format | Static text marker adjacent to `Skill(...)` call in the markdown | Parseable by both humans and the test file; no runtime stdout dependency; avoids structured logging overhead. |
| Presence-check method | `Read` or `Bash(test -f <literal-path>)` | CWE-78 prevention; no user-supplied path interpolation. |
| Conflict resolution | Closer-to-implementation invocation wins | E.g., `decision-critic` in `/spec` and `/plan` both invoke the same skill; no conflict because they are independent command runs. |
| Idempotency | `session-init` checks for existing log; `reflect` skips when no HIGH-confidence learnings | Handled inside the skills; command edits do not need idempotency guards. |

---

## Security Considerations

- No new attack surface. All skills are existing.
- Presence checks MUST use `Read` or `Bash(test -f <literal-path>)` only. MUST NOT interpolate `$ARGUMENTS` or any user input into shell commands.
- Markdown-only distribution. No executable content. No secrets.
- BUNDLE marker output MUST NOT include file contents, API keys, tokens, or PII in the `<reason>` field.

---

## Testing Strategy

| Layer | Artifact | What is verified |
|---|---|---|
| Static parse | `tests/test_command_bundles.py` | Each command file contains the `Skill(skill="...")` calls from the BundleRegistry. Parses markdown; does not execute commands. |
| Pre-PR gate | `scripts/validation/pre_pr.py` (new check) | Same parser as test file; blocks PRs where required invocations are absent. |
| Shared registry | `tests/conftest.py` or `tests/bundle_registry.py` | Single source of truth for BUNDLE_REGISTRY list, imported by both test and pre_pr.py. Avoids copy-paste drift between consumers. |
| Manual smoke | Run `/spec` on a repo with `.agents/SESSION-PROTOCOL.md` present and absent | Verify `BUNDLE:` text appears in command file and behavior matches. |
| CWE-78 check | `tests/test_command_bundles.py` | All git log commands in build.md and review.md quote file paths (grep for `-- "<`). |

---

## Open Questions

None. All open questions resolved in the PRD.

## Related Documents

- Requirements: `.agents/specs/requirements/REQ-005-command-skill-bundling.md`
- Tasks: `.agents/specs/tasks/TASK-005-command-skill-bundling.md`
- Analysis: `.agents/analysis/command-skill-bundling-2026-05-03.md`
