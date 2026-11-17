# pr-quality-security

Scans your uncommitted and branch changes for vulnerabilities, secret exposure, and OWASP Top 10 anti-patterns. You get one verdict, `PASS`, `WARN`, or `CRITICAL_FAIL`, with findings that cite a file and line.

> [!NOTE]
> This gate reads criteria from `.github/prompts/pr-quality-gate-security.md` and returns JSON that matches `.agents/schemas/pr-quality-gate-output.schema.json`. Both files live in the `rjmurillo/ai-agents` repository. The skill is written for contributors to that repository.

## When to use it

- You want a security check on your working changes before you push.
- You say `security review my changes`, `run the security gate`, or `check this diff for vulnerabilities`.
- You say `pr-quality security`.

## When not to use it

- You want all six axes and one merged verdict: use [`pr-quality-all`](pr-quality-all.md) instead.
- You want the full pre-merge review: use [`review`](review.md) instead.
- You want a fast, scriptable command injection scan of staged files: use [`security-scan`](security-scan.md) instead.

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:pr-quality-security main
```

In GitHub Copilot CLI, or in a Claude Code session inside a checkout of this repository, drop the prefix: `/pr-quality-security`.

Pass the branch you merge into. With no argument, the skill uses `main`. It diffs your working changes against that branch and prints the verdict first.

## What you get

The skill prints this block first, with no text before it:

```text
VERDICT: [PASS|WARN|CRITICAL_FAIL]
MESSAGE: [One sentence summary]

[Detailed findings]
```

After the block, it prints a fenced JSON block that follows `.agents/schemas/pr-quality-gate-output.schema.json` and carries `"agent": "security"`.

| Verdict | Meaning |
| --- | --- |
| `PASS` | The axis found nothing to block or warn about. |
| `WARN` | Findings exist. Review them. |
| `CRITICAL_FAIL` | Blocking findings exist. Fix them first. |

Each finding names a file and a line. If the skill cannot read the diff, it returns `CRITICAL_FAIL` and says what blocked the read. It never returns `PASS` for a diff it could not read.

## Advanced use

This axis looks for input that reaches a sink without validation, a credential or token in the diff, a widened authorization boundary, a path built from user data, and a dependency added without provenance. That list orients the read. The criteria file `.github/prompts/pr-quality-gate-security.md` is authoritative, and the skill reads it on every run.

How the skill picks its diff:

1. It resolves the base from your argument, or `main` if you give none. It rejects an empty value or one that starts with `-`.
2. It resolves the base to a commit with `git rev-parse --verify --quiet`. A ref that does not resolve stops the run. It does not fall back to an empty diff.
3. It builds the changed-file list from `git diff "$BASE_SHA" --name-only` plus untracked files from `git ls-files --others --exclude-standard`. It reads untracked files in full.
4. It judges every criterion in the criteria file. It does not stop at the first failure, so you get the whole list in one round.

[`pr-quality-all`](pr-quality-all.md) runs this skill as one of six axes and parses the first `VERDICT:` line. A preamble before that line breaks the merge. It forwards the resolved SHA, so this skill re-resolves a value that cannot move.

To change what this axis checks, edit `.github/prompts/pr-quality-gate-security.md`. To change the default base, edit step 2 of the skill. A new consumer reads the schema-bound JSON block and needs no change to the skill.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`pr-quality-all`](pr-quality-all.md): run all six axes and merge the verdicts.
- [`security-review`](security-review.md): a deeper security review beyond the diff gate.
- [`security-scan`](security-scan.md): a CWE-78 command injection scan.
- Source: [`SKILL.md`](../../src/claude/skills/pr-quality-security/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
