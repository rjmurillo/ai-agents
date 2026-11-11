# Answer review comments and get a verdict with /pr-review

## Goal

Respond to the review comments on one or more PRs, then run the completion gate
once per PR. The gate tells you whether each PR can merge.

## Before you start

- PR numbers, or `all-open`. With `all-open`, the skill caps the list at 5 PRs by
  default and reports the overflow.
- `gh auth status` shows you are signed in. `uv` is installed.
- You have read [Respond to review threads](how-to-respond-to-review-threads.md).
  `/pr-review` runs that skill once per PR.

## Steps

1. Run the skill:

   ```text
   /pr-review 1234
   /pr-review 12 15 --parallel
   ```

   `--parallel` gives each PR its own git worktree. `--dry-run` prints the planned
   actions as JSON and changes nothing.

2. Let it verify trust first. Before any other command, the skill checks that the
   review config and the scripts it names match the trusted ref (`origin/main`).
   A PR could rewrite them after `gh pr checkout`. The check runs nothing:

   ```bash
   uv run python .claude/skills/github/scripts/pr/run_completion_gate.py \
     --config .claude/skills/pr-review/pr-review-config.yaml \
     --pull-request <PR> --verify-config-only --harness claude_code --json \
     | jq -c '{verified, config_trust, command_trust, blocking_unverifiable_command_tokens}'
   ```

   On a clean checkout you see:

   ```json
   {"verified":true,"config_trust":"trusted","command_trust":"trusted","blocking_unverifiable_command_tokens":[]}
   ```

   Exit 2 means the config or a named script differs from the trusted ref. Show the
   diff to a person and stop. Exit 3 means the check cannot run at all, for
   example outside a git work tree. Fix the environment. Never pass
   `--approve-untrusted-config` yourself.

3. Let it pick the transport once. If `gh` is blocked for the whole session, every
   script fails with HTTP 403 for a reason that has nothing to do with the PR. The
   skill then reads GitHub through MCP tools. It never turns a transport failure
   into a verdict about a PR.

4. Let it cluster and respond. It runs thread clustering, then
   `pr-comment-responder` for each PR. Replying does not resolve a thread. The
   responder resolves each one.

5. Let it settle. After the last thread closes, the skill waits for three zero
   readings in a row, 180 seconds apart. One zero can be wrong, because a bot
   scan can land 30 to 120 seconds after your push.

6. Run the completion gate. It runs once per PR:

   ```bash
   uv run python .claude/skills/github/scripts/pr/run_completion_gate.py \
     --config .claude/skills/pr-review/pr-review-config.yaml \
     --pull-request <PR> --json
   ```

   | Exit | Meaning |
   |---|---|
   | 0 | Every criterion passed. |
   | 1 | At least one criterion failed. Fix it before you claim anything. |
   | 2 | The config is wrong, or it differs from the trusted ref. |
   | 3 | The gate could not run the trust check, or the verdict is `unknown`. |

## Unknown is not fail

A criterion the gate could not verify never passes. ADR-120 adds a second
outcome for one case. In a session where GitHub refuses `gh`, a healthy PR used to
read as failed. Now the gate measures the refusal itself, with two fixed `gh`
calls. It never reads refusal text from verifier output, because a PR author can
write that text. When the refusal is real, the rows read `unknown`, the payload
says `verdict: unknown`, and the exit code is 3.

Two rules follow:

- A failed row outranks an unknown row. Any failure gives `verdict: fail`, exit 1.
- Exit 1 is always an answer. Only a verifier exit above 1, or a verifier that
  reports `api_error: true`, can read as unknown.

When the verdict is unknown, check each criterion by hand with the GitHub MCP
tools. Mark any criterion you cannot read as `unknown`. Do not retry, and do not
arm a merge.

## Check your result

- Each PR has a gate verdict from one run.
- Every thread on it is replied to and resolved.
- If the gate exited 1, you have the failing criterion's name, command, reason,
  and output. You do not re-run the gate for a different answer. The verifier is
  deterministic, so a retry gives the same answer. Fix the cause, then run it once
  more.

## If it fails

| What you see | What to do |
|---|---|
| Verify-config exit 2 | Read the printed diff. A person approves it or you stop. |
| `PyYAML is required to parse the completion-gate config` | Use `uv run --with pyyaml python ...`. A bare `pip install` may change an environment the next run never uses. |
| `warning: true` from clustering | Halt the per-thread loop. Fix the shared source first. |
| Gate exit 3 with `verdict: unknown` | The session is refused, not the PR. Report unknown. |

## Next

- [Let pr-autofix drive a PR](how-to-pr-autofix.md)

## Reference

- [pr-review skill](../../.claude/skills/pr-review/SKILL.md)
- [Trust boundary](../../.claude/skills/pr-review/references/trust-boundary.md)
- [ADR-059: completion gate dispatcher](../../.project-toolkit/architecture/ADR-059-pr-review-completion-gate-dispatcher.md)
- [ADR-120: refused session reads as unknown](../../.project-toolkit/architecture/ADR-120-completion-gate-unknown-verdict.md)
