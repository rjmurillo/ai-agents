# Skill-JQ-002: PR Operation Patterns

**Statement**: Use validated jq patterns for PR status parsing to avoid escape character errors

**Context**: When parsing GitHub CLI PR JSON output with jq. Common operations: filter by status, extract fields, construct objects. Applies to batch PR operations and status monitoring.

**Evidence**: 2025-12-24 PR monitoring: 3 jq syntax errors (`unexpected token "\\"`) when attempting complex conditionals with != operator. Example: `.[] | select(.mergeStateStatus != "MERGED")` failed due to escape handling. Simplified to positive == match succeeded. Lines 162-167 of retrospective.

**Atomicity**: 90% | **Impact**: 8/10

## Pattern

Validated JQ patterns for PR operations (tested, working):

### Filter BLOCKED PRs

```bash
gh pr list --json number,mergeStateStatus | jq '.[] | select(.mergeStateStatus == "BLOCKED")'
```

### Extract PR numbers from status

```bash
gh pr list --json number,mergeStateStatus | jq -r '.[] | select(.mergeStateStatus == "BLOCKED") | .number'
```

### Count PRs by status

```bash
gh pr list --json mergeStateStatus | jq 'group_by(.mergeStateStatus) | map({status: .[0].mergeStateStatus, count: length})'
```

### Extract multiple fields

```bash
gh pr list --json number,title,mergeStateStatus | jq -r '.[] | "\(.number): \(.title) (\(.mergeStateStatus))"'
```

### Check if required check passed

```bash
gh pr checks <PR> --json name,conclusion | jq -r '.[] | select(.name == "Validate Memory Files") | .conclusion'
```

## Anti-Pattern

Complex conditionals with != operator and escape characters:

```bash
# AVOID: Escape character issues
gh pr list --json mergeStateStatus | jq '.[] | select(.mergeStateStatus != "MERGED")'

# USE INSTEAD: Positive match
gh pr list --json mergeStateStatus | jq '.[] | select(.mergeStateStatus == "BLOCKED")'
```

**Why**: The != operator in jq requires careful escape handling in shell contexts. Positive == matches are more reliable and avoid escape character parsing errors.

**Evidence**: 3 failures with != operator in 2025-12-24 session, 0 failures with == operator.
