# The eval corpus is a closed loop: every fixture is worded by the author of the thing it scores

## Question

`evals/` holds the fixtures that score this repository's agents and skills. Do
those fixtures measure how the agents behave on prompts real users write, or
only on prompts the repository's own author wrote?

## Conventional answer

The corpus is fine. It carries a `provenance` field on every fixture, the field
is typed against a closed vocabulary, and a reviewer can see at a glance that
provenance was considered. A corpus that tracks provenance is a corpus that has
handled the provenance problem.

## First-principles position

Tracking provenance and having independent provenance are different properties.
This corpus has the first and not the second. The vocabulary was even built with
an externally sourced value in it, and that value is used zero times, so the gap
is not an oversight in the schema. It is visible in the data the schema records.

The distinction matters specifically for trigger and routing evals, where the
wording of the prompt is the thing under test. When the person who wrote the
skill also writes the prompt that is supposed to fire it, both sides share one
vocabulary, and the score measures self-consistency rather than reach.

## Evidence

Measured on `c02f61ddd2`, all commands run against a clean worktree.

Vocabulary, at `scripts/eval/_eval_agent_types.py:19`, annotated "per REQ-004
AC-4":

```python
ProvenanceLiteral = Literal["synthetic", "public-cve", "paraphrased-from-public"]
```

Corpus, counted over `evals/**/*.json` with a top-level `provenance` key:

| provenance | fixtures |
| --- | --- |
| `synthetic` | 139 |
| `paraphrased-from-public` | 50 |
| `public-cve` | 0 |

189 fixtures across 20 suites. `public-cve` is the one value in the vocabulary
that names an artifact the author did not write, and no fixture uses it. The two
values in use are both author-worded: `synthetic` is written outright, and
`paraphrased-from-public` is public material restated in the author's phrasing.
No fixture is drawn from a session transcript.

The constraint is static only. `Fixture` is a plain dataclass, so the `Literal`
is a type-checker hint with no runtime gate. Confirmed with both controls:

```text
Fixture(provenance="totally-invalid-value")  -> accepted at runtime
Fixture(provenance="public-cve")             -> accepted at runtime
```

The repository already knows how to anchor a fixture to an artifact it did not
author, in a different file under a free-form schema. Four of the seven items in
`scripts/eval/examples/e2e-delivery-fixtures.json` carry values of the form
`merged-pr:https://github.com/rjmurillo/moq.analyzers/pull/1004`. That is a real
external artifact, cited by URL. Nothing in the typed corpus does this.

`.serena/memories/eval-harness-observations.md` records that no skill router or
trigger eval exists in this repository at all, so the closed loop has never been
measured here.

External evidence for the size of the effect, not measured in this repository:
a practitioner's self-authored skill-trigger benchmark scored 93% precision on
prompts he wrote and 27% on prompts mined from his own session transcripts. Cited
because it sets the expected direction and rough magnitude of the inflation, not
as a number this repository has reproduced.

## Decision

Treat every current eval score as an upper bound, not an estimate. The corpus
cannot distinguish "the agent handles this task" from "the agent handles this
task the way its author phrases it."

Do not fix this by adding a vocabulary value. `public-cve` already proves that a
value alone changes nothing. The binding constraint is that no fixture is sourced
from text the author did not write, and the supply of such text already exists in
the local session histories under `~/.copilot/` and `~/.claude/`.

Two consequences to carry:

- A new eval suite that scores its own author's phrasing inherits this ceiling.
  Say so in the suite's own notes rather than reporting the number bare.
- Any claim that a routing or trigger change improved matching is unfalsifiable
  against this corpus, because the corpus contains no prompt the change could
  fail to match in the way a real user would phrase it.
