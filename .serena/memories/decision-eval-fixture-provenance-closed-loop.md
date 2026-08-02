# The eval corpus is a closed loop: every fixture is worded by the author of the thing it scores

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
field at all, and its prompts were written to contain the trigger phrases the
change under test had just added. That is the closed loop in its strongest form:
the eval and the thing it scores were authored together from the same word list.

## Evidence

Measured on `c02f61ddd2` against a clean worktree.

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

### The router suite carries no provenance at all

`evals/skill-router-spike/fixtures.json` is a bare list of 21 items whose keys
are `candidates`, `correct`, `id`, `query`. There is no `provenance` key, so
these 21 sit outside the 189 counted above and outside the typed vocabulary.

`scripts/eval/eval_skill_router.py` scores them. It measures whether the SKIP
clauses issue #2127 added to skill descriptions improve sibling disambiguation,
by showing a model 2 to 4 candidate descriptions plus one query and asking which
candidate matches.

Its docstring calls each query "a verbatim user request". That means phrased the
way a user would phrase it, not taken from a user. The fixture ids are a
constructed taxonomy, one per sibling in tidy families: `memory-01-recall`,
`memory-02-citation-hygiene`, `memory-03-documentary`,
`memory-04-forgetful-guidance`. Each query also carries the trigger phrase that
issue #2127 had just written into the target's description, so
`memory-02-citation-hygiene` asks to "check the memory's health" against a
description rewritten to claim health checking.

So the suite measures whether descriptions containing phrase P match queries
containing phrase P, on prompts written after the descriptions they score, with
the field set narrowed to a handful of pre-chosen siblings rather than the full
skill list.

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
task the way its author phrases it." Treat the router numbers as the loosest
bound of the set, since that suite has no provenance record and its prompts
postdate the descriptions they score.

Do not fix this by adding a vocabulary value. `public-cve` already proves a value
alone changes nothing. The binding constraint is that no fixture is sourced from
text the author did not write, and the supply of such text already exists in the
local session histories under `~/.copilot/` and `~/.claude/`.

Two consequences to carry:

- A new eval suite that scores its own author's phrasing inherits this ceiling.
  Say so in the suite's own notes rather than reporting the number bare.
- A routing or trigger improvement measured only against these fixtures is close
  to unfalsifiable, because the corpus contains no prompt phrased the way a user
  who had never read the description would phrase it.
