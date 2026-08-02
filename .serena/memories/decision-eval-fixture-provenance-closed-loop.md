# The eval corpus is a closed loop, and the router suite currently measures nothing

## Question

`evals/` holds the fixtures that score this repository's agents and skills. Do
those fixtures measure how the agents behave on prompts real users write, or
only on prompts the repository's own author wrote?

## Conventional answer

The corpus is fine. It carries a `provenance` field, the field is typed against
a closed vocabulary, and a reviewer can see at a glance that provenance was
considered. A corpus that tracks provenance has handled the provenance problem.

## First-principles position

Tracking provenance and having independent provenance are different properties.
This corpus has the first and not the second. The vocabulary was built with an
externally sourced value in it, and that value is used zero times, so the gap is
not an oversight in the schema. It is visible in the data the schema records.

The one suite where prompt wording is the thing under test carries no provenance
field at all, its prompts were written to contain the trigger phrases the change
under test had just added, and it is now pinned to a before-reference that makes
its two arms identical. It reports a difference of zero and that reads as a
measurement.

## Evidence

Measured on `c02f61ddd2` against a clean worktree. Every count below was
reproduced independently by an adversarial reviewer on a different model family.

### The typed corpus is entirely author-worded

Vocabulary, at `scripts/eval/_eval_agent_types.py:19`, annotated "per REQ-004
AC-4":

```python
ProvenanceLiteral = Literal["synthetic", "public-cve", "paraphrased-from-public"]
```

Fixtures under `evals/` carrying a top-level `provenance` key:

| provenance | fixtures |
| --- | --- |
| `synthetic` | 139 |
| `paraphrased-from-public` | 50 |
| `public-cve` | 0 |

189 fixtures across 20 suites. `public-cve` is the one value in the vocabulary
naming an artifact the author did not write, and no fixture uses it. The two
values in use are both author-worded: `synthetic` is written outright, and
`paraphrased-from-public` is public material restated in the author's phrasing.

The constraint is static only. `Fixture` is a plain dataclass with no
`__post_init__`, so the `Literal` is a type-checker hint with no runtime gate.
Confirmed with both controls: a bogus value and a declared value are both
accepted at construction.

### The router suite has no provenance field at all

`evals/skill-router-spike/fixtures.json` is a bare list of 21 items whose keys
are exactly `candidates`, `correct`, `id`, `query`. No item carries a
`provenance` key, so these 21 sit outside the 189 counted above and outside the
typed vocabulary.

Its fixture ids are a constructed per-sibling taxonomy: `memory-01-recall`,
`memory-02-citation-hygiene`, `memory-03-documentary`,
`memory-04-forgetful-guidance`.

The queries share wording with the descriptions they are scored against.
Normalized two-word overlap between each query and its target's description is
**21 of 21**. A stricter exact-bigram check against the pre-#2127 text still
matches 19 of 21, the other two differing only by inserted small words:
`memory-02` asks to "Check the memory's health" against a description carrying
"check memory health"; elsewhere "assess maintainability" meets "Assess the
maintainability", and "catch taste/style invariants" meets "Catch taste and
style invariants".

So the suite measures whether descriptions containing a phrase match queries
containing that phrase, on prompts written after the descriptions they score.

Issue #2127 asks for phrases "the user would actually say" and "verbatim user
phrases", and `scripts/eval/eval_skill_router.py` repeats "a verbatim user
request". Read in context that means phrased the way a user would phrase it, not
copied from a transcript. Nothing in the script, the issue, or the fixtures
records a transcript source.

### The suite is a no-op as currently pinned

`eval_skill_router.py:68` sets `BEFORE_REF = "origin/main"` as a module
constant, and line 13 describes it as "the pre-#2127 description". That was true
when written. #2127 has since merged, so `origin/main` now carries the post-#2127
text and both arms read the same bytes.

Measured with the script's own resolution rule, skill first then agent fallback:

```
candidates=18 identical=18 differ=0 unresolved=0
```

Every candidate description is byte-identical between `origin/main` and `HEAD`.
The run is at temperature 0, so the before and after arms receive identical
input and the reported delta is zero by construction. A zero here means the
comparison is empty, not that the change failed. Nothing in the output says so.

### Prior art in this repository

`.serena/memories/eval-harness-observations.md:21` already records that no true
router or trigger eval exists, meaning one that answers whether an arbitrary
query loads a given skill out of the whole catalog, and it names
`eval_skill_router.py` as a first attempt. That entry is accurate. Do not cite it
as saying the file does not exist.

The repository also already knows how to anchor a fixture to an artifact it did
not author, in a different file under a free-form schema. Four of the seven items
in `scripts/eval/examples/e2e-delivery-fixtures.json` carry values of the form
`merged-pr:https://github.com/rjmurillo/moq.analyzers/pull/1004`. That is a real
external artifact cited by URL. Nothing in the typed corpus does this.

### External evidence, not measured here

A practitioner's self-authored skill-trigger benchmark scored 93% precision on
prompts he wrote and 27% on prompts mined from his own session transcripts. Cited
because it sets the expected direction and rough magnitude, not as a number this
repository has reproduced.

## Decision

Treat every current eval score as an upper bound, not an estimate. The corpus
cannot distinguish "the agent handles this task" from "the agent handles this
task the way its author phrases it."

Treat the router suite as reporting nothing at all until its before-reference is
repaired. Pin `BEFORE_REF` to the pre-#2127 commit or accept it as an argument,
then rerun. Until then describe it as a router-format harness, never as evidence
that #2127 helped or failed to help.

Do not fix the provenance gap by adding a vocabulary value. `public-cve` already
proves a value alone changes nothing. The binding constraint is that no fixture
is sourced from text the author did not write, and the supply of such text
already exists in the local session histories under `~/.copilot/` and
`~/.claude/`.

Three consequences to carry:

- A before-and-after eval pinned to a moving ref decays into a no-op the moment
  the change under test merges. Pin to a commit, not a branch.
- A new eval suite that scores its own author's phrasing inherits the ceiling.
  Say so in the suite's own notes rather than reporting the number bare.
- A routing or trigger improvement measured only against these fixtures is close
  to unfalsifiable, because the corpus contains no prompt phrased the way a user
  who had never read the description would phrase it.
