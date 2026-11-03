# Rule Audit Parser Forensics: adversarial lessons from one judge parser

Companion to `rule-audit-procedure.md`. This file records parser failure
patterns and the invariants that close them. It intentionally omits historical
result counts and size claims. Read it when changing judge-output recovery.

## Preserve the source before interpreting it

Store the complete judge response whenever recovery may matter. A truncated
preview can turn a valid diagnosis into a truncation diagnosis. Recovery must
preserve the original request, response, and verdict exactly.

The entry point owns the observable result. Helpers such as `_recover_verdict`
and `_salvage_scores` cover different recovery routes. A helper returning
`None` does not prove that the entry point cannot recover a valid top-level
triple through another route.

## Fences are syntax, not a selection mechanism

Pair a closing fence with the width of the opening fence. Reject ambiguous
fenced output. Unwrap only when the text outside the fence is whitespace. A
fenced example beside an unfenced verdict must not win by position.

## Strict JSON can still contain a second verdict

A payload can parse cleanly while nesting another score-bearing object, list
element, or string. Duplicate-key rejection does not catch a nested key.
Apply `_names_a_score_field_twice` to every decoded layer before publishing a
result. Run the guard before the parse path that needs it, not only in a
recovery helper.

Do not apply one lexical guard to every path without checking the question that
path answers. A successfully parsed payload can inspect decoded structure. A
raw tail after an object needs a stricter textual guard. Different questions
need different instruments.

## Field names are schema slots, not verdicts

The walker must distinguish a schema key from a value that merely names a
score field. Skipping a matching key is valid when the parser already consumed
that schema slot. Skipping a value is unsafe because a competing verdict can
refer to a field from value position.

Do not make padding, punctuation, or quoting rules carry the whole invariant.
Walk the decoded structure and reject a score-bearing field wherever an
untrusted payload can introduce one.

## Attribute recovered payloads by input

Matching a recovered payload to a published cell by its parsed score is
circular. The score is the value under test. The judge input contains the
response being graded, so the input is the authoritative join key. Preserve
the response preview and correlate it with the transcript before accepting a
recovered payload.

## Treat schema mismatches as failures

The archive uses dictionaries for rules and mechanisms, and a list for
scenarios. A walker that assumes every container is a list can find no samples
and print a clean result from no data. Follow the schema path explicitly and
fail when a required container is absent or has the wrong shape.

## No fabrication on recovery failure

Malformed, incomplete, ambiguous, or unavailable source data is unknown. Do
not fill missing score fields, infer a verdict from surrounding prose, or
replace an authoritative refusal with a guess. Preserve the error context and
return an unconfirmed result.

The measurement failure patterns behind these lessons remain in
`rule-audit-measurement-discipline.md`. Historical result evidence remains in
`rule-audit-evidence.md`.
