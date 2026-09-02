---
name: merge-resolver
version: 2.3.0
description: Resolve merge conflicts by analyzing git history and commit intent. Handles PR conflicts, branch conflicts, and session file conflicts with automated resolution for known patterns. Use when you say "resolve merge conflicts", "fix conflicts on this branch", "PR has conflicts with main", "can't merge due to conflicts", or "resolve PR conflicts". Do NOT use for rebasing, cherry-picking, or complex history rewrites (use git-advanced-workflows).
license: MIT
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
| 2.5 | Stage all resolved files | `git diff --cached --check MERGE_HEAD` clean |

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
| Session file conflict | Accept `--theirs`, rename ours with a distinguishing suffix | Accept `--ours` (alters main's record) |
| Same-numbered session (add/add) | Keep both; rename ours with a suffix, keep the number | Merge both contents into one file |

**Rename, never content-merge.** An add/add conflict on an append-only evidence artifact (session logs `.agents/sessions/*`, QA reports `.agents/qa/*`, retrospectives `.agents/retrospective/*`) means two branches wrote different records to the same filename. Keep both files: accept the base branch version at the original name, rename the head branch version with a distinguishing suffix (keep the session number, append an issue or topic slug), and update any index or report that references the renamed file. Never merge the two contents into one file. PR #4856 proved the anti-pattern: merging both sessions' prose into one file would have destroyed two accurate records to produce one false one (`.agents/retrospective/2026-08-10-pr-4856-session-log-collision.md`). Issue #4751 tracks preventing the collision at allocation time.

See `references/strategies.md` for the full session file resolution workflow.

## Auto-Resolvable Patterns

The script auto-resolves these by accepting the target branch version.

**Add/add caveat**: accept-theirs alone is wrong for an add/add conflict on an append-only evidence artifact (`.agents/sessions/*`, `.agents/qa/*`, `.agents/retrospective/*`), because it silently discards the head branch's own record. After accepting theirs, restore the head branch version under a renamed path per the Session File Rules above. The script does not do the rename half; handle it manually.

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

`*/.claude-plugin/plugin.json` is NOT accept-theirs. When the two sides differ
only in `version`, the script resolves them without manual handling:

- **Either side omits `version`**: the merged manifest carries none. ADR-092
  deleted the field from all three manifests, and the version-field gate
  (`validate_plugin_version_bump.py`) fails when one carries it.
  This is the shape every branch opened before ADR-092 hits when it merges a
  fixed `main`.
- **Both sides carry plain semver**: one patch bump above the higher side (for
  example ours `0.5.168` vs theirs `0.5.169` resolves to `0.5.170`). Retained
  only for branches that predate the deletion on both sides; the merged
  manifest then still carries a field the gate rejects, so delete it before
  pushing.

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
  "files_resolved": [".agents/governance/PROJECT-CONSTRAINTS.md"],
  "files_blocked": []
}
```

**Security**: Branch name validation prevents command injection. Worktree path validation prevents path traversal.

### verify_no_conflict_markers.py

Verifies that resolution is complete: no still-unmerged (UU) files and no leftover conflict markers in any in-flight change. Replaces the broad `git grep -n '<<<<<<<' --` check, which false-fails on intentional fenced examples in committed docs and Serena memories (issue #2424).

```bash
python3 .claude/skills/merge-resolver/scripts/verify_no_conflict_markers.py [--cwd PATH] [--json]
```

Uses `git diff --cached --check MERGE_HEAD` when a merge is in progress (MERGE_HEAD present) to avoid false positives from whitespace already in the incoming branch (issue #4058). Falls back to `git diff HEAD --check` outside merge state. Both forms use `git diff --name-only --diff-filter=U` to catch still-unmerged files.

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
| Alter session files from main | Breaks audit trail (immutable records) | Accept `--theirs`, then rename our session file with a distinguishing suffix |
| Content-merge an add/add session-log conflict | Destroys two accurate records to produce one false one (PR #4856) | Keep both files; rename ours with a suffix; update references |
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
| All conflicts resolved | `python3 -c "import subprocess, sys; r=subprocess.run(['git','status','--porcelain'],capture_output=True,text=True,encoding='utf-8',errors='replace'); sys.exit(r.returncode) if r.returncode else print(sum(1 for l in r.stdout.splitlines() if l.startswith('UU')))"` returns 0 |
| No merge markers remain | `python3 .claude/skills/merge-resolver/scripts/verify_no_conflict_markers.py` exits 0 (during merge: checks staged vs MERGE_HEAD AND working tree vs index; outside merge: checks working tree+index vs HEAD; ignores intentional fenced examples in committed docs -- issues #2424, #4058) |
| Any opted-in session log valid | `validate_session_json.py` exits 0 |
| Markdown lint passes | `npx markdownlint-cli2` exits 0 |
| Push successful | Remote ref updated |

### Completion Checklist

- [ ] All conflicted files staged (`git add`)
- [ ] No UU status in `git status --porcelain`
- [ ] Any conflicted session logs preserved as separate valid records
- [ ] Per-issue handoff updated when work remains
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
- **`.claude/rules/session-logs.md`**: Optional log and continuity requirements
- **strategies.md**: Detailed resolution patterns for edge cases
- **merge-resolver-session-protocol-gap**: Memory documenting root cause analysis

<details>
<summary><strong>Session Protocol Validation Details</strong></summary>

### Why This Matters

Session logs are historical records once created. A malformed staged or
explicitly supplied log still fails validation.

### Validation Commands

```bash
# Validate an existing log only when one is part of the merge.
uv run python scripts/validate_session_json.py ".agents/sessions/<log>.json"
```

### Session End Checklist

| Req | Step | Status |
|-----|------|--------|
| MUST | Update Serena memory (cross-session context) | [ ] |
| MUST | Run markdown lint | [ ] |
| MUST | Route to qa agent (feature implementation) | [ ] |
| MUST | Update the per-issue handoff, when work remains open | [ ] |

### Common Failures

| Error | Cause | Fix |
|-------|-------|-----|
| `E_TEMPLATE_DRIFT` | Existing log checklist outdated | Repair from the retained schema and optional appendix |
| `E_QA_EVIDENCE` | QA row checked but no report path | Add QA report or use "SKIPPED: docs-only" |
| `E_DIRTY_WORKTREE` | Uncommitted changes | Stage and commit all files including `.agents/` |

</details>

<!-- vendor-portability: declared. This skill reasons about consumer git state under .agents/ (sessions/*.json immutability, QA reports under .agents/qa/, retrospectives under .agents/retrospective/, HANDOFF.md, staging the .agents/ tree). The references describe how to treat whatever .agents/ content the consumer repo has; an install without that tree simply has nothing to stage there. The PR #4856 citation (.agents/retrospective/2026-08-10-pr-4856-session-log-collision.md) is upstream evidence in the rjmurillo/ai-agents repository. Issue #2050. -->
