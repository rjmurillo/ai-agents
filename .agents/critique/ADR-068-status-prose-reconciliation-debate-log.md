# Debate Log: ADR-068 Status Prose Reconciliation

## Scope and reviewer

**Single-reviewer record, not a six-role debate.** One reviewer (Claude Code,
autonomous bounded issue campaign, issue #5190) examined the change. The
`adr-review` six-agent roster was not convened. This is stated plainly because
the gate accepts single-reviewer logs by design, and a record that implied a
debate it did not hold would be worse than one that did not exist.

The scope test that justifies the lighter treatment: this change alters **no
decision, no context, no consequence, and no frontmatter**. It adds two lines of
prose to a `## Status` section so the section opens with the lifecycle word the
frontmatter already carries. If the change had moved `status`, added or removed
a supersession edge, or touched any Decision text, this record would not be
sufficient and the roster would be owed.

## The defect

`scripts/validation/check_adr_lifecycle.py` reported exactly one violation
across the 104-record corpus:

```
.agents/architecture/ADR-068-consolidated-hook-dispatcher.md:
  [prose-frontmatter-agree] frontmatter says status: accepted, but the status
  section opens with '**Amended 2026-08-19 (ADR-097): every tool-use
  registration this record describes is retired, and so is the generated
  Copilot dispatcher.'
```

ADR-068's frontmatter reads `status: accepted`. Its `## Status` section opened
with the ADR-097 amendment banner. A reader, or a low-effort model taking the
first line of `## Status` and stopping, could conclude the record was retired
when it is accepted with a scoped amendment. That is the exact failure mode
`AGENTS.md` invites by routing every harness to `.agents/architecture/ADR-*.md`
for constraints.

## The change

Insert one sentence at the head of `## Status`:

```
Accepted (amended 2026-08-19 by ADR-097; the amendment immediately below
retires every tool-use registration this record describes).
```

The amendment paragraph beneath it is byte-for-byte unchanged. Frontmatter is
untouched.

`scripts/validation/adr_lifecycle_baseline.json` then ratchets
`prose-frontmatter-agree` from 1 to 0.

## Evidence

1. **Direction of the fix is prescribed, not chosen.** ADR-073 makes frontmatter
   authoritative, and the gate's own message says "Frontmatter wins; edit the
   prose to match (ADR-073: the gate never rewrites prose)." Editing the
   frontmatter to match the prose would have been the wrong repair.
2. **The wording follows existing house precedent rather than inventing one.**
   `ADR-033` opens `Accepted (amended 2026-07-19: ...)` and `ADR-047` opens
   `Accepted (amended 2026-04-29; see Amendments section)`. Both keep the
   lifecycle word first and the amendment nuance after.
3. **The amendment's substance is preserved.** ADR-097 genuinely retired every
   tool-use registration ADR-068 describes. Nothing in this change softens or
   relocates that; a reader still meets the banner as the second paragraph.
4. **Measured after the edit**: `check_adr_lifecycle.py` reports 0 violations
   across 104 records; `tests/validation/test_check_adr_lifecycle.py` 130
   passed; `check_adr_links.py` 0 violations across 1592 tracked files;
   `check_adr_uniqueness.py` PASS.

## Alternatives considered

| Alternative | Why not |
|---|---|
| Flip frontmatter to `superseded` or `deprecated` | False. ADR-097 amended ADR-068; it did not supersede it. No `superseded-by` edge exists and `status-edge-consistency` would then fail. |
| Rewrite or relocate the amendment banner | Loses the prominence the amendment deserves, and the gate explicitly must not drive prose rewrites of substance. |
| Leave the violation and keep the baseline at 1 | Leaves the corpus one check short of ADR-073 Phase 3, whose precondition is every check at zero. The defect is two lines of prose; carrying it is not a trade. |
| Ratchet the baseline without the prose fix | Would record a false ceiling. The ratchet follows the fix, never substitutes for it. |

## Risk

Low and reversible. The change is additive prose in one record plus a baseline
integer. The ratchet to 0 is the only forward-binding effect: a future record
that opens `## Status` with something other than its lifecycle word now fails
the gate instead of riding the ceiling. That tightening is the intent of
ADR-073 Phase 3 and of issue #5190 acceptance criterion 5, not a side effect.

## Outcome

**Decision: accepted.** The change is the minimum repair the gate prescribes,
in the wording the corpus already uses, with the corpus measured at zero
violations afterward. Recorded as a single-reviewer determination under issue
#5190; no dissent was registered because no other reviewer was convened.
