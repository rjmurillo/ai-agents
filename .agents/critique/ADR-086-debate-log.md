# ADR-086 Review Debate Log: Lefthook for Local Git Hook Orchestration

**Artifact**: `.agents/architecture/ADR-086-lefthook-local-hook-orchestration.md`
(Accepted 2026-07-20)
**Protocol**: ADR Review Protocol, six-role debate
**Date**: 2026-07-20
**Trigger**: PR #3259 and the repository owner's goal to migrate local Git hook
orchestration to Lefthook.
**Scope**: The migration remained one coherent ADR because installation,
scheduling, staging, timeouts, confirmation, and rollback form one local-hook
contract.

## Decision under review

Use Lefthook 2.1.10 as the only local Git hook orchestrator. Keep
repository-specific policy in Python. Remove the custom `.githooks/` and tracked
`scripts/hooks/` framework roots. Keep CI as the authoritative backstop.

## Final votes

| Role | Vote | Core position |
|------|------|---------------|
| Architect | Approve | The ADR defines framework boundaries, version ownership, confirmation, rollback, and review triggers. |
| Critic | Approve | All blocking findings were resolved through documented configuration, staging policy, and acceptance tests. |
| Independent Thinker | Approve | One ADR fits the coupled migration, and the alternatives and trade-offs support the decision. |
| Security | Approve | No Critical or High finding remains. Local hooks are not a security boundary, and CI remains authoritative. |
| Analyst | Approve | Repository evidence supports the dependency pins, removals, scheduler behavior, timeout limits, and test result. |
| High-Level Advisor | Approve | The migration removes repository-owned orchestration while retaining policy checks and rollback criteria. |

**Consensus: 6/6 Approve. Zero blocking findings.**

The post-acceptance active-index clarification also reached 6/6 Accept after
the proposed custom rejection gate was removed.

## Evidence verified

- Lefthook 2.1.10 is pinned in both `pyproject.toml` development dependency
  tables and frozen in `uv.lock`.
- The configured frozen uv command has generated-shim precedence:
  `lefthook: uv run --frozen lefthook`.
- PR #3259 removes `.githooks/` and tracked `scripts/hooks/` content.
- Lefthook provides native scheduling, filters, ordering, standard input
  forwarding, skip conditions, `stage_fixed`, and outer job timeouts.
- Python gives each child process a shorter timeout. Lefthook bounds the whole
  job with an outer timeout.
- Lefthook owns same-file formatter staging through `stage_fixed`. Python owns
  allowlisted generated-output staging.
- Generated staging covers allowlisted additions, modifications, and tracked
  deletions.
- Acceptance requires primary-clone installation confirmation and clean-tree
  checks. The rollback restores both removed framework roots as one change.
- Protected CI remains the enforcement backstop.
- Lefthook native filters and `{staged_files}` use Git's active index, including
  temporary and explicit alternate indexes.
- The full integration suite completed with 275 passed.

## Debate rounds and resolutions

### Initial review

All roles supported the decision direction. They requested clearer decision
drivers, exact framework roots, pin ownership, uv rationale, timeout hierarchy,
confirmation, rollback, review triggers, bypass wording, accurate impact
entries, and child-tool supply-chain disclosure.

The ADR revisions addressed each request without splitting the decision.

### PATH precedence block

The Critic blocked because a generic `PATH` binary could replace the intended
runtime. The resolution added top-level
`lefthook: uv run --frozen lefthook` configuration. Generated-shim precedence
tests verify that this configured command runs before generic `PATH` lookup.

### Confirmation and impact block

The Critic blocked on stale Semgrep timing, mutation-blind confirmation, and
false ADR-062 relocation wording. Documentation and acceptance commands now
state current timing, require clean-tree checks around validation, and describe
ADR-062 as a wording update without an LSP hook relocation.

### Staging ownership block

The Critic blocked because generated-output staging ownership was unclear. The
resolution separates Lefthook native `stage_fixed` from Python allowlisted
generated-output `git add`. The ADR also documents per-child timeout limits and
their outer job boundaries.

### Generated-output deletion block

The Critic blocked because staging covered generated additions and
modifications but did not prove deletion handling. The resolution added safe
discovery and staging for allowlisted tracked deletions.

Tests cover explicit, simple-glob, recursive-root, recursive-nested, and
unrelated-deletion cases.

### Final round

All six roles approved the revised ADR. No blocking finding remained.

### Post-acceptance active-index clarification

A final review warning claimed Lefthook filters inspected only the default index
and proposed rejecting `GIT_INDEX_FILE`. The six-role delta review found that
the rejection would block normal Git hooks because Git exports the active index
path to pre-commit hooks.

Empirical probes then showed Lefthook 2.1.10 selects staged files from the active
index for ordinary, `-a`, partial, and explicit alternate-index commits. The
custom guard was removed. A regression test now proves both directions: a file
staged only in the default index is excluded when an alternate index is active,
while a file staged only in the alternate index is selected and committed
through the installed hook. The default index retains its own blobs.

| Role | Delta vote |
|------|------------|
| Architect | Accept |
| Critic | Accept |
| Independent Thinker | Accept |
| Security | Accept |
| Analyst | Accept |
| High-Level Advisor | Accept |

**Delta consensus: 6/6 Accept. Zero blocking findings.**

### Post-acceptance rollback clarification

The rollback amendment originally required reverting PR #3259 as one atomic
change and prohibited hand reconstruction of the deleted framework roots.
Phase 1 agreed on the safety principle but found the Git operation and trigger
criteria too narrow for future history.

Initial positions were:

| Role | Position |
|------|----------|
| Architect | Accept |
| Critic | Block |
| Independent Thinker | Disagree-and-Commit |
| Security | Accept |
| Analyst | Disagree-and-Commit |
| High-Level Advisor | Disagree-and-Commit |

The high-level-advisor ruled that the findings were P1 documentation defects,
not P0 failures in the live hook system. The accepted resolution:

- Covers installation, execution, routing, fail-open non-execution, standard
  input, staging, filtering, active-index behavior, and failure propagation.
- Requires one forward-fix PR to preserve Lefthook as the sole hook owner and
  pass ADR acceptance before contributors continue.
- Names the landed merge, squash, or exact landed commit set as the Git revert
  unit.
- Requires one coherent pre-PR-3259 hook-owner state when later history prevents
  a clean revert.
- Requires proof that no mixed hook assets remain active, restored bootstrap and
  validation succeed, a hook failure propagates, and tracked state starts and
  ends clean.
- Prohibits partial rollback and hand reconstruction of deleted framework paths.

Round 2 positions:

| Role | Delta vote |
|------|------------|
| Architect | Accept |
| Critic | Accept |
| Independent Thinker | Accept |
| Security | Accept |
| Analyst | Accept |
| High-Level Advisor | Accept |

**Rollback delta consensus: 6/6 Accept. Zero blocking findings.**

## Security disposition

No Critical or High finding remained. Local bypasses are not a security
boundary, and protected CI remains authoritative.

The unpinned `markdownlint-cli2` child tool is an inherited supply-chain risk.
Issue #3279 tracks it separately. Residual TOCTOU and local-override concerns
do not create privilege escalation.

## Unresolved dissent and non-blocking observations

No unresolved dissent remained.

- An empty untracked `scripts/hooks/` directory may exist locally. It is not
  repository state.
- Issue #3279 remains separate from this scheduler migration.
- Per-child timeout diagnostics are not guaranteed when the outer whole-job
  timeout fires first.

## Outcome

ADR-086 was accepted on 2026-07-20. It supersedes ADR-004. PR #3259 includes
the implementation and the active-index regression evidence.
