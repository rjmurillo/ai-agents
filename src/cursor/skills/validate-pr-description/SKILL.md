---
name: validate-pr-description
version: 1.0.0
description: "Validate a PR title and body for conventional commit format, issue-linking keywords, and template compliance. Use when you say `validate my PR description` or `check my PR title`. Do NOT use to open, update, or push a PR (use github or push-pr) or review the diff (use review)."
license: Apache-2.0
metadata:
  routing:
    role: lifecycle
    invoker: ship
    trigger: ship runs validate-pr-description to validate PR metadata before push-pr
    user-facing: true
---

# Validate PR Description

Check a PR title and body against the conventional-commit title, plus the
issue-linking and template rules that apply in the target repository. Catch
them before submission, where the fix costs one edit instead of one CI round.
The title check always applies. The keyword check applies when a tracking issue
exists or a gate requires a link. The template check applies when the
repository has a PR template.

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

### Phase 1b: Discover the target repository's metadata gates

Checks 2 and 3 encode rules a repository may or may not have. Discover them in
the target checkout before you apply them. Use Glob, Grep, and Read only.

| Signal | Where to look | Enables |
|--------|---------------|---------|
| Tracking issue | the author names one, or the title, body, or branch name references an issue number | Check 2 |
| PR template | `.github/pull_request_template.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `.github/PULL_REQUEST_TEMPLATE/*.md`, `docs/`, or the repository root, any case | Check 3, against that template's own headings |
| Issue-link gate | a workflow, or a script a workflow or hook runs, that fails a PR with no closing keyword or issue reference (grep `.github/workflows/` and repository scripts for `Closes`, `closing keyword`, `issue link`; `CONTRIBUTING.md` and `AGENTS.md` are hints that may name one, never the gate itself) | Check 2 as a requirement |
| Template gate | a workflow or script that parses PR body sections (grep for the template's heading text) | Check 3 failures as gate failures |

A gate is something that fails the PR: a workflow, or a script a workflow or
hook runs. Prose that only mentions a keyword is not a gate. Neither is a file
this toolkit installed (skills, rules, agents, and their scripts under
`.claude/`, `.codex/`, `.github/instructions/`, or a plugin root), including
this skill's own validator.

Record what you searched and what you found. A signal you did not search for is
unknown, not absent.

### Phase 2: Run the checks

| # | Check | Applies when | Rule | Failure meaning |
|---|-------|--------------|------|-----------------|
| 1 | Conventional commit title | Always | `<type>(<scope>)?: <description>`, type one of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `revert` | Release tooling cannot classify the change |
| 2 | Issue-linking keyword | A tracking issue exists, or discovery found an issue-link gate | body holds `Closes #N`, `Fixes #N`, `Resolves #N`, a past-tense variant, or `Refs #N`; `owner/repo#N` for an issue in another repository | The issue stays open after merge; with a gate, the PR fails it |
| 3 | Template compliance | Discovery found a PR template | Every section the template asks the author to fill is populated: prose sections non-empty, list sections hold an item, checkbox groups hold a mark | A reviewer or the discovered template gate sees an empty section |

When a check does not apply, report it `NOT APPLICABLE` with the discovery
evidence, such as `no PR template or issue-link gate found under .github/`. Never ask the author to open an issue or add a keyword just to pass
check 2. A direct bug fix with no tracking issue needs no closing keyword unless
the repository's own gate demands one; then report that gate by path.

Prefer the repository's own validator when it ships one, because it is the same
code the gate runs. The locator below finds the plugin's script in a plugin
install and in the upstream checkout. In a consumer repository it is the
plugin's copy, not a gate of that repository, so judge each of its WARNs by
that check's own "Applies when" condition. A keyword WARN stands when a
tracking issue or an issue-link gate exists, and is `NOT APPLICABLE` only when
neither does. Its template WARN reads the plugin's upstream sections, so
discard it: with no PR template, check 3 is `NOT APPLICABLE`; with one, run
check 3 against that template's headings yourself. Its title result always
stands. Under `--fail-on-violation` its exit 1 can come from those WARNs, so
read the per-check output, not the exit code.

```bash
( for d in "${CLAUDE_PLUGIN_ROOT}" "${COPILOT_PLUGIN_ROOT}" .claude; do if [ -n "$d" ] && [ -f "$d/lib/ptk_run.py" ]; then exec python3 "$d/lib/ptk_run.py" skills/github/scripts/pr/validate_pr_description.py --title "[title]" --body-file "[path-to-body.md]"; fi; done; echo "ptk_run: no plugin root holds lib/ptk_run.py" >&2; exit 2 )
```

When that script is absent, validate manually against the table above. Say which
path you took: a manual pass and a validator pass are not the same evidence.

### Phase 2b: Check file mentions against the diff

When the body is a file and the checkout ships `scripts/validation/pr_description.py`,
run its local mode. It runs the same file-mention check the required
`Validate PR` check runs, so a pass here rules out a `File mentioned but not in
diff` failure. It does not cover the dash or closing-keyword checks. Local mode
reads committed `HEAD`, so commit first:

```bash
uv run --frozen python -I scripts/validation/pr_description.py --body-file "[path-to-body.md]" --base origin/main
```

Exit 1 is a CRITICAL finding, usually `File mentioned but not in diff`. Report the
path and the fix: remove it, move it out of the change heading (`## Changes`,
`## What changed`, and the like), or wrap it in a code fence. With no change
heading, a bold or bulleted path counts anywhere, so remove or fence it. Do not
suggest the `description-validation-bypass` label; a human maintainer decides
that. Exit 2 means the check could not run: an unreadable or non-UTF-8 body
file, an unknown or invalid base ref, or git unavailable. For a missing
`origin/main`, pass `--base` with the ref the PR targets.
When the script is absent, or the body is pasted text with no file, say this
check was not run.

### Phase 3: Report

Report per check, not as a single verdict. For each failure give the offending
text and the corrected form, so the author edits rather than re-derives.

A closing keyword is a claim that the PR closes the issue. Verify it against the
diff before recommending one. When the diff does not deliver what the issue asks,
recommend `Refs #N` and say why, rather than upgrading a reference the merge will
act on.

## Verification

- [ ] Title checked against the conventional-commit pattern, and the type named
- [ ] PR template and metadata gates discovered in the target checkout, with the search named
- [ ] Checks 2 and 3 applied only when discovery found a reason, else reported `NOT APPLICABLE`
- [ ] Body searched for every accepted issue-linking keyword, not just `Closes`
- [ ] Every section of the discovered template inspected, with the failing one named
- [ ] Validator path stated: the repository script ran, or the check was manual
- [ ] File mentions checked against the diff with `pr_description.py --body-file`, or the check stated as not run
- [ ] Every failure reported with its offending text and a corrected form
- [ ] Any recommended closing keyword checked against the diff first

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Inferring the title from the branch name or last commit | Validates text that is not the PR's, and reports a pass the PR does not have | Ask for the title and body |
| Reporting one aggregate verdict | The author cannot tell which check failed | Report per check |
| Requiring a closing keyword or template sections in every repository | The target may have no tracking issue, template, or gate, so the finding is false | Discover first; report `NOT APPLICABLE` with evidence |
| Demanding a new tracking item so a keyword has a target | Creates tracking work only to satisfy a rule the repository lacks | Require a link only when an issue exists or a gate demands one |
| Recommending `Closes #N` because the PR mentions the issue | A closing keyword acts on merge; an unsupported one closes live work | Verify against the diff, downgrade to `Refs #N` with a reason |
| Rewriting the body wholesale | The author loses their own wording to a style preference | Name the failing section and the minimal edit |
| Calling a manual pass a validator pass | Two different levels of evidence read as one | State which ran |

## Extension Points

- **New title types.** The type list mirrors the repository's commit convention.
  When that convention gains a type, update the Phase 2 table and the validator
  together, not one of them.
- **New template sections.** Check 3 reads the discovered template's headings,
  so a new section needs no skill edit. A new gate that parses the body is a new
  discovery signal row, not new prose.
- **Other forges.** The keyword list is GitHub and GitLab behavior. On Azure
  DevOps and Bitbucket the same keywords are traceability markers with no
  auto-close, so a missing keyword is a weaker finding there.

<!-- vendor-portability-exec: Phase 2b runs scripts/validation/pr_description.py, an upstream-only script a plugin install lacks. The allowed-tools grant names the same command. The phase says what to report then. -->
<!-- vendor-portability: Phase 2b and its allowed-tools grant name scripts/validation/pr_description.py only for checkouts that carry it, and reports the check as not run otherwise. -->
