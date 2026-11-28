# security-detection

Checks a list of changed files against known security-critical patterns. It tells you whether a change needs the security agent. It only detects. It does not scan source code for vulnerabilities.

## When to use it

- You are about to commit changes that may touch infrastructure or security files.
- You want a pre-commit or CI gate for security-sensitive paths.
- You need to know whether a security agent review is warranted.
- Trigger phrases: `scan for security changes`, `check security-critical files`, `does this change need security review`, `do I need a security review`, `check infrastructure changes`, `did I touch security-critical files`.

## When not to use it

- You want to scan source for injection patterns: use [`security-scan`](security-scan.md).
- You already know you need a review, or you need threat modeling or in-depth auth review: use the [`security`](../agents/security.md) agent directly.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:security-detection`. The agent loads it when your request matches, and [`autoplan`](autoplan.md) routes "did I touch security-critical files" questions here. To ask for it by name, say:

```text
Use the security-detection skill to check my staged files and tell me whether the security agent needs to review them.
```

The skill lists each match with a risk level. For a CRITICAL match it tells you to delegate to the security agent.

## What you get

When files match:

```text
=== Security Review Detection ===

CRITICAL: Security agent review REQUIRED

Matching files:
  [CRITICAL] .github/workflows/deploy.yml
  [CRITICAL] src/Controllers/AuthController.cs
```

When nothing matches, it prints `No infrastructure/security files detected.`

| Level | Meaning | Action | Example patterns |
| --- | --- | --- | --- |
| CRITICAL | Immediate security implications | Review required | `.github/workflows/*`, git hook config (lefthook, `.husky/*`), [`scripts/validation/git_hook_policy.py`](../../scripts/validation/git_hook_policy.py), [`scripts/validation/adr_debate_evidence.py`](../../scripts/validation/adr_debate_evidence.py), `**/Auth/**`, `**/Security/**`, `*.env*`, `*.pem`, `*.key`, `*secret*` |
| HIGH | Potential security impact | Review recommended | `build/**/*.ps1`, `scripts/**/*.sh`, `Dockerfile*`, `docker-compose*`, `**/Controllers/**`, `appsettings*.json`, `*.tf`, `*.tfvars`, `*.bicep` |

## Advanced use

Run the detector from the root of a checkout of this repository:

```bash
uv run python .claude/skills/security-detection/detect_infrastructure.py --files .github/workflows/ci.yml src/auth/login.cs --json
```

| Flag | Meaning |
| --- | --- |
| `--files` | Changed file paths to analyze. |
| `--use-git-staged` | Analyze staged files from git. |
| `--files-from-stdin` | Read NUL-delimited changed paths from stdin. |
| `--json` | Output results as JSON. |
| `--require-security-review` | Exit 1 on a CRITICAL finding unless `--ref` carries a security review marker. Exit 3 when git cannot answer. |
| `--ref` | Commit whose marker is checked. Default `HEAD`. |
| `--base-ref` | Ref a merge above the marker must pull from. Default `origin/main`. |
| `--diff-base` | Commit the changed files are measured from. A CRITICAL file that changed only plain comments then needs no marker. |
| `--repo-root` | Repository root. Default is the current directory. |

`--files`, `--use-git-staged`, and `--files-from-stdin` are mutually exclusive.

| Exit code | Meaning |
| --- | --- |
| 0 | Detection finished. Matches print a warning that does not block. |
| 1 | `--require-security-review` is set and a CRITICAL file has no valid marker. |
| 3 | `--require-security-review` is set and git could not answer. An unanswered check never counts as a marker. |

Without `--require-security-review`, the script always exits 0, so advisory use stays non-blocking. In CI, pipe `git diff --no-renames --name-only -z "$BASE_SHA" "$HEAD_SHA"` into `--files-from-stdin`, because CI checkouts have no staged diff. To change what counts as critical or high, edit `CRITICAL_PATTERNS` and `HIGH_PATTERNS` in the script.

Delegation to the security agent uses the host's subagent tool. If the host has none, run the review yourself in the session.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`security`](../agents/security.md): the agent this skill routes CRITICAL findings to.
- [`security-scan`](security-scan.md): scans source for command injection patterns.
- [`security-review`](security-review.md): inline security review of a diff.
- [`codeql-scan`](codeql-scan.md): full static analysis after detection finds high-risk changes.
- Source: [`SKILL.md`](../../src/claude/skills/security-detection/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
