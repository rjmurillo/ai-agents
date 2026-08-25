# Debate Log: ADR-063 frontmatter transcription

**Records**: ADR-063
**Trigger**: PR #5209 review. Copilot found that
`tests/test_adr_063_memory_skill_decomposition.py` asserts the pre-#5189 parser
contract and still passes, because it replicates the parser instead of calling
it.

## No debate was held

Recording that plainly rather than manufacturing one. This is a transcription of
an already-recorded human decision into a machine-readable field, and a repair
to a record this PR itself broke. It is not a new decision, and there is nothing
for six roles to disagree about.

## What was found

ADR-063 carried no frontmatter. Its machine-readable status was a bare
`status: accepted` line sitting in the body of its `## Status` prose section, at
line 12. That resolved only because `_get_adr_status` searched the whole
document and took the first match.

Issue #5189, closed by this PR, is exactly that defect. So fixing the parser
silently changed ADR-063's effective status from `accepted` to `unknown`. Nothing
caught it, because the three tests covering ADR-063's status each reimplemented
the old regex rather than calling the parser.

Measured before the repair:

```
docstring claims          "proposed"
test assertion requires   "accepted"
canonical parser returns  "unknown"
```

Three answers in one file, two of them in the same docstring-and-assertion pair.

## What changed

1. **ADR-063 gained real frontmatter**, transcribing what its prose already
   records: `status: accepted`, `date: 2026-06-01`, `implemented: true`.
2. **The orphan body `status: accepted` line was removed.** It existed only to
   satisfy the broken parser and is now duplication of the kind the owner
   rejected on ADR-005 and ADR-024.
3. **The tests now call `_get_adr_status`** instead of replicating it, so they
   cannot silently diverge from it again
   (`.claude/rules/canonical-source-mirror.md`).

## Is this a forged approval?

No, and the question deserves an answer rather than an assumption. ADR-073 warns
that "a hand-edit of frontmatter to `accepted` MUST NOT be treated as governance
approval". The acceptance being transcribed here is not created by this edit. It
is recorded in ADR-063's own prose, dated, attributed, and pointing at its
review record:

> Accepted by maintainer 2026-06-17. The maintainer authorization satisfies the
> adr-review gate for this status flip; this acceptance records the human
> decision and does not append a fabricated debate log. Architect-review record:
> `.agents/critique/ADR-063-debate-log.md`.

The prose has said Accepted since 2026-06-17. The frontmatter now says the same
thing in a field a tool can read. No character of the acceptance rationale
changed. This is the same reasoning the six-role review accepted for ADR-042
earlier in this campaign.

The inverse is what would be dishonest: leaving the record reading `unknown` to
every corrected reader, when a maintainer accepted it eight weeks ago.

## Verification

```
canonical parser on ADR-063     accepted   (was unknown after the #5189 fix)
tests                           26 passed
mutation: restore body-only status
  test_detector_resolves_status_to_accepted        FAILED
  test_status_is_declared_in_frontmatter_not_body  FAILED
restored                        26 passed
```

The mutation matters: it proves the new assertions actually detect the shape
that was wrong, rather than passing because the record happens to be correct.
