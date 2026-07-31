# Rule Audit Parser Forensics: many rounds against one judge parser

Companion to `rule-audit-evidence.md`, which carries the published table and
the sample-recovery provenance behind it. This document is the repair history
of the parser that produced those numbers.

Read it before writing an instrument that parses judge output. The defects
below are not exotic; most are one class, and every one of them published a
number that looked ordinary.

Raw artifacts: `.agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/`

**More than twenty rounds of adversarial review have each found at least one
defect in it.** No aggregate defect count is given here, because across the rounds the
count was never defined the same way twice: it variously included parser
defects, regressions introduced by an earlier round's repair, and methodological
defects in how a claim was measured rather than in the code. An aggregate over
categories that shifted is a number with no population, which is the exact
failure this document exists to warn about. What survives restatement is the
direction, not the count. The regex extractor was replaced with a
structure-aware scanner, which review then broke repeatedly, always returning a
wrong verdict. How visible that was varied, and the variation matters more than
the count: most returned through the clean-parse branch, which sets no marker,
and one was marked `judge_salvaged` and was wrong anyway. That last case shows
an audit trail is a weaker defence than a refusal, making a guess reviewable
afterwards rather than correct.

Sixteen defects of one class. A scan desynchronized by a quote inside a
nested object; a second root object that *was* the real verdict; salvage
running after the range gate, re-admitting a `6` as a clean `5`; brace
counting that ignored brackets, so `[{5/5/5 exemplar}]` read as root; the same
search alive on the *success* path, returning an offset-past-zero verdict
indistinguishable from a clean parse; a four-line Markdown-fence
stripper one layer upstream that replaced the whole payload with the first
fence it found, so a verdict followed by a fenced rubric exemplar was answered
with the exemplar, unmarked; a duplicate-name guard that recognized a
key spelled with double quotes or escaped double quotes but not the
single-quote dialect a lenient model emits, so a stated second verdict was
invisible to it; and finally the guard that catches all of those never being
consulted on the one path that does not need to recover anything.

Each round hardened the structural reading and each left the class standing,
because **the defect is selection, not location**: every fix added a
disqualifier to a search that still had to choose which object was the
verdict. What finally worked was removing the choice. Salvage anchors at
offset 0, refuses any payload naming a score field twice as a JSON key
(matching quoted and escaped-quoted spellings), unwraps a fence only when the
payload holds exactly one, and marks every recovery `judge_salvaged`. The
generalization: when a safety argument depends on parsing what you know is
broken, the argument is the defect. Corollaries from rounds 9 and 10: an
unauditable recovery is worse than an auditable refusal, and hardening one
function does not harden the path into it.

That is strict, and it discards recoverable payloads: a leading tool trace, a
nested rubric, and two fences all fail now. The asymmetry justifies it. A
refused sample costs one of three; a fabricated one silently corrupts a
published number.

Salvage is load-bearing on the published table, and an earlier version of this
document said the opposite: that no archived sample carried a salvage marker,
so recovery could never have moved a published number. The zero is real and
the inference was wrong. The artifacts store the state *before* recovery was
applied, so the marker count is a fact about when the files were serialized.
Recovery moved one cell, as recorded above. See the archive README for the
raw counts and for what they cannot answer.

That is not a blind test, because the same author wrote all six parsers.
Falsifying it properly still takes one of: blinded manual transcription of the
failed payloads, a second parser written by someone who has not seen them, or
held-out malformed output. None has been done. Thirteen rounds each hardened
this function and each missed what the next found, so "it survived review" is
weaker evidence here than the round count suggests. Sixteen defects of one
class is evidence against hand-writing the parser at all (issue #3988, which
tracks the argument; its round log stops at nine and is not the history of
record. This document is). ADR-091 records what was decided: the bound salvage
runs under, the residuals accepted, and provider-enforced structured output as
the exit path.

Round 12 found no defect of that class and was aimed at the two least-tested
surfaces: the duplicate guard's paired-quote alternation, and the strict-parse
path that eleven rounds of attacks on salvage had never touched. It confirmed
that strict parsing rejects wrong-typed, out-of-range, duplicate, and
array-rooted verdicts before any of them can reach a cell.

That was first written up here as the first clean round. It was not. Round 13
found a defect of exactly that class in the code round 12 had just examined,
so the round was clean only in the sense that the attacks went somewhere else.
Recording a quiet round as evidence of soundness is the same
inference-from-absence that produced two of the false claims corrected above:
no finding is a fact about the attack, not about the code.

Round 12 did overturn something, and it was a justification rather than a
parser. Round 11 reported that a four-backtick fence closed at the first inner
three-backtick run and lost the sample. That was recorded as a known limit on
the reasoning that widening the matcher would restore the candidate selection
the exactly-one-fence rule exists to remove. Round 12 showed that pairing the
close to the width of the run that opened it collects every block exactly as
before and still refuses anything other than one, so the stated cost did not
exist and the limit was fixed instead. It is the fifteenth defect and the
first of a different class: a delimiter boundary that refuses valid input,
failing safe rather than fabricating. The lesson is narrower than the
selection one and worth keeping separate from it: a declined fix needs its
justification attacked on the same terms as the code.

Round 13 returned to the selection class and found the sixteenth defect, in
the exactly-one-fence rule itself. Requiring exactly one fence removes the
choice among fences. It does not remove the choice between the fence and the
prose around it. A payload whose unfenced lines carried the judge's real
verdict of 1/1/1, and whose single fenced block held a rubric exemplar the
judge had labelled "do not use", was answered with the exemplar: 5/5/5,
marked recovered, into the reducer. The rule now also requires that nothing
but whitespace sit outside the fence, which is the only condition under which
unwrapping is a rewrite rather than a choice. Every one of the twenty-four
archived prefixes recovers to a byte-identical triple afterwards, because none
of them contains a fence at all, so the published table cannot move on this.

The sixteenth defect is the strongest available evidence that the round count
is not a convergence signal. The exactly-one-fence rule was written in round
11 specifically to remove a selection, was reviewed in round 12, was extended
in round 12 with a proof that the extension restored no selection, and still
contained one. Each of those steps was correct about the thing it examined.

Round 14 found the seventeenth defect on the one path eleven rounds of attacks
had treated as safe by construction: the strict parse. A whole-payload parse
succeeding was read as proof that the payload named one answer. It is not
proof of anything of the kind. JSON nests, so a second verdict can sit inside
the first as a member, as a list element, or quoted inside a string, and the
grammar is satisfied either way; `_reject_duplicate_keys` does not see these
because a nested key is not a repeated one. Four such shapes were reproduced,
all valid JSON, all published as clean verdicts.

The guard that refuses exactly this, `_names_a_score_field_twice`, already
existed and already carried the argument for why it applies, in its own
docstring. It was wired into all three recovery paths and none of the strict
one. So the defect was not a missing idea or a missing check. It was a path
that did not know it needed one, which is why the guard now runs once, before
any parse, where a fourth path would inherit it rather than have to remember
it.

This one was worse than the recovery defects it mirrors, and in a way that
inverts the round-13 lesson. Those set `judge_salvaged`, so a wrong verdict
was at least reviewable afterwards. This returned through the clean-parse
branch, which sets no marker, so a fabricated triple was indistinguishable
from a judge that simply answered.

**The cost of this fix could not be measured against the archive at the time,
and the reason why turned out to be wrong.** The sixteen before it had been
bounded by replaying the twenty-four archived raw payload prefixes. That
bounds the *failed* population and only that population: the twenty-four are
the samples that failed, so replaying them proves what a defect cost among
failures, not among the 264 successes. Saying the sixteen were "bounded
exactly" overstates it, and the overstatement has the same shape as the
defects this section is about, a number read off one population and attached
to a sentence about another.

Successes store no raw text: the 264 published samples retain
`activation_score`, `behavior_score`, `citation_score`, `judge_failed`,
`reasoning`, and `sample_index`, and no payload. From that this document
concluded that a success-path defect was "retroactively unmeasurable by
construction." **That conclusion was false, and round 15 disproved it.** The
archive is not the only record of a run. The harness keeps full assistant
messages, so the judge payloads behind the 264 successes still existed and
were recovered. See the round 15 section for what that changed. The archive
gap is real and remains issue #3998: the run artifacts themselves store no raw
payload, and recovering one from a session transcript is a salvage move, not a
property of the instrument. What was wrong was the claim that the gap made the
question unanswerable, which was an inference from absence, not a proof.

The refusal has one cost that was misjudged in the same paragraph. The guard
refuses outright on any `\u` in the payload, because a score field name
spelled with a unicode escape would evade a textual count. This document said
that on the recovery paths it "costs nothing, since those payloads are already
malformed." That is true of the tail-bearing recovery path and false of the
fenced one, where a well-formed verdict merely wrapped in a fence is refused
for containing an em-dash. Round 15 measured the real exposure and repaired
it.

Round 14 left one finding unfixed by design. The two recovery helpers accept
different payloads in both directions: a fenced verdict recovers through
`_recover_verdict` and not `_salvage_scores`, a broken-string verdict the
reverse. Live scoring composes both so it is covered, but archive replay calls
`_salvage_scores` directly, which means a future archived score can depend on
which helper the caller reached for. That is a seam rather than a wrong
answer, and it belongs with the aggregator work rather than the parser work,
so it is filed as issue #3999 and not fixed here.

Round 15 attacked the round 14 fix and broke it in three places, but its most
useful finding was not a defect in the parser at all. It was a defect in the
claim above that the parser could not be measured.

The archive is not a closed population. Copilot CLI keeps every assistant
message in a session transcript, so the raw judge payloads behind the 264
successful samples were still on disk. Recovering them is a scan: 465 of 3366
sessions mention `activation_score`, yielding 474 candidate messages and 466
distinct payload texts. Round 15 correlated each payload back to a published
cell by its parsed triple and reported 264 of 264 matched. Round 16 showed
that correlation was circular and redid it; the recovery itself holds, but the
attribution it produced was wrong for six coordinates. The corrected method is
recorded below.

That moves the parser from "verified on 24 of 288 published cells" to
**verified on all 288**: 264 successes re-score to their published triples
exactly, and the 24 archived failures recover to byte-identical triples. All
288 recovered payloads are archived beside the results they produced as
`recovered-judge-payloads.json`, and
`test_every_published_cell_still_scores_to_its_archived_triple` replays them
on every test run, so this stops being a one-time forensic exercise and
becomes a standing guard. Sabotaging the ambiguity check makes that test
report all 264 cells as changed; it is not a test that can only pass.

What the recovered payloads then measured was that round 14's own fix was a
regression. Round 14 moved the textual ambiguity guard to run before any
parse, on every path, which meant a payload containing `\u` was refused
outright regardless of how healthy it was. Because `json.dumps` defaults to
`ensure_ascii=True`, an em-dash or a curly quote anywhere in a judge's
reasoning serializes to `\uXXXX`. A plain, strictly-parseable verdict whose
prose contained punctuation was therefore scored 0/0/0. Measured cost against
the archive: zero, since no payload among the 288 carries an escape. Forward
cost: a judge writing an em-dash, which is likely.

The repair reverses a round 14 design decision. Round 14 ran one textual guard
everywhere on the reasoning that "divergent strictness between paths is itself
a defect." That conflated two things. Divergent strictness *for the same
question* is a defect; genuinely different questions need different
instruments. Where the parse succeeded, escapes are decoded and structure is
known, so the exact question can be asked exactly: count score-bearing objects
at any depth and scan the decoded strings for a key-shaped score field. No
blanket is needed. Where text follows the object and is never parsed, a second
verdict can hide in that tail with escapes still undecoded, so the raw count
including the `\u` blanket stays. A lone fence is the first case, not the
second, because unwrapping already requires that nothing but whitespace sit
outside it.

Round 15 also found a shape no textual method can catch: Python adjacent
string literals, where `'activation' '_score'` concatenates under the grammar
and the field name is never a contiguous substring. It is reproduced and
accepted rather than fixed, and the reasoning is recorded in
`test_adjacent_string_literals_are_a_known_undetected_shape`. The encoding
space is open, so enumerating spellings cannot close the class; the source
here is a cooperating judge rather than an attacker; none of the 288 payloads
carries the shape; and the top-level object is the schema's answer slot, so an
undetected prose verdict loses to the verdict the judge actually filed. The
durable answer is provider-enforced structured output, not another regex.

Round 16 found two defects, and the first was one this session had just
introduced. The round 15 repair replaced a raw-text guard with a structural
check over the parsed object, and that check walked `dict.values()` only. A
JSON object key is a string too, so a second verdict serialized into a key
passed as a clean 1/1/1 on the plain path and as a salvaged 1/1/1 on the
fenced path. The guard being replaced had caught that shape. A replacement
that is weaker than what it replaces, on the exact case it exists to stop, is
not a repair; the walk now covers both halves of every pair, and
`test_a_verdict_hidden_in_an_object_key_is_two_verdicts` fails without the
fix while a legitimate verdict whose prose carries an em-dash still scores.

The second finding was methodological, and it is the more useful one. The
round 15 correlation matched each recovered payload to a published cell **by
its parsed triple**, then verified the match **by the parsed triple**. Any
wrong payload that happened to produce the same triple satisfied that check by
construction. The measurement is easy to state once seen: 264 coordinates drew
on only 258 distinct source events, with 4 events assigned to 10 coordinates
between them, so 6 coordinates carried a payload that was not theirs.

The fix is an oracle that does not touch the score. Every judge call embeds
the response it is grading under an `**Actual response**` heading, and every
archived mechanism stores a `response_preview` of that same response.
Matching those ties a payload to a cell **by its input**. Recovering the
prompts found 448 of 474; each published mechanism matched exactly its own
judge repeats, and ordering those chronologically assigns every sample. The
result is 288 coordinates on 288 distinct source events with no reuse, and all
264 successes still re-score to their published triples. Six attributions
changed, matching the count the circularity analysis predicted.

Two things came free. Correlating on the input reaches the 24 failures as
well, so their full payloads are archived instead of the 200-character
`reasoning` prefix, which retires that truncation limit for this run. And
replaying all 288 measures the recovery divergence exactly: every one of the
24 samples the published run refused is recovered by the current parser, each
to a triple whose three values appear literally in its raw payload as score
fields. Those triples were never published, so they are pinned as a baseline
rather than checked against a published number. That is the concrete size of
issue #3999 for this run: 24 of 288 cells would change if it were re-scored
today.

Round 16 also hardened the replay test against a gap it left. Walking only the
archive keeps a test green while the archive loses a coordinate or assigns one
source event to two cells. The test now asserts coordinate-set equality
against the published table and source-event uniqueness, and both assertions
were negative-controlled by dropping an entry and by duplicating a source.

Round 17 found three more, and the first is the one that had been assumed
away. Every guard above rests on the parse having decoded the escaping, so a
string was thought to arrive fully decoded. A parse decodes exactly one layer.
A judge that spells its second verdict `{\"\u0061ctivation_score\":5,...}`
inside `reasoning` produces, after the parse, literal backslash-u text that no
pattern for `"activation_score"` matches. The payload carried a corrected
5/5/5 beside a filed 1/1/1, and both parsed-region paths published the 1/1/1
with no mark on it. The guard now peels up to three further escape layers and
asks the question the parse could not.

The second defect was in the guards themselves. Both ambiguity walkers
recursed, and Python's recursion limit is far lower than what the JSON
decoder's C scanner accepts, so a healthy verdict carrying a nested member a
thousand deep raised `RecursionError`. That subclasses `RuntimeError`, which
the scoring call site catches as a transport error, so the sample was filed as
a judge API failure and dropped. A defense against fabrication was silently
deleting valid observations. Both walkers are now iterative.

The third defect is the mirror image, and it corrects a bias in the rule this
session had been applying. A judge writing `I assigned "activation_score": 5
because ...` while filing 5 was refused as carrying two verdicts. It carries
one, stated twice. Refusing it is not the conservative choice: a dropped
sample moves a published median exactly as a fabricated one does. The
discriminator is disagreement, not mention. The guard now compares the named
value against the value actually filed and refuses only on a conflict, or when
the two cannot be compared at all. All 288 archived payloads are unaffected by
all three changes; none carries either shape.


Round 18 corrected the reasoning behind round 17's third fix, and the
correction governs the rest. Round 17 argued that an over-eager refusal is a
defect in the same family as an over-eager accept, "because a dropped sample
moves a published median exactly as a fabricated one does." That equivalence
is wrong. A refusal moves the median **visibly**: it lands in `judge_failed`
and in the sample count, where the recovery pass above found it. A fabricated
sample moves the median **invisibly**, as an unmarked false observation. The
rule that follows is narrower than round 17 wrote it: an equal restatement may
be accepted only where equality is established **exactly**. Two of the four
round-18 defects are cases where round 17 claimed equality without
establishing it exactly.

The first defect is the double serialization that round 17's fix half-solved.
`json.dumps` applied twice turns `\u0061` into `\\u0061`, two backslashes. A
peel that only understands `\uXXXX` matches the *second* backslash, consumes
it, and leaves `\activation_score`, which no further peel can decode and no
field pattern can match. The peel now handles `\\` first, along with `\"`,
`\/`, and the control escapes, so the layer decodes to `\u0061` and the next
one to `a`. Handling order is the whole fix.

The second defect is the inexact comparison. The named-value pattern captured
`(-?[0-9]+)?`, an integer prefix, so a judge writing `"activation_score": 1.5`
beside a filed `1` had its `1.5` read as `1`, matched, and was published as
agreement. `1e1` beside a filed `1` did the same. The pattern now captures the
value token up to the next whitespace or JSON delimiter, and round 19 below
records why stopping there is still not the whole value.

The third defect is the same failure of exactness one level up. The escape
peel stops after a fixed number of layers. A payload escaped four times
exhausted that budget with content still undecoded, and the exhausted walk
returned no contradiction, which the caller read as agreement. Running out of
budget is not evidence of agreement. The walk now reports whether it was
truncated, and a truncated walk refuses.

The fourth is a liveness defect in round 17's own fix. Making both walkers
iterative removed `RecursionError` and with it the recursion limit that had
been terminating a self-referential object by accident. Both walkers now carry
an identity-keyed `seen` set.

The fifth defect in this round is one this session introduced while fixing the
third, and it is recorded because of how it was caught rather than what it
was. The first truncation fix refused on any layer that still had anything to
decode, not on a truncated walk. A judge quoting a Windows path in `reasoning`
leaves a literal `\U` and `\b` in the parsed string; `\b` is a JSON escape, so
that payload decoded further, so it would have been refused. The symptom that
exposed it was a negative control **passing**: disabling the backslash
handling left the double-serialization test green, because the refusal was
coming from the truncation arm rather than from the code the test was supposed
to pin. A negative control that passes is as informative as one that fails.
Both mean the test passes for a reason other than the one claimed. The
Windows-path, regex, and newline cases are now pinned as tests that must
score.

Every round since re-runs the same check: replay all 288 archived judge
payloads and compare the recovery divergences by coordinate, not by count
(issue #3999). The answer has been the same 24 cells every time, through
round 21, so no parser fix recorded here moves the published table.

Round 19 found that the round-18 comparison was still not exact, in both
directions, and the two errors are not symmetric. The value token stops at
whitespace, so `"activation_score": 5 - 1` beside a filed `5` captured `5`,
compared equal, and would have published a 5 the judge had corrected to 4,
with nothing in the record marking it. That is the fabrication class this
whole line of work exists to prevent, reached through the fix that was
supposed to close it. Round 19 answered it by naming `-+*/%` as characters
equality cannot cross, which round 20 then had to withdraw.

The same comparison could also end a run. `int(token)` on a digit run longer
than 4300 characters raises `ValueError`, which CPython imposes deliberately;
`eval_one_scenario` catches `RuntimeError`, so one adversarial judge response
would have aborted every scenario after it. The check now compares decimal
spellings and never converts, which removes the crash and, as a side effect,
stops reading `05` as agreement with a filed `5`.

The over-refusals ran the other way and were larger in practice. Comparing the
raw token refused every judge who ended a sentence on the number, so
`"activation_score": 5.` and `5;` and `5)` all failed; trailing sentence
closers are now stripped, while `1.5` keeps its decimal and stays
uncomparable. A three-layer decode budget refused a judge merely discussing
regex escaping, over a remainder that held no score field at all; the budget
is now eight, which absorbs 256 consecutive backslashes. Each peel strictly
shortens the string, so the walk terminates on its own and the budget bounds
cost rather than termination.

Two of these seven fixes were caught only by negative-controlling them: an
operator set that included `(` refused ordinary parentheticals, and the
budget-exhaustion test kept passing after the budget was raised because the
buried field then decoded into view and refused as a *contradiction* instead.
It asserted the right outcome for the wrong reason. Each of the seven now has
a control that fails when the fix is reverted, and the budget boundary is
pinned from both sides.

Round 20 found the operator list was the wrong shape. Naming `-` invited the
question of what else reaches a token, and the answer was `^`, `&`, `<<`,
`and`, `if/else`, and `?:`, each restating a filed 5 and publishing unmarked.
What replaced it named no operator: a value run bounded by a JSON delimiter,
accepted only when it began with the filed decimal spelling and carried no
further digit. Round 21 broke that too. Operands need not be digits, so
`5 - True` was accepted; stripping sentence closers read `5!` as `5`; the run
bound ended before `5, but corrected it to 1`; and the no-further-digit clause
refused `5 because all 3 concepts were present`, which is ordinary prose.

Three rounds, three proofs of lexical equality, three sets of holes. Each
enumeration was unbounded, so patching one reopened it somewhere else. The fix
was to stop proving equality: any decoded layer that names a score field is now
uncomparable and refuses. The cost was measured before the change rather than
assumed. Across the 264 nested reasoning values in the 288 archived payloads,
zero name a score field in
a layer beyond the top-level object, so refusing the class drops no sample any
real judge has produced.

A first attempt at that measurement counted 1732 and was wrong, in the way this
document keeps warning about: the walk covered the whole archive envelope,
including artifact names, session identifiers, and provenance prose, none of
which the parser ever reads. The population the sentence attaches to is the
nested reasoning values, and there are 264 of them. The claim's direction did
not change, but a number quoted against the wrong population is not evidence
for anything, whichever way it points.

Round 22 found the refusal was still enumerating, one level up. It required the
field name to be quoted and followed by a colon, so `{activation_score:1}`
(JSON5 bare key), `dict(activation_score=1)` (Python, `=` not `:`), and
`Final activation_score: 1, not 5.` (prose, no braces) all bypassed it and
published unmarked. Adding a bare-name-plus-colon alternative would have left
`=` and every other separator, which is the same trap a fourth time. The
refusal now matches the bare field name with no quoting and no separator
required. Measured against the same 264 values, all three candidate policies
refuse zero, so the terminal form costs nothing over the narrow one and has
nothing left to enumerate.

Round 20 also found a regression round 19 had introduced. The pattern grew a
trailing group to capture the value, and being greedy it consumed the rest of
the layer, so every field after the first went unread: a judge restating
`5/1/1` beside a filed `5/4/5` agreed on the one field checked and published
two fabricated scores. The pattern now ends at the colon and captures no value.

Round 23 found that the round-22 repair was itself the next defect, which makes
it the most useful round in this document: the fix and the defect are the same
edit. Dropping the quoting requirement meant the walker's *keys* now matched,
and a healthy payload's own root key is `activation_score`, so every real
payload refused itself. The repair exempted any string equal to a field name,
on the reasoning that a string holding only a name holds no number and so
carries no verdict. That reasoning is true of the string and false of the
payload. It published this unmarked:

    {"activation_score": 5, "citation_score": 4, "behavior_score": 5,
     "corrected_verdict": [{"field": "activation_score", "value": 1}, ...]}

Every field name sits in value position and every competing number sits in a
sibling key, so the exemption excused all three names and the filed 5/4/5 was
published over a stated 1/1/1. The number never had to be in the same string.

The skip now lives in the walker and applies to keys only, and the distinction
it turns on is not lexical: a key that is exactly a field name is the schema
slot the parser already read, while a value that equals a field name is a
*reference* to a field, which is the shape a competing verdict record takes.
Padding no longer excuses either, because the skip is equality rather than
`strip`, so `"  activation_score  "` is not the slot the schema defines and a
judge emitting one is naming a field somewhere the parser does not read.

Round 23 also found two defects in how claims about this work were measured
rather than in the code: a test-count detector that could not see the tests it
was quoted for, and an edit that silently consumed the structural marker at the
foot of this file. Both belong to a class that has now recurred often enough to
have its own record, with the false negative controls from round 20 and the
1732 miscount above. See `rule-audit-measurement-discipline.md`.

<!-- vendor-portability: declared. This file cites
.agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/ as the archive holding the eight runs whose forensics are recorded here, so a reader can re-measure every claim instead of taking it on faith. It is a citation in a narrative, not a path the skill reads or writes. A vendored install loses the ability to re-measure our raw artifacts locally; the forensics still read as a record of what went wrong and what to check for, which is what this file is for. Issue #2050. -->
