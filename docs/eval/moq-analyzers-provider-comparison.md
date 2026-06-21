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

## Addendum: strong models (Opus, GPT-5, gpt-5.5) - do they find something else?

Yes, and they find different KINDS of things. Anthropic API budget is exhausted,
so Opus ran via the `claude -p` CLI (subscription, model `claude-opus-4-8`);
GPT-5 ran on github-models but only after dropping `max_tokens`/`temperature`
for `max_completion_tokens` (see the #2710 limitation below); gpt-5.5 ran via the
`codex exec` CLI (ChatGPT subscription, `model = gpt-5.5`, reasoning effort
`xhigh`, `--output-schema` forcing the JSON shape). The two CLI transports both
bypass the exhausted API budget, the same reason `claude -p` carried Opus.

## Overall scores, all tiers

| file | mid-tier (gpt-4o/mistral/deepseek) | Opus | GPT-5 | gpt-5.5 |
| :--- | :-- | :-- | :-- | :-- |
| MockDetectionHelpers | 8 | **6** | 9 | 8 |
| MockBehaviorDiagnosticAnalyzerBase | 7-8 | **6** | 8 | 7 |
| CallbackSignatureShouldMatchMockedMethodFixer | 7-8 | 7 | 8 | 8 |

The mid-tier "everyone agrees within 1 point" was agreement on the EASY signal.
The strong models break that consensus in opposite directions: Opus grades down,
GPT-5 grades up, and gpt-5.5 lands between them.

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

## gpt-5.5 (codex) = the calibrated middle, design lens, no bug-hunt

gpt-5.5 at `xhigh` scores between Opus and GPT-5: overall **8 / 7 / 8** across the
three files. On overall and on the two most divisive axes (testability,
non-redundancy) it lands strictly between Opus and GPT-5 on all three files;
milder than Opus, stricter than GPT-5. (One outlier: it rated
`MockBehaviorDiagnosticAnalyzerBase` encapsulation 8, above both Opus and GPT-5 at
7.)

- Same design debt Opus caught, scored milder: the `TypeArguments.Length == 1`
  single-type-arg extraction duplicated across
  `IsValidMockOfInvocation`/`IsValidMockInvocation`; the two
  `TryReportMockBehaviorDiagnostic` and two `TryHandleMissingMockBehaviorParameter`
  overloads differing only by `mockedTypeName`; `MoqKnownSymbols` constructed
  directly rather than injected (coupling + use-mixed-with-creation); the Roslyn
  `OperationAnalysisContext`/`CompilationStartAnalysisContext` testability ceiling.
- Did NOT surface the correctness or performance bugs GPT-5 uniquely found. No
  mention of imprecise `GetDiagnosticLocation` as a bug, the `Constructor != null`
  over-constraint, the fragile `FindToken(...).Parent`, the unguarded duplicate
  parameter names, or the `ImmutableDictionary` hot-path allocation. It named
  `GetDiagnosticLocation` only as needing Roslyn fixtures to test, not as a risk.
- Register differs: gpt-5.5 writes a balanced reviewer's note (leads with the
  cohesion/encapsulation strengths, then states the issue) where GPT-5 emits a
  terse issue list. gpt-5.5 stayed faithful to the maintainability rubric; GPT-5
  exceeded it by hunting bugs.
- Reliability: 3/3 clean JSON via codex `--output-schema`, ~28-35s per file at
  `xhigh`. No parse failures (contrast llama-3.3's JSON breakage on the github
  transport).

Reproduce (strong models): Opus via `claude -p --output-format json
--append-system-prompt <rubric> --model claude-opus-4-8`; gpt-5.5 via `codex exec
-m gpt-5.5 -s read-only --ephemeral --output-schema <schema.json> -o <out> "<rubric>"`
with the `.cs` file piped on stdin. Both bypass the API budget through CLI
subscription auth.

## Within-family version sweep: does the point release move the grade?

Ran the older point releases of each family on the same three files: Claude
`opus-4-7` and `opus-4-6` (via `claude -p`), and codex `gpt-5.4` (via `codex
exec`). `gpt-5.3` is unavailable: codex returns HTTP 400, "The 'gpt-5.3' model is
not supported when using Codex with a ChatGPT account."

Overall score per file (1-10):

| model | MockDetectionHelpers | MockBehaviorBase | CallbackFixer |
| :--- | :-- | :-- | :-- |
| opus-4-8 | 6 | 6 | 7 |
| opus-4-7 | 7 | 6 | 7 |
| opus-4-6 | 7 | 6 | 7 |
| gpt-5.5 | 8 | 7 | 8 |
| gpt-5.4 | 8 | 7 | 8 |

**Headline: within-family drift is tiny; the cross-family gap is the whole story.**
The Claude family clusters at 6-7 overall; the OpenAI family clusters at 7-8. The
model FAMILY sets the grading posture (Claude strict, OpenAI lenient). The point
release inside a family barely moves the number.

Claude family (4.8 vs 4.7 vs 4.6):

- Overall verdict is stable across all three versions: same number on
  MockBehaviorBase (6) and CallbackFixer (7); a 1-point wobble on
  MockDetectionHelpers where 4.8 is the strictest (6 vs 7), driven by lower
  encapsulation (6 vs 7-8) and non-redundancy (5 vs 7). So the newest Opus grades
  marginally harder, not softer.
- All three independently catch the same design debt: the `IsValid*`
  single-type-arg duplication, the two overload pairs differing only by
  `mockedTypeName`, the `MoqKnownSymbols` coupling, the Roslyn testability
  ceiling, and the asymmetric delegate-constructor guard in the fixer. The Opus
  design-debt lens is consistent version to version, not a 4.8-only trait.

codex family (gpt-5.5 vs gpt-5.4):

- Identical overall on all three files (8 / 7 / 8). Per-quality wobble is minor
  (gpt-5.4 rates encapsulation a touch higher, cohesion a touch lower; same mean).
- Two real differences, neither in the score:
  - Latency: gpt-5.4 at `xhigh` took ~107-125s per file, roughly 4x gpt-5.5's
    ~28-35s. The newer release is much faster for the same grade.
  - Findings: gpt-5.4 was MORE bug-grounded than gpt-5.5. It flagged the
    imprecise `GetDiagnosticLocation` (first `GenericNameSyntax` descendant) and
    the `Constructor != null` over-constraint, two of the correctness issues
    gpt-5.5 missed and GPT-5 caught. It also cites line ranges. So the terse,
    bug-light register of gpt-5.5 is a 5.5 trait, not an OpenAI-family trait.

Reliability note: `claude -p` has no output-schema flag, so its JSON is
best-effort; `opus-4-6` returned one fenced, truncated object (MockBehaviorBase)
that needed a re-run. codex `--output-schema` never broke across all runs. If you
drive Claude as an eval grader, validate and retry the JSON.

## Effort dimension: codex and Claude

Both CLIs expose a reasoning-effort knob, with different ceilings:

- codex: `-c model_reasoning_effort=<level>`, levels `none, minimal, low, medium,
  high, xhigh`. `max` is rejected: "Invalid value: 'max'. Supported values are:
  'none', 'minimal', 'low', 'medium', 'high', and 'xhigh'." xhigh is the ceiling.
- Claude: `claude --effort <level>`, levels `low, medium, high, xhigh, max`.
  Claude DOES support `max`; codex does not.

Caveat on earlier Opus runs: this host had `CLAUDE_EFFORT=xhigh` set in the
session environment, which `claude -p` inherits. So the strong-model and
version-sweep Opus numbers above were all produced at xhigh. The explicit xhigh
run below reproduces opus-4-8 at 6/6/7 exactly, confirming both the inheritance
and the run-to-run stability.

### gpt-5.5 (codex), overall + latency

| effort | MockDetectionHelpers | MockBehaviorBase | CallbackFixer | avg latency |
| :--- | :-- | :-- | :-- | :-- |
| medium | 8 | 7 | 7 | ~19s |
| high | 8 | 7 | 7 | ~21s |
| xhigh | 8 | 7 | 8 | ~31s |

Effort barely moves the codex grade. medium and high are identical on all three
files; xhigh adds one point (CallbackFixer), via a systematic +1 cohesion. Latency
rises ~1.6x medium to xhigh.

### opus-4-8 (Claude, --effort forced), overall + latency

| effort | MockDetectionHelpers | MockBehaviorBase | CallbackFixer | avg latency |
| :--- | :-- | :-- | :-- | :-- |
| medium | 7 | 5 | 7 | ~24s |
| high | 7 | 6 | 7 | ~22s |
| xhigh | 6 | 6 | 7 | ~31s |
| max | 6 | 5 | 7 | ~56s |

The Claude grade also stays in a 1-point band, but it wobbles
**non-monotonically**: more effort is not more strict. MockDetectionHelpers drifts
down (7,7,6,6), MockBehaviorBase goes up then down (5,6,6,5), CallbackFixer is flat
(7,7,7,7). No clean "higher effort = different verdict" signal. Latency, by
contrast, scales hard and monotonically: max (~56s) is ~2.4x medium (~24s), one
file hitting 68s.

### What effort buys

Effort is the weakest of the four dimensions for the score, on both families:
within a 1-point band, no reliable direction. It mostly buys latency (1.6x on
codex, 2.4x on Claude). For this maintainability rubric, run medium: it matches or
ties high everywhere and trails the top tier by at most one point on one file, at a
fraction of the wall-clock. Spend xhigh/max only for the richer, more bug-grounded
findings the top tiers tend to produce, not for a different number. Caveat: one
sample per cell, so treat single-point score wobbles as noise and the latency
direction as real.

## Token economics

Pricing basis (verified 2026-06-21 against three sources that agree to the dollar:
GitHub Copilot models-and-pricing, OpenAI API pricing, Anthropic API pricing).
Copilot resells at the model providers' direct per-token rates, no markup. All per
1M tokens, standard tier:

| model | input | output | batch input | batch output |
| :--- | :-- | :-- | :-- | :-- |
| gpt-5.5 | $5.00 | $30.00 | $2.50 | $15.00 |
| gpt-5.4 | $2.50 | $15.00 | $1.25 | $7.50 |
| gpt-5.3-codex | $1.75 | $14.00 | ~$0.88 | ~$7.00 |
| Claude Opus 4.8 / 4.7 / 4.6 | $5.00 | $25.00 | $2.50 | $12.50 |

Batch API is 50% off on both families. Evals are asynchronous and batchable, so
batch is the correct rate for an eval pipeline. (gpt-5.3-codex is priced but was
unreachable via the codex CLI on a ChatGPT account, so it has no measured tokens.)

Measured cost per single-file eval (the largest file, MockBehaviorBase: 2193 clean
input tokens; output tokens captured live). Human opportunity cost is the wall-clock
wait priced at $384k/yr = $184/hr = $0.0511/sec:

| model / effort | output tok | latency | token $ (std) | token $ (batch) | human $ (blocking) | all-in (blocking) |
| :--- | :-- | :-- | :-- | :-- | :-- | :-- |
| gpt-5.5 / high | 957 | 18s | $0.040 | $0.020 | $0.93 | **$0.96** |
| opus-4-8 / medium | 965 | 20s | $0.035 | $0.018 | $1.00 | $1.04 |
| gpt-5.5 / xhigh | 1298 | 19s | $0.050 | $0.025 | $0.98 | $1.03 |
| opus-4-8 / high | 1284 | 20s | $0.043 | $0.022 | $1.03 | $1.07 |
| opus-4-8 / xhigh | 2243 | 29s | $0.067 | $0.034 | $1.46 | $1.53 |
| opus-4-8 / max | 4088 | 61s | $0.113 | $0.057 | $3.13 | $3.24 |
| gpt-5.4 / xhigh | 5482 | 72s | $0.088 | $0.044 | $3.67 | $3.76 |

**Token cost is noise; human wait time is the bill.** Every eval's token cost is a
few cents (3.5 to 11 cents standard, half that batched). The human wait at $184/hr
is **20x to 42x** the token cost in every row. If a person blocks on the result,
you pay dollars in time for pennies in tokens.

This flips the optimization target by scenario:

- Human blocks on the result: minimize LATENCY, not tokens. gpt-5.5 is fast at any
  effort (~18-20s, ~$1 all-in). Avoid the slow tail: gpt-5.4/xhigh and opus-4-8/max
  both cost ~$3.2-3.8 all-in because they emit 4x the tokens AND take 3x the time,
  for the same or worse score.
- Async / batch pipeline (no human waiting): token cost is all that remains, and
  it is pennies. opus-4-8/medium batched is the floor at ~$0.018/file. Pick on
  quality, not price; the spread is noise.

The trap is the per-token sticker price. gpt-5.5 costs 2x gpt-5.4 per token, yet
gpt-5.5/xhigh is **3.6x cheaper all-in** than gpt-5.4/xhigh ($1.03 vs $3.76) for an
identical 8/7/8 score, because it emits a quarter of the tokens and finishes 4x
faster. What you pay is rate x tokens-emitted x (latency if blocking), not the rate
on the price sheet.

Caveats: one file, one sample per cell; output tokens vary per file and run. Costs
use clean input (2193 tokens); driving through `claude -p`/`codex` adds ~16-18k
tokens of harness context per call (~$0.08-0.09 input), still pennies. The Copilot
seat subscription and the codex/Claude CLI subscriptions are separate fixed costs
not modeled here; this is marginal per-eval cost.

## Takeaway

- Stronger models do not just move the number; they change the finding type.
  GPT-5 = best bug/perf finder (most actionable, exceeds the rubric). Opus =
  strictest grader + design-discipline. gpt-5.5 = the calibrated middle: agrees
  with Opus's design-debt signal at milder scores, rubric-faithful, but does not
  bug-hunt. Mid-tier = fast consensus on the obvious, blind to the subtle
  (over-generous on non-redundancy/testability).
- For an eval provider you want rigor from: GPT-5 (richest, catches latent bugs)
  or Opus (harshest, catches design debt). gpt-5.5 is the steadiest grader if you
  want a number you trust without manual recalibration. The mid-tier agreement in
  the first comparison was a false comfort: it agreed because it missed the hard
  parts.
- The grade is set by model FAMILY, not point release. Across 4.8/4.7/4.6 and
  5.5/5.4 the overall scores barely move within a family (<=1 point), while the
  Claude-vs-OpenAI gap is a steady 1-2 points. Pin the family for a comparable
  baseline; a point upgrade does not silently re-baseline your scores. Latency and
  finding quality DO shift with the release (gpt-5.5 is ~4x faster than gpt-5.4 but
  terser and less bug-aware), so re-check those, not the number, on upgrade.
- Reasoning effort moves the grade even less than the point release, on BOTH
  families. codex: medium = high on every file, xhigh adds at most 1 point. Claude
  (`--effort low/medium/high/xhigh/max`, max is Claude-only): grade wobbles
  non-monotonically inside a 1-point band, no direction. Effort mostly buys latency
  (1.6x codex, 2.4x Claude). Run medium for this rubric; reserve the top tiers for
  richer findings, not a different score. The two knobs that actually change the
  verdict are model FAMILY (posture) and prompt RIGOR (bug-hunt vs rubric-only),
  not the version or effort dial.
- Economics: the token bill is pennies; the human wait is the cost. At $184/hr a
  blocking eval costs 20-42x its tokens in human time. So if a person waits,
  minimize LATENCY (gpt-5.5 at any effort, ~$1 all-in) and avoid the slow tail
  (gpt-5.4/xhigh, opus/max ~$3+). If it runs async/batched, only tokens remain and
  they are noise (pick on quality). Ignore the per-token sticker price: gpt-5.5 is
  2x gpt-5.4 per token but 3.6x cheaper all-in for the same score, because it emits
  fewer tokens and finishes faster. Cost = rate x tokens-emitted x latency-if-blocking.

## #2710 limitation found (now fixed)

The github/openai provider in `_providers.py` hardcoded `max_tokens` and
`temperature`. OpenAI reasoning models (gpt-5, o1, o3, o4-mini) REJECT both with
HTTP 400; they require `max_completion_tokens` and no custom temperature. The
github transport therefore could not reach any reasoning model before this fix.
The fix detects reasoning models by id and sends `max_completion_tokens` with no
`temperature` in `_OpenAICompatibleProvider.complete`.

> Update: fixed in issue #2711 / PR #2712 - the OpenAI-compatible provider now sends `max_completion_tokens` (no `temperature`) for reasoning models, so gpt-5 / o-series work through the github transport.
