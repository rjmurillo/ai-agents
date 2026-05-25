# gh-native - Copilot CLI Optimized GitHub Scripts

This directory contains bash wrapper scripts that call `gh` CLI directly without PowerShell overhead. These scripts are optimized for **Copilot CLI** environments where PowerShell spawn cost (183-416ms) becomes a bottleneck.

## Performance Impact

| Operation | PowerShell Variant | gh-native Variant | Improvement |
|-----------|-------------------|-------------------|-------------|
| Get PR context | 600-900ms | 250-550ms | 40-50% |
| Set issue labels | 500-600ms | 150-250ms | 55-70% |
| Set issue milestone | 500-600ms | 150-250ms | 55-70% |
| Post issue comment | 500-600ms | 150-250ms | 55-70% |

**Typical workflow impact**: PR review with 21 operations: 8.4s → 3.2s (62% faster)

## Scripts

### `get-pr-context.sh`

Get PR metadata including title, body, state, labels, reviewers, and optionally diff/files.

**Usage:**

```bash
./get-pr-context.sh --pull-request 123 [--owner owner] [--repo repo] [--include-diff] [--include-changed-files] [--diff-stat]
```

**Output:** JSON object with PR metadata

**Exit codes:** 0=success, 1=invalid params, 2=not found, 3=API error, 4=auth error

---

### `set-issue-labels.sh`

Add one or more labels to an issue.

**Usage:**

```bash
./set-issue-labels.sh --issue 123 --labels "bug,urgent" [--owner owner] [--repo repo]
```

**Output:** JSON object with applied and failed labels

**Exit codes:** 0=success, 1=invalid params, 3=API error

---

### `set-issue-milestone.sh`

Set a milestone on an issue.

**Usage:**

```bash
./set-issue-milestone.sh --issue 123 --milestone "v1.0" [--owner owner] [--repo repo]
```

**Output:** JSON object with success status

**Exit codes:** 0=success, 1=invalid params, 2=milestone not found, 3=API error

---

### `post-issue-comment.sh`

Post a comment to an issue, optionally with idempotency marker.

**Usage:**

```bash
./post-issue-comment.sh --issue 123 --body "Comment text" [--owner owner] [--repo repo] [--marker "unique marker"]

# Or from file
./post-issue-comment.sh --issue 123 --body-file comment.md [--owner owner] [--repo repo]
```

**Output:** JSON object with comment ID

**Exit codes:** 0=success, 1=invalid params, 2=issue not found, 3=API error

---

### `add-comment-reaction.sh`

Add an emoji reaction to a comment.

**Usage:**

```bash
./add-comment-reaction.sh --comment-id 12345 --reaction "thumbsup" [--comment-type issue|review] [--owner owner] [--repo repo]
```

**Output:** JSON object with success status

**Exit codes:** 0=success, 1=invalid params, 2=comment not found, 3=API error

---

## Comparison: gh-native vs Python Skills

| Feature | Python Skill | gh-native |
|---------|--------------|-----------|
| **Full-featured** | Yes (label auto-create, validation) | No (basic operations only) |
| **Speed** | ~400-500ms (for simple ops) | ~150-250ms |
| **Platform** | Claude Code, VS Code | Copilot CLI |
| **Best for** | When validation needed | When speed is critical |

**Decision tree**: Use `gh-native/` when labels/milestones are guaranteed to exist and validation isn't needed. Use Python skills when auto-create or comprehensive error handling required.

---

## Exit Codes (ADR-035)

All scripts follow standardized exit codes:

| Code | Meaning | Action |
|------|---------|--------|
| 0 | Success | Continue |
| 1 | Invalid parameters / logic error | Fix inputs |
| 2 | Not found (PR, issue, label, milestone) | Verify ID |
| 3 | External error (API failure) | Retry with backoff |
| 4 | Authentication error | Check `gh auth` |

---

## Requirements

- bash 4.0+
- `gh` CLI 2.60+
- `python3` (for JSON processing)
- GitHub CLI authentication (`gh auth status` returns 0)

---

## Examples

**Get PR #42 with diff:**

```bash
./get-pr-context.sh --pull-request 42 --include-diff
```

**Add urgent label to issue #123:**

```bash
./set-issue-labels.sh --issue 123 --labels "urgent"
```

**Post comment with idempotency (skip if marker exists):**

```bash
./post-issue-comment.sh --issue 123 --body "Reviewing this" --marker "[copilot-review]"
```

---

## Integration

These scripts are designed for Copilot CLI agent usage. They can also be called from:

- GitHub Actions workflows
- Custom CLI tools
- CI/CD pipelines
- Shell scripts

Just ensure `gh` CLI is installed and authenticated.

---

## Related

- Python equivalents: `.claude/skills/github/scripts/pr/` and `.claude/skills/github/scripts/issue/`
- GitHub MCP skill: For Claude Code and VS Code (full-featured)
- Performance analysis: `.agents/analysis/gh-native-benchmark.md`
