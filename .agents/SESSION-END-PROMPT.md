# Session Finalization Checklist

Before ending, complete ALL mandatory steps:

## 1. Task Completion Verification

- [ ] All attempted tasks marked in PROJECT-PLAN.md:
  - `[x]` for completed
  - `[ ]` with note for incomplete (document why)
- [ ] Acceptance criteria validated for completed tasks
- [ ] No uncommitted changes remain

## 2. Documentation Updates

- [ ] Session log complete at `.agents/sessions/YYYY-MM-DD-session-NN.md`:
  - Tasks attempted and outcomes
  - Decisions made and rationale
  - Challenges encountered and resolutions
  - Files created/changed with commit references
  - Metrics (if applicable): token usage, time spent

- [ ] `.agents/HANDOFF.md` updated with:
  - Current phase and task status
  - What was completed this session
  - What's next for following session
  - Any blockers or concerns
  - Branch state (merged, open PR, WIP)

- [ ] PROJECT-PLAN.md metrics updated (if applicable)

## 3. Retrospective (MANDATORY)

Invoke retrospective agent before finalizing:

```text
@orchestrator

Route to retrospective agent for session analysis:

## Session Summary
- Phase: [N]
- Tasks attempted: [List]
- Outcomes: [Success/Partial/Blocked]

## Analysis Request
1. What patterns emerged during this session?
2. What should be added to skillbook?
3. What process improvements are needed?
4. What risks were discovered?

Save findings to: .agents/retrospective/YYYY-MM-DD-session-NN.md
```

- [ ] Retrospective document created
- [ ] Skills extracted and documented
- [ ] Learnings committed

## 4. Linting and Validation

Run BEFORE final commit:

```powershell
# Fix markdown formatting
npx markdownlint-cli2 --fix "**/*.md"

# Validate traceability (if Phase 2+ complete)
./scripts/Validate-Traceability.ps1

# Check for broken internal links
# (manual review of related: fields in YAML front matter)
```

- [ ] Markdown lint passes
- [ ] Traceability validation passes (if applicable)
- [ ] No broken cross-references

## 5. Git Operations

```powershell
# Stage all documentation
git add .agents/

# Stage new agent prompts
git add src/claude/

# Stage scripts
git add scripts/

# Commit with conventional message
git commit -m "feat(phase-N): [description]

- [Change 1]
- [Change 2]

Task-ID: [F-001, S-002, etc.]"

# Push branch
git push origin [branch-name]
```

- [ ] All changes staged
- [ ] Commit message follows conventional format
- [ ] Branch pushed to remote
- [ ] PR created (if phase complete)

## 6. Verification

- [ ] All new files are committed
- [ ] HANDOFF.md accurately reflects current state
- [ ] Next session can start from HANDOFF.md alone
- [ ] No sensitive data or absolute paths in committed files

## Critical Reminder

**The next session has ZERO context except checked-in documentation.**

Ensure documentation is complete enough for any agent to continue:
- HANDOFF.md is the single source of session state
- PROJECT-PLAN.md tracks overall progress
- Session logs preserve decision history
- Retrospective captures reusable patterns

## Session Log Template

Save to: `.agents/sessions/YYYY-MM-DD-session-NN.md`

```markdown
# Session Log: YYYY-MM-DD Session NN

## Session Info
- **Date**: YYYY-MM-DD
- **Phase**: [N - Name]
- **Branch**: [branch-name]
- **Duration**: [approx time]

## Objectives
- [ ] [Task ID]: [Description]

## Work Completed

### [Task ID]: [Title]
**Status**: Complete | Partial | Blocked
**Commits**: [SHA list]
**Files Changed**:
- `path/to/file`: [what changed]

**Decisions Made**:
- [Decision]: [Rationale]

**Challenges**:
- [Challenge]: [Resolution]

## Metrics
| Metric | Value |
|--------|-------|
| Tasks completed | N/M |
| Commits made | N |
| Files changed | N |

## Next Session
- Continue with: [Task ID]
- Blockers to resolve: [List]
- Questions for user: [List]

## Retrospective Summary
[Link to retrospective document or inline summary]
```
