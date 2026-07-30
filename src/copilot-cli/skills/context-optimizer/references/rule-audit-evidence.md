# Rule Audit Evidence: the 2026-07-29 unified-software-engineering run

Companion to `rule-audit-procedure.md`. That document is the procedure and
carries the published table; this one carries the forensics behind it: which
judge samples were lost, what recovering them changed, and what twenty-three rounds
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

**Two sources, and the difference decides what is knowable.** The eight run
artifacts store, for each of the 24 failures, the first 200 characters of the
judge output and nothing more; all 24 are exactly 200, the truncation ceiling.
`recovered-judge-payloads.json` is a later addition and holds the *full*
original for all 288 samples, 169 to 674 characters, the 24 failures spanning
353 to 625. It was recovered from the Copilot CLI session transcripts and
correlated on the judge prompt's **Actual response** block, which is the
sample's input and so independent of the score the payload produces, and it
resolved to 288 distinct source events for 288 samples. Claims below that were
written against the prefixes are marked where the originals now settle them.

**The cause is recoverable, and it is uniform.** All 24 break inside the
`reasoning` value at an unescaped double quote, where the judge quoted a phrase
from the response it was grading. Re-parsing the 200-character prefixes
reported `Unterminated string` for 19 of 24, which was the truncation talking;
at full length the error is `Expecting ',' delimiter` for 24 of 24. An earlier
draft asserted unescaped quotes, a later one retracted it as unmeasurable at
200 characters. The retraction was right about the prefixes and the original
assertion was right about the payloads.

**The failure is entirely model-correlated.** All 24 sit in Opus-judged runs;
the 144 Sol-judged samples produced none. The mechanism is not verbosity,
though the verbosity gap is real: Opus payloads average 456 characters against
Sol's 213. It is inline quotation and the escaping of it. Opus attempts a
quoted phrase inside `reasoning` in 28 of its 144 payloads (19.4%) against
Sol's 6 of 144 (4.2%), and escapes it correctly in 4 of those 28 (14%) against
Sol's 6 of 6 (100%). So Opus reaches for the construct four times as often and
then mostly gets it wrong, which is a sharper statement than "verbose models
trip it more often" and is measured against both populations rather than one.

**The discarded-tail worry is closed.** An earlier draft noted that a longer
original whose cut-off tail named the score fields a second time would produce
a byte-identical 200-character prefix, would be refused by the duplicate-name
guard rather than recovered, and that the archive could not check it. The
originals check it: 0 of 24 trip the duplicate-name guard, and all 24 salvage
to three top-level integers. The same holds for the related worry that a
recovered prefix is authentically the judge's first answer but not its final
one. With the whole payload in hand there is no unseen tail to carry a
correction, and none of the 24 contains a second verdict.

**Recovery is all-or-nothing**: a payload missing any of the three fields fails
rather than recovering a partial verdict. A salvaged sample counts as graded
and is marked `judge_salvaged`. The published table in `rule-audit-procedure.md`
is recomputed with all 24 recovered; that moved one cell (`fx-opus5` baseline,
3.83 to 3.89) and left the sign count unchanged, with the pooled description
delta shifting from -0.13 to -0.14.

**Replaying all 288 through the current parser diverges on exactly 24
coordinates, and they are exactly the 24 failures.** The two sets are identical,
so the parser's repairs changed the outcome only where the judge emitted
malformed JSON and left the other 264 untouched. A divergence set that matched
the failure set by count but not by coordinate would be the worrying result;
this one is the reassuring one.

The headline survives all of it. The sign test is 7 positive to 1 negative,
p = 0.0703125, identically under the pre-recovery table, the post-recovery
table, and either reduction in issue #3989.

State the limit plainly. The extractor was written after seeing which samples
failed, so this is post-hoc recovery, not independent replication. Recovering
*every* failure rather than a chosen subset avoids outcome selection.

## The instrument that produced this table was reviewed across 23 rounds

Every number above comes out of one parser. That parser has been under
adversarial review for twenty-three rounds, and the rounds keep finding defects,
so its repair history is evidence about the table as much as the table is.
`rule-audit-parser-forensics.md` carries the round-by-round record: what each
round found, what it cost, and which fixes were themselves wrong. Read it
before writing a new instrument that parses judge output, and before trusting
any parser of this kind that has not been attacked.
<!-- vendor-portability: declared. This file cites .agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/ as the archive holding the eight runs whose forensics are recorded here, so a reader can re-measure every claim instead of taking it on faith. It is a citation in a narrative, not a path the skill reads or writes. A vendored install loses the ability to re-measure our raw artifacts locally; the forensics still read as a record of what went wrong and what to check for, which is what this file is for. Issue #2050. -->
