# A shipped plugin routed users to a skill it deliberately does not contain

Session 3716. Branch `fix/autoplan-dangling-skill-route`. One route fixed, one
gate added.

- Issue: #3716
- Starting commit: `95da12691b`
- Artifacts: `scripts/validation/check_shipped_skill_routes.py`, its tests, the
  routing fix in both trees, and registration in the local and CI gates

## What this was

The wiki concept "Coordination Drift Is an Architecture Risk" makes a testable
claim: parallel discovery systems disagree about what is active while each
passes its own tests. This repository maintains two skill trees. Auditing the
claim against them found a live defect in a shipped plugin.

`src/copilot-cli/skills/autoplan/SKILL.md` line 93 routed merge-conflict work
to `Skill: merge-resolver`. The Copilot toolkit does not contain that skill. A
consumer who installed project-toolkit and hit a merge conflict was sent to a
route that does not resolve.

## Nobody made a mistake

That is the interesting part. Both edits were correct in isolation.

Issue #2026 dropped `merge-resolver` from the Copilot shipping set on purpose.
The skill is hard-wired to this repository's layout: `gh`, `.agents/sessions`,
`.serena`, session-protocol scripts. Shipping it to a consumer repo would give
them a skill that fails on first use. The exclusion is right, and
`templates/platforms/copilot-cli.yaml` line 18 records the reasoning.

The routing table is also right, in the tree it was written for. `.claude/`
has the skill. The Copilot copy is byte-identical to its canonical source,
which is what the generation-drift gates check and what they found.

Two control planes. Each internally consistent. Each passing its own tests.
Disagreeing about what is reachable.

## Why every gate passed

The gates ask whether the shipped copy matches its source. That is a real
question and the answer was yes. It is not the same question as whether the
shipped copy's references resolve in the shipped tree.

No gate compared a tree's routes against that same tree's contents. The defect
lived exactly in the space between two correct checks. Adding a stricter
version of either existing gate would not have found it.

## What I got wrong on the way

The first test file used importlib to load the validator. It failed at
collection with an `AttributeError` inside `@dataclass`, because the module is
absent from `sys.modules` when the decorator runs. I had written the tests to
the shape I expected rather than reading how this repository tests validators.
`tests/validation/test_check_adr_uniqueness.py` uses subprocess, which also
exercises the CLI exit contract that TESTING-RIGOR requires. Rewriting to match
was strictly better, not merely conformant.

The lesson generalizes past this file: when a test harness fights you, check
the local convention before inventing around the friction.

## Two closed loops, both broken deliberately

The tests validate a validator written in the same session. That is one closed
loop, and a green suite proves nothing about it.

Two controls broke the loop. A mutation control neutered the gate's failure
branch and confirmed exactly the four negative tests fail while the ten others
stay green, so the negatives are load-bearing. A negative control stashed the
routing fix to restore the real historical defect, not a synthetic one, and
confirmed the gate exits non-zero with the precise file, line, and missing
path, then exits zero again when the fix returns.

The second control matters more. A synthetic fixture proves the regex works. A
replay of the actual incident proves the gate would have caught the thing it
was built for.

## Precision over recall, on purpose

A bare `Skill: <word>` scan produces a false positive on a checklist line where
`create` follows the label as an English verb. The filter reports a name only
when that name exists as a skill in the canonical tree.

That is not a workaround for the false positive. It is the drift signature
stated directly: the canonical tree has it, the shipped tree dropped it, and a
reference survives. An unknown name is prose or a typo, which is a different
defect class and not worth the false-positive rate.

## Registered twice, on evidence

Reachability was the first question, because issue #3329 shipped two gates with
green tests and no caller anywhere. The gate now runs in `pre_pr.py`, which
lefthook invokes pre-push, and as a CI step beside its sibling self-containment
gate.

Paying for it in both places needed a number, not an argument. The gate runs in
137ms. Local feedback saves a push-fail round trip, CI makes the enforcement
durable, and both call the same script, so there is one source of truth.

## What this does not cover

The gate scans `Skill:` labels. A routing table that names a skill in some
other shape, for example a bare markdown link into a skill directory, is
invisible to it. `SHIPPED_TREES` lists `src/copilot-cli` alone, and nothing
forces a third shipping tree to be added there.

Both are recorded in the session log rather than fixed here. The gate closes
the class that actually shipped a defect.
