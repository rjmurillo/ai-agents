# Skill-Verification-003: Verify Artifact-API State Match

**Statement**: Verify artifact state matches API state using diff before phase transitions

**Context**: Before resolving threads (Phase 8 gate)

**Trigger**: Before any phase completion that involves external state

**Action**: Compare artifact counts with API counts; block if mismatch

**Evidence**: Verification step logged with counts matching

**Anti-pattern**: Resolving threads while artifacts show items as pending

**Atomicity**: 92%

**Tag**: critical

**Impact**: 9/10

**Created**: 2025-12-20

**Validated**: 1 (PR #147 - Thread resolved via API but tasks.md showed [ ] pending)

**Category**: Verification

**Source**: PR #147 retrospective analysis (2025-12-20-pr-147-comment-2637248710-failure.md)

## Verification Pattern

```bash
# Before resolving threads (Phase 8)

# 1. Count completed tasks in artifact
ARTIFACT_COMPLETE=$(grep -c "^\\- \\[x\\]" .agents/planning/tasks.md)

# 2. Count resolved threads via API
API_RESOLVED=$(gh api graphql -f query='
query($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviewThreads(first: 100) {
        nodes { isResolved }
      }
    }
  }
}' -f owner=OWNER -f repo=REPO -F number=PR | jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved)] | length')

# 3. Block if mismatch
if [ "$ARTIFACT_COMPLETE" -ne "$API_RESOLVED" ]; then
  echo "BLOCKED: Artifact shows $ARTIFACT_COMPLETE complete, API shows $API_RESOLVED resolved"
  exit 1
fi
```

## Evidence Logging

Session log must show:

```markdown
## Phase 8: Verification

- [x] Artifact count: 29 tasks complete
- [x] API count: 29 threads resolved
- [x] Counts match: PASS
```

## Related Skills

- Skill-Tracking-001: Update artifact status atomically with fix application
- Skill-Protocol-004: RFC 2119 MUST requirements with verification evidence
- Skill-PR-Comment-003: API Verification Before Phase Completion
