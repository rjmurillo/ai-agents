# Rule Audit Measurement Discipline: how the checks themselves went wrong

Companion to `rule-audit-parser-forensics.md`, which records what broke in the
parser. This file records what broke in the *checking* of it, and those are
different failures with different fixes. A parser defect publishes a wrong
number. A measurement defect publishes a wrong number and a clean report saying
it was verified.

Read this before quoting a figure you produced with a one-off command.

## A check that cannot fail has not been run

Two of the six negative controls covering parser round 20 were themselves false
at first. One mutated a comment rather than the pattern. One invoked a `python`
absent from PATH, so the interpreter never ran. Both reported clean against
unmodified code, which is the same output a genuinely passing control produces.

The control for a control is cheap and unconditional: confirm the mutation
actually reached the file, run the suite, and confirm it now fails. `diff`
against a backup before trusting a clean result. In this repository the
interpreter must be invoked as `uv run --frozen python`, because bare `python`
is not on PATH and its absence is silent inside a script that swallows the
error.

## A number needs the population it was read off

Three separate figures in this audit were wrong not because the count was
miscomputed but because it was computed over the wrong set.

A claim that "1732 nested reasoning values name no score field" walked the
whole archive envelope, including artifact names, session identifiers, and
provenance prose, none of which the parser ever reads. The population the
sentence attached to was the nested reasoning values, and there are 264 of
them. The claim's direction did not change, but a number quoted against the
wrong population is not evidence for anything, whichever way it points.

A file-size finding was reported as three affected files when the gate scans
markdown and code and does not scan `.xml` or `.txt`; the real figure was one.

A test-addition delta was checked with `grep -o '^def test_'` against a file
whose tests are all indented class methods, so the command returns zero and can
never contradict the claim it is quoted for. The corrected form matches leading
whitespace, and the real figure was 76 to 87 with no deletions.

The shared shape is a detector applied to a set that could not have contained
the thing being counted. Before quoting a figure, state the denominator out
loud and check that the detector can see a member of it.

## An unintended deletion does not announce itself

A find-and-replace anchored on a structural opener deletes that opener unless
the replacement re-emits it. In this audit it took a `def` line twice, removing
a test while leaving its body attached to the previous function, and it took
the `<!-- vendor-portability:` marker at the foot of the forensics file,
turning two long-declared path references back into undeclared drift.

Each time, the edit reported success. The portability gate caught the third,
but only because the gate was run. The check that costs nothing is
`git diff | grep '^-'` after each edit: an unintended deletion shows up as a
line nobody meant to remove. For multi-function edits, prefer removing an AST
span to matching on a `def` line.

## A helper probed alone can answer a different question than the entry point

Verifying the claim that all 24 archived judge failures salvage, the obvious
check was to call the recovery helper on each stored payload. It returned
`None` for 24 of 24, and the strict parser raised on 24 of 24. Both counts were
correct. Both were about a different question than the one being asked.

The entry point returns `judge_failed=False` and `judge_salvaged=True` for all
24. `_recover_verdict` returning `None` means no *embedded complete object* was
found, which is one route among several; the three top-level integers are still
extractable, and the function named `_judge_parse_failure` extracts them. Its
name asserts an outcome it does not produce, which is now issue #4031.

Two correct measurements pointed the opposite way from the real behaviour, and
the reason was reading a name instead of a return value. Had the claim been
retracted on that evidence, a true finding would have been replaced with a
false one, and the retraction would have looked better supported than the
original because it cited two numbers.

The procedure that catches it: verify a claim about observable behaviour
through the entry point that produces the observable, not through the helper
that looks responsible for it. Reach for a helper only to explain a result the
entry point already established, and when a helper's answer contradicts the
entry point, the entry point wins and the contradiction is a finding about the
helper.

A second-order form of the same trap: this instrument has two duplicate-name
guards, a textual one for payloads that did not parse and a structural one for
payloads that did. Checking the wrong one is not a wrong answer, it is an
answer to the other question, and on a population where the chosen guard cannot
run it returns a clean zero that reads like evidence. The measurement of the 24
failures had exactly that shape at first, because the structural guard was
applied to payloads that by definition do not parse. Name the guard in the
claim, and confirm with a control that the chosen one fires on a positive case
drawn from the same population.

## An over-eager refusal is not symmetric with an over-eager accept

This is the asymmetry the whole instrument turns on, and it governs how much
evidence each direction needs before shipping.

A refusal is visible. It sets a marker, it moves the judge-failure count, and
it shows up in the sample totals, so a reviewer can find it and measure its
cost. A fabrication is an unmarked false observation: it returns through the
clean-parse branch, sets nothing, and is indistinguishable from a judge that
simply answered.

So a fix that refuses a wider class than strictly necessary is cheap to audit
and a fix that accepts a narrower one is not. The rule that follows: refuse the
whole class, then measure the refusal's cost against the correct population
before shipping it. Every round that instead enumerated the bad cases reopened
the hole somewhere else.
