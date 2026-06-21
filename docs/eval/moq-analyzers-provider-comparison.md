<!-- Eval artifact generated 2026-06-21. Cross-provider comparison of the
code-qualities-assessment skill on rjmurillo/moq.analyzers via the #2710
EVAL_PROVIDER transports. Reproduce with the driver referenced below. -->

# Cross-provider eval comparison: code-qualities-assessment on moq.analyzers

Ran the `code-qualities-assessment` skill rubric (5 qualities, 1-10) on 3
representative `rjmurillo/moq.analyzers` source files through the EVAL_PROVIDER
transports shipped in ai-agents PR #2710. Same system rubric + same code per
provider; scores diffed.

Files: `src/Common/MockDetectionHelpers.cs`,
`src/Analyzers/MockBehaviorDiagnosticAnalyzerBase.cs`,
`src/CodeFixes/CallbackSignatureShouldMatchMockedMethodFixer.cs`.

## Transport availability (the headline)

| transport (#2710) | status | why |
| :--- | :--- | :--- |
| anthropic (urllib) | DOWN | HTTP 400 "reached your specified API usage limits, regain access 2026-07-01" |
| openai (direct) | DOWN | no `OPENAI_API_KEY` on this host |
| github-models | LIVE | gh token; OpenAI-compatible gateway to many vendors |

This is the exact scenario #2710 was built for: the Anthropic budget is
exhausted, and the github-models transport carried the entire comparison. The
multi-provider design is validated live, not in theory.

Because only github-models was usable, the cross-provider comparison runs across
the model vendors that transport reaches.

## Reliability (3 files each, via github-models)

| vendor/model | success | median latency |
| :--- | :--- | :--- |
| deepseek/deepseek-v3-0324 | 3/3 | 1.9s |
| openai/gpt-4o | 3/3 | 2.9s |
| mistral-ai/mistral-medium-2505 | 3/3 | 3.7s |
| meta/llama-3.3-70b-instruct | 2/3 | 3.7s (1 unparseable JSON) |
| microsoft/phi-4 | 1/3 | 2 timeouts at 120s |

Workhorses: deepseek-v3 (fastest), gpt-4o, mistral-medium. llama-3.3 occasionally
breaks the JSON contract. phi-4 is unusable here (timed out on the two larger
files).

## Scores: providers agree strongly on moq.analyzers

Overall (1-10) per file:

| file | gpt-4o | llama-3.3 | phi-4 | mistral | deepseek |
| :--- | :-- | :-- | :-- | :-- | :-- |
| MockDetectionHelpers | 8 | 9 | 9 | 8 | 8 |
| MockBehaviorDiagnosticAnalyzerBase | 7 | 8 | - | 8 | 7 |
| CallbackSignatureShouldMatchMockedMethodFixer | 7 | - | - | 8 | 8 |

Inter-provider agreement: the spread (max-min across vendors) is **1 point per
quality** on every file (max 2). The providers do not just agree on the overall
number; they converge on the same per-quality profile.

Per-quality means across files:

| vendor | cohesion | coupling | encapsulation | testability | non-redundancy |
| :--- | :-- | :-- | :-- | :-- | :-- |
| gpt-4o | 8.0 | 6.3 | 8.0 | 7.0 | 7.7 |
| llama-3.3 | 8.5 | 7.0 | 9.0 | 7.5 | 8.5 |
| phi-4 | 9.0 | 8.0 | 9.0 | 8.0 | 9.0 |
| mistral | 9.0 | 7.3 | 8.0 | 8.0 | 7.7 |
| deepseek | 8.7 | 7.3 | 8.7 | 7.3 | 7.3 |

**Coupling is the consistent weak axis** (lowest column for every vendor), and
the findings explain why identically: all five independently flag the dependency
on `MoqKnownSymbols` threaded through method parameters, name
`GetDiagnosticLocation` as the cohesion/testability outlier, and note
duplication across the `IsValid*` methods. The signal is model-independent.

## What this comparison tells you

1. **#2710 works and earns its place.** With Anthropic budget-exhausted, evals
   keep running on github-models. Without #2710, the assessment would have been
   blocked until 2026-07-01.
2. **For this skill, the model barely matters; reliability and latency do.**
   Scores agree within 1 point, so pick the provider on availability/speed:
   deepseek-v3 (fastest, 3/3) or gpt-4o (3/3). Avoid phi-4 (timeouts) and treat
   llama-3.3's JSON as needing a retry.
3. **moq.analyzers is well-built** by the rubric (overall 7-9). The one real,
   cross-provider-agreed improvement axis is coupling to Roslyn/`MoqKnownSymbols`
   in the analyzer/helper layer, which is partly inherent to Roslyn analyzers.

## Method / reproduce

Driver: `/tmp/eval_compare.py` (imports #2710's `_anthropic_api` + `_providers`).
Raw results: `/tmp/eval_compare_report.json`.

```bash
export GITHUB_TOKEN="$(gh auth token)"
export ANTHROPIC_API_KEY="$(grep ^ANTHROPIC_API_KEY= <ai-agents>/.env | cut -d= -f2-)"
python3 /tmp/eval_compare.py   # 3 files x 7 provider entries
```

Caveat: the openai package is required for the openai/github transports
(`pip install openai`). github-models model IDs come from
`https://models.github.ai/catalog/models`.

---

## Addendum: strong models (Opus, GPT-5) - do they find something else?

Yes, and they find different KINDS of things. Anthropic API budget is exhausted,
so Opus ran via the `claude -p` CLI (subscription); GPT-5 ran on github-models
but only after dropping `max_tokens`/`temperature` for `max_completion_tokens`
(see the #2710 limitation below).

## Overall scores, all tiers

| file | mid-tier (gpt-4o/mistral/deepseek) | Opus | GPT-5 |
| :--- | :-- | :-- | :-- |
| MockDetectionHelpers | 8 | **6** | 9 |
| MockBehaviorDiagnosticAnalyzerBase | 7-8 | **6** | 8 |
| CallbackSignatureShouldMatchMockedMethodFixer | 7-8 | 7 | 8 |

The mid-tier "everyone agrees within 1 point" was agreement on the EASY signal.
The strong models break that consensus in opposite directions.

## Opus = strictest grader + design-debt lens

Opus drops testability to 5 and non-redundancy to 5 where mid-tier said 8-9,
because it catches what they averaged over:

- Quotes the exact copy-paste: the `TypeArguments.Length == 1` extraction block
  duplicated across `IsValidMockOfInvocation`/`IsValidMockInvocation` (gpt-4o
  rated this file's non-redundancy **9**; Opus **5**).
- Names the testability ceiling precisely: which methods need real Roslyn
  `OperationAnalysisContext`/`CompilationStartAnalysisContext` vs which are unit-
  testable in isolation.
- New findings nobody else raised: the null-forgiving `knownSymbols.MockBehavior!`
  repeated across four methods (a non-null invariant leaked to callers); an
  asymmetric delegate-constructor guard in the fixer (a latent correctness bug);
  `new MoqKnownSymbols(...)` constructed inside a method (use mixed with creation).

## GPT-5 = widest, most actionable findings, incl. bugs + perf

GPT-5 scores leniently (8-9) but produces the richest finding set, and uniquely
surfaces correctness and performance issues no other model (mid-tier OR Opus)
mentioned:

- Correctness: `GetDiagnosticLocation` may report imprecise locations (first
  `GenericNameSyntax` descendant); `IsValidMockCreation` over-constrains on
  `Constructor != null`; `root.FindToken(...).Parent` is fragile (use
  `AdditionalLocations`); `BuildParameterList` does not guard duplicate parameter
  names -> could emit invalid signatures.
- Performance: "each diagnostic report constructs a new `ImmutableDictionary`;
  cache or use a lighter properties mechanism to reduce allocations in hot
  paths" - the only model to flag allocation in a hot path.
- API design: `GetMockedTypeName` internal virtual should be protected; stateless
  helpers could be static; the `"T"` magic-string fallback.

## Takeaway

- Stronger models do not just move the number; they change the finding type.
  GPT-5 = best bug/perf finder (most actionable). Opus = strictest grader +
  design-discipline. Mid-tier = fast consensus on the obvious, blind to the
  subtle (over-generous on non-redundancy/testability).
- For an eval provider you want rigor from: GPT-5 (richest, catches latent bugs)
  or Opus (harshest, catches design debt). The mid-tier agreement in the first
  comparison was a false comfort: it agreed because it missed the hard parts.

## #2710 limitation found (now fixed)

The github/openai provider in `_providers.py` hardcoded `max_tokens` and
`temperature`. OpenAI reasoning models (gpt-5, o1, o3, o4-mini) REJECT both with
HTTP 400; they require `max_completion_tokens` and no custom temperature. The
github transport therefore could not reach any reasoning model before this fix.
The fix detects reasoning models by id and sends `max_completion_tokens` with no
`temperature` in `_OpenAICompatibleProvider.complete`.

> Update: fixed in issue #2711 / PR #2712 - the OpenAI-compatible provider now sends `max_completion_tokens` (no `temperature`) for reasoning models, so gpt-5 / o-series work through the github transport.
