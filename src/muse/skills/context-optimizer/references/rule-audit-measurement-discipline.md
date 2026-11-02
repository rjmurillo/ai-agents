# Rule Audit Measurement Discipline: how the checks themselves went wrong

Companion to `rule-audit-parser-forensics.md`. That file records parser
defects. This file records defects in the checks that judged the parser. Read it
before quoting a result from a one-off command.

## A check that cannot fail has not been run

A negative control can mutate the wrong file, call an unavailable interpreter,
or never reach the code under test. It can then report clean against unchanged
code. That output is indistinguishable from a passing control.

Confirm that the mutation reached the target. Run the suite. Confirm that the
suite fails before trusting the clean result. Use `diff` against a backup when
the control edits a file. Invoke Python through `uv run --frozen python`; a
missing bare interpreter must not disappear inside a swallowed subprocess
error.

## A result needs the population it was read from

A detector can be correct over the wrong population. State the population
before stating the result, and verify that the detector can see every member of
it. Keep the population fixed while comparing revisions.

The same instability affects running totals in prose. A total changes while a
document waits for review, and nothing fails when it becomes stale. State the
bound or the invariant the reader needs. Keep exact counts inside the artifact
that owns the closed population, not in active guidance.

## An unintended deletion does not announce itself

A structural find-and-replace can consume the opener it was meant to preserve.
The edit reports success while the file loses a test or a portability marker.

Inspect deleted lines after every structural edit. Assert that the base path is
a file, not merely an existing Git object. Compare against the branch tip when
the file is new. For renames, name both paths and enable rename detection.

Deleted-line search proves only that text disappeared. The stronger check is the
invariant that owns the structure: test collection for a test, portability for a
vendor marker, and parity for a manifest. Prefer an AST span for multi-function
edits.

## A helper can answer a different question than the entry point

A helper's return value may describe one recovery route while the entry point
composes several routes. Verify observable behavior through the entry point.
Use a helper only to explain a result the entry point already established.
When the answers disagree, the entry point wins and the helper mismatch is the
finding.

The same trap appears with duplicate-name guards. A textual guard and a
structural guard answer different questions. Run the guard against a positive
control from the same population. A clean result from a guard that cannot run
is not evidence.

## Refusal and acceptance are not symmetric

A refusal is visible. It sets a marker and surfaces in the result. Fabrication
is an unmarked false observation that travels through the clean path.

Refuse ambiguous or incomplete classes before publishing a result. Measure any
refusal against the correct population before shipping it. Do not enumerate
known bad examples as a substitute for a structural invariant. The invariant
must cover the next unseen shape too.

## Evidence ownership

Keep historical result details in the archived artifact. Keep active guidance
focused on the invariant, the decision rule, and the verification command.
Never copy a measured snapshot into a document that governs future runs.
