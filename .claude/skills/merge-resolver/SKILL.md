---
name: merge-resolver
version: 2.2.0
description: Resolve merge conflicts by analyzing git history and commit intent. Handles PR conflicts, branch conflicts, and session file conflicts with automated resolution for known patterns. Use when you say "resolve merge conflicts", "fix conflicts on this branch", "PR has conflicts with main", "can't merge due to conflicts", or "resolve PR conflicts". Do NOT use for rebasing, cherry-picking, or complex history rewrites (use git-advanced-workflows).
license: MIT
model: claude-opus-4-6
metadata:
  domains:
  - git
  - github
  - merge-conflicts
  - pr-maintenance
  type: workflow
  complexity: advanced
---
# Merge Resolver

Resolve merge conflicts by analyzing git history and commit intent.

## Quick Start

```bash
# Resolve conflicts for a specific PR
python3 .claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py \
    --pr-number 123 --branch-name "fix/my-feature" --target-branch "main"

# Dry-run mode (no side effects)
python3 .claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py \
    --pr-number 123 --branch-name "fix/test" --dry-run
```

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `resolve merge conflicts` | Auto-detect branch/PR and resolve |
| `fix conflicts on this branch` | Context-aware conflict resolution |
| `PR has conflicts with main` | Merge-based conflict resolution |
| `can't merge due to conflicts` | Analyze and fix blocking conflicts |
| `resolve PR conflicts` | Resolve conflicts for a specific PR number |

## Process

### Phase 0: Execution Capability Precondition (BLOCKING)

Run this self-check FIRST, before any context gathering, analysis, or plan. Conflict resolution requires shell execution: worktree creation, `git merge`, staging, commit, and `git push`. Without those tools you can only describe steps, never resolve anything.

| Step | Action | Verification |
|------|--------|--------------|
| 0.1 | Confirm shell/Bash is available (`git`, worktree creation, `git push`) | A tool result in this run shows a shell command executed |
| 0.2 | If shell is unavailable: return immediately with status [BLOCKED], one-line reason, route execution back to the orchestrator, and STOP | No resolution plan, phase list, or report is produced |

If shell execution is unavailable, do NOT produce a step-by-step resolution plan. A plan reads as completed work and is the exact failure this precondition prevents (issue #2646). Return BLOCKED and route execution back to the orchestrator.

**Completion rule (applies to every execution phase below)**: mark a phase complete ONLY when a tool result in this run proves it ran. A plan is not a completion. Never report "create worktree", "merge", "push", or "run gates" as complete from instructions alone.

### Phase 1: Context Gathering

| Step | Action | Verification |
|------|--------|--------------|
| 1.1 | Fetch PR metadata via `gh pr view` | PR metadata displayed |
| 1.2 | Checkout PR branch | `git branch --show-current` matches |
| 1.3 | Attempt merge with base (`--no-commit`) | Conflict markers created |
| 1.4 | List conflicted files | `git diff --name-only --diff-filter=U` output |

### Phase 2: Analysis and Resolution

| Step | Action | Verification |
|------|--------|--------------|
| 2.1 | Classify files (auto-resolvable vs manual) | Classification logged |
| 2.2 | Auto-resolve known patterns (accept `--theirs`) | Files staged cleanly |
| 2.3 | For manual files: run `git blame`, analyze intent | Commit messages captured |
| 2.4 | Apply manual resolutions per decision framework | Conflict markers removed |
| 2.5 | Stage all resolved files | `git diff --check` clean |

### Phase 3: Validation (BLOCKING)

| Step | Action | Verification |
|------|--------|--------------|
| 3.1 | Verify no remaining conflict markers and no unmerged files | `python3 .claude/skills/merge-resolver/scripts/verify_no_conflict_markers.py` exits 0 |
| 3.2 | Run session protocol validator | `validate_session_json.py` exits 0 |
| 3.3 | Run markdown lint | `npx markdownlint-cli2` exits 0 |
| 3.4 | Commit merge resolution | Commit SHA recorded |
| 3.5 | Push to remote | Remote ref updated |

## Intent Classification

Classify each side's changes to determine resolution priority.

| Type | Indicators | Priority |
|------|------------|----------|
| Security | "security", "vuln", "CVE" in message | Highest (1) |
| Bugfix | "fix", "bug", "patch", "hotfix" in message | High (2) |
| Feature | "feat", "add", "implement"; new functionality | Medium (3) |
| Refactor | "refactor", "cleanup", "rename"; no behavior change | Medium (3) |
| Style | "style", "format", "lint"; whitespace only | Lowest (4) |

Priority is a strict priority hierarchy: Security (1) > Bugfix (2) > Feature/Refactor (3) > Style (4). Intent priority is the PRIMARY sort key when two sides conflict. A Security change is NEVER dropped: if it cannot be cleanly combined with the other side, Security wins and the lower-priority change is reapplied around it. Recency and test coverage are tiebreakers ONLY between two changes in the same priority tier; they never let a lower-tier change beat a higher-tier one.

## Decision Framework

| Scenario | Resolution |
|----------|------------|
| Same intent, compatible changes | Merge both |
| Bugfix vs feature | Bugfix wins; integrate feature around it |
| Security vs anything else | Security wins and is preserved; reapply the other change around the security fix (never drop the security change) |
| Higher-priority vs lower-priority tier (e.g. Bugfix vs Refactor) | Higher-priority wins; integrate the lower-priority change around it |
| Same-tier conflict / Conflicting logic | Combine if possible; else break the tie by better-tested, then more recent |
| Style vs Style conflicts | Accept either; prefer consistency with surrounding code |
| Deletions vs modifications | Investigate why; deletion usually intentional |

## Session File Rules

**CRITICAL**: Session files from main are immutable audit records.

| Action | Correct | Wrong |
|--------|---------|-------|
| Session file conflict | Accept `--theirs`, rename ours to next number | Accept `--ours` (alters main's record) |
| Same-numbered session | Keep both with different numbers | Overwrite one version |

See `references/strategies.md` for the full session file resolution workflow.

## Auto-Resolvable Patterns

The script auto-resolves these by accepting the target branch version.

| Pattern | Rationale |
|---------|-----------|
| `.agents/sessions/*.json` | Session files from main are immutable audit records |
| `.agents/*` | Session artifacts, constantly changing |
| `.serena/*` | Serena memories, auto-generated |
| `.claude/skills/*/*.md` | Skill definitions, main is authoritative |
| `.claude/commands/*` | Command definitions, main is authoritative |
| `.claude/agents/*` | Agent definitions, main is authoritative |
| `templates/*` | Template files, main is authoritative |
| `src/copilot-cli/*` | Platform agent definitions |
| `src/vs-code-agents/*` | Platform agent definitions |
| `src/claude/*` | Platform agent definitions |
| `.github/agents/*` | GitHub agent configs |
| `.github/prompts/*` | GitHub prompts |
| `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml` | Lock files; regenerate from main |

### Plugin Manifests (Special Rule)

`*/.claude-plugin/plugin.json` is NOT accept-theirs. Accepting main's copy
makes head version equal to the merge-base and re-trips the plugin
version-bump gate with `not-bumped` (issue #2543). When the two sides differ
only in `version`, the script resolves to one patch bump above the higher
side (for example ours `0.5.168` vs theirs `0.5.169` resolves to `0.5.170`).
Any other field difference, or a prerelease/build-metadata version, blocks
auto-resolution and requires manual handling.

## Scripts

### resolve_pr_conflicts.py

Resolves PR merge conflicts with auto-resolution for known file patterns.

```bash
python3 .claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py \
    --pr-number <number> --branch-name <name> [--target-branch <branch>] \
    [--worktree-base-path <path>] [--dry-run]
```

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Conflicts resolved successfully (and, if not `--dry-run`, pushed) |
| 1 | Non-auto-resolvable conflicts remain |

When running with `--dry-run`, exit code `0` indicates that conflicts were fully auto-resolvable and the changes would have been pushed, but no changes were made because of dry-run mode.

**Output format** (JSON):

```json
{
  "success": true,
  "message": "Successfully resolved conflicts for PR #123",
  "files_resolved": [".agents/HANDOFF.md"],
  "files_blocked": []
}
```

**Security**: Branch name validation prevents command injection. Worktree path validation prevents path traversal.

### verify_no_conflict_markers.py

Verifies that resolution is complete: no still-unmerged (UU) files and no leftover conflict markers in any in-flight change. Replaces the broad `git grep -n '<<<<<<<' --` check, which false-fails on intentional fenced examples in committed docs and Serena memories (issue #2424).

```bash
python3 .claude/skills/merge-resolver/scripts/verify_no_conflict_markers.py [--cwd PATH] [--json]
```

Uses `git diff HEAD --check` (catches leftover markers in working tree + index) plus `git diff --name-only --diff-filter=U` (catches files still unmerged). Both inspect in-flight changes only, so committed historical content is intentionally ignored.

**Exit codes:**

| Code | Meaning |
|------|---------|
| 0 | Clean: no unmerged files and no leftover conflict markers |
| 1 | Resolution incomplete: markers remain or unmerged files exist |
| 2 | Usage error: not inside a git working tree |
| 3 | External error: a git command failed unexpectedly |

## Anti-Patterns

| Anti-Pattern | Why It Fails | Instead |
|--------------|--------------|---------|
| Alter session files from main | Breaks audit trail (immutable records) | Accept `--theirs`, then rename our session file to the next available number |
| Push without session validation | CI blocks with MUST violations | Run `validate_session_json.py` first |
| Manual edit of generated files | Lost on regeneration | Edit template, run generator |
| Accept `--ours` for HANDOFF.md | Branch version often stale | Accept `--theirs` (main is canonical) |
| Merge lock files manually | JSON corruption, broken deps | Accept base, regenerate with `npm install` |
| Skip `git blame` analysis | Wrong intent inference | Always check commit messages |
| Resolve before fetching PR context | Missing context, wrong base | Always `gh pr view` first |
| Forget to stage `.agents/` | Dirty worktree CI failure | Include all `.agents/` changes |

## Verification

### Success Criteria

| Criterion | Evidence |
|-----------|----------|
| All conflicts resolved | `git diff --check` returns empty |
| No merge markers remain | `python3 .claude/skills/merge-resolver/scripts/verify_no_conflict_markers.py` exits 0 (uses `git diff HEAD --check` + `git diff --diff-filter=U`; ignores intentional fenced examples in committed docs -- issue #2424) |
| Session protocol valid | `validate_session_json.py` exits 0 |
| Markdown lint passes | `npx markdownlint-cli2` exits 0 |
| Push successful | Remote ref updated |

### Completion Checklist

- [ ] All conflicted files staged (`git add`)
- [ ] No UU status in `git status --porcelain`
- [ ] Session log exists at `.agents/sessions/`
- [ ] Session end checklist completed
- [ ] Serena memory updated
- [ ] Merge commit created
- [ ] Branch pushed to origin

## Extension Points

### Custom Auto-Resolvable Patterns

Add patterns to `AUTO_RESOLVABLE_PATTERNS` in `resolve_pr_conflicts.py`.

### Custom Resolution Strategies

Add entries in `references/strategies.md` for domain-specific conflicts.

### CI/CD Integration

```yaml
- name: Resolve conflicts
  env:
    PR_NUMBER: ${{ github.event.pull_request.number }}
    HEAD_REF: ${{ github.head_ref }}
    BASE_REF: ${{ github.base_ref }}
  run: |
    python3 .claude/skills/merge-resolver/scripts/resolve_pr_conflicts.py \
      --pr-number "$PR_NUMBER" \
      --branch-name "$HEAD_REF" \
      --target-branch "$BASE_REF"
```

## Related

- **Security**: Branch name and path validation prevent injection and traversal
- **SESSION-PROTOCOL.md**: Session end requirements (blocking gate)
- **strategies.md**: Detailed resolution patterns for edge cases
- **merge-resolver-session-protocol-gap**: Memory documenting root cause analysis

<details>
<summary><strong>Session Protocol Validation Details</strong></summary>

### Why This Matters

Session protocol validation is a CI blocking gate. Pushing without completing session requirements causes CI failures with "MUST requirement(s) not met" errors.

### Validation Commands

```bash
# 1. Ensure session log exists
SESSION_LOG=$(ls -t -- .agents/sessions/*.json 2>/dev/null | head -1)
if [ -z "$SESSION_LOG" ]; then
    echo "ERROR: No session log found."
    exit 1
fi

# 2. Run session protocol validator
python3 scripts/validate_session_json.py "$SESSION_LOG"
```

### Session End Checklist (REQUIRED)

| Req | Step | Status |
|-----|------|--------|
| MUST | Complete session log (all sections filled) | [ ] |
| MUST | Update Serena memory (cross-session context) | [ ] |
| MUST | Run markdown lint | [ ] |
| MUST | Route to qa agent (feature implementation) | [ ] |
| MUST | Commit all changes (including .serena/memories) | [ ] |
| MUST NOT | Update `.agents/HANDOFF.md` directly | [ ] |

### Common Failures

| Error | Cause | Fix |
|-------|-------|-----|
| `E_TEMPLATE_DRIFT` | Session checklist outdated | Copy canonical checklist from SESSION-PROTOCOL.md |
| `E_QA_EVIDENCE` | QA row checked but no report path | Add QA report or use "SKIPPED: docs-only" |
| `E_DIRTY_WORKTREE` | Uncommitted changes | Stage and commit all files including `.agents/` |

</details>

<!-- vendor-portability: declared. This skill reasons about consumer git state under .agents/ (sessions/*.json immutability, HANDOFF.md, staging the .agents/ tree). The references describe how to treat whatever .agents/ content the consumer repo has; an install without that tree simply has nothing to stage there. Issue #2050. -->
