# Issue #5394 Serena cleanup disposition

Per-file disposition for the six memory families issue #5394 names, produced on
2026-09-22 against `main` at `f562b5df2`. Classes follow the placement contract
in `.claude/rules/knowledge-persistence.md`: a memory holds evidence, and a
rule, skill, or agent holds behavior.

Every `delete` and `thin` row names the artifact that now owns the behavior,
read directly. A row with no owner is `keep`.

## Scope

In scope: `agent-behavior/` (4), `agent-workflow/` (11), `autonomous/` (6),
`orchestration/` (14), `session/` (17), `protocol/` (11). Plus the top-level
index layer, `memory-index.md`, `README.md`, and repository references to the
paths this change deletes.

Out of scope, recorded under "Findings handed on": the remaining
placement-flagged memories outside these families, validator changes owned by
#4313, #4776, and #4705, capability metadata (#5396), structural ratchets
(#5397), and a measurement authority (#5400).

## agent-behavior, agent-workflow, autonomous (21 files)

Issue #5392 and #5393 already reduced these to evidence. Twenty of the 21 carry
the `placement: evidence` marker and a named owner. No file needed further
thinning.

| Memory path | Disposition | Owner artifact |
|---|---|---|
| `agent-behavior/error-recovery-obligations.md` | keep | `.claude/rules/universal.md` "Recovery and truthfulness" |
| `agent-behavior/retrospective-accuracy.md` | keep | `.claude/rules/universal.md` "Evidence and retrospective claims" |
| `agent-behavior/self-blame-still-needs-evidence.md` | keep | `.claude/rules/universal.md` "Evidence and retrospective claims" |
| `agent-behavior/stuck-subagent-and-worktree-recovery.md` | keep | `.claude/rules/universal.md` MUST NOT 6 |
| `agent-workflow/agentskills-io-standard-integration.md` | keep | external standard reference; cited as a source by `.agents/architecture/SKILL-STANDARDS-RECONCILED.md` |
| `agent-workflow/agentworkflow-005-structured-handoff-formats-88.md` | keep | `.claude/agents/orchestrator.md` "Handoff Contract" |
| `agent-workflow/agent-workflow-atomic-commits.md` | keep | `.claude/rules/universal.md` SHOULD-5 |
| `agent-workflow/agent-workflow-collaboration.md` | keep | `.claude/skills/reflect/SKILL.md` |
| `agent-workflow/agent-workflow-critic-gate.md` | keep | `.claude/skills/plan/SKILL.md` step 7; `.claude/agents/critic.md` Review Axes |
| `agent-workflow/agent-workflow-mvp-shipping.md` | keep | `.claude/rules/builder-ethos.md` "Boil the Lake" |
| `agent-workflow/agent-workflow-observations.md` | keep | `AGENTS.md` Routing |
| `agent-workflow/agent-workflow-pipeline.md` | keep | `.claude/skills/autoplan/SKILL.md` tier table |
| `agent-workflow/agent-workflow-post-implementation-critic-validation.md` | keep | `.claude/skills/build/SKILL.md` exit gates |
| `agent-workflow/agent-workflow-scope-discipline.md` | keep | `.claude/rules/universal.md` "Autonomous execution boundaries" |
| `agent-workflow/fleet-worktree-live-versus-abandoned.md` | keep | `.claude/skills/git-advanced-workflows/references/worktree-triage.md` |
| `autonomous/autonomous-circuit-breaker.md` | keep | `.claude/rules/universal.md` three-attempt limit |
| `autonomous/autonomous-circuit-breaker-pattern.md` | keep | `.claude/rules/universal.md` three-attempt limit |
| `autonomous/autonomous-execution-failures-pr760.md` | keep | `.claude/rules/universal.md` "Autonomous execution boundaries" |
| `autonomous/autonomous-execution-guardrails.md` | keep | `.claude/rules/universal.md`; consumed by `src/claude/skills/review/references/agent-safety.md` |
| `autonomous/autonomous-patch-signal.md` | keep | `.claude/rules/universal.md` user-supplied patch signal |
| `autonomous/autonomous-trust-metric.md` | keep | no owner; the file disclaims defining the metric and defers to #5400 and #5405 |

### One upstream classification re-checked and upheld

The auditor proposed deleting `agent-workflow/agentskills-io-standard-integration.md`
on the grounds that `SKILL-STANDARDS-RECONCILED.md` resolved its open questions.
Rejected. `SKILL-STANDARDS-RECONCILED.md` cites that memory as one of its own
sources, so the architecture document depends on it rather than replacing it.
The #5393 inventory classified the file "unchanged" and nothing contradicts
that. Its two stale path citations in `SKILL-STANDARDS-RECONCILED.md` were
repointed instead, because both named a top-level path for a file that lives in
a subdirectory.

## orchestration, session, protocol (42 files)

One memory was replaced rather than deleted:
`session/session-init-pattern.md` described the removed session-init skill, but
its third section held a dated collision incident and a live field trap in
`scripts/validate_session_json.py`. That content now lives at
`session/session-number-collision-and-episode-rename.md`, whose title matches
what it holds.

Anchor evidence: commit `ba541c21f` (PR #5179) removed the `session`,
`session-init`, `session-end`, and `session-log-fixer` skills and the session
protocol. `.agents/SESSION-PROTOCOL.md`, `.agents/HANDOFF.md`, and
`scripts/Validate-SessionEnd.ps1` are absent from the tree, and
`.claude/rules/session-logs.md` states that session log creation is
discontinued. A memory whose whole content is a procedure against those
artifacts describes a mechanism that no longer exists.

### Deleted (17)

| Memory path | Why | Owner or successor |
|---|---|---|
| `orchestration/orchestration-001-parallel-execution-time-savings.md` | duplicate | `orchestration/orchestration-parallel-execution.md` keeps the same Sessions 19-21 measurement |
| `orchestration/orchestration-validation-gate.md` | duplicate | `orchestration/orchestration-003-handoff-validation-gate.md` keeps the 24-session measurement |
| `session/changelog-session-log-fixer.md` | version history of a deleted skill | `ba541c21f` |
| `session/logging-002-session-log-early.md` | creates a session log | `.claude/rules/session-logs.md` |
| `session/session-capture-protocol.md` | duplicated verbatim | `templates/agents/orchestrator.shared.md` "Session Capture Protocol" |
| `session/session-init-003-branch-declaration.md` | session-log header template | `.claude/rules/session-logs.md`; flagged stale by the #5393 inventory |
| `session/session-init-constraints.md` | proposal already built | `.agents/governance/PROJECT-CONSTRAINTS.md` |
| `session/session-init-pattern.md` | describes a removed skill; its 2026-08-05 collision evidence moved, not lost | replaced by `session/session-number-collision-and-episode-rename.md` |
| `session/session-init-skill-validation.md` | duplicate policy | `.agents/governance/PROJECT-CONSTRAINTS.md` Skill Usage Constraints; its Session 15 count folded into `protocol/protocol-001-verificationbased-gates.md` |
| `session/session-init-verification-gates.md` | duplicate | `protocol/protocol-001-verificationbased-gates.md` holds the same measurements |
| `session/session-scope-002-multi-issue-limit.md` | duplicate | `session/session-scope-002-limit-sessions-two-issues.md` |
| `session/session-validation-reconciliation.md` | describes a removed validator | `ba541c21f` |
| `protocol/protocol-002-verification-based-gate-effectiveness.md` | duplicate | `protocol/protocol-001-verificationbased-gates.md` |
| `protocol/protocol-005-template-enforcement.md` | session-log template | `.claude/rules/session-logs.md` |
| `protocol/protocol-012-branch-handoffs.md` | workaround for a removed validator | `.agents/architecture/ADR-014-distributed-handoff-architecture.md` |
| `protocol/protocol-013-verification-based-enforcement.md` | duplicate | `protocol/protocol-014-trust-antipattern.md` keeps the PR #669 counts |
| `protocol/protocol-continuation-session-gap.md` | proposals for a retired protocol | `.agents/retrospective/2026-01-09-session-protocol-violation-analysis.md` holds the incident |
| `protocol/protocol-legacy-sessions.md` | duplicate | `protocol/protocol-006` content, both retired |

### Thinned (14 in these families; 15 counting `user-preferences/user-facing-content-restrictions.md`, which sits outside the six)

Each keeps its dated observation or measurement and drops the procedure that a
first-class artifact now owns.

| Memory path | Kept | Dropped | Owner |
|---|---|---|---|
| `orchestration/coordination-001-branch-isolation-gate.md` | Sessions 40-41 shared-branch incident, 30-minute detection delay | 5-gate sequence, sign-off templates | `.claude/agents/orchestrator.md` worktree-per-agent |
| `orchestration/orchestration-003-handoff-validation-gate.md` | 23 of 24 agents, 79% versus 4% compliance | validator command, rejection template | `.claude/agents/orchestrator.md` Handoff Contract |
| `orchestration/orchestration-003-orchestrator-first-routing.md` | Session 04 wrong-fix observation | routing decision tree and tables | `.claude/skills/autoplan/SKILL.md`, orchestrator Routing Algorithm |
| `orchestration/orchestration-parallel-execution.md` | Sessions 19-21, 50 to 20 minutes, 10 to 20% overhead | HANDOFF aggregation step | `.claude/agents/orchestrator.md` Routing Algorithm |
| `orchestration/orchestration-scope-002-minimal-viable-fix.md` | PR #395, 847 lines against an expected 50 | rules list, checkpoint template | `.claude/rules/builder-ethos.md` Task Completion Contract |
| `protocol/protocol-001-verificationbased-gates.md` | Session 15 and 19-21 compliance table, 42% clean-outcome rate | Phase 1.5 roadmap, force-field analysis | `lefthook.yml`, `.claude/rules/push-lock.md` |
| `protocol/protocol-014-trust-antipattern.md` | three failures with counts, including HANDOFF.md at 35 KB and 80% conflicts | fix procedure | `lefthook.yml`, ADR-014 |
| `protocol/protocol-blocking-gates.md` | Session 92 ADR-review reuse | session-protocol gate template | `.claude/skills/adr-review/SKILL.md` |
| `protocol/protocol-rfc-evidence.md` | PR #147 unbacked compliance claim | session-log evidence format | `.claude/rules/voice.md` "Clear The Gate Or Drop The Claim" |
| `session/session-observations.md` | the one LOW-confidence note | empty Constraints, Preferences, Edge Cases headings | n/a |
| `session/session-protocol-observations.md` | PR #908: 228+ comments, 59 commits, 53 files reformatted | the compaction and HANDOFF re-init bullet | `scripts/validation/pr_commit_count.py` |
| `session/session-scope-002-limit-sessions-two-issues.md` | PR #669 co-mingling incident | PowerShell scope gate, session-log template | none; the incident is kept as judgment material |
| `orchestration/coordination-002-handoff-conflict-risk.md` | PR #206, 4 conflicts over 3 days, Sessions 55-61 divergence | defensive merge procedure | ADR-014, which carries only the repository-wide rate |
| `protocol/protocol-006-legacy-session-grandfathering.md` | PR #53, an artifact blocked by a gate that postdated it | LEGACY marker format | none; the failure shape recurs with any retroactive gate |

### Kept unchanged (10)

`orchestration/orchestration-copilot-swe-anti-patterns.md`,
`orchestration/orchestration-observations.md`,
`orchestration/orchestration-pr-chain.md`,
`orchestration/orchestration-process-workflow-gaps.md`,
`orchestration/orchestration-prompt-002-copilot-swe-constraints.md`,
`orchestration/orchestration-recursive-learning-extraction.md`,
`session/init-003-memory-first-monitoring-gate.md`,
`session/recovery-001-lost-code-investigation.md`,
`session/session-protocol-validator-pipe-bug.md`,
`session/session-writing-todo-in-evidence-trips-the-contradiction-scanner.md`.

No first-class artifact was found that carries their content. The last one
documents a gotcha in `scripts/validate_session_json.py`, which is still live.

## Navigation layer

### The listing premise was false

`.serena/memories/README.md` stated that subdirectory memories are hidden from
`list_memories`, and `memory/serena-memory-subdirectory-convention.md` credited
the subdirectory layout with saving about 4,700 tokens per session.

Measured on 2026-09-22 against this tree: one `list_memories` call returned
every name, nested included, at 11,629 tiktoken `cl100k_base` tokens. The
top-level names alone would be 1,232. Both files now state the observed
behavior and mark the 2026-02 figure as historical.

The index layer is kept because it still routes keywords. It is not kept for a
listing saving it does not produce.

### Index changes

| Index | Change |
|---|---|
| `skills-session-init-index.md` | 5 rows removed for deleted files, 1 row added for the retained scope memory |
| `skills-protocol-index.md` | 4 rows removed, 1 row added for `protocol-001` |
| `skills-orchestration-index.md` | 1 row removed, 2 rows added for retained thinned files |
| `memory-index.md` | 1 route removed; the `[User Constraints (MUST READ)]` section retired |

No index lost all of its rows, so none was removed. Removing an index whose
targets survive would make those files unreachable from `memory-index.md` and
would raise the orphan count.

`memory-index.md` previously carried a `[User Constraints (MUST READ)]` section
that presented policy as a Serena capability. One row already deferred to
`.claude/rules/universal.md` and added nothing; it is gone. The other now sits
under `[Governance Evidence]` and points at a memory thinned to the PR #212
incident, with `.claude/rules/claude-agents.md` MUST-5 named as the owner.

### Dead links

621 relative markdown links inside memory bodies pointed at files that did not
exist at the stated path. The 2026-02 restructure moved memories into
subdirectories without updating in-body links, and the `## Related` lists
accumulated duplicates.

| Action | Count |
|---|---:|
| Repointed to the correct relative path | 316 |
| Dangling or duplicate `## Related` bullets removed | 277 |
| Degraded to a code span, target gone from the tree | 16 |
| Wrong-depth path corrected | 2 |

Remaining: 2, both inside fenced code blocks in `README.md` that illustrate the
index row format. Dead links outside code fences: 0.

## Repository sweep

Every deleted basename was searched across `*.md`, `*.py`, `*.yml`, `*.yaml`,
and `*.json`. Live consumers updated:

- `.agents/architecture/SKILL-STANDARDS-RECONCILED.md`: two memory paths
  repointed to their subdirectories.
- `.serena/memories/git/git-hooks-004-branch-name-validation.md` and
  `git/git-004-branch-verification-before-commit.md`: references repointed to
  `protocol-014-trust-antipattern`.
- `.serena/memories/governance/debate-002-everything-deterministic-evaluation.md`:
  the skill-bypass citation repointed to `protocol-001`, which now carries the
  count it cited.
- `.serena/memories/adr/adr-retroactive-amendment-criteria.md` and
  `retrospective/retrospective-artifact-efficiency-pattern.md`: wiki links
  repointed to `protocol-014-trust-antipattern`.
- `.serena/memories/memory/curation-2026-06-10-dedupe-audit.md` and
  `session/session-writing-todo-in-evidence-trips-the-contradiction-scanner.md`:
  references to deleted files stated as history rather than as links.

`.agents/specs/agent-orchestration-mcp-spec.md` carried a link to a memory path
that never resolved, even before this change; it now points at the surviving
memory. Two ADRs carry the same class of dangling link
(`ADR-011-session-state-mcp.md`, `ADR-013-agent-orchestration-mcp.md`). Editing
either one arms the debate-log gate, which exists for decision changes, not
link repairs, so both are recorded under "Findings handed on" instead.

The search covers every tracked file with no extension filter.

Left unchanged: `.agents/sessions/`, `.agents/qa/`, `.agents/critique/`,
`.agents/retrospective/`, `.agents/archive/`, `.agents/memory/episodes/`, and
`.claude-mem/` backups. Those
record what was true at the time, which the issue says not to rewrite.
`.agents/analysis/5393-serena-workflow-inventory.md` also stands as the upstream
record; this file supersedes its downstream rows rather than editing them.

## Findings handed on

Not acted on here. Each needs its own decision.

1. **368 placement-flagged memories tree-wide.** The full scan reports 160
   normative and 186 suspect after this change, against 181 and 187 before.
   Thinning the remainder spans sessions.
2. **87 top-level non-index memories.** `README.md` says the top level holds
   indexes and special files only. The tree holds 87 other files there.
   Relocating them would churn many paths.
3. **Near-duplicate families outside the six audited.** `pr-review/` carries
   parallel `pr-NNN-*` and `pr-review-NNN-*` series with the same lessons.
4. **Generic tutorial content.** The `jq/` family, 18 files, reproduces
   documentation that is re-derivable in under a minute.
5. **Untracked leftovers.** `.claude/skills/session-end/` and
   `.claude/skills/session-init/` hold only untracked `__pycache__`
   directories, left behind by `ba541c21f`.
6. **Two ADRs with dangling memory links.**
   `.agents/architecture/ADR-011-session-state-mcp.md` and
   `ADR-013-agent-orchestration-mcp.md` link to `.serena/memories/skill-*.md`
   paths that have never existed. Both predate this change. Repairing them
   requires a debate log, which a link fix does not warrant on its own.
7. **The four extraction candidates** the #5393 inventory names
   (`bash-integration` exit contract, `coderabbit` configuration,
   `design` authoring norms, `gemini` configuration) still have no owner.
