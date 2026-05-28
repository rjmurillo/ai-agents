# Analyst-Spike Fixture Corpus

Held-out corpus driving `scripts/eval/eval-agent-vs-baseline.py` for the
`analyst` agent. Measures whether the analyst's specialized system prompt
(evidence-level tagging, search-before-claiming, hypothesis ranking, open-
questions discipline) outperforms a deliberately naive baseline prompt on
investigation, research, and pushback tasks.

## Provenance

| Fixture | Provenance | Source notes |
|---|---|---|
| F001 | synthetic | Auth library bump + KeyError. Constructed for hypothesis-ranking signal. |
| F002 | synthetic | Vague request. Tests pushback / clarification behavior. |
| F003 | synthetic | Queue selection. Tests comparison + recommendation. |
| F004 | synthetic | Post-incident close-out. Tests OK verdict when no action is warranted. |
| F005 | paraphrased-from-public | Python `secrets` entropy. Tests citation discipline. |
| F006 | paraphrased-from-public | Django async ORM version. Tests search-before-claiming. |
| F007 | synthetic | CI vs local Postgres connection refused. Tests hypothesis ranking + cheap-check ordering. |
| F008 | synthetic | Region migration with no constraints. Tests open-questions surfacing. |

## Verdict distribution

| Verdict | Fixtures | Count |
|---|---|---|
| IDENTIFY | F001, F003, F005, F007 | 4 |
| OK | F004 | 1 |
| ESCALATE | F002, F006, F008 | 3 |

## Agent-discriminating fixtures (REQ-004 AC-5, >=30% required)

Four of eight fixtures (F005, F006, F007, F008) require knowledge encoded in
the analyst system prompt that a naive baseline cannot supply:

| Fixture | Why naive baseline cannot score correctly | What the analyst prompt provides |
|---|---|---|
| F005 | Asks for entropy source + multi-process suitability. Naive may give a vague yes/no. | "Search before claiming" + evidence-level tagging forces a concrete cite. |
| F006 | Explicit instruction to cite or say source unavailable. Naive often confabulates. | Analyst's L4 (training knowledge) is "not publishable"; must move to Open Questions. |
| F007 | Many possible causes; the value is RANKING by probability with cheapest check first. | Hypothesis-ranking rubric (Consistency High, Recency High, Simplicity Med, Reproducibility Med, Cost Low). |
| F008 | Cannot decide without missing inputs; naive may answer yes/no anyway. | "Never skip step 7" (Open Questions) + Push back on vague requests with no concrete problem. |

## Per-fixture rationale

### IDENTIFY (4)

- **F001** auth library bump from 2.4.1 to 2.5.0 + KeyError on nonce. Right answer names the library bump as primary hypothesis + cites the changelog as cheap-check evidence.
- **F003** queue selection with explicit constraints. Right answer compares 2-3 queues and recommends one with a one-line rationale.
- **F005** `secrets.token_urlsafe()` entropy + multi-process safety. Right answer cites `os.urandom`/`getrandom` and says "yes, suitable" with reasoning.
- **F007** integration tests fail in CI but pass locally with connection refused on Postgres. Right answer ranks service-container readiness / health-check / depends_on / port forwarding by probability with cheap checks.

### OK (1)

- **F004** root-cause already identified, fix landed, regression test exists. Right answer is "nothing to add, close the incident" - no investigation needed.

### ESCALATE (3)

- **F002** vague "look into the database; something feels off". Right answer pushes back for symptoms, repro steps, scope.
- **F006** explicit "don't speculate; either name the version or say source unavailable". Right answer escalates because the analyst cannot verify the version in-session.
- **F008** "should we move our auth service to a different region? Decide and respond." Right answer enumerates the missing inputs (latency baseline, cost, compliance, user distribution) and asks for them before deciding.

## Cross-references

- [evals/security-spike/fixtures/README.md](../../security-spike/fixtures/README.md) - reference shape this corpus follows.
- [templates/agents/analyst.shared.md](../../../templates/agents/analyst.shared.md) - agent under test.
- [scripts/eval/eval-agent-vs-baseline.py](../../../scripts/eval/eval-agent-vs-baseline.py) - runner.
- [.agents/architecture/ADR-057-prompt-behavioral-evaluation.md](../../../.agents/architecture/ADR-057-prompt-behavioral-evaluation.md) - prompt behavioral evaluation.
- REQ-004 / DESIGN-004 / [.agents/plans/active/PLAN-1854-agent-eval-harness-spike.md](../../../.agents/plans/active/PLAN-1854-agent-eval-harness-spike.md) - harness origin.
