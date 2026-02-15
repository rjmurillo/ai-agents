# CI YAML and Shell Patterns

## Skill-CI-Heredoc-001: YAML Heredoc Indentation (95%)

**Statement**: In YAML run blocks, heredoc content must have consistent indentation; zero-indent lines are parsed as YAML.

**Evidence**: Session 04 - "could not find expected ':'". Heredoc with zero indentation parsed as YAML keys.

**Fix**: Move large heredoc to separate files or ensure consistent indentation.

## Skill-CI-Auth-001: GH_TOKEN Auto-Authentication (92%)

**Statement**: When GH_TOKEN env var is set, gh CLI auto-authenticates; explicit `gh auth login` fails.

**Evidence**: Session 04 - `gh auth login --with-token` failed with exit code 1.

```yaml
# WRONG: Explicit login when token is set
- run: echo "${{ secrets.TOKEN }}" | gh auth login --with-token

# RIGHT: Just set env var
- name: Use gh
  env:
    GH_TOKEN: ${{ secrets.TOKEN }}
  run: gh pr list
```

## Skill-CI-Regex-001: Fixed-Length Lookbehinds (90%)

**Statement**: GNU grep lookbehinds must be fixed-length; use sed for portable variable-length regex.

**Evidence**: Session 04 - Pattern `(?<=VERDICT:\s*)` failed - "lookbehind not fixed length".

```bash
# WRONG: Variable-length lookbehind
grep -oP '(?<=VERDICT:\s*)\w+' file.txt

# RIGHT: Use sed
sed -n 's/.*VERDICT:\s*\(\w\+\).*/\1/p' file.txt
```

## Skill-CI-Shell-Interpolation-001: Use Env Vars for Shell Variables (95%)

**Statement**: Never use `${{ }}` directly in shell strings; use env vars for safe interpolation.

**Evidence**: Session 07 - Direct interpolation broke when output contained quotes.

```yaml
# WRONG: Direct interpolation
- run: |
    if [ -n "${{ steps.review.outputs.findings }}" ]; then

# RIGHT: Use env var
- run: |
    if [ -n "$FINDINGS" ]; then
  env:
    FINDINGS: ${{ steps.review.outputs.findings }}
```
