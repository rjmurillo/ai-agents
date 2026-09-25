---
type: design
id: DESIGN-038
title: External claims ledger and the research claim gate
status: implemented
priority: P1
related:
  - REQ-040
  - DESIGN-036
  - TASK-049
created: 2026-09-25
updated: 2026-09-25
author: spec-generator
tags:
  - skills
  - research
  - routing
---

# DESIGN-038: External claims ledger and the research claim gate

## Requirements Addressed

REQ-040 criteria 1 to 10.

## Where the gate sits

The `research` skill writes three durable artifacts: the analysis document
(Phase 2), the Serena memory (Phase 4), and the issue body (Phase 5). Each
artifact is first written to a draft file with its own ledger. The claim gate
validates the ledger against the draft, and the draft moves to its final
location only on exit 0. A direct `/research` call passes through the same
phases, so it cannot skip the gate.

| Artifact | Draft | Ledger |
|---|---|---|
| Analysis | `{topic-slug}-analysis.draft.md` | `{topic-slug}-analysis-claims.json` |
| Memory | `{topic-slug}-memory.draft.md` | `{topic-slug}-memory-claims.json` |
| Issue body | `{topic-slug}-issue.draft.md` | `{topic-slug}-issue-claims.json` |

One ledger per artifact, because a memory or an issue body restates only
some of the analysis claims, and rule 11 needs every kept wording present.

`ai-agents-external-claims` owns the contract. `research` invokes it.

## Ledger

```json
{
  "artifact": "{analysis-dir}/queue-backpressure.md",
  "activation": {"decision": "activate", "reason": "vendor and statistic claims"},
  "claims": [
    {
      "id": "C1",
      "claim": "Kafka consumers pause fetches when the buffer is full",
      "category": "vendor",
      "time_sensitive": false,
      "source": {"kind": "primary", "url": "https://...", "published": null,
                 "accessed": "2026-09-25", "secondary_reason": null},
      "confidence": "high",
      "disposition": "verified",
      "final_wording": "Kafka consumers pause fetches when the buffer is full",
      "gap": ""
    }
  ]
}
```

## Validator rules

`.claude/skills/ai-agents-external-claims/scripts/claim_ledger.py`.

```text
claim_ledger.py --ledger PATH [--artifact PATH]
```

1. `decision` is `activate` or `skip`, and `reason` is non-empty.
2. `skip` carries no claims. `activate` carries one or more.
3. `category` is one of `vendor`, `api`, `statistic`, `legal`,
   `project-status`, `comparative`. `source.kind` is one of `primary`,
   `secondary`, `none`. `confidence` is one of `high`, `medium`, `low`,
   `none`. `disposition` is one of `verified`, `narrowed`, `qualified`,
   `removed`. Dates are ISO `YYYY-MM-DD`. Claim ids are unique.
4. `primary` and `secondary` sources need `url` and `accessed`.
5. `secondary` needs `secondary_reason`, and caps confidence at `medium`.
6. `verified` needs a `primary` source and `high` or `medium` confidence.
7. `none` allows only `qualified` or `removed`, at `low` or `none`
   confidence.
8. Any disposition other than `verified` needs a non-empty `gap`.
9. `removed` needs an empty `final_wording`. Every other disposition needs a
   non-empty one.
10. A kept `time_sensitive` claim needs "as of" in its `final_wording`, and a
    `published` date when its source kind is not `none`.
11. With `--artifact`, each kept `final_wording` must appear in the draft.
    A removed claim, or the gathered sentence of a narrowed or qualified
    claim, must not appear outside the kept wordings. Matching is
    case-insensitive, whitespace-collapsed, and on word boundaries.
12. With `--artifact`, a `skip` decision fails when the draft cites an
    `http` or `https` URL. Internal-only drafts cite repository files by path.
13. `artifact` is a non-empty string naming the final location.

Exit codes: 0 pass, 1 defects, 2 unreadable input or bad arguments. Output is
one sorted JSON object on stdout, naming the ledger and the draft.

## Routing

`ai-agents-external-claims` becomes `role: conditional-adjunct`, `invoker:
research`. The `rationale` key goes, since only `explicit-only` needs it. The
`autoplan` research row names the gate.

## Tests

`tests/skills/ai-agents-external-claims/test_claim_ledger.py` covers each
rule, each REQ-040 criterion 8 case, and the exit codes. Eval scenarios in
`tests/evals/skill-scenarios/research.json` cover activation and skip.
