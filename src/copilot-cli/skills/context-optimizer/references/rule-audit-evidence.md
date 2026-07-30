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

**Fourteen rounds of adversarial review have found seventeen defects in it, the
most recent in round 14.** The regex extractor was replaced with a
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

**The cost of this fix cannot be measured against the archive, and that is
itself the finding.** Every one of the sixteen before it was bounded exactly,
by replaying the twenty-four archived raw payload prefixes. That works only
because failures store their raw text. Successes do not: the 264 published
samples retain `activation_score`, `behavior_score`, `citation_score`,
`judge_failed`, `reasoning`, and `sample_index`, and no raw payload. A defect
on the success path is therefore retroactively unmeasurable by construction.
The archive gives no evidence either way about whether any published cell came
from an ambiguous payload. The only signal available is weak and indirect: no
stored `reasoning` on any of the 264 trips the guard. That is not the same
question, because `reasoning` is the parsed field rather than the payload it
came from. Recorded as issue #3998; the fix is to retain a truncated raw
payload on success as well as on failure.

The refusal has one unmeasured cost, in the same direction. The guard refuses
outright on any `\u` in the payload, because a score field name spelled with a
unicode escape would evade a textual count. On the recovery paths that costs
nothing, since those payloads are already malformed. On the strict path it can
now refuse a healthy verdict whose `reasoning` happens to carry an escape. How
often that happens cannot be read off the archive either, for the same reason.
It is accepted rather than optimized away: a refusal costs one of three
samples and announces itself, and this session has now produced seventeen
demonstrations that the other direction does not.

Round 14 left one finding unfixed by design. The two recovery helpers accept
different payloads in both directions: a fenced verdict recovers through
`_recover_verdict` and not `_salvage_scores`, a broken-string verdict the
reverse. Live scoring composes both so it is covered, but archive replay calls
`_salvage_scores` directly, which means a future archived score can depend on
which helper the caller reached for. That is a seam rather than a wrong
answer, and it belongs with the aggregator work rather than the parser work,
so it is filed as issue #3999 and not fixed here.


Reproduce the recovery from any archived run. The failed samples store the
truncated raw payload in their `reasoning` field behind a
`judge parse error: ` prefix; strip that prefix and feed the remainder to
`_salvage_scores`. Walking the artifact needs care about its shape: `rules` is
a **dict keyed by rule name**, and each scenario's `mechanisms` is likewise a
**dict keyed by** `baseline`/`description`/`full`, not a list. Only
`scenarios` is a list. A walker that assumes lists finds zero samples and
prints a clean result from no data, which is the same failure class as the
parser defects recorded above: a confident answer derived from nothing. A
walker that reads
`rules[<name>].scenarios[].mechanisms[<mech>].score_samples[]` and re-medians
each cell reproduces the published table exactly.

<!-- vendor-portability: declared. This file cites .agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/ as the archive holding the eight runs whose forensics are recorded here, so a reader can re-measure every claim instead of taking it on faith. It is a citation in a narrative, not a path the skill reads or writes. A vendored install loses the ability to re-measure our raw artifacts locally; the forensics still read as a record of what went wrong and what to check for, which is what this file is for. Issue #2050. -->
