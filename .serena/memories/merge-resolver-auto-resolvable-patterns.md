# Merge Resolver: Auto-Resolvable File Patterns

## Location

`.claude/skills/merge-resolver/scripts/Resolve-PRConflicts.ps1`

## Current Patterns (2025-12-26)

Files that can be auto-resolved by accepting main branch version:

```powershell
$script:AutoResolvableFiles = @(
    # Session artifacts - constantly changing, main is authoritative
    '.agents/HANDOFF.md',
    '.agents/sessions/*',
    '.agents/*',
    
    # Serena memories - auto-generated, main is authoritative
    '.serena/memories/*',
    '.serena/*',
    
    # Lock files - should match main
    'package-lock.json',
    'pnpm-lock.yaml',
    'yarn.lock',
    
    # Skill definitions - main is authoritative (with subdirectories)
    '.claude/skills/*',
    '.claude/skills/*/*',
    '.claude/skills/*/*/*',
    '.claude/commands/*',
    '.claude/agents/*',
    
    # Template files - main is authoritative (with subdirectories)
    'templates/*',
    'templates/*/*',
    'templates/*/*/*',
    
    # Platform-specific agent definitions
    'src/copilot-cli/*',
    'src/vs-code-agents/*',
    'src/claude/*',
    
    # GitHub configs
    '.github/agents/*',
    '.github/prompts/*'
)
```

## Important: PowerShell Pattern Matching

PowerShell `-like` does NOT do recursive matching. You MUST add explicit subdirectory patterns:
- `templates/*` only matches `templates/file.md`
- `templates/*/*` matches `templates/agents/file.md`
- `templates/*/*/*` matches `templates/agents/sub/file.md`

## Files That Require AI Analysis

These files are NOT auto-resolvable and fall through to AI analysis:
- `.github/workflows/*.yml` - Workflow logic requires semantic understanding
- `CLAUDE.md`, `AGENTS.md` - Project documentation needs careful merging
- `test/**/*.Tests.ps1` - Test files may have semantic conflicts
- `scripts/*.ps1` - Script logic requires understanding intent

## Strategy

1. Auto-resolution: Accept main branch version for frequently-changing files
2. AI fallback: Use merge-conflict-analysis.md prompt for semantic conflicts

## BLOCKING: Session Protocol Validation (2025-12-27)

Before pushing resolved conflicts, MUST validate session protocol compliance.

### Why

Session protocol validation is a CI blocking gate. User reports "template sync check often fails" are MISIDENTIFIED - the actual failure is session protocol validation, not template sync.

Evidence from PR #246:
- Template sync validation: PASS
- Session protocol validation: FAIL (9 MUST violations)

### Pre-Push Requirements

| Req | Step |
|-----|------|
| MUST | Session log exists at `.agents/sessions/YYYY-MM-DD-session-NN.md` |
| MUST | Session End checklist completed (all rows checked) |
| MUST | Serena memory updated |
| MUST | Markdown lint passed |
| MUST | Changes committed (including `.agents/` files) |
| MUST | Validation script passed |

### Validation Command

```bash
pwsh scripts/Validate-SessionEnd.ps1 -SessionLogPath ".agents/sessions/[session-log].md"
```

### Common Failures

| Error | Fix |
|-------|-----|
| `E_TEMPLATE_DRIFT` | Copy canonical checklist from SESSION-PROTOCOL.md |
| `E_QA_EVIDENCE` | Add QA report path or "SKIPPED: docs-only" |
| `E_DIRTY_WORKTREE` | Commit all files including `.agents/` |

### Cross-Reference

- Skill: `.claude/skills/merge-resolver/SKILL.md` Step 7
- Analysis: `.agents/analysis/001-merge-resolver-session-protocol-gap.md`
- Memory: `merge-resolver-session-protocol-gap`
