# EUREKA: an agent's own "ready to ship" carried no information; 9 of 9 were refuted

## Question

When an implementation agent runs its own tests, reports negative controls, and
declares its work complete, how much of the verification budget can be skipped?

## Conventional answer

An agent that has written the test, run it, watched it fail without the fix and
pass with it, has done the thing verification is for. Re-reviewing that is
duplicated work, and the usual advice is to reserve independent review for
high-consequence changes. `.claude/rules/builder-ethos.md` already warns that a
model reviewing its own output is one closed loop, but treats scaling review to
consequence as the remedy.

## First-principles position

Self-assessment and review do not measure the same thing. The author's tests
answer "does my change do what I intended", and every failure below was a case
where the intent itself was wrong, unreachable, or incomplete. No amount of
running your own suite detects a fix that calls a flag which does not exist,
because the test was written against the same false premise as the code.

## Evidence

Measured 2026-08-03 on this repository, one session, 9 independent cases. In
every case the agent reported completion and an independent reviewer holding
only the artifact, never the reasoning, found otherwise. Nothing survived.

Round 1, 6 fix branches, 3 reviewers each through different lenses:

| Branch | What the author missed |
|---|---|
| push-lock-and-force-push | `gh pr view --head` does not exist. `gh pr view --head x --json baseRefName` returns `unknown flag: --head` on gh 2.97.0, so the fix was inert. Its test faked a `gh` that accepted the flag, so the suite confirmed the author's premise instead of the binary's behavior. |
| session-and-eval-gates | Routed a script through a module importing `markdown_it`, but `.github/workflows/ai-spec-validation.yml:126` invokes it with bare `python3`. Would have taken the required check `Validate Spec Coverage` red on every PR while passing locally under `uv`. |
| gh-auth-quota-classification | Claimed the root cause was fixed once in the shared helper. Five named sibling call sites still carried it. |

Round 2, corrections of 3 of those branches, each re-checked independently:

| Branch | Self-assessed | Re-check |
|---|---|---|
| push-lock-and-force-push | `ready_to_push=True` | 1 finding still open, 1 new defect |
| ci-verification-gaps | `ready_to_push=True` | 2 still open, 1 new defect |
| mutation-guard-corpus | `ready_to_push=True` | 1 partial, 2 new defects |
| gh-auth-quota-classification | `ready_to_push=True` | all 17 closed, but 1 new defect |

Three of four corrections introduced a NEW defect while fixing the old ones.
`ci-verification-gaps` reintroduced issue #4286's exact bug: a docstring rewrap
moved a guard finding from line 83 to 85 and the line-keyed baseline read it as
lost coverage, `2 failed, 9 passed`, bisected to commit `4463c3965`.

The last row is the sharpest, because that branch was genuinely good. Its one
new defect was a guard that did not bite: `TestGraphqlRetryEnvelope` asserted
`sleeps[0] <= REFUSAL_BACKOFF_SECONDS[0]`, an upper bound that every value of
the old 1s/2s ladder also satisfies. Reverting the retry ladder left the file at
`50 passed` while the worst-case budget fell from 45s to 3s, back inside the
refusal window it existed to outlast. An author cannot catch this by running the
test, because the test passes. Only inverting the fix and watching the test
still pass finds it.

Two of the nine were mine, not a subagent's: I filed #4395 as a duplicate of
#4324 and re-derived a trap already recorded in
`new-pr-stale-main-ref-trap.md`, both because I skipped the BLOCKING Serena
init.

## Decision

Do not let an implementation agent's own completion signal gate a push. Pair
every implementation stage with a separate agent that receives the artifact and
not the reasoning, and require it to reproduce each claim by running the command
rather than reading the code. The re-check stage costs roughly one extra agent
per branch and caught a defect in 4 of 4 corrections, so it pays for itself on
the first branch it stops.

Two cheap checks caught most of it, and both are mechanical:

1. **Run the real binary.** A fix that calls a flag or endpoint must be proven
   against the installed tool, not against a fake the author also wrote.
2. **Invert the fix and rerun.** A test that passes with the fix reverted proves
   nothing. Delete `__pycache__` between runs or the interpreter may execute the
   previous bytecode (`.claude/rules/testing.md` SHOULD 8).

Related: `.claude/rules/testing.md` SHOULD 9 landed on main during this session
and states the same requirement from the test-design side.
