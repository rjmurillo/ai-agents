# Skill Quick Reference (Auto-loaded)

> **Purpose**: Passive context for high-value skills. Based on Vercel research showing models don't invoke skills 56% of the time—surfacing skill summaries here improves utilization.
>
> **Auto-loaded**: Via @import in CLAUDE.md to ensure skill awareness every session.

## Skill Invocation Triggers

When you encounter these patterns, **immediately check the corresponding skill**:

| Trigger Pattern | Skill to Use | Location |
|-----------------|--------------|----------|
| PR review comments to address | `pr-comment-responder` | `.claude/skills/pr-comment-responder/` |
| GitHub CLI operations (gh pr, gh issue) | `github` | `.claude/skills/github/` |
| Creating session logs | `session-init` | `.claude/skills/session-init/` |
| ADR created or modified | `adr-review` | `.claude/skills/adr-review/` |
| Memory operations | `memory` | `.claude/skills/memory/` |
| Merge conflicts | `merge-resolver` | `.claude/skills/merge-resolver/` |
| Security review needed | `threat-modeling` | `.claude/skills/threat-modeling/` |
| CI failures to debug | `github/fix-ci` | `.claude/skills/github/fix-ci.md` |
| Session log validation fails | `session-log-fixer` | `.claude/skills/session-log-fixer/` |
| Reflection/learning extraction | `reflect` | `.claude/skills/reflect/` |

## Top 5 Most-Used Skills (Summary)

### 1. GitHub Skill (`.claude/skills/github/`)

**Use for**: All GitHub CLI operations (PRs, issues, workflows, comments)

**Key scripts**:

```bash
# Get unaddressed PR comments
pwsh .claude/skills/github/scripts/pr/Get-UnaddressedComments.ps1 -PullRequest <num>

# Post PR comment reply
pwsh .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 -PullRequest <num> -Body "..."

# Get PR check logs for CI failures
pwsh .claude/skills/github/scripts/pr/Get-PRCheckLogs.ps1 -PullRequest <num>
```

**NEVER**: Use raw `gh pr comment`, `gh issue edit`, etc. when these scripts exist.

### 2. Session Init (`.claude/skills/session-init/`)

**Use for**: Creating protocol-compliant session logs

**Key command**:

```bash
pwsh .claude/skills/session-init/scripts/New-SessionLog.ps1
```

**Or via slash command**: `/session-init`

### 3. PR Comment Responder (`.claude/skills/pr-comment-responder/`)

**Use for**: Systematic handling of PR review feedback

**Workflow**:

1. Gather all comments with `Get-UnaddressedComments.ps1`
2. Categorize by priority (blocking, suggestion, question)
3. Address each systematically
4. Reply to each thread

**Key pattern**: Acknowledge every piece of feedback—don't skip any.

### 4. Memory Skill (`.claude/skills/memory/`)

**Use for**: Cross-session context persistence via Serena

**Key scripts**:

```bash
# Extract learnings from session
pwsh .claude/skills/memory/scripts/Extract-SessionEpisode.ps1 -SessionLogPath <path>
```

**Remember**: Update Serena memory at session end with cross-session context.

### 5. ADR Review (`.claude/skills/adr-review/`)

**Use for**: Multi-agent consensus when ADRs are created or modified

**Trigger**: Any file matching `.agents/architecture/ADR-*.md` is created or edited

**Process**: Routes ADR through architect, security, and critic agents for review.

## Pattern Recognition for Skill Use

### When Starting Work on a PR

```text
1. Check for unaddressed comments → pr-comment-responder skill
2. Get PR context → github skill (Get-PRReviewComments.ps1)
3. Understand CI status → github skill (Get-PRCheckLogs.ps1)
```

### When Ending a Session

```text
1. Validate session log → session-log-fixer if needed
2. Extract learnings → memory skill
3. Update Serena memory → memory skill
```

### When CI Fails

```text
1. Get failure logs → github/fix-ci.md
2. Analyze locally → Test-WorkflowLocally.ps1
3. Fix and verify → run tests before commit
```

## Skill Discovery

If you need functionality not listed here:

```bash
# List all skills
ls .claude/skills/

# Read a skill's instructions
cat .claude/skills/<skill-name>/SKILL.md
```

## Why This File Exists

Research shows that **passive context** (information loaded every session) significantly outperforms **on-demand retrieval** (skills the model must choose to invoke). By surfacing the most critical skill patterns here, we ensure the model has awareness of these capabilities without requiring explicit lookup.

This is the difference between:

- ❌ "I could look up if there's a skill for this..." (often skipped)
- ✅ "I know from SKILL-QUICK-REF that pr-comment-responder handles this"

---

**Full skill documentation**: Each skill has a `SKILL.md` with complete instructions.
