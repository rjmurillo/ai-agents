# Rule Audit Evidence: the 2026-07-29 unified-software-engineering run

Companion to `rule-audit-procedure.md`. That document is the procedure and
carries the published table; this one carries the forensics behind it: which
judge samples were lost, what recovering them changed, and what eighteen rounds
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

## The instrument that produced this table was repaired 21 times

Every number above comes out of one parser. That parser has been under
adversarial review for twenty-one rounds, and the rounds keep finding defects,
so its repair history is evidence about the table as much as the table is.
`rule-audit-parser-forensics.md` carries the round-by-round record: what each
round found, what it cost, and which fixes were themselves wrong. Read it
before writing a new instrument that parses judge output, and before trusting
any parser of this kind that has not been attacked.
<!-- vendor-portability: declared. This file cites .agents/analysis/eval-artifacts/2026-07-29-unified-software-engineering/ as the archive holding the eight runs whose forensics are recorded here, so a reader can re-measure every claim instead of taking it on faith. It is a citation in a narrative, not a path the skill reads or writes. A vendored install loses the ability to re-measure our raw artifacts locally; the forensics still read as a record of what went wrong and what to check for, which is what this file is for. Issue #2050. -->
