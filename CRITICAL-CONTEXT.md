# Critical Context (Auto-loaded)

> **Purpose**: Blocking gates and constraints that MUST be followed in every session.
> **Auto-loaded**: Via @import in CLAUDE.md to eliminate redundant tool calls.

## RETRIEVAL-LED REASONING (MANDATORY)

**IMPORTANT**: Prefer retrieval-led reasoning over pre-training-led reasoning for ALL project-specific decisions.

**What this means**:

- Framework versions (Next.js, React) → Read project docs, NOT pre-training
- Project constraints (languages, patterns) → Read PROJECT-CONSTRAINTS.md, NOT pre-training
- Learned patterns (skills, conventions) → Read Serena memories, NOT pre-training
- Architecture decisions → Read ADRs, NOT pre-training
- Session protocol → Read SESSION-PROTOCOL.md, NOT pre-training

**Retrieval Sources Index**:

- Constraints: `.agents/governance/PROJECT-CONSTRAINTS.md`
- Session protocol: `.agents/SESSION-PROTOCOL.md`
- Memory index: Serena `memory-index` (read via `mcp__serena__read_memory`)
- Architecture: `.agents/architecture/ADR-*.md`
- Planning: `.agents/planning/*.md`
- Skills: `.claude/skills/{skill-name}/SKILL.md`

When in doubt: **Read first, reason second.**

## Blocking Constraints

| Constraint | Rationale | Verification |
|------------|-----------|--------------|
| **Python-first** (.py preferred) | ADR-042: AI/ML ecosystem alignment | New scripts in Python; PowerShell grandfathered |
| **No raw gh when skill exists** | usage-mandatory: Skills are tested, validated | Check `.claude/skills/github/` first |
| **No logic in workflow YAML** | ADR-006: Testability | Delegate to PowerShell scripts |
| **Verify branch before git ops** | SESSION-PROTOCOL: Prevent wrong-branch commits | `git branch --show-current` |
| **HANDOFF.md is read-only** | ADR-014: Distributed handoff architecture | Never edit, only read |
| **ADR created/edited → adr-review** | AGENTS.md: Multi-agent consensus required | Run adr-review skill |
| **Local workflow test before push** | Shift-left: Catch workflow errors locally | `gh act` on changed `.github/workflows/` files |

## Session Protocol Gates

### Session Start (BLOCKING)

1. Initialize Serena: `mcp__serena__activate_project` → `mcp__serena__initial_instructions`
2. Read HANDOFF.md (read-only dashboard)
3. Create session log: `.agents/sessions/YYYY-MM-DD-session-NN.json`
4. Read usage-mandatory memory
5. Verify branch: `git branch --show-current`

### Session End (BLOCKING)

1. Complete session log with outcomes and decisions
2. Update Serena memory with cross-session context
3. Run scoped markdownlint on changed files (ADR-043)
4. Route to qa agent (features only)
5. Commit all changes (including `.agents/` and `.serena/`)
6. Run `pwsh scripts/Validate-SessionJson.ps1 -SessionPath [log]`
   - If validation fails, use `/session-log-fixer` skill to fix issues

Exit code 0 (PASS) required before claiming completion.

**Test Exit Code Requirement**: ANY test output showing errors OR failures (e.g., "66 passed, 1 error") has non-zero exit code and MUST block commits. Both "failed" and "error" are failures.

## Skill-First Pattern

Before EVERY operation, ask: "Is there a skill for this?"

This is a positive checkpoint, not a negative prohibition. The habit must be:

1. Pause before executing any git, gh, or script command
2. Check SKILL-QUICK-REF.md "User Phrasing → Skill" mapping
3. If a skill exists, use it. If not, proceed with raw command.

```text
BEFORE: Think "I need to create a PR" → run `gh pr create`
AFTER:  Think "I need to create a PR" → check skill map → use github skill
```

**Why this matters**: Session analysis (1183) showed agents bypass skills even with
full catalog awareness. The problem is decision-making habit, not trigger matching.
Negative framing ("never use raw commands") fails. Positive checkpoint succeeds.

**Common operations with skills**:

| Operation | Skill | NOT raw command |
|-----------|-------|-----------------|
| Create/manage PRs | github | `gh pr create` |
| Respond to reviews | pr-comment-responder | `gh pr comment` |
| Resolve conflicts | merge-resolver | manual git merge |
| Create session log | /session-init | manual JSON creation |
| Fix CI failures | session-log-fixer | manual debugging |
| Complete session log | session-end | manual JSON editing |
| Commit and push | /push-pr | `git commit && git push` |

**If capability missing**: Add to skill, then use it. Never write inline.

## PR Review Comment Routing

When responding to PR review comments, ALWAYS route through skills first:

| Comment Pattern | Skill to Use | NOT manual fix |
|-----------------|--------------|----------------|
| CWE-* security issues | security-scan | Manual code review |
| Style/linting feedback | style-enforcement | Manual ruff/mypy runs |
| Documentation gaps | doc-coverage | Manual doc review |
| Path traversal | security-scan --cwe 22 | Manual path validation |
| Command injection | security-scan --cwe 78 | Manual input escaping |

**Pattern Detection:**

- CWE-XX in comment → security-scan skill
- "missing documentation" → doc-coverage skill
- "line too long", "naming convention" → style-enforcement skill

**Workflow:**

1. Detect comment type (CWE pattern, style, docs)
2. Route to appropriate skill with scanner
3. Let skill verify the issue exists
4. Apply skill's recommended fixes
5. Re-run skill to verify fix (exit code 0)
6. Reply to bot comment with evidence from skill output

## Full Documentation

- **Complete protocol**: `.agents/SESSION-PROTOCOL.md`
- **All constraints**: `.agents/governance/PROJECT-CONSTRAINTS.md`
- **Primary reference**: `AGENTS.md`
