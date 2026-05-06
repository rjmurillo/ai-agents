---
type: requirement
id: REQ-005
title: Bundle Dedicated Skills into Lifecycle Commands
status: draft
priority: P1
category: functional
epic: command-skill-bundling
related:
  - DESIGN-005
  - TASK-005
author: spec-agent
created: 2026-05-03
updated: 2026-05-05
---

# REQ-005: Bundle Dedicated Skills into Lifecycle Commands

## Context

Lifecycle commands at `.claude/commands/{spec,plan,build,test,review,ship,pr-review}.md` miss seven dedicated skills and re-prompt agents inline for two more. The gaps are:

- `/spec` and `/ship` skip `session-init` and `session-end`, causing missing session logs on every run.
- `/plan` steps 6-7 prompt `analyst` and `critic` inline instead of invoking `pre-mortem` and `decision-critic` skills, causing critique quality to drift from the same skills `/spec` uses.
- `/build` has no preflight retrieval step, causing the recurring "started coding before reading rules" failure.
- `/test` Gate 3 skips `threat-modeling` on complex changes; Gate 6 skips `slo-designer` and `observability`.
- `/review` has no documentation axis and no legacy-code guard.
- `/pr-review` does not auto-invoke `merge-resolver` when a PR has conflicts.
- `/research` does not run context-gather before web fetches.

All seven command files are hand-edited markdown. There is no template generator for commands (verified: `templates/agents/` exists; no `templates/commands/`). Reversal is `git revert`. No runtime code is involved; the markdown IS the artifact.

## Requirement Statement

WHEN a lifecycle command is invoked,
THE SYSTEM SHALL invoke each dedicated skill specified in the BundleRegistry below via `Skill(skill="<name>")` syntax, gating conditional bundles on presence markers,
SO THAT protocol drift, lost learning, and inconsistent quality are eliminated across the dev lifecycle.

## Acceptance Criteria

### AC-1: /spec session-init

WHEN `/spec` is invoked,
THE SYSTEM SHALL invoke `Skill(skill="session-init")` unconditionally,
SO THAT session logs are created for every spec session.

The `session-init` skill is responsible for handling missing `.agents/SESSION-PROTOCOL.md` (its own precondition); commands do not gate on external infrastructure markers. This matches the PR #1894 pattern where prose-driven bundling at the agent layer ships universal behavior and skills own their own preconditions.

User stories covered: US-1.

### AC-2: /ship session-end and reflect

WHEN `/ship` completes PR creation successfully,
THE SYSTEM SHALL invoke `Skill(skill="session-end")` first (unconditional), then `Skill(skill="reflect")` (unconditional; minimum-delta guard: skip if diff is fewer than 5 changed files),
SO THAT learnings persist and the session log validates after every ship, without noisy reflect invocations on trivial changes.

The `session-end` skill owns its own missing-marker behavior internally; commands do not gate on `.agents/SESSION-PROTOCOL.md` presence (matches PR #1894 precedent: skills own their preconditions).

User stories covered: US-1.

### AC-3: /plan pre-mortem

WHEN `/plan` reaches the pre-mortem step (currently Step 6),
THE SYSTEM SHALL invoke `Skill(skill="pre-mortem")` instead of inline-prompting an analyst to run a pre-mortem,
SO THAT plan critique uses the same structured template `/spec` uses and quality does not drift between commands.

User stories covered: US-2.

### AC-4: /plan decision-critic

WHEN `/plan` reaches the critic step (currently Step 7),
THE SYSTEM SHALL invoke `Skill(skill="decision-critic")` instead of inline-prompting a critic,
SO THAT decision critique uses the same skill both `/spec` and `/plan` invoke, preventing template divergence.

User stories covered: US-2.

### AC-5: /build preflight chain

WHEN `/build` is invoked,
THE SYSTEM SHALL run a preflight chain in order: `Skill(skill="context-gather")` then `Skill(skill="steering-matcher")` then conditional `Skill(skill="chestertons-fence")` when the diff touches a file whose last commit is older than six months (determined by `git log --format=%at -1 -- <file>`),
SO THAT context and applicable rules are loaded before any code is written.

Each preflight skill has a 120-second timeout budget. If a skill exceeds the budget, emit `BUNDLE: build -> <skill> (failed:timeout)` and continue.

User stories covered: US-4.

### AC-6: /test Gate 3 threat-modeling

WHEN `/test` runs Gate 3 (Security Testing) and the complexity tier assigned by Step 0 (PR Type Classification) is 3 or higher,
THE SYSTEM SHALL invoke `Skill(skill="threat-modeling")` in addition to the existing security agent,
SO THAT OWASP STRIDE analysis uses the dedicated skill rather than ad-hoc agent prompting on complex changes.

Note: complexity tier is computed by `/test` Step 0's analyst classification. This AC does not define the tier; it consumes it.

### AC-7: /test Gate 6 slo-designer and observability

WHEN `/test` runs Gate 6 (Observability and Monitoring),
THE SYSTEM SHALL invoke `Skill(skill="slo-designer")` and `Skill(skill="observability")` in addition to the existing architect agent,
SO THAT SLI/SLO definitions and observability gaps are assessed by dedicated skills, not inline architect judgment.

### AC-8: /review doc-accuracy and chestertons-fence

WHEN `/review` runs,
THE SYSTEM SHALL include an Axis 6 (Documentation) that invokes `Skill(skill="doc-accuracy")` and shall conditionally invoke `Skill(skill="chestertons-fence")` in Axis 1 (Architecture) for any diff into files whose last commit is older than six months,
SO THAT documentation drift is caught pre-merge and legacy-code changes pass Chesterton's Fence before review completes.

### AC-9: /pr-review merge-resolver

WHEN `/pr-review` checks PR status (Step 2) and `gh pr view $PR --json mergeable -q '.mergeable'` returns `CONFLICTING` or `UNKNOWN`,
THE SYSTEM SHALL invoke `Skill(skill="merge-resolver")` for `CONFLICTING` and prompt the user for guidance on `UNKNOWN`,
SO THAT operators do not need to invoke merge-resolver manually when conflicts exist.

User stories covered: US-5.

### AC-10: /research context-gather

WHEN `/research` is invoked,
THE SYSTEM SHALL run `Skill(skill="context-gather")` as its first step before any web fetch or memory write,
SO THAT research operates on current repo context rather than stale or absent local knowledge.

### AC-11: BUNDLE marker on every invocation

WHEN any bundled skill invocation fires (whether it succeeds, skips, or fails),
THE SYSTEM SHALL contain a parseable `BUNDLE: <command> -> <skill> (<status>)` marker adjacent to the `Skill(...)` call in the command file, where `<status>` is one of `invoked`, `skipped:no-marker`, or `failed:<reason>`,
SO THAT bundle coverage is statically verifiable by automated tests that parse the command markdown.

Note: this is a static contract (the marker exists in the file text), not runtime stdout. The test parses the `.md` file, not CLI output.

User stories covered: US-7.

### AC-12: Runtime-conditional skip behavior

WHEN a skill's runtime gate condition is not met (`chestertons-fence` when no diff file is older than six months; `merge-resolver` when `gh pr view --json mergeable -q '.mergeable'` is not `CONFLICTING`/`UNKNOWN`),
THE SYSTEM SHALL emit `BUNDLE: <command> -> <skill> (skipped:condition-not-met)` and continue without aborting the command,
SO THAT runtime-conditional skills do not fire when their precondition is absent.

Note: AC-12 applies only to **runtime conditionals**, not to external-infrastructure presence checks. Skills that depend on `.agents/` infrastructure (e.g., `session-init`, `session-end`) own their own missing-marker handling internally per AC-1 and AC-2.

### AC-13: Failed skill warn-and-continue

WHEN a bundled skill invocation returns an error,
THE SYSTEM SHALL emit `BUNDLE: <command> -> <skill> (failed:<reason>)` and continue to downstream steps without retrying,
SO THAT a transient skill failure does not abort the entire lifecycle command.

### AC-14: pre_pr.py bundle coverage check (advisory)

WHEN `scripts/validation/pre_pr.py` runs,
THE SYSTEM SHALL parse each command file for required `Skill(skill="...")` invocations and emit an advisory WARN (not BLOCKING) finding for any AC-required invocation absent from its target command file,
SO THAT bundle coverage drift is surfaced to reviewers without converting the registry into a system-wide CI gate that would push the change to Tier 3.

Advisory framing matches PR #1894's approach to prose-driven changes: drift is detected and surfaced, but humans (PR reviewers) are the enforcement layer. A future spec MAY escalate this to BLOCKING once the registry has stabilized over multiple PRs and an ADR captures the decision.

---

## Rationale

The lifecycle commands are the primary interface for repo maintainers and agents executing the dev lifecycle. When dedicated skills exist for a workflow step, commands should invoke them rather than re-prompt agents inline. Inline prompting produces inconsistent quality, accumulates protocol drift, and prevents skills from being independently improved without touching command files. Bundling also creates a verifiable registry (AC-14) that CI can enforce.

## Dependencies

- **Prerequisite verification**: Before implementation begins, verify all 16 skills in the BundleRegistry exist by confirming `.claude/skills/<name>/SKILL.md` is present for each. This is T5-0 in TASK-005.
- All skills in the BundleRegistry must already exist. New skills are out of scope.
- `scripts/validation/pre_pr.py` must be extensible to parse markdown for skill invocations. The existing pre-PR runner already parses command files for other checks.
- `tests/test_command_bundles.py` must be added (new file; covered in TASK-005).
- `/research` command file must exist at `.claude/commands/research.md` (AC-10 target).

## Out of Scope

- Cross-command Serena context handoff. Future spec.
- A new `/audit` cadence command. Future spec.
- Modifying existing skill internals. This spec only adds call sites.
- Modifying agent definitions under `templates/agents/` or `.claude/agents/`.
- Modifying any `.claude/rules/*.md` file.
- Whether `pipeline-validator` should also fire in `/test` Gate 4 (currently only in `/ship`). Deferred; see below.

## Deferred

- `/test` Gate 4 `pipeline-validator` bundle. Owner: maintainer; revisit after this spec lands.
- `reflect` idempotency hash-based dedupe. Owner: skill author; current idempotency claim (skip when no HIGH-confidence learnings) is unchanged. The minimum-delta guard (< 5 changed files = skip reflect) is enforced at the command level in AC-2.

## Related Documents

- Analysis: `.agents/analysis/command-skill-bundling-2026-05-03.md`
- Design: `.agents/specs/design/DESIGN-005-command-skill-bundling.md`
- Tasks: `.agents/specs/tasks/TASK-005-command-skill-bundling.md`
