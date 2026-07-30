# Rule Audit Evidence: the 2026-07-29 unified-software-engineering run

Companion to `rule-audit-procedure.md`. That document is the procedure and
carries the published table; this one carries the forensics behind it: which
judge samples were lost, what recovering them changed, and what fourteen rounds
of adversarial review found in the verdict-parsing code.

Read this before citing a number from the procedure document, and before
writing a new instrument that has to parse judge output.

Raw artifacts: `.agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/`.

## The judge discarded Opus samples unevenly, and it was recoverable

An earlier version of this table claimed every cell was graded on the full
sample. **That was false.** Seventeen of the 48 Opus cells, one in three, were
averaged over one or two judge samples instead of three: 10 cells lost one
sample and 7 lost two. That is 24 of 144 Opus judge samples, one in six, all
in positive scenarios. The `total_judge_failures` field the claim rested on
counts affected cells, not failed samples (issue #3958), which is how the
undercount survived.

**The loss is confined to Opus, and that is a confound, not a footnote.** All
24 failures sit in the four Opus artifacts (`fx-opus5` 6, `var-opus-1` 8,
`var-opus-2` 4, `var-opus-3` 6). All four Sol files lost nothing. The Opus
rows are also the rows carrying the large positive delta-full (+1.11, +1.22,
+1.22) that drives the headline result, so the runs most affected by recovery
are the runs the conclusion leans on. An earlier draft placed all 24 in
`var-opus-*.json`, which is wrong; a sixth of them are in `fx-opus5.json`.

**Seventeen published cells carry a recovered sample**, and all seventeen are
Opus. Pre-recovery the archive holds 7 cells at n=1, 10 at n=2, and 79 at n=3;
the 7 and the 10 account for exactly the 24 lost samples. The published table
is the post-recovery one, so all 96 cells use three samples, and no published
cell rests on a single observation. What the seventeen rest on instead is
post-hoc recovery: seven of them (`fx-opus5` S1/description and S3/full,
`var-opus-1` S3/baseline and S3/full, `var-opus-2` S1/description,
`var-opus-3` S1/description and S3/description) take two of their three
samples from recovered prefixes, and ten take one. An earlier draft called
these "seven published cells resting on a single graded sample," which read
the pre-recovery population and attached it to the post-recovery table.

A cell reduced to two samples takes the median of an even count, so its score
can land on a half-integer and the scenario average can leave the 1/9 grid a
full sample would put it on. That is where the `fx-opus5` baseline of 3.83
came from. If a pre-recovery number will not divide by 9, this is why.

**The cause is not recoverable from the archive, so do not state one.** The
artifacts retain only a 200-character prefix of the judge output. Re-parsing
those prefixes reports `Unterminated string` for 19 of 24, which is the
truncation talking, and only 5 show a stray quote inside the window. An
earlier draft asserted all 24 were unescaped quotes and that verbose models
trip it more often. The first is unmeasurable at 200 characters; the second is
a mechanism the artifacts never recorded. Widen the prefix before claiming a
cause again (issue #3975).

**All 24 stored prefixes recover**, each yielding three top-level integers
ahead of the prose that broke the parse. Recovery is all-or-nothing: a payload
missing any of the three fails rather than recovering a partial verdict. A
salvaged sample counts as graded and is marked `judge_salvaged`. The published
table in `rule-audit-procedure.md` is recomputed with all 24 recovered; that
moved one cell (`fx-opus5` baseline, 3.83 to 3.89) and left the sign count
unchanged, with the pooled description delta shifting from -0.13 to -0.14.

**That is a claim about the prefixes, not about what the judge emitted.** All
24 stored prefixes are exactly 200 characters, the truncation ceiling, so
every one of them is cut. The same 200-character limit that makes the cause
unrecoverable two paragraphs above makes the originals unrecoverable here, and
an earlier draft applied it to the cause and forgot it for the recovery. A
longer original whose discarded tail named the score fields a second time
would produce a byte-identical stored prefix and would be refused by the
duplicate-name guard rather than recovered. The recomputed table therefore
assumes no discarded tail would have changed the verdict, and the archive
cannot check that assumption.

An earlier draft went one step further and said the error has a direction:
that the recovered values are a genuine prefix of what the judge wrote, so
they cannot be wrong. **The second half does not follow from the first.**
Genuine bytes are not a final verdict. A judge that scored, then corrected
itself further down the payload, emits a prefix that is authentically its
first answer and not its answer. The concrete case is the one cell this
recovery moved: appending `and then corrected itself: "activation_score":1,
"citation_score":1, "behavior_score":1.` to the stored `fx-opus5` S3 baseline
prefix leaves the first 200 characters byte-identical and makes the real
parser refuse the payload outright. So the recovered values were genuinely
emitted but may be neither the final nor the uniquely intended verdict, and a
sample the real parser would have refused can be present. Widen the prefix
(issue #3975) before treating the recomputed cells as measured.

The headline survives all of it. The sign test is 7 positive to 1 negative,
p = 0.0703125, identically under the pre-recovery table, the post-recovery
table, and either reduction in issue #3989.

State the limit plainly. The extractor was written after seeing which samples
failed, so this is post-hoc recovery, not independent replication. Recovering
*every* failure rather than a chosen subset avoids outcome selection.

**Fifteen rounds of adversarial review have found seventeen defects in it, plus
one regression introduced by the round 14 repair and caught in round 15.** The
regex extractor was replaced with a
structure-aware scanner, which review then broke repeatedly, always in the same
direction: it returned a wrong verdict. How visible that was varied, and the
variation matters more than the count. Most returned through the clean-parse
branch, which sets no marker. The sixteenth was marked `judge_salvaged` and was
wrong anyway, which is the case that shows an audit trail is a weaker defence
than a refusal: it makes a guess reviewable afterwards, not correct.

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
record. This document is).

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
gap is real and remains issue #3998; the claim that it made the question
unanswerable was an inference from absence, not a proof.

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

One process note, since it cost real work. Negative-controlling a source fix
by reverting the file with `git checkout` destroys any *other* uncommitted
change in it. That is how the two fixes above were lost and had to be rebuilt.
Copy the file aside and copy it back instead; the tests written moments
earlier are what caught the loss.

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


Reproduce the recovery from any archived run. The failed samples store the
truncated raw payload in their `reasoning` field behind a
`judge parse error: ` prefix; strip that prefix and feed the remainder to
`_salvage_scores`. The successful samples store no payload in the artifact at
all. Both are recovered in full in `recovered-judge-payloads.json` beside it,
keyed by the same coordinates and attributed by the input-based oracle
described above rather than by the score. Walking the artifact needs care about its
shape: `rules` is a **dict keyed by rule name**, and each scenario's
`mechanisms` is likewise a **dict keyed by**
`baseline`/`description`/`full`, not a list. Only
`scenarios` is a list. A walker that assumes lists finds zero samples and
prints a clean result from no data, which is the same failure class as the
parser defects recorded above: a confident answer derived from nothing. A
walker that reads
`rules[<name>].scenarios[].mechanisms[<mech>].score_samples[]` and re-medians
each cell reproduces the published table exactly.

<!-- vendor-portability: declared. This file cites .agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/ as the archive holding the eight runs whose forensics are recorded here, so a reader can re-measure every claim instead of taking it on faith. It is a citation in a narrative, not a path the skill reads or writes. A vendored install loses the ability to re-measure our raw artifacts locally; the forensics still read as a record of what went wrong and what to check for, which is what this file is for. Issue #2050. -->
