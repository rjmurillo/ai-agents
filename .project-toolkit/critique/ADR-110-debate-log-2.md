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
| R1-8 | independent-thinker | Add an explicit `canonical-text` key | ADR-110 section 2 closes the block vocabulary, and a path key in the owner is the second registry section 1 refuses. Include edges already name the partial |
| R1-9 | critic | Restore the original `date` | ADR-073 and `adr-generator` define `date` as last-updated |
| R1-10 | architect, independent-thinker | Private `_partial_slugs` import | `build/scripts/skill_templates.py:161` already imports the private `_SLUG` from the same module. Sharing the renderer's parser is the canonical-source-mirror rank 1 |
