---
name: validate-pr-description
version: 1.0.0
description: Validate a PR title and body against conventional commit format, issue-linking keywords, and template compliance before submission. Use when you say `validate my PR description`, `check my PR title`, or `is this PR body compliant`. Do NOT use to open, update, or push a PR (use the github skill or push-pr), and do NOT use to review the code diff (use review).
license: MIT
allowed-tools:
  - Bash(python3:*)
  - Bash(git:*)
  - Read
  - Glob
  - Grep
argument-hint: '[pr-title path-to-body-file]'
user-invocable: true
---

# Validate PR Description

Check a PR title and body against the three things this repository's gates read:
the conventional-commit title, the issue-linking keyword, and the template
sections the spec-coverage job parses. Catch them before submission, where the
fix costs one edit instead of one CI round.

Migrated from `.claude/commands/validate-pr-description.md` under ADR-064, which
makes skills the single user-invocable surface. `user-invocable: true` is what
fires it as `/validate-pr-description` in both Claude Code and Copilot CLI.

## Triggers

`validate my PR description`, `check my PR title`, `is this PR body compliant`,
`validate PR metadata`

## Inputs

| Input | Source | Required |
|-------|--------|----------|
| PR title | `$0`, or stated in conversation | Yes |
| PR body | `$1` as a path to a file, or pasted text | Yes |
| Target repository | current checkout | Yes |

## Process

### Phase 1: Resolve the inputs

Read the title and body from the arguments when given. When they are not, ask for
both rather than inferring them from the branch or the last commit: a PR body is
usually longer than any commit message, and validating the wrong text reports a
pass that does not describe the PR.

When the body arrives as a path, read the file. When it arrives as pasted text,
work from the text directly.

### Phase 2: Run the three checks

| # | Check | Rule | Failure meaning |
|---|-------|------|-----------------|
| 1 | Conventional commit title | `<type>(<scope>)?: <description>`, type one of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `revert` | Release tooling cannot classify the change |
| 2 | Issue-linking keyword | body holds at least one of `Closes #N`, `Fixes #N`, `Resolves #N`, or a past-tense variant | The issue stays open after merge, and the PR fails the repository's issue-linkage rule |
| 3 | Template compliance | Summary non-empty, Changes has at least one item, Type of Change has at least one marked checkbox | The spec-coverage job reports FAIL on an unpopulated section |

Prefer the repository's own validator when it ships one, because it is the same
code the gate runs. Resolve the script root through a plugin-root variable so the
invocation works in a plugin install and not only in the upstream checkout:

```bash
SCRIPTS_DIR="${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/github/scripts/pr"
uv run python "$SCRIPTS_DIR/validate_pr_description.py" \
  --title "[title]" \
  --body-file "[path-to-body.md]"
```

When that script is absent, validate manually against the table above. Say which
path you took: a manual pass and a validator pass are not the same evidence.

### Phase 3: Report

Report per check, not as a single verdict. For each failure give the offending
text and the corrected form, so the author edits rather than re-derives.

A closing keyword is a claim that the PR closes the issue. Verify it against the
diff before recommending one. When the diff does not deliver what the issue asks,
recommend `Refs #N` and say why, rather than upgrading a reference the merge will
act on.

## Verification

- [ ] Title checked against the conventional-commit pattern, and the type named
- [ ] Body searched for every accepted issue-linking keyword, not just `Closes`
- [ ] All three template sections inspected, with the failing one named
- [ ] Validator path stated: the repository script ran, or the check was manual
- [ ] Every failure reported with its offending text and a corrected form
- [ ] Any recommended closing keyword checked against the diff first

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Inferring the title from the branch name or last commit | Validates text that is not the PR's, and reports a pass the PR does not have | Ask for the title and body |
| Reporting one aggregate verdict | The author cannot tell which of the three checks failed | Report per check |
| Recommending `Closes #N` because the PR mentions the issue | A closing keyword acts on merge; an unsupported one closes live work | Verify against the diff, downgrade to `Refs #N` with a reason |
| Rewriting the body wholesale | The author loses their own wording to a style preference | Name the failing section and the minimal edit |
| Calling a manual pass a validator pass | Two different levels of evidence read as one | State which ran |

## Extension Points

- **New title types.** The type list mirrors the repository's commit convention.
  When that convention gains a type, update the Phase 2 table and the validator
  together, not one of them.
- **New template sections.** The three checked sections are the ones the
  spec-coverage job parses. A new parsed section is a new row, not new prose.
- **Other forges.** The keyword list is GitHub and GitLab behavior. On Azure
  DevOps and Bitbucket the same keywords are traceability markers with no
  auto-close, so a missing keyword is a weaker finding there.
