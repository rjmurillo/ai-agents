# Analyst-Spike Fixture Corpus

Held-out corpus driving `scripts/eval/eval-agent-vs-baseline.py` for the
`analyst` agent. Ten fixtures derived from real public issues in
[rjmurillo/moq.analyzers](https://github.com/rjmurillo/moq.analyzers),
plus one synthetic ESCALATE case for vague-report coverage.

## Why real issues

The first version of this corpus used eight synthetic fixtures. The
agent under-performed the naive baseline (-0.083) because most synthetic
scenarios were too easy: the verdict was obvious from the input alone,
without needing the analyst prompt's specialization. Real bug reports
require evidence gathering, hypothesis ranking, and search-before-claiming,
which is precisely what the analyst prompt is designed to do.

Each fixture paraphrases the symptom from the issue body. The known root
cause from the linked PR/commit is NOT in the input; the agent has to
reach it itself. The assertion regex matches the actual fix's root-cause
keyword.

## Provenance

| Fixture | Provenance | Source issue |
|---|---|---|
| F001 | paraphrased-from-public | [moq.analyzers#1010](https://github.com/rjmurillo/moq.analyzers/issues/1010) - false-positive Moq1302 on LINQ to Mocks |
| F002 | paraphrased-from-public | [moq.analyzers#1081](https://github.com/rjmurillo/moq.analyzers/issues/1081) - pre-push hook PowerShell parse error |
| F003 | paraphrased-from-public | [moq.analyzers#1080](https://github.com/rjmurillo/moq.analyzers/issues/1080) - recurring .git/config corruption |
| F004 | paraphrased-from-public | [moq.analyzers#981](https://github.com/rjmurillo/moq.analyzers/issues/981) - string-based detection violates mandate |
| F005 | paraphrased-from-public | [moq.analyzers#991](https://github.com/rjmurillo/moq.analyzers/issues/991) - PerfDiff error handling gaps |
| F006 | paraphrased-from-public | [moq.analyzers#1086](https://github.com/rjmurillo/moq.analyzers/pull/1086) / [#1067](https://github.com/rjmurillo/moq.analyzers/issues/1067) - false-positive Moq1203 on extension-method-wrapped Setup |
| F007 | synthetic | Vague "Moq analyzer is broken" report with no details. ESCALATE coverage. |
| F008 | paraphrased-from-public | [moq.analyzers#1057](https://github.com/rjmurillo/moq.analyzers/pull/1057) - post-fix "anything to investigate" with concrete resolution already named |
| F009 | paraphrased-from-public | [moq.analyzers#1040](https://github.com/rjmurillo/moq.analyzers/pull/1040) (closes #991) - five-gap triage and prioritization |
| F010 | paraphrased-from-public | [moq.analyzers#1043](https://github.com/rjmurillo/moq.analyzers/pull/1043) - System.CommandLine 2.0.0-beta to 2.0.3 migration risks |

## Verdict distribution

| Verdict | Fixtures | Count |
|---|---|---|
| IDENTIFY | F001, F002, F003, F004, F005, F006, F009, F010 | 8 |
| OK | F008 | 1 |
| ESCALATE | F007 | 1 |

## Agent-discriminating fixtures (REQ-004 AC-5, >=30% required)

Four fixtures (F001, F003, F006, F009) are explicitly agent-discriminating: the right answer requires evidence-level tagging, hypothesis ranking, or specific symbol-vs-string reasoning that a naive baseline cannot supply. That is 40 percent of the corpus, above the threshold.

## Cross-references

- [evals/security-spike/fixtures/README.md](../../security-spike/fixtures/README.md) - reference shape this corpus follows.
- [templates/agents/analyst.shared.md](../../../templates/agents/analyst.shared.md) - agent under test.
- [scripts/eval/eval-agent-vs-baseline.py](../../../scripts/eval/eval-agent-vs-baseline.py) - runner.
- [evals/baseline-report.md](../../baseline-report.md) - aggregate baseline across spikes.
- [.agents/architecture/ADR-057-prompt-behavioral-evaluation.md](../../../.agents/architecture/ADR-057-prompt-behavioral-evaluation.md).
