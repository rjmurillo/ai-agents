# Retrospective: pr-4670-portability-recovery

## Session Info
- **Date**: 2026-08-05
- **Agents**: Copilot, security, QA, code review
- **Task Type**: Bug
- **Outcome**: Success

## Phase 0: Data Gathering
Observed: PR #4568 merged before its final reviewed commits reached GitHub.
Responded: restored the missing work, fixed new review findings, and opened PR
#4670. The execution trace is in the
`2026-08-04-session-9999-land-4568-post-merge-portability-hardening` session.
PR #4670 merged as `c96662c18f98462c381e500902bf0bebcbe7cd78`.

Glad: 154 focused tests and 23,457 pre-push tests passed. Every review thread
closed before merge. Mad: repeated review found filesystem races and Windows
junction handling late. Sad: one delegated PR triage lacked GitHub tools and
produced no PR evidence.

## Phase 1: Insights Generated
Five Whys for late filesystem findings:

1. Review found parent-swap and junction gaps after the first implementation.
2. The first implementation checked pathnames instead of pinned directories.
3. The design treated symlinks as the only redirect mechanism.
4. Windows junction behavior was not included in the original trust model.
5. The boundary was framed as a POSIX path check, not a filesystem redirect
   check.

Fishbone factors: pathname APIs, platform differences, bounded ancestor scans,
and reviewers seeing separate diff snapshots.

Pattern: the root-cause fix moved security into shared filesystem and Git
boundaries. Each caller then inherited the fix.

Learning matrix: keep shared boundaries and exact diff reviews. Drop delegated
GitHub triage when the agent lacks GitHub tools. Add direct index entries for
new retrieval memories.

### Failure Mode Classification

Primary classification: FM-5, Premature Merge and Deploy. PR
[#4568](https://github.com/rjmurillo/ai-agents/pull/4568) merged before its
final reviewed commits reached GitHub. PR
[#4670](https://github.com/rjmurillo/ai-agents/pull/4670) restored the reviewed
tree and completed the live merge gate.

Contributing classification: FM-7, Self-Contained Agent Delegation Failure. A
delegated PR triage lacked GitHub tools and returned no verifiable PR evidence.

### Remediation

| Action | Owner | Tracking |
|--------|-------|----------|
| Keep exact-tip review and live merge checks | PR author | PR #4670 |
| Add changed-file mypy to pre-PR feedback | Validation maintainers | Issue #4674 |
| Validate portability declarations, not marker counts | Portability maintainers | Issue #4116 |
| Normalize mixed session timestamp forms | Memory maintainers | Issue #4675 |
| Ignore plain memory prose in raw command scans | GitHub skill maintainers | Issue #4677 |

## Phase 2: Diagnosis

### Successes (Tag: helpful)
| Strategy | Evidence | Impact | Atomicity |
|----------|----------|--------|-----------|
| Shared security boundary | Descriptor-relative replacement fixed every baseline writer | 10 | 90% |
| Exact review artifact | Fifteen axes reviewed code SHA `15da5b785c6a` | 9 | 85% |
| Live completion gate | Clean merge state, passing checks, zero threads | 10 | 95% |

### Failures (Tag: harmful)
| Strategy | Error Type | Root Cause | Prevention | Atomicity |
|----------|------------|------------|------------|-----------|
| Pathname replacement | Race | Parent directory could change after validation | Pin and traverse directory descriptors | 90% |
| Symlink-only validation | Platform gap | Windows junctions also redirect paths | Check both redirect types | 90% |
| Delegated PR triage | Tool mismatch | Agent had no GitHub-capable tool | Verify tool access before delegation | 85% |

### Near Misses
| What Almost Failed | Recovery | Learning |
|--------------------|----------|----------|
| Windows junction bypass | Security review found it before push | Model redirect behavior, not one API |
| New memory stayed hard to retrieve | Copilot requested a direct root index row | Index new memories where keyword search starts |
| Review marker became non-tip | Separate review covered the one-line follow-up | Bind code review to SHA and disclose later edits |

## Phase 3: Decisions

### Action Classification
| Action | Decision |
|--------|----------|
| Keep | Shared Git and baseline security helpers |
| Drop | GitHub triage delegated without GitHub access |
| Add | Changed-file mypy to the documented pre-PR gate, tracked by #4674 |
| Modify | Reopened #4116 because aggregate marker counts do not validate claims |
| Fix | Mixed timezone session extraction crash, tracked by #4675 |

### SMART Validation
Issue #4674 names one command gap, current files, and four acceptance criteria.
Issue #4116 now includes current source and test evidence.

### Action Sequence
1. Merge the reviewed portability recovery.
2. Resolve and close every review thread.
3. Refresh the PR body with final evidence.
4. File or update process issues from verified evidence.

## Phase 4: Extracted Learnings

### Learning 1
- **Statement**: Treat every filesystem redirect mechanism as one trust boundary.
- **Atomicity Score**: 90%
- **Evidence**: PR #4670 rejected symlinks and Windows junctions across all ancestors.
- **Skill Operation**: TAG
- **Target Skill ID**: security-filesystem-boundaries

## Skillbook Updates

### ADD
```json
{
  "skill_id": "security-filesystem-boundaries",
  "statement": "Treat every filesystem redirect mechanism as one trust boundary.",
  "context": "Validate paths before secure filesystem mutation.",
  "evidence": "PR #4670",
  "atomicity": 90
}
```

### UPDATE

| Skill ID | Current | Proposed | Why |
|----------|---------|----------|-----|
| None | None | None | No existing skill text required a change |

### TAG

| Skill ID | Tag | Evidence | Impact |
|----------|-----|----------|--------|
| security-filesystem-boundaries | helpful | PR #4670 | Prevents path-redirection races |

### REMOVE

| Skill ID | Reason | Evidence |
|----------|--------|----------|
| None | None | None |

## Deduplication Check

| New Skill | Most Similar | Similarity | Decision |
|-----------|--------------|------------|----------|
| security-filesystem-boundaries | security-review | 55% | Keep as evidence tag, not new skill code |
