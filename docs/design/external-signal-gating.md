# External-Signal Gating for AI Quality Workflows

> Status: design (scripts shipped, workflow wiring tracked in follow-up).
> Origin: issue [#1855](https://github.com/rjmurillo/ai-agents/issues/1855).

## Problem

Two CI workflows — `ai-pr-quality-gate.yml` and `ai-spec-validation.yml` —
currently produce their final verdict from LLM agent output alone. README
badges that read those workflows therefore advertise "verified" status that
was decided by a model judging another model's work. That is a single closed
loop: a ghost grading a ghost.

The repo's own SOUL.md says "distrust your own artifacts." A test you wrote
validating code you wrote is one loop. The same critique applies when the
test *is* an LLM judgment over LLM output.

## Contract

Every quality gate **MUST** produce its block / allow decision from at least
one **externally-grounded signal**: a deterministic tool whose verdict does
not depend on a language model. LLM agents **MAY** still post reviews — they
remain valuable for explaining *why* a finding matters — but their verdicts
are advisory, never gating.

External signals (non-exhaustive):

| Gate                     | External signal(s)                                         |
|--------------------------|------------------------------------------------------------|
| Code quality             | lint exit code, static-analysis findings, complexity caps  |
| Test coverage            | actual pytest/Pester run + measured coverage %             |
| Security                 | CodeQL findings delta, dependency scan, secret-scan exit   |
| Spec / acceptance        | mechanically-extracted acceptance checkboxes + diff grep   |
| Prose                    | markdownlint, link checker, broken-anchor scan             |

## Helpers shipped in this PR

These live under `scripts/external_signals/` and are deterministic,
network-free, and unit-tested.

### `acceptance_criteria.py`

Parses `## Acceptance` / `## Acceptance Criteria` Markdown checkboxes out of
an issue or PR body. Exits non-zero if any criterion is unchecked, or — when
a unified diff is supplied — if a criterion's keywords are entirely absent
from the diff (a coarse smoke-grep).

```bash
python3 scripts/external_signals/acceptance_criteria.py \
  --body pr-body.md --diff pr.diff --json
```

Exit codes (ADR-035): 0 pass, 1 logic failure, 2 config error.

### `gate_aggregator.py`

Combines signal verdicts produced by external tools and LLM agents and emits
the final gate verdict. **Refuses to return `PASS` when every signal is an
LLM judgment** — the rule that closes issue #1855.

```bash
python3 scripts/external_signals/gate_aggregator.py \
  --signal external:pytest=PASS \
  --signal external:codeql=PASS \
  --signal llm:security=WARN \
  --json
```

Aggregation rules:

1. Any blocking verdict (`FAIL` / `CRITICAL_FAIL` / `REJECTED`) wins, regardless of signal kind.
2. Otherwise, at least one `external:*` signal must be present with a `PASS` or `WARN` verdict; if all signals are `llm:*`, the result is forced to `NEEDS_REVIEW` with reason `closed-loop`.
3. `WARN` / `NEEDS_REVIEW` downgrades an otherwise clean pass to `WARN`.
4. Otherwise `PASS`.

## Why not edit the workflows in this PR?

`agent-can-edit-workflows` is not on issue #1855. Per the repo's bot safety
rails, this PR ships the *deterministic helpers and the contract document*
only; the workflow wiring that calls them in `ai-pr-quality-gate.yml` and
`ai-spec-validation.yml` is split into a follow-up issue so a maintainer can
review the workflow change explicitly.

Acceptance items from #1855 map as:

| Acceptance item                                  | Status here                                  |
|--------------------------------------------------|----------------------------------------------|
| Each gate exits non-zero on non-LLM signal       | Helpers exist + tested; wiring deferred      |
| README badges reflect external signal            | Documented in follow-up issue (workflow scope) |

## Follow-up

A new issue tracks the workflow wiring and badge swap (workflows-only edit,
gated by the `agent-can-edit-workflows` label). When that lands, the
helpers in this PR become the gate's source of truth.
