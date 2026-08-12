# ADR-080 Amendment 2026-08-12: review log

Review of the **Amendment 2026-08-12** section added to
`.agents/architecture/ADR-080-model-pin-justification-policy.md`. The six
Decision rules were not edited.

## Protocol deviation, stated up front

This was **not** the full adr-review protocol. The skill specifies six agents
(architect, critic, independent-thinker, security, analyst, high-level-advisor)
debating to consensus over up to ten rounds. Two reviewers ran, one round.

Justification: the change corrects rationale under an unchanged Decision, adds
no rule, and removes none. A security lens has no surface here (no auth, no
secrets, no execution path), and a high-level-advisor tie-break is only needed
when reviewers disagree, which they did not.

This deviation is recorded rather than papered over. A reader who needs the full
protocol should treat this as a partial review.

Cross-vendor review did not happen. Codex / GPT-5.6 Sol was unavailable for the
entire session (`ERROR: Your workspace is out of credits`, confirmed against
`codex-cli 0.147.0` on both a real prompt and a one-token probe). Both reviewers
therefore share a vendor and a training lineage, which is a weaker adversarial
basis than the repository's own guidance asks for.

## Reviewers and lenses

| Reviewer | Lens | Verdict |
|---|---|---|
| critic | Contradiction with the Decision, citation accuracy, overstatement, completeness | NEEDS_REVISION |
| independent-thinker | Steelman the opposite of every claim; argue supersede over amend | NEEDS_REVISION |

Both received the artifact only, never the reasoning that produced it.

## Findings and disposition

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | Retirement probe used `claude-opus-9-9-retired`, a string that never existed, while the section claimed the retirement cost was "falsified". A never-registered id and a retired id are different resolver inputs. | Critical | **Accepted.** Re-probed with `claude-opus-4.5`, the id the Context names. Result was the same fallback, but the claim is now stated as narrowed on this surface, not falsified everywhere. Heading changed. |
| 2 | Draft cited `.github/agents/quality-auditor.agent.md:4` as a rule 1 policy defect. It is hand-copy drift: source is `sonnet`, template is `model_tier: sonnet`, and the generated Copilot agent correctly resolves to `claude-sonnet-4.6`. | Critical | **Accepted.** Repointed at `src/copilot-cli/skills`, which ships 8 untranslated aliases and is the genuine instance. |
| 3 | "Every versioned pin in the corpus is already non-compliant, removal is mandated" is false on both terms. The source tree holds zero versioned pins, and the 46 baseline entries are grandfathered by rule 6 with a burn-down obligation. | Critical | **Accepted.** Section deleted outright. |
| 4 | "The Decision above is unchanged" is false for rules 1 and 3, and the "what did not change" list silently omitted both. | Critical | **Accepted in substance.** Rule 3's cost-exception gap is now stated explicitly as a finding. The claim was reworded from "unchanged" to "the Decision stands; the cost model is narrowed". |
| 5 | Both Context line citations were off by six, the exact length of the Status block the amendment itself inserted. | Critical | **Accepted.** Replaced with bullet-name anchors, which survive future insertions. Found independently before the reviews returned. |
| 6 | Claims overstated relative to one probe: "every generated agent", a miscounted third config, and `visual-studio.yaml` described as carrying "the same default" when it carries a display name. | High | **Accepted.** Bounded to what was measured; both unmentioned configs now named with their literal values. |
| 7 | No probe artifact committed. Rule 4 imposes a stricter evidence standard on a weaker claim. | High | **Accepted.** Method, full result table, and transcripts committed to `.agents/analysis/2026-08-12-adr-080-copilot-model-resolution.md`. |
| 8 | 110 lines producing roughly 15 lines of decision-relevant content; measurement narrative belongs in `.agents/analysis/`, precedent already exists. | High | **Accepted.** Amendment cut from 117 lines to a focused correction. |
| 9 | Amend versus supersede. | Medium | **Rejected, with reasoning.** Both reviewers landed on amend. Superseding an unchanged Decision would restate all six rules in a second file, creating two sources of truth and orphaning live citations in #2840, the `check_model_pins.py` docstring, and `pr-validation.yml`. |
| 10 | Stale `implemented: false` and "(new)" labels on the check and manifest. | Medium | **Deferred, and named in the amendment.** Out of scope for a rationale correction; belongs with the change that flips the flag. |

## A finding the reviewers produced that the amendment did not have

The contrarian established, and I verified, that the de-versioning migration has
already run: the source tree holds zero versioned pins, where it held 75 at ADR
acceptance. The amendment had been written as though that work were outstanding.
That reframing is why finding 3 is a deletion rather than a rewording.

## What a fuller review would still add

- A security lens was not run. Judged to have no surface here; if a later
  amendment touches the manifest schema or the gate's trust boundary, it does.
- No reviewer probed Claude Code or VS Code resolvers. The amendment's claims
  are scoped to Copilot CLI 1.0.79 and say so.
- No cross-vendor reviewer. See the deviation note above.
