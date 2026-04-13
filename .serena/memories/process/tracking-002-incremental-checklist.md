# Skill-Tracking-002: Incremental Checklist Completion

## Statement

Update Session End checklist during session as tasks complete; don't defer to end

## Context

Mark Session End checklist items `[x]` immediately when requirements satisfied (e.g., HANDOFF.md update)

## Evidence

**Session End compliance cliff (2025-12-20)**: At T+3-4 when work done -> low energy -> protocol skipped

**Fishbone analysis**: "Checklist requires retrospective effort" - batch completion at end increases cognitive load

**Force Field restraining force**: "Session End low priority after work done" (strength 4/5)

## Metrics

- **Atomicity**: 88%
- **Impact**: 8/10
- **Category**: tracking, workflow, cognitive-load
- **Created**: 2025-12-20
- **Tag**: helpful
- **Validated**: 1 (24-session analysis)

## Pattern

### CORRECT: Incremental Completion

```markdown
# During session, update checklist as work progresses:

[11:23] Update HANDOFF.md with analysis findings
-> Edit session log: [x] Update HANDOFF.md

[12:45] Run npx markdownlint-cli2 --fix "**/*.md"
-> Edit session log in JSON lint

[14:10] git commit -m "feat: implement feature X"
-> Edit session log: [x] Commit all changes
-> Add commit SHA: 3b6559d

# At session end: Already complete, just verify
```

### INCORRECT: Batch Completion

```markdown
# Work throughout session without updating checklist

[11:23-14:30] Multiple actions (HANDOFF, lint, commits)

# At session end (14:30): Try to remember what was done
- [ ] Update HANDOFF.md <- Did I do this?
- [ ] Run markdown lint <- Can't remember
- [ ] Commit changes <- Skip, too tired

# Result: Incomplete checklist, session closure without compliance
```

## Verification

**Check session log edit history:**

```bash
git log --follow --oneline .agents/sessions/2025-12-20-session-47.json

# Good pattern:
# 14:10 feat: implement feature X
# 14:12 chore: update session log checklist (incremental)
# 12:46 chore: update session log checklist (incremental)

# Bad pattern:
# 14:30 chore: add session end section (all at once)
```

**Check timestamp distribution:**

```markdown
# Session log timestamps should be distributed:
[11:23] - [x] Session Start complete
[12:45] - [x] HANDOFF.md updated
[13:15] - [x] Markdown lint run
[14:10] - [x] Changes committed

# Not concentrated at end:
[14:28] - [x] Session Start complete
[14:29] - [x] HANDOFF.md updated
[14:29] - [x] Markdown lint run
[14:30] - [x] Changes committed  <- All retrofitted
```

## Benefits

1. **Reduced cognitive load**: No retrospective effort required at session end
2. **Accurate tracking**: Check boxes as work happens (not from memory)
3. **Higher completion rate**: Small incremental wins vs large deferred task
4. **Early error detection**: Realize missing step during session, not at end

## Related Skills

- Skill-Tracking-001 (Artifact Status Atomic Update)
- Skill-Protocol-002 (Verification-Based Gate Effectiveness)
- Skill-Logging-002 (Session Log Early Creation)

## Source

`.agents/retrospective/2025-12-20-session-protocol-mass-failure.md` (Learning 5, lines 719-737)
