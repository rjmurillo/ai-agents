---
name: merge-resolver
version: 2.1.0
description: Resolve merge conflicts by analyzing git history and commit intent. Handles PR conflicts, branch conflicts, and session file conflicts with automated resolution for known patterns.
license: MIT
model: claude-opus-4-5
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
| 3.1 | Verify no remaining conflict markers | `git grep -n '<<<<<<<' --` returns no matches |
| 3.2 | Run session protocol validator | `validate_session_json.py` exits 0 |
| 3.3 | Run markdown lint | `npx markdownlint-cli2` exits 0 |
| 3.4 | Commit merge resolution | Commit SHA recorded |
| 3.5 | Push to remote | Remote ref updated |

## Intent Classification

Classify each side's changes to determine resolution priority.

| Type | Indicators | Priority |
|------|------------|----------|
| Security | "security", "vuln", "CVE" in message | Highest |
| Bugfix | "fix", "bug", "patch", "hotfix" in message | Highest |
| Feature | "feat", "add", "implement"; new functionality | Medium |
| Refactor | "refactor", "cleanup", "rename"; no behavior change | Medium |
| Style | "style", "format", "lint"; whitespace only | Lowest |

## Decision Framework

| Scenario | Resolution |
|----------|------------|
| Same intent, compatible changes | Merge both |
| Bugfix vs feature | Bugfix wins; integrate feature around it |
| Conflicting logic | Prefer more recent or better-tested change |
| Style conflicts | Accept either; prefer consistency with surrounding code |
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
| No merge markers remain | `git grep -n '<<<<<<<' --` returns no matches |
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
