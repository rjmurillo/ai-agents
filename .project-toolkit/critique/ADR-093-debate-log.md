# ADR-093 debate log

Reviewers: `architect`, `critic`. Both read the proposed ADR and the governance
rules it must satisfy. Their verdicts disagreed, which is the useful part.

## Verdicts

| Reviewer | Verdict |
|---|---|
| architect | Accept with one wording change |
| critic | Revise, two blocking items |

## The disagreement that mattered

The critic's central objection: the rule would not have fired in the incident
it documents, because the author believed the local run *was* the same checker.
A rule saying "only claim it is cleared when the checker matches" does not
catch someone who thinks it matches. On that reading the active ingredient is
the fact, not the rule, and the fact lives in GOTCHAS rather than always-on.

The architect reached the opposite conclusion on the same text, resting on the
escape clause: "State the command and why it is the same check; if you cannot,
say the check is red and you could not reproduce it." That clause is a required
artifact, and the author could not have written it truthfully, having no basis
for the equivalence beyond assumption.

Both readings are defensible against the original wording, which is itself the
finding. A rule two competent reviewers read oppositely is underspecified.

**Resolution.** The rule now requires the checker, ruleset, flags, and version
to be *demonstrably identical* rather than to *match*. Belief satisfies
"match"; it cannot satisfy "demonstrably". That is the clause the critic's
objection was asking for and the wording the architect proposed independently,
which is a reasonable signal it is the right change.

## The gap neither the ADR nor the author had considered

The critic asked whether a CI-side fix had been evaluated: ship a semgrep
config so a local run *can* reproduce the check. It had not been, and that was
a real omission. An alternative that removes a failure mode beats one that
documents it, and it costs zero always-on bytes.

Checking it changed the advice:

```
$ semgrep ci --help
When logged in, `semgrep ci` runs rules configured on Semgrep App
and semgrep.dev.
```

So `SEMGREP_APP_TOKEN=<token> semgrep ci` is an exact reproduction, and the
check is locally reproducible after all. The GOTCHAS entry claimed the opposite
and has been corrected.

This weakens the case for the rule on semgrep specifically without removing it.
A token is required, so the reproduction is unavailable to anyone without one,
and the rule governs every remote checker rather than this one. The rule now
has a documented way to be *satisfied* rather than only a way to be *admitted*,
which is a better rule than the one first proposed.

## Items raised and not disputed

- The percentage in the doctrine had not been recalculated against the new
  denominator: 14,152 / 71,640 is 19.8%, not 20.1%.
- The new corpus figures were still attributed to a commit that measured the
  previous corpus, which repeats the stale-attribution error the ADR itself
  describes.
- The GOTCHAS text said "treat a local pass as a necessary condition", which
  contradicts the same section's claim that a clean local result says nothing.
  A pass from a different ruleset is neither necessary nor sufficient.
- The `#4725` citation made the python36 false positives appear to support the
  claim that both taint findings were real. Two incidents, opposite
  conclusions, now separated in the text.
- The session log marked `handoffRead` complete while citing AGENTS.md and
  GOTCHAS.md, which do not support it. Corrected to record when HANDOFF.md was
  actually read rather than back-filling the claim.

## Consensus

Accepted with the wording change and the CI-side alternative documented.
Recorded here as the consensus evidence `governance.md` MUST 3 requires for a
rule that governs every role.
