# GitHub Actions Workflow Patterns for AI Review

## Overview

Documented patterns discovered during Session 13 (2025-12-18) for building robust AI-powered CI/CD workflows using GitHub Copilot CLI.

## Key Patterns

### 1. Composite Action Encapsulation

**Pattern**: Centralize Copilot CLI invocation in a reusable composite action.

**Why**: Eliminates duplication of Node.js/npm setup, authentication, agent loading, prompt building, and verdict parsing across workflows.

**Implementation**: `.github/actions/ai-review/action.yml`

**Inputs**:

- `agent`: Agent name (analyst, critic, qa, roadmap, etc.)
- `context-type`: pr-diff, issue, session-log, spec-file
- `additional-context`: Extra context to append
- `prompt-file`: Path to prompt template
- `bot-pat`: GitHub PAT for API access
- `copilot-token`: Copilot authentication token

**Outputs**:

- `verdict`: PASS | WARN | CRITICAL_FAIL
- `findings`: Full AI response text
- `labels`, `milestone`: Parsed structured data

### 2. Shell Interpolation Safety

**Anti-pattern**: Direct `${{ }}` interpolation in shell scripts.

```yaml
# BAD - vulnerable to injection
run: |
  echo "${{ github.event.pull_request.body }}"
```

**Pattern**: Use env vars for safe interpolation.

```yaml
# GOOD - safe from injection
env:
  PR_BODY: ${{ github.event.pull_request.body }}
run: |
  echo "$PR_BODY"
```

**Why**: GitHub context values can contain shell metacharacters. Env vars are properly escaped.

### 3. Matrix Strategy for Parallel Validation

**Pattern**: Use matrix strategy with artifacts (not job outputs) for parallel processing.

**Why**: Job outputs only expose one leg of a matrix. Artifacts persist data from all legs.

**Implementation**:

```yaml
jobs:
  detect-changes:
    outputs:
      files: ${{ steps.find.outputs.json_array }}
  
  validate:
    needs: detect-changes
    strategy:
      matrix:
        file: ${{ fromJson(needs.detect-changes.outputs.files) }}
    steps:
      - uses: actions/upload-artifact@v4
        with:
          name: result-${{ hashFiles(matrix.file) }}
          path: validation-results/
  
  aggregate:
    needs: [detect-changes, validate]
    steps:
      - uses: actions/download-artifact@v4
        with:
          pattern: result-*
          merge-multiple: true
```

### 4. GITHUB_OUTPUT with Heredocs

**Pattern**: Use heredoc syntax for multi-line outputs.

```bash
{
  echo "context<<EOF_CONTEXT"
  echo "## Additional Context"
  echo "$CONTENT"
  echo "EOF_CONTEXT"
} >> $GITHUB_OUTPUT
```

**Why**: YAML inputs can't execute shell commands. Prepare content in a prior step.

### 5. Verdict Token Standards

**Pattern**: Use structured verdict tokens for automation.

| Token | Meaning | CI Result |
|-------|---------|-----------|
| PASS | All checks satisfied | Success |
| WARN | Non-blocking issues | Success with warning |
| CRITICAL_FAIL | Blocking issues | Failure |

**Implementation**: Prompts instruct agents to emit `VERDICT: TOKEN` format.

### 6. Report Generation Pattern

**Pattern**: Generate markdown reports with consistent structure.

```markdown
<!-- UNIQUE-COMMENT-ID -->
## Report Title

> [!NOTE|TIP|WARNING|CAUTION]
> **Verdict: STATUS**

<details>
<summary>Details</summary>
...
</details>

---
<sub>Footer with workflow links</sub>
```

**Why**: Comment ID enables idempotent updates via `post_pr_comment()`.

## Common Mistakes to Avoid

1. **Function definitions in YAML env block**: Shell functions must be in `run:`, not `env:`.

2. **Shell commands in YAML inputs**: `$(...)` doesn't work in YAML `with:` blocks. Use a prior step.

3. **Using job outputs with matrix**: Only one matrix leg populates outputs. Use artifacts.

4. **Manual Copilot CLI setup**: Always use the composite action for consistency.

5. **Direct PR body interpolation**: Always use env vars for user-controlled content.

## Related Files

- `.github/actions/ai-review/action.yml` - Core composite action
- .github/scripts/ai-review-common.sh (removed) - Shared bash utilities
- `.github/workflows/ai-pr-quality-gate.yml` - Reference implementation
