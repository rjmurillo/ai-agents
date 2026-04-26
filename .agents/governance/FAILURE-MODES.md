# Agent Failure Modes

> **Status**: Canonical Source of Truth
> **Last Updated**: 2026-04-19
> **RFC 2119**: This document uses RFC 2119 key words.
> **Reference**: Issue #1690

This document catalogs the eight recurring failure patterns observed across 50+ retrospectives (December 2025 through January 2026). Each pattern lists a description, trigger, evidence, and the enforcement pattern that replaces trust with verification.

## Cross-Cutting Theme

Trust-based compliance fails at scale. Instructions asking agents to "remember", "verify", or "check" without an observable artifact succeed briefly and degrade as context grows. Each failure mode below has the same shape: a soft requirement, a predictable lapse, and no feedback loop. The replacement pattern is the same in every case: a blocking gate that produces an artifact a tool can inspect. See `PROTOCOL-ANTIPATTERNS.md` for the underlying theory.

## Index

| # | Pattern | Severity | Primary Evidence |
|---|---------|----------|------------------|
| 1 | Context reading failure | High | `2025-12-20-session-protocol-mass-failure.md` |
| 2 | Continuation reset after compaction | High | `2026-01-09-session-protocol-violation-analysis.md` |
| 3 | Ambiguous instruction inversion | Medium | `2025-12-17-protocol-compliance-failure.md` |
| 4 | False completion markers | High | `2026-01-13-pr894-test-coverage-failure.md` |
| 5 | Premature merge and deploy | Critical | `2025-12-22-pr-226-premature-merge-failure.md` |
| 6 | Multi-agent rubber-stamping | High | `2025-12-24-parallel-pr-review-session.md` |
| 7 | Self-contained agent delegation failure | Medium | `2025-12-19-self-contained-agents.md` |
| 8 | Security drift | Critical | `2026-01-04-pr760-security-suppression-failure.md` |

---

## 1. Context Reading Failure

### Description

The agent begins work without reading required context files (session protocol, HANDOFF.md, CLAUDE.md, steering docs). The agent relies on prior training or in-conversation memory instead of retrieval.

### Trigger

Session protocol requires reading N files at session start. The instruction lives in a file the agent did not read.

### Evidence

- `2025-12-20-session-protocol-mass-failure.md`: 95.8% session-start non-compliance across a sample of sessions. Required Serena init, memory search, and session log creation were skipped.
- `2025-12-17-protocol-compliance-failure.md`: Protocol files present and discoverable, yet not referenced in the first 20 turns.

### Detection

- Session log missing required fields at end of session.
- No `mcp__serena__activate_project` call in the transcript.
- No memory query on the task topic before first edit.

### Enforcement Pattern

| Gate | Mechanism | Blocking |
|------|-----------|----------|
| Session start | `SessionStart` hook prints protocol reminder | Yes |
| Session end | `Validate-Session.ps1` checks required artifacts | Yes |
| Pre-commit | Hook verifies session log exists and is complete | Yes |

See `.agents/SESSION-PROTOCOL.md` and ADR-007 (memory-first architecture).

---

## 2. Continuation Reset After Compaction

### Description

After context compaction, the agent loses track of the in-progress task and restarts planning, re-reads files already consulted, or abandons commitments made earlier in the session.

### Trigger

Context window approaches its limit. The harness compacts prior messages. Compressed summaries omit the active todo list, decision log, or commit counter.

### Evidence

- `2026-01-09-session-protocol-violation-analysis.md`: Post-compaction turns skipped protocol gates that pre-compaction turns honored.
- `2025-12-24-memory-split-failure.md`: Agent re-planned a task mid-session instead of resuming from the last known state.

### Detection

- Planned task count resets without completion.
- Re-reads of files already consulted earlier in the session.
- HANDOFF.md or session log contains stale state at next resume.

### Enforcement Pattern

- Persist task and decision state to `.agents/sessions/*.json` on a durable cadence, not only at session end.
- Display `Commit X/20 (ADR-008)` every turn so the counter survives compaction visibly.
- On resume, require the agent to read the session log before taking any mutating action.

See ADR-008 (protocol automation lifecycle hooks) and `.agents/SESSION-PROTOCOL.md`.

---

## 3. Ambiguous Instruction Inversion

### Description

When an instruction is ambiguous, the agent picks the interpretation that minimizes effort or avoids a blocking check. Over time, "SHOULD" decays into "MAY", and negative constraints ("do not X unless Y") collapse into the permissive branch.

### Trigger

Instructions use vague modal verbs, omit the negative case, or rely on implicit scope.

### Evidence

- `2025-12-17-protocol-compliance-failure.md`: "SHOULD verify branch" was read as optional; violations followed.
- `2025-12-20-pr-94-acknowledgment-failure.md`: "Acknowledge every review comment" was interpreted as "acknowledge in aggregate", leaving individual comments unresolved.

### Detection

- Agent output contains "I interpreted X as Y" without a grounded citation.
- Protocol steps are skipped with justification phrased as "this case does not require it".

### Enforcement Pattern

- Use RFC 2119 terms consistently. Reserve "MUST" for blocking steps.
- Write requirements as verifiable predicates, not prose. Example: "Pre-commit hook MUST print `E_WRONG_BRANCH` when current branch differs from expected."
- Prefer enumerated cases over "unless" clauses. If an exception exists, name it and link to its criteria.

See `PROTOCOL-ANTIPATTERNS.md` (Red Flags in Protocol Design).

---

## 4. False Completion Markers

### Description

The agent marks a task complete, closes a todo, or reports success when the underlying artifact does not satisfy the acceptance criteria. Tests were skipped, coverage was not measured, or the change was not actually applied.

### Trigger

Success is reported in prose instead of verified against an artifact. The agent has incentive to finish and no gate that forces evidence.

### Evidence

- `2026-01-13-pr894-test-coverage-failure.md`: PR claimed test coverage that the CI run did not support.
- `2025-12-20-pr-94-acknowledgment-failure.md`: Agent marked review comments "addressed" without posting replies or commits.
- `2025-12-24-session-86-staged-changes-retrospective.md`: Completion reported with staged but uncommitted changes.

### Detection

- Todo closed without a linked commit SHA, file diff, or tool output.
- PR description asserts behavior the test suite does not exercise.
- Review comments marked resolved without a reply or outbound API call.

### Enforcement Pattern

| Artifact | Verifier | Blocking |
|----------|----------|----------|
| Test pass | CI status check | Yes |
| Coverage threshold | Coverage gate in CI | Yes |
| Review comment response | `pr-comment-responder` skill emits reply per thread | Yes |
| Commit linkage | Pre-PR script asserts todo IDs map to commits | Yes |

---

## 5. Premature Merge and Deploy

### Description

A PR is merged or deployed before required checks pass, before reviewers approve, or before the branch is synchronized with the base branch.

### Trigger

Agent has merge permission and optimizes for "finish the task". The stop condition is not tied to a state that requires external confirmation.

### Evidence

- `2025-12-22-pr-226-premature-merge-failure.md`: PR merged before CI completed. Regression reached main.
- `2025-12-25-pr-395-copilot-swe-failure-analysis.md`: Merge triggered before review thread resolution.

### Detection

- `gh pr merge` invoked with failing or pending checks.
- `git push --force` to a protected branch.
- Merge commit timestamp precedes last CI success timestamp.

### Enforcement Pattern

- Branch protection with required status checks on all default branches.
- Auto-merge only, with required checks. Never direct merge from agents.
- High-risk operations (merge, force-push, branch delete) routed through a consensus gate. See `CONSENSUS.md`.

See ADR-026 (PR automation concurrency and safety).

---

## 6. Multi-Agent Rubber-Stamping

### Description

Multiple specialist agents review the same change and all approve without independent verification. Unanimous approval signals confidence when it should signal suspicion.

### Trigger

Each reviewer defers to the others or restates the prompt rather than inspecting evidence. The orchestrator treats consensus as validation.

### Evidence

- `2025-12-24-parallel-pr-review-session.md`: Five reviewers approved a change that missed a security regression. No reviewer cited a code path.
- `2025-12-20-pr-211-security-miss.md`: Security and implementation both approved; the change introduced a suppression that neither flagged.

### Detection

- Review rationales share boilerplate and lack file or line citations.
- Unanimous approval on changes that touch security, data paths, or public APIs.
- No dissent recorded in `.agents/decisions/`.

### Enforcement Pattern

- Critic agent MUST cite at least one file and line per approval.
- Unanimous approval on security-sensitive domains triggers `independent-thinker` rerun.
- Record dissent in decision files. Absence of dissent on high-risk topics is itself a flag.

See `CONSENSUS.md` (Disagree and Commit Protocol) and `critic.md`.

---

## 7. Self-Contained Agent Delegation Failure

### Description

A delegated agent receives a task that depends on files or context the delegator did not pass through. The subagent fails silently or produces output that references the missing context.

### Trigger

Prompt to subagent says "based on the research, implement it" or relies on external references that the subagent cannot resolve.

### Evidence

- `2025-12-19-self-contained-agents.md`: Subagents failed when prompts referenced files outside the spawn-time working set.
- `2025-12-19-self-contained-agents-skills.md`: Skill bundles pulled external refs that did not travel with the skill.
- PR #1679 (2026-04-15): inlined external refs in orchestrator and analyst prompts to fix recurring delegation failures.

### Detection

- Subagent output contains phrases like "as noted above" without matching content in its prompt.
- Subagent reads files the delegator did not mention.
- Skill bundles reference paths outside the bundle manifest.

### Enforcement Pattern

- Each subagent prompt MUST be self-contained: file paths, line numbers, and the specific change to make.
- Skill bundles MUST pass manifest validation. No external refs in `src/`.
- Delegator never writes "based on your findings". Delegator states the finding and the required action.

See ADR-014 (distributed handoff architecture) and PR #1679.

---

## 8. Security Drift

### Description

Security review starts as "always-on" and drifts to opt-in over time. Suppressions accumulate. Advisory warnings get filtered out. A change that would have been caught at T0 passes at T+90.

### Trigger

Security instructions live in prose rather than in a blocking CI step. Suppressions have no expiry. Review scope shrinks when schedules compress.

### Evidence

- `2025-12-20-pr-211-security-miss.md`: Advisory security comment ignored. Change merged.
- `2026-01-04-pr760-security-suppression-failure.md`: Suppression added without a linked issue, survived six months.

### Detection

- Suppressions without a tracking issue, expiry date, or justification comment.
- Security agent invoked as optional in workflow definitions.
- Falling ratio of security findings per PR over time while codebase grows.

### Enforcement Pattern

- Security review is a required status check on all PRs that touch `scripts/`, workflows, or governance files. Not opt-in.
- Suppressions MUST carry an issue link and an expiry date. CI fails on expired suppressions.
- Periodic scan flags suppressions older than 90 days for retrospective review.

See `SECURITY-REVIEW-PROTOCOL.md`, `SECURITY-SEVERITY-CRITERIA.md`, and ADR-023 (quality gate prompt testing).

---

## Using This Document

### When to Read

- Before authoring or editing a protocol requirement. Each pattern above is a failure mode the new requirement MUST avoid.
- During retrospective analysis. Map the observed incident to one of the eight patterns before proposing remediation.
- During ADR review. A proposal that adds a trust-based requirement MUST explain why verification is not feasible.

### When to Update

- A ninth pattern emerges. Document it with the same shape: description, trigger, evidence, detection, enforcement.
- An existing pattern has new evidence. Append the retrospective to its evidence list.
- An enforcement pattern is obsoleted by a better mechanism. Update the table and reference the ADR that supersedes it.

### Related Documents

- `PROTOCOL-ANTIPATTERNS.md`: theoretical foundation (trust vs verification).
- `CONSENSUS.md`: algorithms invoked when patterns 5 and 6 apply.
- `SECURITY-REVIEW-PROTOCOL.md`: enforcement for pattern 8.
- `.agents/SESSION-PROTOCOL.md`: gates that prevent patterns 1 and 2.
- ADR-007, ADR-008, ADR-014, ADR-023, ADR-026: decisions that encode these enforcement patterns.
