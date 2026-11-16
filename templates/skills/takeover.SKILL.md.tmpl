---
name: takeover
version: 1.0.0
license: MIT
description: Take over existing work and finish its original goal while keeping the original contributors' credit. Use when you say `take over this PR`, `take over this branch`, `take over this thread`, or `takeover`. Do NOT use to answer review threads on your own PR (use pr-comment-responder), to only resolve merge conflicts (use merge-resolver), to triage many open PRs (use pr-autofix), or to attribute a blocked check (use repository-pr-recovery).
user-invocable: true
metadata:
  routing:
    role: front-door
    invoker: autoplan
    trigger: autoplan matches a request to take over another contributor's PR, branch, or agent thread
    user-facing: true
    intents:
      - take over this PR
      - take over this branch
      - take over an agent thread
      - finish someone else's PR
      - continue an abandoned PR
---
# Takeover

Forked from t3dotgg/tstack by Theo Browne, under MIT.
Copyright (c) 2026 Theo Browne. See `LICENSE`.
Maintainers: read `references/upstream-sync.md` before reconciling upstream changes.

Take responsibility for finishing the original goal while preserving the
original contributors' credit. Do not defend an implementation just because
another agent already built it.

## Triggers

| Trigger phrase | Source |
|---|---|
| `take over this PR` | An open or closed pull request |
| `take over this branch` | A pushed or local branch |
| `take over this thread` | Another agent's session or thread |
| `takeover` | Whatever source the request names |

## Process

1. **Inherit.** Read the source PR, branch, or thread, including review
   findings and the user's later corrections. Resolve the handoff to the
   actual code and current head, and account for uncommitted work. Treat the
   handoff as context, not proof.
2. **Branch.** For a replacement PR, import the original commits onto a new
   branch and add your fixes separately. Honor an explicitly requested
   in-place or stacked continuation instead. Do not overwrite unrelated work
   or change the original PR without authorization.
3. **Credit.** Preserve Git authorship and existing co-author trailers. Credit
   the original contributors in the PR description and link the original PR
   when there is one. If the work will be squashed, preserve human
   author/co-author credit in the merge commit too, using verified identities
   rather than guessed emails. Model attribution is not a substitute for
   contributor credit.
4. **Update.** Update the continuation against its intended base and current
   architecture. Rework what is necessary to finish the same goal, not
   unrelated features. Simplify the implementation without dropping intended
   behavior or surfaces. Recheck the source PR too: it may have improved while
   you were working. Use `merge-resolver` when the update hits conflicts.
5. **Verify.** Independently verify the original failure and realistic
   workflows, following repository guidance and permissions. Green mocked
   tests do not prove the user experience works. State what remains
   unverified.
6. **Finish.** When the requested finish includes a PR, use `push-pr` to file
   it. Do not stop at creation: follow checks with the `github` skill and
   answer review threads with `pr-comment-responder`. Merge or close the
   original PR only when authorized.

## Verification

Report each item before you call the takeover done:

- [ ] What you inherited: source, head SHA, and uncommitted work
- [ ] What you changed, kept separate from the imported commits
- [ ] How you verified it, and what remains unverified
- [ ] How credit was preserved: authors, trailers, PR link
- [ ] Any remaining decision for the user

## Anti-Patterns

| Avoid | Instead |
|---|---|
| Defending inherited code because an agent wrote it | Judge it against the original goal |
| Squashing away the original authors | Keep authorship and co-author trailers |
| Guessing a contributor's email | Use a verified identity |
| Editing or closing the original PR unasked | Get authorization first |

## Extension Points

Map new upstream steps to local skills in `references/upstream-sync.md`.
