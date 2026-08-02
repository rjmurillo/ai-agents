# The fixture corpus extends a known closed loop, and the router suite currently measures nothing

## Prior art, read this first

The closed-loop thesis is already settled here. Do not rediscover it.

- Issue #3509 measured it: 22 of 212 documented trigger phrases, 10.4%, have
  ever appeared in a real user prompt; 8 of 140 promoted into descriptions, 5.7%.
- `.agents/governance/skill-description-trigger-standard.md:267` carries those
  numbers in an Independent-Distribution Validation section.
- `.serena/memories/decision-neither-session-store-carries-usable-authorship.md`
  records why the obvious fix does not work.

This entry adds two things that prior art does not cover: the same loop measured
on the **eval fixture corpus** rather than on trigger phrases, and a live defect
that makes the router suite report nothing.

## Question

Trigger phrases were measured. The fixtures under `evals/` were not. Do they
carry independent provenance, and does the suite that scores routing still
measure the change it was built for?

## Conventional answer

The fixture corpus is in better shape than the trigger phrases were, because it
carries an explicit `provenance` field typed against a closed vocabulary. A
corpus that records provenance has handled the provenance problem.

## First-principles position

Recording provenance and having independent provenance are different properties.
The corpus has the first and not the second, and it says so in its own data: the
vocabulary was built with an externally sourced value in it, and that value is
used zero times.

Separately, the suite where prompt wording is the thing under test has no
provenance field at all and is pinned to a before-reference that makes both of
its arms identical. It reports a delta of zero, and that reads as a measurement.

## Evidence

Measured on `c02f61ddd2` against a clean worktree. Every count was reproduced
independently by an adversarial reviewer on a different model family.

### The typed corpus is entirely author-worded

`scripts/eval/_eval_agent_types.py:19`, annotated "per REQ-004 AC-4":

```python
ProvenanceLiteral = Literal["synthetic", "public-cve", "paraphrased-from-public"]
```

| provenance | fixtures |
| --- | --- |
| `synthetic` | 139 |
| `paraphrased-from-public` | 50 |
| `public-cve` | 0 |

189 fixtures across 20 suites. `public-cve` is the only value naming an artifact
the author did not write, and nothing uses it. Both values in use are
author-worded: `synthetic` is written outright, `paraphrased-from-public` is
public material restated in the author's phrasing.

The constraint is static only. `Fixture` is a plain dataclass with no
`__post_init__`, so the `Literal` is a type-checker hint with no runtime gate.
Confirmed with both controls: bogus and declared values are both accepted.

### The router suite has no provenance field

`evals/skill-router-spike/fixtures.json` is a bare list of 21 items keyed exactly
`candidates`, `correct`, `id`, `query`. No item carries `provenance`, so these 21
sit outside the 189 and outside the typed vocabulary. Their ids are a constructed
per-sibling taxonomy: `memory-01-recall`, `memory-02-citation-hygiene`,
`memory-03-documentary`, `memory-04-forgetful-guidance`.

Normalized two-word overlap between each query and its target's description is
**21 of 21**. A stricter exact-bigram check against pre-#2127 text holds at 19 of
21, the two misses differing only by inserted small words: "Check the memory's
health" against a description carrying "check memory health"; "assess
maintainability" against "Assess the maintainability".

Issue #2127 asks for phrases "the user would actually say", and the script
repeats "a verbatim user request". In context that means phrased the way a user
would phrase it, not copied from a transcript. Nothing in the script, the issue,
or the fixtures records a transcript source.

### The suite is a no-op as currently pinned

`eval_skill_router.py:68` sets `BEFORE_REF = "origin/main"` as a module constant,
and line 13 calls it "the pre-#2127 description". True when written. #2127 has
merged, so `origin/main` now carries the post-#2127 text and both arms read the
same bytes.

Measured with the script's own resolution rule, skill path first then agent
fallback:

```
candidates=18 identical=18 differ=0 unresolved=0
```

Runs are at temperature 0, so the delta is zero by construction. A zero means the
comparison was empty, not that the change failed. Nothing in the output says so.

Checking only `.claude/skills/` gives a misleading 16 identical and 2 unresolved;
`milestone-planner` and `task-decomposer` are agents, and the script falls back
to `.claude/agents/<name>.md`.

### The repository can anchor a fixture externally, in one place

Four of the seven items in `scripts/eval/examples/e2e-delivery-fixtures.json`
carry values like `merged-pr:https://github.com/rjmurillo/moq.analyzers/pull/1004`,
a real external artifact cited by URL, under a free-form schema. Nothing in the
typed corpus does this.

## Decision

Treat every current eval score as an upper bound, not an estimate. Treat the
router suite as reporting nothing until its before-reference is repaired: pin
`BEFORE_REF` to the pre-#2127 commit or make it an argument, then rerun. Until
then describe it as a router-format harness, never as evidence about #2127.

Do not close the provenance gap by adding a vocabulary value. `public-cve`
already proves a value alone changes nothing.

**Do not propose mining the local session stores as the supply of real prompts.**
That path is closed and the reason is recorded in
`decision-neither-session-store-carries-usable-authorship.md`: Copilot's store
has no author field and the harness writes machine text into the column named for
the human, and Claude's `promptSource` label is trustworthy but covers 1% of
entries. Four attempts assumed otherwise and each produced a confident wrong
number. PR #3513 was withdrawn on this.

Two general lessons:

- A before-and-after eval pinned to a moving ref decays into a no-op the moment
  the change under test merges. Pin to a commit, not a branch.
- A new eval suite scoring its own author's phrasing inherits the 10.4% ceiling
  #3509 measured. Say so in the suite's own notes rather than reporting the
  number bare.
