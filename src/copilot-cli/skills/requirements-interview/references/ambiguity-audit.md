# Ambiguity Audit Reference

Detail for the ambiguity-audit mode of `requirements-interview`. Load it when the
input is an existing multi-section specification. The engine is the
`spec_audit.py` script beside `SKILL.md`. It composes `decision-question`'s
`decision_question.py` for option, question, recommendation, hold, and dependency
bounds, so none of those rules are restated here.

## Scope

This mode owns source-anchored coverage, decision capture, rebuild, and
verification. `decision-question` owns how a single decision is rendered. The
mode does not score question count or document size as quality.

## The ledger

One JSON object. `coverage_reviewed` must list all eight categories, or `check`
returns `invalid`: a clean verdict needs a finished pass.

```json
{
  "coverage_reviewed": ["edge_case", "undefined_state", "permissions", "error_behavior",
                        "data_constraint", "concurrency", "contradiction", "terminology"],
  "candidates": [
    {
      "id": "Q1",
      "category": "contradiction",
      "disposition": "ask",
      "anchors": [
        {"section": "3.1 Session count", "quote": "at most 3 active sessions"},
        {"section": "5.2 Concurrency", "quote": "up to 5 concurrent sessions"}
      ],
      "statement": "How many concurrent sessions may one account hold?",
      "why_now": "Sections 3.1 and 5.2 give different limits.",
      "options": [
        {"id": "three", "label": "3 sessions", "consequence": "A fourth sign-in is refused."},
        {"id": "five", "label": "5 sessions", "consequence": "Storage per account grows."}
      ]
    }
  ],
  "answers": {},
  "paging": {}
}
```

| Field | Rule |
|-------|------|
| `id` | Stable global ID such as `Q1`. Unique. Never renumbered. |
| `category` | One of the eight coverage categories. |
| `disposition` | `ask` (default), `answered_in_document`, or `answered_in_codebase`. |
| `anchors` | Section plus an exact `quote` or a `lines` range `[first, last]`. The quote must appear verbatim in that section (line wrapping ignored). A contradiction needs anchors in two different sections. |
| `evidence`, `answer` | Required for the two `answered_*` dispositions. Document evidence is an anchor. Codebase evidence is `{"path", "lines"}` under `--repo-root`. |
| `recommendation` | Allowed only with `recommendation_reason` and `recommendation_evidence` (repository evidence or an existing contract). Without one, the question carries `Owner decision, no evidence-backed recommendation`. |
| `requires` | Prior answers that keep the decision alive, as in `decision-question`. |
| `answers`, `paging` | Recorded user picks and `_more` counts, as in `decision-question`. |

## Question construction

- One decision per question. Anchor it to the phrase that exposes the gap.
- Options are materially distinct. Prefer mutually exclusive and collectively
  exhaustive options when the domain supports it. Do not list `Other`: the
  harness adds it, and `check` rejects an option labeled `Other`.
- Keep each question answerable with a short selection plus an optional qualifier.
- If the document or the codebase answers it, record the answer with evidence.
  Do not ask.
- A term used without a definition, or defined two ways, becomes a closed
  definition decision with one option per reading.

## Batching and dependencies

`check` returns a `batch` of live decisions, at most the harness question limit
(`--max-questions`, default from `decision_question.py`), in ID order. Each entry
carries its prompt `pages`, capped by `--max-options`. A decision whose
prerequisite is unanswered is listed under `deferred`. An answer that voids a
decision lists it under `pruned`. IDs survive batches, deferrals, and regenerated
dependent questions. A recommendation that an earlier answer removed returns
`revise_recommendation`.

## Verification log

After the user answers, rebuild or patch the spec. Then write a log with one
entry per `ask` candidate and run `spec_audit.py verify`:

```json
[
  {"id": "Q1", "outcome": "accepted",
   "text": "The concurrent session limit is 3 per account.",
   "replaces": ["Each account supports up to 5 concurrent sessions."]},
  {"id": "Q2", "outcome": "open"}
]
```

`verify` fails when:

- an accepted `text` appears other than exactly once in the rebuilt document, or
  already existed in the source;
- a `replaces` quote is missing from the source or still in the rebuilt document;
- an accepted contradiction supersedes no side;
- an `open` ID is not listed exactly once under an `Open decisions` heading, or
  its anchored source text was removed without a decision;
- any source line outside the replaced quotes was deleted;
- an `ask` candidate has no log entry, or a log entry has no candidate.

`growth` in the output reports character counts as an observation only. It never
changes the status.

## Evaluation notes

Score a response on whether anchors are verbatim, whether answered requirements
are recorded instead of asked, and whether the rebuild integrates each decision
once. Do not score by number of questions. The `~400 inconsistencies` figure in
the originating Reddit report has no published source document, deduplication
rule, or definition, so it is not ground truth.
