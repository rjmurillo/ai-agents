# Critical Context (Auto-loaded)

> **Purpose**: Blocking gates and constraints that MUST be followed in every session.
> **Auto-loaded**: Via @import in CLAUDE.md to eliminate redundant tool calls.

## Blocking Constraints

| Constraint | Rationale | Verification |
|------------|-----------|--------------|
| **PowerShell only** (.ps1/.psm1) | ADR-005: Cross-platform consistency | No bash/Python in scripts/ |
| **No raw gh when skill exists** | usage-mandatory: Skills are tested, validated | Check `.claude/skills/github/` first |
| **No logic in workflow YAML** | ADR-006: Testability | Delegate to PowerShell scripts |
| **Verify branch before git ops** | SESSION-PROTOCOL: Prevent wrong-branch commits | `git branch --show-current` |
| **HANDOFF.md is read-only** | ADR-014: Distributed handoff architecture | Never edit, only read |
| **ADR created/edited → adr-review** | AGENTS.md: Multi-agent consensus required | Run adr-review skill |

## Session Protocol Gates

### Session Start (BLOCKING)

1. Initialize Serena: `mcp__serena__activate_project` → `mcp__serena__initial_instructions`
2. Read HANDOFF.md (read-only dashboard)
3. Create session log: `.agents/sessions/YYYY-MM-DD-session-NN.md`
4. Read usage-mandatory memory
5. Verify branch: `git branch --show-current`

### Session End (BLOCKING)

1. Complete session log with outcomes and decisions
2. Update Serena memory with cross-session context
3. Run `npx markdownlint-cli2 --fix "**/*.md"`
4. Route to qa agent (features only)
5. Commit all changes (including `.agents/` and `.serena/`)
6. Run `pwsh scripts/Validate-SessionProtocol.ps1 -SessionPath ".agents/sessions/[log].md"`
   - If validation fails, use `/session-log-fixer` skill to fix issues

Exit code 0 (PASS) required before claiming completion.

## Skill-First Pattern

**NEVER use raw commands when a skill exists.**

Check `.claude/skills/` before writing inline code:

```powershell
# WRONG: Raw gh command
gh pr comment 123 --body "Comment"

# CORRECT: Use skill
& .claude/skills/github/scripts/pr/Post-PRCommentReply.ps1 -PullRequest 123 -Body "Comment"
```

**If capability missing**: Add to skill, then use it. Never write inline.

## Full Documentation

- **Complete protocol**: `.agents/SESSION-PROTOCOL.md`
- **All constraints**: `.agents/governance/PROJECT-CONSTRAINTS.md`
- **Primary reference**: `AGENTS.md`
