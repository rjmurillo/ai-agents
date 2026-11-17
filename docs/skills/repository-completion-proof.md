# repository-completion-proof

Proves that a pull request in this repository is complete after review, recovery, or trust verification. It reports three results: execution trusted, criteria passed, and requested outcome observed.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You want to prove a PR is complete: `prove an ai-agents PR is complete`.
- Review is done but completion is unclear: `review is finished but completion is uncertain`.
- You want trust verified before review commands run: `verify before dispatching review commands`.

## When not to use it

- You need to prove consumer behavior: use [`repository-consumer-proof`](repository-consumer-proof.md) instead.
- The PR is blocked or a check is missing: use [`repository-pr-recovery`](repository-pr-recovery.md) instead.

## Quick start

This skill is not a front door, so you rarely start it yourself. In a Claude Code session inside this repository you can still type `/repository-completion-proof`. The agent loads it when your request
matches. To ask for it by name, say:

```text
Use the repository-completion-proof skill to prove that PR 1234 in this repository is complete.
```

The agent verifies the review config and command files, checks the merged state, runs the completion gate, and reports each result separately.

## What you get

Three separate results: execution trusted, criteria passed, requested outcome observed. The gate output carries `all_passed` and a result per criterion. A merged PR is checked as a merged artifact instead of against the open-PR criteria.

## Advanced use

The skill needs the inputs PR number, acceptance criteria, and authorized scope. It runs in three phases: prove execution trust, run completion criteria after verified review work, then separate readiness, acceptance, and downstream completion. Verification passes only when `verified: true`; an untrusted config is surfaced for human inspection. `--approve-untrusted-config` is for use only after explicit human review, and never for an unverifiable Git state. After the final push the skill requires three consecutive complete-and-zero readings from the config's `wait_for_settled_zero`. Unresolved security threads are not force-resolved.

`instruments.py` lists and runs the linked checks.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/repository-completion-proof/scripts/instruments.py --repo . list
uv run python .claude/skills/repository-completion-proof/scripts/instruments.py --repo . run <id>
```

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`repository-pr-recovery`](repository-pr-recovery.md): attributes a blocked PR or missing check.
- [`repository-consumer-proof`](repository-consumer-proof.md): proves consumer behavior and releases.
- [`pr-review`](pr-review.md): config resolution and the settling contract.
- [`pr-comment-responder`](pr-comment-responder.md): reconciles each review thread.
- [`reviewer-findings`](reviewer-findings.md): verifies findings before changes.
- [`ship`](ship.md): authorized shipping handoff.
- Source: [`SKILL.md`](../../.claude/skills/repository-completion-proof/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
