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

## Round 2 (2026-08-15): full 6-agent review of finding 4's "harmless" claim

Unlike round 1, this is the **full** adr-review protocol: all six roles
(architect, critic, independent-thinker, security, analyst, high-level-advisor)
ran independently against one narrow diff — the correction to finding 4
described below. No scoped-review deviation is claimed for this round.

### Trigger

A GitHub Copilot PR review comment on PR #4954 (unresolved as of commit
`861eedc62`) found that finding 4 called `model_tier`-to-versioned-id
translation for generated plugin agents "harmless," while finding 1 (same
amendment, unchanged) measured that a versioned pin overrides an operator's
explicitly selected session model on delegation. `build/generate_agents_common.py:222-227`
resolves a template's `model_tier` to a versioned `model` id via
`templates/platforms/copilot-cli.yaml`'s `model_tiers` map before a plugin
agent ships, so the two findings describe the same versioned-id mechanism
while reaching opposite conclusions about its cost.

### Reviewers and lenses

| Reviewer | Lens | Verdict |
|---|---|---|
| architect | Structure, governance, coherence, ADR compliance | ACCEPT |
| critic | Gaps, risks, alignment, completeness | ACCEPT |
| independent-thinker | Steelman that the fix is still wrong or insufficient | ACCEPT_WITH_CHANGES |
| security | Trust-boundary and threat-model consequences of the override | ACCEPT_WITH_CHANGES |
| analyst | Root cause, direct evidence verification, feasibility | ACCEPT_WITH_CHANGES |
| high-level-advisor | Tie-break between the ACCEPT and ACCEPT_WITH_CHANGES votes | ACCEPT (tie-breaker, deciding vote) |

Each reviewer received the current finding 4 text, the proposed replacement,
and the two source citations (`build/generate_agents_common.py:222-227`,
`templates/platforms/copilot-cli.yaml` `model_tiers`), independently.

### Findings and disposition

| # | Finding | Reviewer(s) | Disposition |
|---|---|---|---|
| 1 | The proposed text resolves the Copilot finding: it drops "harmless," states the override is the same mechanism finding 1 measured, and records that whether the override is acceptable "is undecided here and remains an open gap." | architect, critic | **Accepted as-is.** |
| 2 | The override was not independently re-probed for a `model_tier`-resolved id; the proposed text should not claim it as measured. | independent-thinker, analyst | **Accepted as-is.** The proposed text already states "not independently probed... inferred from finding 1's mechanism, not separately reproduced." No change needed. |
| 3 | Add a prescriptive "Migration item" sentence naming concrete resolution options (stop emitting `model`, emit a bare alias, or accept the override with explicit operator opt-in). | independent-thinker, security | **Rejected by tie-break.** high-level-advisor: this ADR amendment is scoped as "a rationale correction, not a rule change," and its own established pattern (the "Suggested sequence" list, and finding 4's own closing sentence: "is migration work this ADR does not currently name") consistently narrates gaps without prescribing unscoped follow-up work. Prescribing migration options belongs in a follow-up PR or ADR entry in the suggested sequence, not in this correction. |
| 4 | The override has trust-boundary implications (an operator's explicit model choice may be a safety/assurance decision, not only a cost preference) and should be framed that way, citing ASI09/CWE-346. | security | **Rejected by tie-break**, same reasoning as finding 3: out of scope for a rationale-only correction. Recorded here so a future amendment that does touch the manifest schema or trust boundary does not have to rediscover this framing. |
| 5 | `build/generate_agents_common.py:222-227` should instead read `223-228`. | analyst | **Rejected on the facts.** Re-verified directly against the source file: line 222 is the `# Resolve model:` comment, 223 is `model_tier = frontmatter.get(...)`, 224 is a comment, 225 is the `model_tiers = ...` lookup, 226 is the `if model_tier and isinstance(...)` guard, and 227 is `result["model"] = str(model_tiers[model_tier])` — the complete resolution block, matching the citation in the Copilot review comment that raised this finding. Line 228 is the `else:` branch for the non-tier fallback path, not part of the resolution being cited. `222-227` is correct; `223-228` would drop the leading comment and add an unrelated branch. |

### Consensus

6 of 6: 3 ACCEPT, 3 ACCEPT_WITH_CHANGES resolved by the high-level-advisor
tie-break in favor of the unmodified proposed text (candidate A). Final text
applied verbatim as proposed; no further edits from this round.
