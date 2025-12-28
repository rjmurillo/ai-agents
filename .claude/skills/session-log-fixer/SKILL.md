---
name: session-log-fixer
description: Fix session protocol validation failures in PRs. Use when a PR fails the "Session Protocol Validation" workflow with MUST requirement failures. Analyzes workflow logs, identifies non-compliant session files, reads the session content, determines missing requirements, and applies fixes.
---

# Session Log Fixer

Fix session protocol validation failures by analyzing CI logs and updating session files.

## Trigger

Use this skill when:

- A PR fails with "Session protocol validation failed: N MUST requirement(s) not met"
- The failed job is "Aggregate Results" in the "Session Protocol Validation" workflow
- User provides a GitHub Actions run URL

## Workflow

1. **Get workflow run status** - Check if validation failed
2. **Identify failing sessions** - Find NON_COMPLIANT verdicts
3. **Download artifacts** - Get detailed validation results
4. **Read session file** - Understand current state
5. **Apply fixes** - Add missing protocol elements
6. **Commit and push** - Trigger new CI run

## Step 1: Get Workflow Run Status

```bash
# Extract run ID from URL (e.g., .../runs/20548622722/...)
gh run view <run-id> --json status,conclusion,jobs --jq '{
  status,
  conclusion,
  failed_jobs: [.jobs[] | select(.conclusion == "failure") | {name, conclusion}]
}'
```

**Expected output for session protocol failure:**

```json
{
  "conclusion": "failure",
  "failed_jobs": [{"conclusion": "failure", "name": "Aggregate Results"}]
}
```

## Step 2: Identify Failing Sessions

```bash
# Check which sessions are NON_COMPLIANT
gh run view <run-id> --log 2>&1 | grep -E "Found verdict.*NON_COMPLIANT"

# List all validated sessions
gh api repos/{owner}/{repo}/actions/runs/<run-id>/jobs --jq '.jobs[] | .name'
```

## Step 3: Download Artifacts

```bash
# Download validation artifacts to inspect verdicts
gh run download <run-id> --dir /tmp/session-artifacts

# View verdict details
find /tmp/session-artifacts -name "*.txt" -exec cat {} \;
```

**Artifact structure:**

```text
<session-name>-verdict.txt contains:
- Line 1: COMPLIANT or NON_COMPLIANT
- Line 2: MUST failure count
- Line 3+: Detailed validation output with per-requirement status
```

## Step 4: Read Session File

```bash
# Session files location
.agents/sessions/YYYY-MM-DD-session-NN-*.md
```

**Required Protocol Compliance structure:**

```markdown
## Protocol Compliance

### Session Start (COMPLETE ALL before work)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Initialize Serena: `mcp__serena__activate_project` | [x] | Tool output present |
| MUST | Initialize Serena: `mcp__serena__initial_instructions` | [x] | Tool output present |
| MUST | Read `.agents/HANDOFF.md` | [x] | Content in context |
| MUST | Create this session log | [x] | This file exists |
| MUST | List skill scripts in `.claude/skills/github/scripts/` | [x] | Output documented below |
| MUST | Read skill-usage-mandatory memory | [x] | Content in context |
| MUST | Read PROJECT-CONSTRAINTS.md | [x] | Content in context |
| SHOULD | Search relevant Serena memories | [x] | Memory results present |
| SHOULD | Verify git status | [x] | Output documented below |
| SHOULD | Note starting commit | [x] | SHA documented below |

### Session End (COMPLETE ALL before closing)

| Req | Step | Status | Evidence |
|-----|------|--------|----------|
| MUST | Complete session log (all sections filled) | [x] | This file |
| MUST | Update Serena memory (cross-session context) | [x] | Memory write confirmed |
| MUST | Run markdown lint | [x] | 0 errors |
| MUST | Route to qa agent (feature implementation) | [x] | QA report: .agents/qa/[report].md |
| MUST | Commit all changes (including .serena/memories) | [x] | Commit SHA: _______ |
| MUST NOT | Update `.agents/HANDOFF.md` directly | [x] | HANDOFF.md unchanged |
| SHOULD | Update PROJECT-PLAN.md | [ ] | N/A |
| SHOULD | Invoke retrospective (significant sessions) | [ ] | N/A |
| SHOULD | Verify clean git status | [x] | Clean state |
```

## Step 5: Common Fixes

### Missing Session Start Table

Add the full "Session Start (COMPLETE ALL before work)" table after `## Protocol Compliance` header.

### Missing Session End Table

Add the full "Session End (COMPLETE ALL before closing)" table.

### "Pending commit" Instead of SHA

**Problem:** Evidence shows "Pending commit" instead of actual commit SHA.

**Fix:**

```bash
# Find the relevant commit SHA from PR
gh pr view <pr-number> --json commits --jq '.commits | .[] | "\(.oid[0:7]) \(.messageHeadline)"'

# Update the session log
# Change: | MUST | Commit all changes... | [x] | Pending commit |
# To:     | MUST | Commit all changes... | [x] | Commit SHA: <sha> |
```

### Missing Evidence Column

Each row needs explicit evidence, not just a checkbox:

| Bad | Good |
|-----|------|
| `[x]` | `[x] \| Tool output present` |
| `[x]` | `[x] \| Content in context` |
| `[x]` | `[x] \| Commit SHA: abc1234` |

### N/A vs Skip

- Use `[N/A]` for SHOULD requirements that don't apply
- Use `[x]` with evidence for completed requirements
- Never leave MUST requirements unchecked without explanation

## Step 6: Commit and Push

```bash
# Stage the fixed session log
git add .agents/sessions/<session-file>.md

# Commit with conventional message
git commit -m "docs: fix session protocol compliance for <session-name>

Add missing <what was missing> to satisfy session protocol validation.

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# Push to trigger new CI
git push
```

## Validation

After pushing, verify the new CI run passes:

```bash
# Watch for new run
gh run list --branch <branch> --limit 3

# Check result
gh run view <new-run-id> --json conclusion
```

## Reference: SESSION-PROTOCOL.md

The canonical source for session protocol requirements is:

```text
.agents/SESSION-PROTOCOL.md
```

Key sections:

- **Session Start Protocol** - Phase 1-4 requirements
- **Session End Protocol** - Phase 1-4 requirements
- **Session Start Checklist** - Template to copy
- **Session End Checklist** - Template to copy
- **Session Log Template** - Full template structure
