# Rule Audit Evidence: the 2026-07-29 unified-software-engineering run

Companion to `rule-audit-procedure.md`. That document is the procedure and
carries the published table; this one carries the forensics behind it: which
judge samples were lost, what recovering them changed, and what thirteen
rounds of adversarial review found in the recovery code.

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

**Seven published cells rest on a single graded sample**, and all seven are
Opus: `fx-opus5` S1/description and S3/full, `var-opus-1` S3/baseline and
S3/full, `var-opus-2` S1/description, `var-opus-3` S1/description and
S3/description. A median of one sample is one observation. Across all 96
cells: 7 at n=1, 10 at n=2, 79 at n=3.

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

**All 24 were recovered**, each yielding three top-level integers ahead of the
prose that broke the parse. Recovery is all-or-nothing: a payload missing any
of the three fails rather than recovering a partial verdict. A salvaged sample
counts as graded and is marked `judge_salvaged`. The published table in
`rule-audit-procedure.md` is recomputed with all 24 recovered; that moved one
cell (`fx-opus5` baseline, 3.83 to 3.89) and left the sign count unchanged,
with the pooled description delta shifting from -0.13 to -0.14.

State the limit plainly. The extractor was written after seeing which samples
failed, so this is post-hoc recovery, not independent replication. Recovering
*every* failure rather than a chosen subset avoids outcome selection.

**It has since survived ten rounds of adversarial review and failed the first
nine.** The regex extractor was replaced with a structure-aware scanner, which
review then broke repeatedly, always in the same direction: it returned a
wrong verdict and reported it as a clean parse.

Thirteen defects, all one class. A scan desynchronized by a quote inside a
nested object; a second root object that *was* the real verdict; salvage
running after the range gate, re-admitting a `6` as a clean `5`; brace
counting that ignored brackets, so `[{5/5/5 exemplar}]` read as root; the same
search alive on the *success* path, returning an offset-past-zero verdict
indistinguishable from a clean parse; and finally a four-line Markdown-fence
stripper one layer upstream that replaced the whole payload with the first
fence it found, so a verdict followed by a fenced rubric exemplar was answered
with the exemplar, unmarked. Full round-by-round history is in issue #3988.

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
held-out malformed output. None has been done. Ten rounds each hardened this
function and each missed what the next found, so "it survived review" is
weaker evidence here than the round count suggests. Thirteen defects of one
class is evidence against hand-writing the parser at all (issue #3988).


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
