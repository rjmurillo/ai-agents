# ADR Debate Log 2: Capability Ownership and the Artifact Dependency DAG

Record under review: `.project-toolkit/architecture/ADR-110-capability-ownership-dag.md`
Tracker: issue #7641. Prior debate log: `.project-toolkit/critique/ADR-110-debate-log.md`
(closed with status proposed, revision 5).
Claims ledger: `.project-toolkit/critique/ADR-110-claims-ledger.md`

## Scope

The change rewrites the stale `## Status` paragraph, adds a 2026-11-25
amendment to section 7, and sets `implemented: true`. It also changes the gate
the record names, `scripts/validation/check_capability_graph.py`. That touches
executable enforcement, so the full six-seat panel ran.

Each seat received the diff, the ledger, and the context documents. No seat
saw the author's reasoning or another seat's findings.

## Round 1

| Seat | Vote | Load-bearing objection |
|---|---|---|
| architect | Disagree-and-Commit | No debate log covers this amendment; REQ-031 item 11 and DESIGN-029 still describe an owner-file-only check |
| critic | Disagree-and-Commit | Intersecting include sets lets one dependent with an unrelated include switch the check off for the whole capability |
| independent-thinker | Disagree-and-Commit on code, Block on acceptance | Same intersection hole; an explicit `canonical-text` key would be more honest than inference |
| security | Disagree-and-Commit | The `*.shared.md` exemption is open-ended, so a fifth copy passes; no CWE-22 hole, slugs match `[a-z0-9]+(-[a-z0-9]+)*` |
| analyst | Block | No shell in the seat: five ledger rows not run; Status counts measure the working tree, not `0b31dc034`; "three-milestone" contradicts five milestones; "invariant 7" names nothing in the file |
| high-level-advisor | Disagree-and-Commit | Issue premise was stale (51 nested blocks at `902278fa5`); the fix is in scope; acceptance is the owner's decision |

### Findings accepted

| ID | Seat | Finding | Fix |
|---|---|---|---|
| R1-1 | critic, independent-thinker | Intersection rule fails open | `_canonical_texts` counts includes per partial: a partial counts when two or more dependents include it. New test `test_a_dependent_with_only_unrelated_includes_does_not_switch_the_check_off` |
| R1-2 | security, critic | Open-ended `*.shared.md` exemption | `test_only_the_approved_residue_carries_the_policy_verbatim` pins the four files by name. Negative control: a fifth `zz-probe.shared.md` copy failed the test |
| R1-3 | architect | REQ-031 item 11 and DESIGN-029 drift from the gate | Both now state the partial side of the comparison |
| R1-4 | analyst | Status counts tied to the wrong tree | Status now says the counts are at `0b31dc034` and the refusal is this change |
| R1-5 | analyst | "three-milestone sequence" | Now "five-milestone sequence" |
| R1-6 | analyst | "invariant 7" names nothing | Now "the seventh check", which the module docstring calls "A seventh" |
| R1-7 | security, architect | Fail-open cases undocumented in the ADR | Section 7 records them as accepted residual risk |

### Findings rejected

| ID | Seat | Finding | Reason |
|---|---|---|---|
| R1-8 | independent-thinker | Add an explicit `canonical-text` key | ADR-110 section 7 keeps the partial paths out of the owning rule, because the rule ships to installs that have no `templates/` tree. A path key in the owner's block would put a dead path into the shipped rule. Include edges already name the partial. (Round 2 corrected this citation from sections 1 and 2.) |
| R1-9 | critic | Restore the original `date` | ADR-073 and `adr-generator` define `date` as last-updated |
| R1-10 | architect, independent-thinker | Private `_partial_slugs` import | `build/scripts/skill_templates.py:161` already imports the private `_SLUG` from the same module. Sharing the renderer's parser is the canonical-source-mirror rank 1 |

## Round 2

Each seat received commit `bcccf3c16` and the round 1 dispositions above.

| Seat | Vote | Notes |
|---|---|---|
| architect | Accept | All three round 1 objections resolved; asked that this log record round 2 before status changes |
| critic | Accept | Ran the real-tree test against `origin/main`'s gate: it returned True on the paste, so the test fails before the fix |
| independent-thinker | Disagree-and-Commit | R1-8 holds on section 7, not sections 1 and 2; citation corrected above. Residual risk acceptable as recorded |
| security | Accept | The four-file pin closes the open exemption. Low: the residue test scans `templates/` only |
| analyst | Accept | Ran every ledger row with a shell. All verified. Old gate exit 0, new gate exit 1 on the same pasted copy. Ledger line 518 corrected to 517 |
| high-level-advisor | Accept | The owner's issue #7641 done-when item asks for accepted; consensus supplies the ADR-073 gate |

## Outcome

- Consensus reached in round 2: five Accept, one Disagree-and-Commit.
- Status moves from proposed to accepted in the same change as this log (ADR-073).
- `implemented: true`: TASK-040 Milestones 1 to 5 merged in PRs #5879, #5881, and #5885.

### Dissent recorded

independent-thinker: inferring the canonical partial from include counts goes
silent when a capability drops to one including dependent. Nothing signals that
loss of coverage. Recorded as accepted residual risk in ADR-110 section 7.

### Evidence provenance

All six seats ran on one model family, so their agreement is not independent
proof. The deterministic checks carry the weight: the real-tree test fails on
the `origin/main` gate and passes on this branch, and the residue pin failed on
a planted fifth copy. Reverting the gate change is a one-commit revert of
`scripts/validation/check_capability_graph.py` and its tests.

## Changes after the round 2 vote

The panel voted on `bcccf3c16`. Two later commits touched this change.

- `69e0f5aad` set `status: accepted`, rewrote the Status opening, and rewrapped
  two paragraphs. No decision text changed.
- `54fd51038` came from the `/review` pass, not the panel. It adds `compares`
  lines to the text report, drops the unused agent partial directory, and adds
  three tests. ADR-110's text is unchanged by it. Deterministic re-check at that
  commit: 57 capability tests pass, and the real-tree gate exits 0 with one
  `compares untrusted-content-handling` line.
