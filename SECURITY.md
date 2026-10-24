# Security Policy

## Supported Versions

Only the latest commit on `main` is supported. The plugins ship from `main`
without version numbers (ADR-092), so a fix lands for every user on their next
plugin update.

| Surface | Supported |
|---|---|
| `main` branch, all plugin trees under `src/` | Yes |
| Forks, older commits, local edits | No |

## Reporting A Vulnerability

Report privately through GitHub:
<https://github.com/rjmurillo/ai-agents/security/advisories/new>

Do not open a public issue for a vulnerability. Include:

- the affected file, hook, skill, or agent;
- the host (Claude Code, GitHub Copilot CLI, Codex, Cursor) and its version;
- steps to reproduce, and what an attacker gains.

Confirmed issues are fixed on `main` and disclosed in a GitHub security
advisory once the fix ships.

## Scope

In scope: hooks and scripts that run on a user's machine, skills and agents
that execute commands, plugin and marketplace manifests, and GitHub Actions
workflows in this repository.

Out of scope: intentionally vulnerable samples under
`.project-toolkit/security/benchmarks/vulnerable_samples/` and test fixtures
that contain fake credentials.
