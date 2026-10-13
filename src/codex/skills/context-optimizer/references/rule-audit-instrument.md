# Rule Audit Instrument

What the eval harness can measure, what it cannot, and where clean output can
still be wrong. Companion to `rule-audit-procedure.md`, which defines the
workflow. Read this before trusting an eval result or writing a new instrument.

## What the instrument can and cannot resolve

The rule path is single-shot against an LLM judge. Identical rule text can
produce different outcomes, so a single run cannot resolve a small effect.
Repeated runs establish direction only when the repeat design was fixed before
the results existed.

## Read direction, not magnitude

Compare `full` with `description`. Do not use an unrelated baseline to decide
whether progressive disclosure changed behavior. Record ties. Read the result
with the preregistered two-tailed rule. A large delta in one run is not enough.

### Registered decision rule, 2026-08-03

Fix the decision rule before running the audit. Do not add runs because the
result is close. Discard a run only for a recorded provider error, never for
its result.

- Each non-tied run contributes the direction of its delta.
- Magnitude is context. It does not vote.
- A tie contributes no direction.
- Declare the direction and tail before running the audit.
- Apply the registered sign-test threshold. Below threshold means unresolved.
- A cut fails when the pre-cut version wins at that threshold. Otherwise the
  result does not prove that the cut is safe.

## Scoring contract

The judge returns required score fields for each sample. Reduce fields within a
cell using the registered reduction, then derive the mechanism result from the
scenario set. Preserve incomplete or malformed cells as unmeasured. Never
replace missing observations with zero or an inferred value.

The writer records the reduction explicitly. Negative scenarios remain in the
gate. A score that the judge never returned is an instrument defect, not a
valid result.

## Known instrument gotchas

These defects cost real time. The shapes recur even after the specific fix.

- Judge failures once scored as zero and could invert the ranking. Reject
  incomplete gating cells instead of averaging them into a mechanism result.
- Fence parsing once closed a wider legal fence at an inner run. Pair the close
  with the opening width and reject ambiguous fenced output.
- An unfenced verdict once lost to a fenced example beside it. Unwrap only when
  the surrounding text is whitespace.
- A clean parse once passed nested verdicts. Walk every decoded layer for
  duplicate score-bearing fields before publishing a result.
- Provider output is not necessarily clean JSON. Read the event log and bind
  the response to the sandbox working directory. Do not fall back to stdout
  parsing when that would mix tool traces into the answer.
- Provider usage metadata is not authoritative. Use the event log for provider
  state and read `session.usage_checkpoint` according to its event schema.
- The CLI loads `AGENTS.md` from its working directory. Eval calls must isolate
  the working directory and disable user-level instructions when required.
- A keyless provider can still fail at an entry point that demands
  `ANTHROPIC_API_KEY`. Keep provider selection and key loading separate.
- The archive nests dictionaries where a walker may expect lists. Follow the
  schema path through rule, scenario, mechanism, and score samples. A walker
  that finds no samples must fail, not print a clean result.
- Failed samples may carry a truncated payload in `reasoning`. Successful
  samples may carry no raw payload in the result artifact. Recover from the
  session transcript and attribute by the graded input, never by the score.

## Scenario files

Live in `tests/evals/rule-scenarios/`. Each scenario needs an `input`, an
`expected_gate`, and a `desc`. Include a negative case with
`expected_gate` set to `skip-rule-not-applicable`, so the eval can catch a rule
that fires on unrelated work.

Write scenarios where the rule's specific guidance can change the answer. A
scenario the model handles correctly with an empty system prompt proves
nothing about the rule.
