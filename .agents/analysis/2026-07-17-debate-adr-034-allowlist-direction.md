# Debate: ADR-034 allowlist direction

**Date**: 2026-07-17
**Subject**: ADR-034 (investigation session QA exemption)
**Question**: SESSION-PROTOCOL.md teaches 5 allowlist patterns. The module
`scripts/modules/investigation_allowlist.py` enforces 8. Align the docs up to
the code, or narrow the code down to the documented 5?

## Why a debate was required

The 2026-07-08 Amendment to ADR-034 re-added `.agents/critique/` after the
original Conflict Resolutions table recorded a 5-of-6 EXCLUDE ruling against
it. Aligning the protocol up to 8 propagates a reversal of a supermajority
decision into the document agents actually read. That is a governance move,
not a typo fix, so it went to a multi-model debate rather than a single review.

## Panel

| Model | Role | Verdict |
|---|---|---|
| claude-opus-4.8 | governance | SHIP WITH CHANGES |
| grok-4.5 | adversarial | SHIP WITH CHANGES |
| gpt-5.6-sol | adversarial | REQUEST CHANGES (2 findings, both adopted) |

Every prompt carried four guard clauses: paste a transcript before calling
anything broken, run a negative control on your own detector, verify the
proposed correction independently, and check adjacent statements that rot.

**Sol reviewed a stale snapshot.** Its evidence cited "19 passed" and a
"three-file diff"; the branch was at 35 tests and 16 files when the review
landed. Long-running background reviewers snapshot the worktree at some point
during their run, so every finding was re-derived against current state before
any action. Two of the four stale surfaces it named were already fixed. Both
underlying findings were still real.

## Resolution: align the docs up to the code

Both landed reviewers reached this independently, on evidence this author
reproduced.

**The reversal already happened, in-ADR and dated.** The Amendment at line 200
cites issues #732 and #831, carries a per-pattern rationale table, and updates
the Not-Allowed table in the same change. The ADR test-cases table at line 319
already records `.agents/critique/` staged as PASS. Aligning the protocol
propagates a decision the ADR already made; it does not make one.

**The original ruling is not destroyed.** It survives verbatim in the Conflict
Resolutions table at line 362. This change adds a forward pointer beneath it
and edits none of it. The protocol prose was a stale mirror, never the sole
record.

**The loophole the original ruling feared is structurally bounded.** The
allowlist is applied conjunctively; every staged file must match or the
exemption fails. Reproduced:

```text
critique only    disallowed=[] -> EXEMPT
critique + code  disallowed=['src/app.py'] -> FAILS exemption
```

A critique that actually drives implementation stages that code and loses the
exemption. This sentence is now recorded in the ADR forward pointer.

**Narrowing to 5 would cost more than it buys.** It would contradict the
Amendment, the Not-Allowed table, and the test-cases table; break the
hardcoded session-skill copy locked by `TestSessionSkillAllowlistParity`;
falsify two shipped skill docs that already teach 8; and reintroduce the #732
false failures.

## Findings adopted

Each was reproduced before it was acted on.

1. **CONTRIBUTING.md taught the stale 5** (both reviewers). Confirmed at line
   700. Updated to 8 with a pointer to the module as source of truth.
2. **`session-init/references/template-extraction.md` taught the stale 5**
   (grok only). Confirmed at line 84. This is a live template agents copy
   from, unlike the session archives carrying the same text, which are
   historical records and were left intact.
3. **The change falsified `ai-agents-validation-and-qa/SKILL.md`** (both).
   It asserted `SESSION-PROTOCOL.md:754` "still lists only the first 5",
   which this change makes false. Rewritten to state the three agree.
4. **The parity test was over-fit to formatting** (both). Three spurious
   failures reproduced against the real clause: a hand wrap, a contrast
   clarifier naming a not-allowed path, and a bolded path. Fixed by reading
   the whole clause block, matching paths independent of their delimiters,
   and asserting containment rather than set equality.
5. **The examples section was unlocked** (grok only). The section carrying the
   original "critique sessions require QA" defect was covered by no test, so
   that exact defect could return with everything else green. Now locked, and
   the lock fails against the pre-fix document.
6. **Containment accepted a widened allowlist** (sol only). Reproduced with a
   mutation matrix run against the real document. Narrowing the enumeration
   failed the suite as intended, but adding `src/` to the protocol clause
   passed everything green. That is the dangerous direction: prose teaching
   that staging `src/` earns a QA exemption, with no test objecting. Fixed by
   scoping exact set equality to the enumeration span rather than the whole
   clause. The span is a bare comma-separated list bounded by
   `limited to investigation artifacts:` and `. Use evidence:` for the clause,
   and by `when only staging:` and `See ADR-034` for the checklist comment,
   so legitimate contrast prose living outside it stays immune. The span
   parser applies no prefix filter, so a forbidden path like `src/` is
   collected and breaks equality. Reproduced after the fix: four
   widening and narrowing mutations FAIL, four formatting mutations PASS.
   Sol's own proposed fix, dropping the prefix filter across the whole clause,
   would have reintroduced the contrast false positive that finding 4 fixed.
7. **Four more surfaces taught a stale count** (sol only, list re-derived).
   `ai-agents-change-control/SKILL.md` was a frozen snapshot of the module as
   it stood on 2026-07-07. It taught 9 patterns, named
   `.agents/memory/episodes/` among them, and cited
   `ADR-034...md:79-83` to show the code had "drifted wider than the ADR"
   and would stay divergent "until an amendment lands". Every one of those
   statements was true when written and all three were invalidated by a single
   commit. `96e9bf7d2` (2026-07-08, PR #2958, "reconcile investigation
   allowlist to 8 patterns") dropped `.agents/memory/episodes/`, which was
   redundant under `.agents/memory/`, taking the module from 9 to 8, and the
   ADR Amendment landed the same day. Measured across history with the real
   accessor: `a333cb70c` 9, `59e6587c4` 9, `96e9bf7d2` 8.

   This is worth naming precisely, because the first reading was wrong. These
   are not three fabrications. They are one stale snapshot, internally
   consistent, that nobody re-measured after the commit that invalidated it.
   The citation is the instructive part: `79-83` was the whole list on
   2026-07-07 and is the first five sixths of it now, because lines 84-86 were
   appended, each tagged "Amendment 2026-07-08". A line-range citation silently
   converts into a truncated one when the cited block grows, and a truncated
   range reads exactly like evidence of drift. The remedy applied here is to
   stop restating the list in prose and call
   `get_investigation_allowlist_display()` instead; `references/provenance.md`
   keeps a range and is widened to `79-86`.

   The other two surfaces were plain staleness. `session/SKILL.md` documented
   the eligibility script's `AllowedPaths` output as 5 entries in three JSON
   examples; the script emits 8, and the real output was used rather than a
   hand-written list. `tests/evals/skills/triage-prompts.json` is a grading key
   whose expected answer listed 5 paths, so a correct 8-path answer scored
   wrong.

## Findings considered and not adopted

**Token matching cannot tell "listed as allowed" from "listed as forbidden".**
Grok showed a clause that forbids `.agents/critique/` still passes. True, and
not fixable by token matching. The two-layer check that finding 6 installed
catches both directions of the drift that actually happens, prose falling
behind code and prose running ahead of it, and the module stays authoritative.
Semantic inversion remains out of reach; the limit is recorded in the test
docstring rather than papered over.

**Path smuggling under allowlisted prefixes.** Grok confirmed a `.py` file
under `.agents/analysis/` matches, and equally confirmed this predates the
change. Out of scope for a documentation fix; not introduced here.

**ADR-034 error-message pseudocode still enumerates 5.** Already disclaimed by
the Amendment as illustrative, and the runtime message is generated from
`get_investigation_allowlist_display()`. Cosmetic and pre-existing; left alone
to keep this change scoped.

## Outcome

Docs aligned up to the code. Original ruling preserved with a forward pointer
that now states why the loophole is bounded. Four live 5-pattern teachers
corrected. Parity tests hardened against formatting and extended to the
previously unlocked examples section.
