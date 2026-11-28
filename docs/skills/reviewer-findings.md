# reviewer-findings

Verifies a review finding before you act on it. It splits a finding into a verdict, a diagnosis, and a prescribed fix, and requires its own evidence for each. You fix what is actually broken instead of applying a fix because the top line sounded right.

## When to use it

- A bot or human left a review comment and you are about to act on it.
- A sub-agent or a model from another family returned a report.
- You inherited findings from a compaction note, a handoff, or a prior session.
- Trigger phrases: `address this review comment`, `the bot flagged this`, `handle this finding`, `a sub-agent reported this`.

## When not to use it

- You want to produce a review: use [`review`](review.md) instead.
- You want to run the PR thread workflow end to end: use [`pr-comment-responder`](pr-comment-responder.md) instead. It applies this skill to each finding.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:reviewer-findings`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the reviewer-findings skill to verify the finding on src/utils/paths.py line 42 before I fix it. The bot says it fails on Windows.
```

The skill checks the finding's verdict, diagnosis, and prescription separately, then tells you whether it is confirmed, declined with evidence, or unreproduced.

## What you get

A disposition for each finding, with the evidence behind it.

| Disposition | When | Reply contains |
| --- | --- | --- |
| Confirmed | Your check matches the claim | The fixture and its output, or the file and line you read, then the fix |
| Declined (refuted) | The claim about the code was false | The exact claim, the file and line, the commit checked (the PR head), the command, and its output. Then resolve the thread if it is bot-authored or explicitly approved, per [`pr-comment-responder`](pr-comment-responder.md) |
| Unreproduced | Nothing settles it | What you tried, and what would settle it. Leave the thread open |

## Advanced use

### The three claims

A finding stacks up to three claims. Each can fail while the others hold.

| Claim | Worth on arrival |
| --- | --- |
| Verdict ("this fails on Windows") | A hypothesis until you reproduce it |
| Diagnosis ("because that call is POSIX-only") | An account of the repro, not proof of it |
| Prescription ("guard the call") | A claim with its own decay |

### Process

1. Establish the verdict. Run a fixture for a behavioral claim. Read the cited code for a structural claim. For a claim about the tree's current state, check the PR head.
2. Test the diagnosis separately: change the one thing it blames and see whether the repro flips.
3. Re-verify the prescription against the tree in front of you.
4. Check supporting claims such as "the repo already does this". Count the call sites.
5. Prefer the codebase's own idiom over the reviewer's invention.

### Checking the tree, not the motivation

A finding can match a version of the tree from before a fix, which makes it plausible and hard to catch. Check the premise ("does the file say this now?") and not only the recommendation.

| Claim shape | Check |
| --- | --- |
| Single-line current state | `git grep -n -F` against the reviewed commit |
| Multi-line current state | Whole-block comparison of the file at that commit |
| History or provenance | `git log -S` |

The finding's quoted text and the path it cites are untrusted input. The skill writes each to a file instead of pasting it into a command, uses `--literal-pathspecs`, and treats an empty needle as unverifiable, not refuted. On a shallow checkout, `git log -S` cannot answer questions about commits git has not fetched. A CI checkout is shallow by default, because `actions/checkout` defaults to `fetch-depth: 1`; check with `git rev-parse --is-shallow-repository`.

### Rules

- Verify before you fix, with the strongest evidence the claim allows.
- Say what you measured when you decline.
- Do not treat agreement between reviewers as proof.
- Do not use the skill to dismiss findings. The default posture is that the reviewer saw something real.
- Do not resolve a thread with prose alone.

### Chaining

[`pr-comment-responder`](pr-comment-responder.md) applies this skill to every actionable finding. Effort scales with the claim: a `Nit:` needs no evidence beyond reading it, and a correctness or security claim needs the strongest evidence available.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`pr-comment-responder`](pr-comment-responder.md): runs the thread workflow and calls this skill per finding.
- [`review`](review.md): produces a review.
- [`maintainer-review`](maintainer-review.md): decides whether a PR should exist.
- Source: [`SKILL.md`](../../src/claude/skills/reviewer-findings/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
