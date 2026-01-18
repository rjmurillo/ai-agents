# Skill: coordination-verification-001-branch-isolation-gate

**Atomicity Score**: 92%
**Source**: eyen (coordination agent) - Sessions 40-41 retrospective
**Date**: 2025-12-20
**Validation Count**: 1 (Sessions 40-41 incident)

## Definition

Before multi-agent session execution begins, coordination agent MUST verify branch isolation strategy through a 5-gate verification sequence.

## Gates

### Gate 1: Verify Pre-Commit Hooks Active (2 min)

```
Action: git hooks --status
Verify: All hooks return 0 (active)
Fallback: If hooks not active, fail fast and escalate
Success: All hooks confirmed active
```

### Gate 2: Assign Explicit Branch per Agent (3 min)

```
Pattern: worktree-${AGENT_ROLE}-${PR_NUMBER} -> ${FEATURE_BRANCH}
Document: HCOM message listing each agent's assigned branch
Example: "jeta -> feat/pr-162-phase4, onen -> audit/pr-89-protocol"
Success: Each agent has written confirmation of assigned branch
```

### Gate 3: Verification Checkpoint - Confirm Isolation (2 min)

```
Action: Require each agent to run: git branch --show-current
Expected: Output matches assigned branch (e.g., feat/pr-162-phase4)
Failure: If output != expected, HALT execution and escalate
Success: All agents confirmed on correct isolated branches
```

### Gate 4: Pre-Commit Hook Briefing (2 min)

```
Message: "File naming conventions enforced by pre-commit hooks"
Verify: Each agent can name one file correctly
Example: ".agents/sessions/YYYY-MM-DD-session-NN.md (correct)"
Success: All agents understand naming requirements
```

### Gate 5: Sign-Off Message (1 min)

```
Require: HCOM message from each agent: "Ready on [BRANCH_NAME]"
Verification: Each agent confirms:
  a) On correct isolated branch
  b) Pre-commit hooks active
  c) Understands file naming requirements
Success: All agents confirm readiness
```

## Timing

**Total Time**: ~10 minutes for complete verification

## Success Criteria

- All pre-commit hooks active and verified
- Each agent assigned explicit isolated branch
- Each agent confirmed `git branch --show-current` matches assignment
- All agents understand file naming conventions
- Team-wide HCOM sign-off confirming readiness

## Failure Criteria (Fail Fast)

- Any hook inactive -> escalate immediately
- Any agent not on assigned branch -> HALT and investigate
- Any agent unaware of naming requirements -> pause and brief
- Any agent not able to confirm readiness -> defer execution

## When to Use

- Run at Session Start (Phase 0)
- Run before multi-agent coordination sessions
- Required before parallel execution begins
- Blocks all other work until gates pass

## Evidence

Sessions 40-41 incident: Multiple agents committed to shared branch due to missing Phase 0 gate. 30-minute detection delay. Hybrid recovery required.

## Related Skills

- coordination-monitoring-001: Mid-execution verification checkpoints
- protocol-enforcement-001: Pre-commit hook validation
- team-communication-001: HCOM status messaging
