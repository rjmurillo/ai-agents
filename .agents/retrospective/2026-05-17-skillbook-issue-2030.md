# Retrospective: Session 1153 - Skillbook (Issue #2030)

**Date**: 2026-05-17
**Session log**: `.agents/sessions/2026-05-17-session-1153-implement-issue-2030-evidence-tiered-agent.json`
**Issue**: [#2030 - Evidence-tiered agent policies / "skillbook"](https://github.com/rjmurillo/ai-agents-issue-2030/issues/2030)
**Branch**: `agent/issue-2030-evidence-tiered-policies`
**Outcome**: Feature complete, PR pending

## Impact

| Area | Severity | Notes |
|------|----------|-------|
| Session startup delay | Low | ~10 min diagnosing and fixing bare-worktree misconfiguration |
| Session log mislocation | Low | Log written to bare dir before fix; manually relocated |
| Persona coverage gap | Medium | First-pass seed covered 13/24 agent personas; caught by QA before PR |
| Deferred integration | Low | `pre_pr.py` validator wire-up deferred to follow-up issue |

---

## Execution Trace

| Phase | Action | Outcome |
|-------|--------|---------|
| Start | `git status` failed with "must be run in a work tree" | Diagnosed shared config had `core.bare = true` with `extensions.worktreeConfig` enabled and no per-worktree override |
| Fix | `git config --worktree core.bare false` | Resolved; session log relocated from bare dir to worktree |
| Convention discovery | Delegated to Explore subagent | Success; kept main context lean |
| Implementation | 4 JSON schemas, `scripts/skillbook.py` (6 CLI commands), `scripts/validation/validate_skillbook.py`, seed data, `.agents/hooks/post-eval.py`, CI workflow, README, 100 pytest tests | 9 commits, ~96% coverage |
| QA gate | QA agent: PASS WITH CONCERNS | Identified persona-count gap (13/24) and missing `agent/**` CI trigger |
| Fix | Extended seed to all 24 personas; added `agent/**` trigger | Resolved |
| Critic gate | APPROVED_WITH_CONCERNS, all 10 ACs PASS | 7 findings: 6 resolved in-session (naming disambiguation, idempotency-key docs, scope note, assertion wording, 2 test branches); 1 deferred |
| End | Clean ruff + tests + validators | PR pending |

### Commits (branch `agent/issue-2030-evidence-tiered-policies`)

| SHA | Message |
|-----|---------|
| `838d92da` | feat(skillbook): add JSON schemas for evidence-tiered policies |
| `66930edc` | feat(skillbook): add skillbook CLI and schema validator |
| `9c4a2b1a` | feat(skillbook): seed policy, tension, and workflow registries |
| `9e1e6159` | feat(skillbook): add post-eval hook and tag the security eval |
| `cfb43d38` | test(skillbook): add tests for evidence math, promotion, and CLI |
| `3686ef16` | test(skillbook): add tests for the validator and post-eval hook |
| `d6b82fea` | ci(skillbook): add schema validation workflow |
| `939552ba` | docs(skillbook): clarify naming, idempotency key, and scope |
| `b4cdb6d7` | test(skillbook): cover tension re-pointing and evidence validation |

---

## Failure Mode Classification

### FM-1 (Context Reading Failure) - LOW CONFIDENCE MATCH

The implementer did not enumerate the persona directory before generating seed data. The issue text stated "1 policy per persona minimum" but the first-pass seed covered 13 of 24 personas. This is closest to **FM-1 (Context Reading Failure)**: required context (the persona directory count) was present and discoverable but not consulted before producing the artifact.

The lapse did not survive gating: QA caught it before the PR was opened. No production impact. No existing FM entry precisely describes "incomplete requirements enumeration during implementation"; this is a partial FM-1 instance.

### Environment Issue - No Existing FM Match

The `git config core.bare = true` state in the shared worktree config is an infrastructure/environment failure, not an agent cognition failure. No existing FM class covers mis-provisioned worktree configuration. A new FM is not warranted from a single environmental incident, but the `new_session_log.py` path-resolution behavior under a failing `git status` is worth examining (see Remediation below).

---

## Five Whys: Persona Coverage Gap

**Problem**: Seed data covered 13 of 24 agent personas on first pass.

1. Why? The implementer generated representative seed data without counting available persona files.
2. Why? The persona directory was not enumerated as an explicit precondition before writing seed data.
3. Why? The implementation plan did not include a "count personas and assert coverage" step.
4. Why? The issue text said "minimum 1 per persona" but the planner did not convert that into a measurable pre-implementation check.
5. Why? No checklist or gate exists that requires persona enumeration before seed generation.

**Root cause**: Planning step did not convert the "1 per persona minimum" requirement into an explicit count-then-cover precondition.

**Actionable fix**: Add a step to implementer checklist: when issue says "N per X entity," enumerate X entities and assert count before writing seed/fixture data.

---

## What Worked

- Delegating convention discovery to an Explore subagent kept the main context lean and fast.
- Hand-rolling the draft-07 schema subset checker avoided a `jsonschema` dependency/lockfile change while keeping schemas load-bearing.
- QA-then-critic gate sequence caught the persona-count gap and untested branches before the PR. Both reviewers added independent signal; neither rubber-stamped the other.
- Nine atomic commits kept each change reviewable in isolation.

---

## Remediation and Follow-ups

| Action | Owner | Issue |
|--------|-------|-------|
| Wire `validate_skillbook.py` into `pre_pr.py` so the schema check runs in the pre-PR gate | implementer | Open follow-up issue referencing critic finding |
| Investigate `new_session_log.py` path resolution when `git status` fails: does the script fall back to a safe path or silently write to cwd? | architect / implementer | New investigation issue |
| Add "enumerate entities before generating seed data" step to implementer planning checklist (addresses FM-1 partial match) | architect | Update `.agents/steering/` or implementer template |
| Update `FAILURE-MODES.md` if the `new_session_log.py` investigation confirms a reproducible agent-side failure | retrospective agent | After investigation closes |

---

## +/Delta

### Keep
- QA-then-critic two-gate sequence before PR.
- Explore subagent for convention discovery on large codebases.
- Atomic commits (1 concern per commit).

### Change
- Session-init script should validate `git status` succeeds and log the path it will write to before writing, not after.
- Implementer planning should include an explicit "enumerate required entities, assert count" step when requirements state a per-entity minimum.
