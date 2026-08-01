# Skill-PR-Review-007: CI Verification Before Completion

## Statement

Before claiming PR review complete, verify ALL CI checks pass via `gh pr checks`; `mergeable: MERGEABLE` only indicates no conflicts, not CI status.

## Context

When completing PR review response (Phase 8 verification). The `mergeable` field from `gh pr view --json mergeable` only checks:
- No merge conflicts
- Branch is compatible with base

It does NOT indicate:
- CI checks passing
- Required status checks satisfied

## Evidence

**Run 20487393463 (Session 56)**: Agent claimed PR #199 was "MERGEABLE" based on `gh pr view --json mergeable` returning `"MERGEABLE"`, but failed to verify CI checks. The run failed with `MUST: HANDOFF.md Updated: FAIL` but agent claimed completion without checking CI.

**Root Cause**: Agent verified:
1. ✅ Resolved all 11 review threads via GraphQL mutations
2. ✅ Verified 0 unresolved threads via GraphQL query
3. ✅ Ran `gh pr view 199 --json state,mergeable,reviewDecision` → `{"mergeable":"MERGEABLE",...}`

But MISSED:
- ❌ Did NOT run `gh pr checks 199` to verify CI status

## Atomicity

**Score**: 96%

**Deductions**: None - single concept, measurable, actionable, has metrics

## Impact

**Score**: 10/10 (CRITICAL)

**Rationale**: Claiming PR is ready to merge when CI checks are failing wastes reviewer time and can introduce broken code to main branch.

## Pattern

### INCORRECT: Relying on `mergeable` field alone

```bash
# Agent checks mergeable status
gh pr view 199 --json state,mergeable,reviewDecision
# Returns: {"mergeable":"MERGEABLE","state":"OPEN","reviewDecision":"APPROVED"}

# Agent concludes: PR is ready to merge ❌ WRONG
```

**Problem**: `mergeable: "MERGEABLE"` only means no conflicts, not that CI passes.

### CORRECT: Verify CI checks explicitly

```bash
# After all other verification, BEFORE claiming completion
# Use mktemp to avoid race conditions with concurrent agents
checks_file=$(mktemp)
trap 'rm -f "$checks_file"' EXIT

gh pr checks 199 --json name,bucket,link > "$checks_file"

# Parse results. `bucket` is gh's normalized category: pass, fail, pending,
# skipping, cancel. Prefer it over `state`, which reports NEUTRAL separately
# even though gh already buckets NEUTRAL as skipping.
failed_checks=$(jq '[.[] | select(.bucket != "pass" and .bucket != "skipping")]' "$checks_file")

if [ "$(echo "$failed_checks" | jq 'length')" -gt 0 ]; then
  echo "[BLOCKED] CI checks not passing:"
  echo "$failed_checks" | jq -r '.[].name'
  # Do NOT claim completion
  exit 1
fi
```

## Verification Checklist

Before claiming PR review complete, ALL must be true:

| Criterion | Verification Command | Required |
|-----------|---------------------|----------|
| All comments resolved | count of resolved markers equals total, see command below | Yes |
| No new comments | Re-check after 45s wait returned 0 new | Yes |
| **CI checks pass** | **`gh pr checks` all success/skipped** | **Yes** |
| No unresolved threads | GraphQL query for unresolved reviewThreads | Yes |
| Commits pushed | `git status` shows "up to date with origin" | Yes |

The resolved-marker count uses a GNU basic regular expression, where `\|` is
alternation. That spelling is a GNU extension, not portable POSIX BRE.
`man 7 regex` says of obsolete ("basic") REs: "'|', '+', and '?' are ordinary
characters and there is no equivalent for their functionality." Measured here
on GNU grep 3.11.

It is shown outside the table because a table cell would need `\\|`, and
whether that still matches depends on two things, not one.

First, the bytes grep receives. One backslash is alternation and matches, two
is an escaped backslash followed by a literal pipe and matches nothing. Each
layer between the author and grep's argv either collapses the pair or
preserves it. Measured against a two-line fixture holding both markers, using
the table form of the pattern:

- bash inline double quotes: collapses, reports 2
- bash single quotes: preserves, reports 0
- bash double-quoted variable expansion: preserves, reports 0
- bash ANSI-C quoting, `$'...'`: collapses, reports 2
- Python non-raw string literal: collapses, reports 2
- Python raw string literal: preserves, reports 0
- `xargs` default mode: treats backslash as an escape, which mangles the pattern
  without flattening it. `\[` and `\]` lose their shields and become bracket
  expressions, while `\\` collapses to a single `\`, so the GNU BRE `\|`
  alternation survives. grep receives `Status: [COMPLETE]\|[WONTFIX]` and reports
  2, but the hits are single characters drawn from the class `[WONTFIX]`, not the
  literal markers: the right answer for the wrong reason. Do not restate this as
  "strips every backslash"; a full strip yields `Status: [COMPLETE]|[WONTFIX]`,
  whose bare pipe is literal in BRE and reports 0. `xargs -d '\n'` preserves,
  reports 0.

Second, the dialect flag. Argv bytes are necessary but not sufficient, because
`-E` inverts the escaping. Against the same fixture: `grep` with one backslash
reports 2; `grep -E` with one backslash reports 0, because that is a literal
pipe in ERE; `grep -E` with a bare pipe reports 2; `grep -E` with the table
form reports 1, reading it as a literal backslash alternated with the second
marker. A reader who copies the pattern and adds `-E` gets a silent zero, so
any claim about this pattern has to name both the dialect and the
implementation.

So neither "double quotes work" nor "no shell means it breaks" holds on its
own. Fencing the command removes the ambiguity.

```bash
grep -c "Status: \[COMPLETE\]\|\[WONTFIX\]" review-threads.md
```

## Implementation

### In pr-comment-responder Phase 8.4

Add after Phase 8.3 (re-check for new comments), before Phase 8.5 (completion criteria checklist):

```bash
#### Phase 8.4: CI Check Verification

**MANDATORY**: Verify CI checks pass before claiming completion.

\```bash
# Check PR CI status
echo "=== CI Check Verification ==="

# Create a secure temporary file (avoids race conditions with concurrent agents)
checks_file=$(mktemp)
trap 'rm -f "$checks_file"' EXIT

# Fetch all fields in one call, reuse for both waiting and verification
gh pr checks [number] --json name,bucket,link > "$checks_file"

# Parse for failures. `bucket` is gh's normalized category.
failed_checks=$(jq '[.[] | select(.bucket != "pass" and .bucket != "skipping")]' "$checks_file")
failed_count=$(echo "$failed_checks" | jq 'length')

if [ "$failed_count" -gt 0 ]; then
  echo "[BLOCKED] $failed_count CI checks not passing:"
  echo "$failed_checks" | jq -r '.[] | "  - \(.name): \(.bucket)"'

  # Parse actionable items from failures
  echo ""
  echo "Actionable items:"
  echo "$failed_checks" | jq -r '.[] | "  - \(.name): Review logs at \(.link | select(length > 0) // "N/A")"'

  # Return to Phase 6 for fixes
  exit 1
fi

echo "[PASS] All CI checks passing ($(jq 'length' "$checks_file") checks)"
# trap handles cleanup automatically
\```

**Exit codes**:

- `0`: All checks passing (or skipped)
- `1`: One or more checks failed (blocks completion)
```

### In pr-review command

Update completion criteria table to emphasize CI verification:

```markdown
| Criterion | Verification | Required |
|-----------|--------------|----------|
| All comments resolved | Each comment has [COMPLETE] or [WONTFIX] status | Yes |
| No new comments | Re-check after 45s wait returned 0 new | Yes |
| **CI checks pass** | **`gh pr checks` all green (including AI Quality Gate)** | **Yes** |
| No unresolved threads | GraphQL query for unresolved reviewThreads | Yes |
| Commits pushed | `git status` shows "up to date with origin" | Yes |
```

## Related Skills

- Skill-PR-003: Verification count (comment count matching)
- Skill-PR-Review-002: Conversation resolution protocol
- Skill-Validation-006: Self-report verification (don't trust agent claims)

## Category

pr-review, ci-infrastructure, verification

## Tags

helpful, critical, blocking-gate

## Validation Count

1 (Session 56, PR #199 false completion)

## Created

2025-12-24 (from Issue #369 analysis)

## Source

Issue #369: "fix: Add mandatory CI check verification before claiming PR review complete"

## Related

- [pr-156-review-findings](pr-156-review-findings.md)
- [pr-320c2b3-refactoring-analysis](pr-320c2b3-refactoring-analysis.md)
- [pr-52-retrospective-learnings](pr-52-retrospective-learnings.md)
- [pr-52-symlink-retrospective](pr-52-symlink-retrospective.md)
- [pr-753-remediation-learnings](pr-753-remediation-learnings.md)
