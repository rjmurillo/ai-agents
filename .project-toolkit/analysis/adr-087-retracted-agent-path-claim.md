# ADR-087: a retracted agent-path claim, and the guard it produced

Moved verbatim from `.project-toolkit/architecture/ADR-087-held-out-validated-improvement.md` (section "Validation Status") on 2026-11-28, so the ADR stays inside its lifecycle size cap while it takes the 2026-11-28 amendment. The text below is unchanged.

An earlier revision of this section claimed the architect spike reproduced the
rule finding on a second benchmark: two runs of `claude-sonnet-4-6` against the
same eight fixtures, five of eight moving, and an ACCEPT on a pure null control.
**That claim was wrong. It is withdrawn in full, and so is the twelve of
twenty-four figure built on it.**

The two runs did not share a corpus. Each agent report carries
`fixture_set_sha`, and `_fixture_set_sha` in `eval-agent-vs-baseline.py`
documents its purpose exactly: it "allows the report consumer to verify that two
runs hit the same set." The two architect runs report `be99fa1b1180` and
`26136df314d6`, and all eight individual `fixture_sha` values differ. The
fixtures were committed once, on 2026-05-29, after both runs; the committed
copies match the later run, so the earlier corpus is unrecoverable. Fixture
content is a second changed variable, so nothing about the movement can be
attributed to run-to-run noise.

The two corroborating pairs fail for a different reason. The critic and
high-level-advisor comparisons hold `fixture_set_sha` fixed but differ in
`agent_prompt_sha`. There the prompt is the changed variable. Three confounded
comparisons pooled together do not make one valid one.

The corrected state of the evidence is one measured path, not three:

- **Rule path, measured.** The artifact was restored byte-for-byte and verified
  identical to `origin/main` before the re-run, holding both the corpus and the
  artifact fixed. Both held-out gains that earned the ACCEPT reproduced under
  the no-op.
- **Agent path, unmeasured.** A control needs two runs agreeing on both
  `fixture_set_sha` and `agent_prompt_sha`. No committed pair did at the time.
  The 2026-11-25 amendment records the first such pair.
- **Hook path, deterministic by construction.**

The error is more useful than the claim would have been, and it belongs in this
ADR rather than in a commit message. The report schema already carried the field
that falsifies the comparison. The tool that performed the comparison never read
it. Nothing in the design would have stopped the next person from repeating the
mistake, and the person who made it had just spent a session arguing that a
property reported but not enforced is not a property. Open requirement 12
already named the missing piece, that the seam carries no corpus identity. This
is the first evidence of what that costs, and it raised the requirement from a
budget-accounting nicety to a correctness gap: the same absence that lets two
unrelated corpora share a ledger also lets two unrelated corpora be compared to
each other. Decision Requirement 5 closes the comparison half on the one path
whose
scorer publishes an identity.
