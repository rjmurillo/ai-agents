# Debate Log: ADR-068 UserPromptSubmit Docs-Silence vs Measured Runtime

Issue #4727. Reviewing the amendment landed alongside PR #5350's follow-up fixes.

## Scope and reviewer

**Single-reviewer record, not a six-role debate.** One reviewer (Claude Code,
implementer role, working the adversarial-review findings on PR #5350) examined
this change. The `adr-review` six-agent roster was not convened, because this
session cannot dispatch subagents. Stated plainly rather than implied: the gate
accepts single-reviewer logs by design, and a record dressed as a debate it did
not hold would be worse than none. This follows the precedent set by
`ADR-068-status-prose-reconciliation-debate-log.md` in this same directory.

The scope test that justifies the lighter treatment: this amendment changes
**no decision, no alternative's verdict, and no frontmatter**. Every registration
ADR-068 describes stays exactly as it was, the dispatcher still suppresses
UserPromptSubmit output, and the "Keep UserPromptSubmit direct" row is still
Rejected. What changes is the stated *reason*, which had hardened a docs-silence
observation into a claim about the runtime that a later measurement contradicted.
Had the amendment flipped a decision or moved `status`, this record would be
insufficient and the roster would be owed.

## The defect

Three spans in ADR-068 rested on the same conflation:

- Line ~425: "PreCompact and UserPromptSubmit have no documented config-file
  output field."
- Line ~565 (Alternatives table): "Keep UserPromptSubmit direct | Rejected when
  a vendored source exists because plaintext output has no documented host
  field..."
- Line ~846: "The dormant UserPromptSubmit adapter also discards both channels
  because no output field is documented..."

Each is true as written about the *documentation*. Each was being read as a
statement about the *runtime*, which is the step that does not follow. Issue
#4727 measured Copilot CLI 1.0.79-6 consuming a top-level `additionalContext`
document on the `.claude/settings.json` surface while discarding plain stdout,
against a matched-pair negative control. The rule file
(`.claude/rules/generated-artifacts.md`) and the probe sidecar had already been
updated to say the runtime is measured; the ADR they restate still said the
opposite.

That is torn state, and it fails in the expensive direction. `AGENTS.md` routes
every harness to `.agents/architecture/ADR-*.md` for constraints, so a future
reader resolving the conflict between a rule file and the ADR it derives from
lands on the ADR, which was the stale side.

## Review by lens

Six lenses applied by one reviewer. Findings, not agent voices.

| Lens | Finding | Priority |
|---|---|---|
| **architect** | The amendment preserves ADR-068's structure and touches no Decision text. It corrects a Consequences rationale and qualifies one Alternatives row. Correct placement: the measurement belongs in the sidecar (it is there), and the ADR carries the pointer plus the distinction. No structural objection. | none |
| **critic** | The gap that motivated this was real and the fix closes it in all three spans rather than the one a reader would hit first. One residual: ADR-068 now depends on `probe-evidence.md` section 8 staying accurate, which is a coupling the ADR did not previously have. Accepted as the lesser cost, since the alternative is copying a version-scoped measurement into a durable record where it would rot silently. | P2, documented |
| **independent-thinker** | Challenged whether the amendment should instead flip the "Keep UserPromptSubmit direct" rejection, now that the channel is known to work. It should not. The dispatcher's suppression was never only about field availability; the load-bearing half is that current producers emit branch-controlled repository prose that must not become model context. That reason survives the measurement untouched. Flipping the row would be the measurement driving a policy change it does not support. | resolved |
| **security** | The distinction being drawn makes a model-visible channel newly explicit, so it is worth naming what did not change: the adapter still discards, and the only producer now emitting the envelope is the memory-recall hook, whose content is the repository's own `.serena/memories`. Branch-controlled prose does not gain model reach through this amendment. No new threat surface. | none |
| **analyst** | Root cause is the docs-silent-to-absent conflation, which is a recurring shape in this repository rather than a one-off. The evidence standard is met: the runtime claim carries a version, a surface, and a matched-pair control, and the ADR labels it version-scoped rather than a vendor guarantee. The amendment does not overstate; it says the event stays DOCS SILENT. | none |
| **high-level-advisor** | No conflict to break. The change is a factual correction that lowers the chance of a future reader building on a stale rationale, at the cost of three qualified sentences. Proceed. | none |

## Anti-pattern self-check (Zimmermann)

- **Pass Through**: no. Three spans identified and changed, one alternative
  considered and rejected with a reason.
- **Copy Edit**: partly a risk here, since the change is prose-only. Guarded by
  the independent-thinker lens, which tested whether a decision should move and
  concluded it should not on substantive grounds.
- **Siding / Dead End**: no. Every finding stays on ADR-068's UserPromptSubmit
  rationale.
- **Groundhog Day**: the prior ADR-068 logs in this directory cover the ADR-097
  retirement and a status-prose reconciliation. Neither addressed the
  docs-vs-runtime conflation, so this is not a re-raise.

## Issues

| Priority | Issue | Resolution |
|---|---|---|
| P2 | ADR-068 now points at `probe-evidence.md` section 8 for the measurement, coupling the durable record to a version-scoped one | Documented, not resolved. Preferred over copying a 1.0.79-6 measurement into an ADR, where it would age without a refresh trigger. The sidecar carries the refresh rules. |

No P0 or P1 issues.

## Outcome

**Accepted.** Single reviewer, no dissent to record.

Frontmatter `status` unchanged (`accepted`); this amendment does not transition
lifecycle state, so the ADR-073 Phase-3 acceptance gate is not engaged.

## Changes landed

1. ADR-068 Consequences (~line 425): the docs-silent statement now says so
   explicitly and names the measured runtime behavior beside it, with the issue
   and sidecar section cited.
2. ADR-068 Alternatives (~line 565): the "Keep UserPromptSubmit direct" row is
   qualified so its no-documented-field half is not read as absence.
3. ADR-068 (~line 846): the dormant-adapter discard rationale states that the
   discard is a policy choice about producer content, not a claim the channel
   is unavailable.
4. `.serena/memories/copilot-hooks-observations.md` and
   `.serena/memories/copilot-hook-generation-invariants.md` take the same
   distinction, plus the `CLAUDE_PROJECT_DIR` and `COPILOT_CLI` findings.
