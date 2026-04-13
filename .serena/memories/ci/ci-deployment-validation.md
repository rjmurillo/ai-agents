# CI Deployment Validation

## Skill-CI-Research-002: Research Platform Before Implementation (92%)

**Statement**: Before implementing CI/CD features, read platform documentation for known limitations.

**Evidence**: Sessions 03-07 - All issues were documented behaviors that could have been researched.

**Pre-Implementation Research**:

| Platform | Key Documentation |
|----------|-------------------|
| GitHub Actions | [Contexts](https://docs.github.com/en/actions/writing-workflows), [Outputs](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/passing-information-between-jobs), [Matrix](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/running-variations-of-jobs-in-a-workflow) |
| GitHub CLI | [Authentication](https://cli.github.com/manual/gh_auth) |
| Shell | Regex compatibility (grep vs sed) |
| YAML | Heredoc handling |

**Known Limitations**:

1. **Matrix outputs**: Only ONE leg exposed - use artifacts
2. **GH_TOKEN**: Auto-authenticates - don't call `gh auth login`
3. **Lookbehinds**: GNU grep requires fixed-length - use sed
4. **YAML heredocs**: Zero-indent parsed as YAML keys

## Skill-CI-Infrastructure-004: Label Pre-Validation (92%)

**Statement**: Validate GitHub labels exist before deploying workflows that depend on them.

**Evidence**: PR #202 - "could not add label: 'drift-detected' not found"

```bash
# Pre-deployment: Create labels if missing
gh api repos/{owner}/{repo}/labels -X POST \
  -f name="drift-detected" \
  -f description="Agent drift detected" \
  -f color="d73a4a" || true  # Ignore if exists
```

```yaml
# In workflow
- name: Ensure required labels exist
  run: |
    for label in drift-detected automated; do
      gh label create "$label" --color 5319e7 2>/dev/null || true
    done
```
