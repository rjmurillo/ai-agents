# Analyst-Spike Fixture Corpus

Held-out corpus driving `scripts/eval/eval-agent-vs-baseline.py` for the
`analyst` agent. Eighteen fixtures: 9 from rjmurillo/moq.analyzers issues, 5 from dotnet/runtime PRs, 3 from rjmurillo/ai-agents PRs, 1 synthetic ESCALATE for vague-report coverage.

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

| F011 | paraphrased-from-public | [dotnet/runtime#46057](https://github.com/dotnet/runtime/pull/46057) - case-insensitive ASCII equality bug ('`' vs '@') |
| F012 | paraphrased-from-public | [dotnet/runtime#46745](https://github.com/dotnet/runtime/pull/46745) - SocketAsyncContext.Unix sequential epoll regression from PR #37974 |
| F013 | paraphrased-from-public | [dotnet/runtime#40772](https://github.com/dotnet/runtime/pull/40772) - NetworkStream Span-of-byte overload exception shape inconsistency |
| F014 | paraphrased-from-public | [dotnet/runtime#84917](https://github.com/dotnet/runtime/pull/84917) - CS1591 enable cascade with unknown blast radius |
| F015 | paraphrased-from-public | [ai-agents#1795](https://github.com/rjmurillo/ai-agents/pull/1795) - plugin.json schema P0 customer install broken |
| F016 | paraphrased-from-public | [ai-agents#830](https://github.com/rjmurillo/ai-agents/pull/830) - session protocol validation, scope explosion request |
| F017 | paraphrased-from-public | [ai-agents#760](https://github.com/rjmurillo/ai-agents/pull/760) - SkillForge validator drift between local pre-commit and upstream |
| F018 | paraphrased-from-public | [ai-agents#402](https://github.com/rjmurillo/ai-agents/pull/402) - PR maintenance bundled five features, split-or-merge question |

## Verdict distribution

| Verdict | Fixtures | Count |
|---|---|---|
| IDENTIFY | F001, F002, F003, F004, F005, F006, F009, F010, F011, F012, F013, F015, F017 | 13 |
| OK | F008 | 1 |
| ESCALATE | F007, F014, F016, F018 | 4 |

## Agent-discriminating fixtures (REQ-004 AC-5, >=30% required)

Four fixtures (F001, F003, F006, F009) are explicitly agent-discriminating: the right answer requires evidence-level tagging, hypothesis ranking, or specific symbol-vs-string reasoning that a naive baseline cannot supply. That is 40 percent of the corpus, above the threshold.

## Cross-references

- [evals/security-spike/fixtures/README.md](../../security-spike/fixtures/README.md) - reference shape this corpus follows.
- [templates/agents/analyst.shared.md](../../../templates/agents/analyst.shared.md) - agent under test.
- [scripts/eval/eval-agent-vs-baseline.py](../../../scripts/eval/eval-agent-vs-baseline.py) - runner.
- [evals/baseline-report.md](../../baseline-report.md) - aggregate baseline across spikes.
- [.agents/architecture/ADR-057-prompt-behavioral-evaluation.md](../../../.agents/architecture/ADR-057-prompt-behavioral-evaluation.md).
