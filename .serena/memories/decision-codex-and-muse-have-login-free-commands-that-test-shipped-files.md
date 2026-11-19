# EUREKA: Codex and Muse Code have login-free commands that test shipped files without a model call

## Question

Proving that shipped Codex or Muse files load seems to need a logged-in session and a model call. Does it?

## Conventional answer

Install the host CLI, sign in, run a prompt, and see whether the skill or agent appears. ADR-115 Decision 8 even requires a logged-in Muse Code run before merge.

## First-principles position

Both CLIs have subcommands that read the files and report without credentials. The 2026-11-11 issue 7226 comment says both build a prompt or validate skills with no login. Re-run on 2026-11-11 with an empty config directory:

| Host | Command | Result |
|---|---|---|
| Muse Code 1.4.15 | `HOME=<empty dir> muse skills validate src/muse/skills/adr-generator/ --json` | `compatibility.result` is `compatible`, no diagnostics |
| Codex 0.167.0 | `CODEX_HOME=<empty dir> codex debug prompt-input "hello"` | exit 0, prints the model-visible prompt input list as JSON |

The issue comment also records that `muse skills validate` accepted all 105 shipped skills. That count is from the comment, not re-run.

## Limits

- The Codex command renders the prompt. A probe `.codex/agents/probe.toml` placed in a scratch git repository did not appear in its output. So this memory does NOT show that `prompt-input` proves a custom agent loads. Whether a trusted project or a feature flag is needed is untested.
- `muse skills validate` checks skills. It says nothing about agents.
- A login-free pass does not replace the logged-in Muse Code run that ADR-115 Decision 8 requires.

## Practice

Use the login-free command first. It is fast and works in CI and in a scratch `HOME`. Treat its output as a load check for what it reads, and state which files it did not cover.

## Evidence

- Issue 7226 comment `issue-7226-agents-status`, line "Login-free load checks".
- The two commands above, run 2026-11-11 against `origin/main` at `c4550d9ee`.

## Relations

- **related_to**: [decision-codex-and-muse-could-run-our-agents-the-blocker-was-task-syntax](decision-codex-and-muse-could-run-our-agents-the-blocker-was-task-syntax.md)
