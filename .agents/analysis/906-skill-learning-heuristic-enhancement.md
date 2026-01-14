# Invoke-SkillLearning.ps1 Improvements

## Source Analysis

Analyzed `.claude-mem/memories/direct-backup-2026-01-03-1434-ai-agents.json` (9.3MB) to identify real user feedback patterns.

## Pattern Discovery

### HIGH Confidence Patterns (Corrections)

**Original patterns**:

- `no`, `not like that`, `wrong`, `never do`, `always do`

**Enhanced patterns** (from memory analysis):

- Added: `nope`, `that's wrong`, `incorrect`, `must use`, `should not`, `avoid`, `stop`
- Added Chesterton's Fence violations: `trashed without understanding`, `removed without knowing`, `deleted without checking`
- Added immediate corrections: `debug`, `root cause`, `correct`, `fix all`, `address`, `broken`, `error`, `issue`, `problem`

**Evidence from memory**:

```
"PR 730 containing your changes contains a number of feedback items from reviewers
and has failed required checks. Debug, root cause, and correct the procedure..."

"we generate @.claude/skills/github/github.skill using frontmatter
metadata.generator.keep_headings you just trashed without understanding.
This is a Chesterton's Fence situation"

"yeah, it's wrong. When I query the sqlite database, there's 3535 observations"
```

### MEDIUM Confidence Patterns (Preferences/Success)

**Original patterns**:

- Success: `perfect`, `great`, `yes`, `exactly`, `that's it`, `good`
- Edge cases: Questions with `?`

**Enhanced patterns** (from memory analysis):

- Tool preferences: `instead of`, `rather than`, `prefer`, `should use`, `use X not Y`, `better to`
- Expanded success: `excellent`, `good job`, `well done`, `correct`, `right`, `works`
- Edge cases: `what if`, `how does`, `how will`, `what about`, `don't want to forget`, `ensure`, `make sure`, `needs to`
- Added question type distinction: Short questions (<150 chars) may indicate confusion

**Evidence from memory**:

```
"for memory, the canonical location is .claude/skills/memory/scripts.
Do fix the blocking issues..."

"Rather than accessing the database directly, it communicates
with a background worker process via HTTP API..."

"are the concepts in Issue 722/Phase 2C covered in the
@.agents/planning/enhancement-PROJECT-PLAN.md and related documents?
Don't want to forget about it while implementing"
```

### LOW Confidence Patterns (Command Preferences)

**New pattern**:

- Track repeated command patterns: `./`, `pwsh`, `gh`, `git`

**Evidence from memory**:

- Frequent use of `/pr-review`, `/session-init`, `gh pr`, `pwsh scripts/`
- Pattern repetition indicates workflow preferences

## Skill Detection Improvements

**Original**: 4 hardcoded skills (github, memory, session-init, SkillForge)

**Enhanced**: 13 predefined skills + dynamic detection:

**Added skills**:

- `adr-review`
- `incoherence`
- `retrospective`
- `reflect`
- `pr-comment-responder`
- `code-review`
- `api-design`
- `testing`
- `documentation`

**Dynamic detection**:

1. Explicit references: `.claude/skills/{skill-name}`
2. Slash commands: `/command-name` with mapping to skills
3. Command-to-skill mapping: `/pr-review` → `github`, `/memory-search` → `memory`

**Evidence from memory**:

```
"run `/pr-review-toolkit:review-pr 735` and fix ALL items found..."

"use incoherence skill recursively until no issues are found"

"for @.claude/skills/research-and-incorporate/SKILL.md add a model to use"
```

## Memory Update Improvements

**Character limits increased**: 100 → 150 characters for source/context capture to preserve more detail.

## Impact

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| HIGH patterns | 2 | 3 categories (11+ phrases) | 5.5x |
| MED patterns | 2 | 4 categories (20+ phrases) | 10x |
| LOW patterns | 0 | 1 category (4 patterns) | ∞ |
| Skills detected | 4 | 13+ dynamic | 3x+ |
| Context preserved | 100 chars | 150 chars | 50% |

## Testing Recommendations

1. **Test with this session**: Should detect SkillForge, reflect, memory usage
2. **Test corrections**: Try saying "no, that's wrong" after output
3. **Test preferences**: Try saying "use X instead of Y"
4. **Test Chesterton's Fence**: Try "you removed that without understanding"
5. **Test edge cases**: Ask "what if X happens?"
6. **Test questions**: Ask short questions after output

## Related

- Source: `.claude-mem/memories/direct-backup-2026-01-03-1434-ai-agents.json`
- Hook: `.claude/hooks/Stop/Invoke-SkillLearning.ps1`
- Skill: `.claude/skills/reflect/SKILL.md`
- PR: <https://github.com/rjmurillo/ai-agents/pull/908>
