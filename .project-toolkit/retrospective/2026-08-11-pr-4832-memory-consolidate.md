# Retrospective: PR 4832 Memory Consolidation

## Session Info

- **Date**: 2026-08-11
- **Task Type**: Feature and review remediation
- **Outcome**: Ready for push after local gates

## Phase 0: Data Gathering

The session resumed after an out-of-memory crash. The branch already contained
the skill, tests, and review evidence. Four unresolved review threads remained.
Later review exposed unsafe deletion authority, unbounded discovery, stale QA
evidence, shell path interpolation, and symlink races in `search_memory.py`.

Measured results:

- 50 of 50 pre-PR checks passed before the first push.
- 25,497 tests ran during pre-push. One ceiling-ratchet test failed.
- Serena contained 1,002 Markdown files and 2,951,803 bytes.
- Final focused search and contract suites passed.

## Phase 1: Insights Generated

### Five Whys: Repeated QA Evidence Churn

1. QA evidence became stale because code changed after each evidence commit.
2. Code changed because each review round found another safety boundary.
3. Review continued after session-end artifacts were treated as final.
4. The workflow bound evidence before adversarial review converged.
5. No gate prevented session evidence from being refreshed too early.

Root cause: evidence binding ran before the last code-producing review loop.

### Fishbone: Push Delay

| Factor | Evidence |
|--------|----------|
| Process | QA and session commits repeated after every fix |
| Safety | Reused search code had path escape and file-swap gaps |
| Scope | Test-placement policy work shared the feature branch |
| Governance | Retrospective and instruction ceilings blocked push late |
| Review | Several agents consumed stale `pr_body.md` data |

## Phase 2: Diagnosis

### Successes

| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Verify review claims before fixing | False overlap and stale-head claims were separated from real defects | Prevented wrong fixes | 80% |
| Use adversarial path tests | Symlink escape and swap tests reproduced leakage | Closed data exposure | 85% |

### Failures

| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Refresh QA after each fix | Process churn | Evidence ran before review convergence | Bind QA after final code review | 65% |
| Trust reused search helper | Security boundary | Helper followed mutable symlink paths | Test reused I/O helpers at the trust boundary | 70% |

### Near Misses

| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Soft reset exposed unrelated merged-main changes | Local backup branch and soft restore recovered the worktree | Compare the remote branch delta before rewriting unpublished history |
| Quoted shell placeholders remained injectable | Replaced command strings with shell-free argument lists | Quoting is not an argv boundary |

## Phase 3: Decisions

| Action | Decision |
|--------|----------|
| Keep | Reviewer-finding verification before edits |
| Drop | Early QA and session evidence refreshes |
| Add | Symlink escape and file-swap tests for memory search |
| Modify | Run adversarial review before session-end evidence |

No new repository rule is justified. Existing review, security, and session
skills already own these controls.

## Phase 4: Extracted Learnings

### Learning 1

- **Statement**: A filesystem search must read the same contained file identity
  it validated, or a symlink swap can expose content outside the root.
- **Atomicity Score**: 85%
- **Evidence**: `search_memory.py` containment tests and commits
  `412ea861f1`, `b5f78fb83f`, and `cfe586aed5`.
- **Skill Operation**: No skillbook change. The code and tests carry the rule.

### Learning 2

- **Statement**: Bind QA evidence only after the final code-producing review
  loop passes.
- **Atomicity Score**: 65%
- **Evidence**: Repeated QA and session evidence commits in this branch.
- **Skill Operation**: Rejected for persistence. Existing session validation
  already detects stale evidence.

## Skillbook Updates

No skillbook update. Learning 1 is enforced by code and tests. Learning 2 did
not reach the 70% persistence threshold.

## Deduplication Check

No new memory was written. Existing security and session skills cover both
topics.

## Closing

- **Plus**: Adversarial review found defects that phrase tests missed.
- **Delta**: Evidence binding occurred too early and repeated.
- **ROTI**: 3 of 5. Safety improved, but review and evidence churn dominated.
- **Helped**: Deterministic tests, Git history, reviewer claim verification.
- **Hindered**: Stale PR artifacts, branch commit volume, late push-only gates.
- **Hypothesis**: Moving session evidence after final review will remove most
  repeated artifact commits.
