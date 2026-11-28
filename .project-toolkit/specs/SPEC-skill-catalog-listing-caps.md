# Keep the skill catalog usable under host skill-listing caps

Status: Draft, 2026-11-28. Owner: Richard Murillo.
Scope: every skill tree this repo ships (`src/*/skills/`) and the dogfood tree `.claude/skills/`.
Evidence of record: `.project-toolkit/analysis/copilot-cli-skill-char-budget-2026-11-28.md` (PR #7871).
Related: #7779 (description diet), #7801 (routing under a cap), #7831 (budget gate fix), epic #1944 (catalog triage).

## Direction of record

Richard ruled on 2026-11-28:
"Document all of this as a new spec and start a thread to shrink 1) the number of skills,
2) the descriptions of the surviving skills. We're going to blow A LOT of tokens on evals,
but we need to keep this monstrosity actually usable".

Earlier standing rules still hold: no broad compression without evals; evals are the gate.

## Problem

Each host shows a skill's description to the model only while the skill list fits a budget.
Past the budget, the host lists the skill by name only. The model then routes by name alone.
This repo ships more skill text than either measured host shows.

| Tree at f8398e1b2d (2026-11-28) | Skills | Listing chars needed |
|---|---|---|
| `src/copilot-cli/skills` | 103 | 42,453 |
| `.claude/skills` | 121 | 50,344 |

Listing chars use the Copilot entry cost: 93 characters of markup plus the name plus the description.

## Host listing budgets

| Host | Budget | Override | Past the budget | Source |
|---|---|---|---|---|
| Copilot CLI | About 15,000 chars in effect here; upstream says 15,000 or 30,000 | `SKILL_CHAR_BUDGET` env var | Name only, order not determined | PR #7871 note |
| Claude Code | 1% of the model's context window; fallback 8,000 chars | `skillListingBudgetFraction`, `SLASH_COMMAND_TOOL_CHAR_BUDGET` | Name only; least-invoked skills lose descriptions first | Claude Code docs, below |

Claude Code docs, fetched 2026-11-28:

- `skills.md`: "The budget scales at 1% of the model's context window. When the listing overflows,
  Claude Code drops descriptions starting with the skills you invoke least".
- `env-vars.md`, `SLASH_COMMAND_TOOL_CHAR_BUDGET`: "The budget scales dynamically at 1% of the context window,
  with a fallback of 8,000 characters."
- `skills.md`: "the combined `description` and `when_to_use` text is truncated at 1,536 characters in the skill listing".
- `skills.md`: "To free budget for other skills, set low-priority entries to `"name-only"` in `skillOverrides`".

The docs do not say how a token window becomes a character budget.
INFERRED: 4 characters per token, because 1% of 200,000 tokens times 4 equals the 8,000-char fallback.
Under that reading a 200,000-token window gives 8,000 chars and a 1,000,000-token window gives 40,000.
REQ-6 measures this before any target depends on it.

The routing eval for #7779 measured the Claude Code cap in one workspace on 2026-11-26.
At the default cap, 48 of 121 descriptions showed before #7779 and 71 of 121 after
(`evals/reports/skill-description-routing-2026-11-26.md`, section "The listing cap").

Two host behaviors differ, and the design must serve both:

- Claude Code keeps the most-used skills described. A rarely used skill goes name-only first.
- Copilot CLI fills in an order this repo does not control. In 3 sessions in this repo (logs read 2026-11-28), `build` and every later skill by name went name-only, so `review`, `ship`, and `test` did too.

## Step 0 First Principles

### Q1 Demand Reality

Richard Murillo, owner, on 2026-11-28 in the token-diet thread: "start a thread to shrink 1) the number of skills,
2) the descriptions of the surviving skills". The owner also reported on the same day: "Copilot won't load over a certain size".

### Q2 Status Quo

1. A user opens Copilot CLI or Claude Code in this repo, or in a repo with the plugin installed.
2. The host builds the skill list and drops descriptions past its budget.
3. The model sees `review`, `ship`, or `test` as a bare name in Copilot (3 sessions in this repo, logs read 2026-11-28, before #7779).
4. The user types the skill name by hand (`/review`), or the model skips the skill.
5. Evals work around the cap with `SLASH_COMMAND_TOOL_CHAR_BUDGET=80000`, so eval results do not show what users see.

Reframing: skipped (owner fixed the direction on 2026-11-28: fewer skills, then shorter descriptions).

### Q3 Desperate Specificity

Copilot CLI 1.0.116 sessions in `rjmurillo/ai-agents`. In the 3 sessions that listed `adr-generator` through `benchmark-models`, 24 skills kept descriptions,
and `build` and every skill after it were name-only (PR #7871 note, receipt B).

### Q4 Narrowest Wedge

Bring `src/copilot-cli/skills` under 15,000 listing chars with eval-gated cuts, and add a listing-char gate.
About 40 hours of AI-assisted work, most of it eval runs.

### Q5 Observation

Receipt B in the PR #7871 note: 9,390 local Copilot sessions, full entries at most 14,915 chars, 9,386 with name-only skills (2026-11-28).
The #7779 eval report: "At the default cap, 50 of 121 skills still show a name and no description" (issue #7801, 2026-11-26).

### Q6 Future-fit

At 10 times the skills, the listing cap binds harder, not softer. A gate tied to each host's budget scales with growth: every new skill must fit or displace one.
The cuts in this spec become more valuable as the catalog grows.

## Prior Art / Constraints

Search ran on 2026-11-28: `.serena/memories/` grep, git log on skill trees, `.project-toolkit/specs/`, `.project-toolkit/analysis/`.

| Prior art | Decision |
|---|---|
| Epic #1944, Skill Catalog Triage (closed): M1 and M2 deleted skills by design docs | Honor the shape. Reuse its checklists. |
| `.project-toolkit/specs/design/DESIGN-007-skill-catalog-prune-m1.md` (M1) and `DESIGN-018-skill-catalog-prune-m2-session-cluster.md` (M2): delete source, delete mirror, fix references, run `build/scripts/build_all.py --check` | Honor. Each removal follows that checklist. |
| `.agents/governance/agent-consolidation-process.md`: overlap thresholds and merge or retire steps | Honor for shipped skills. |
| `.project-toolkit/analysis/skill-overlap-2026-06-05.md`, `skill-overlap-2026-06-17.md`, `.project-toolkit/qa/pr-2649-m4-overlap-eval.md` | Reuse as merge candidates. Re-measure; they are five months old. |
| #7628: Azure DevOps skills moved into their own pack | Honor. An opt-in pack is a valid disposition. |
| #7563 and #7541: path rules folded into skills after a held-out routing eval | Honor the eval method. |
| #7779: routing eval harness `evals/skill-description-routing/`, per-skill gate G4 | Reuse the harness and gates. |
| `scripts/skill_description_budget.json` (#2801, #6012): description-char ratchet, "Not a measured limit of any model host" | Keep, and add a listing-char gate per host (REQ-1). |

Coverage notes: no prior spec in `.project-toolkit/specs/` names host listing caps. Hindsight was not searched.
`chestertons-fence` was not run as a separate skill. The git and spec search above stands in for it, at lower confidence.

## User stories

1. As a Copilot CLI user of the plugin, I see a description for every shipped skill, so the model can route to `review` or `ship` without my typing it.
2. As a Claude Code user, I see a description for every shipped skill at the design-point context window.
3. As the owner, I get an eval report for each cut and each shortened description, so I can accept or reject it on evidence.
4. As a maintainer, a gate fails when a new or longer skill pushes a shipped tree past a host budget.

## Ontology

| Name | Meaning |
|---|---|
| Skill | One `SKILL.md` with a name and description, in one tree |
| Tree | A skill root: shipped (`src/<host>/skills/`) or dogfood (`.claude/skills/`) |
| HostBudget | One host's listing budget: chars, entry cost, overflow rule, host version, source |
| ListingChars | Sum over a tree of entry cost: 93 + name + description, under the Copilot entry rule |
| Disposition | What happens to a skill: keep, shorten, merge-into(target), move-to-pack(pack), retire |
| CutList | The owner-approved set of Dispositions other than keep |
| RoutingEval | A registered eval run: queries, arms, models, cap setting, gates, cost |

Relationships: a Tree holds Skills. A CutList assigns one Disposition per Skill. A RoutingEval admits or rejects a CutList entry.
Decision rule: no Disposition other than keep merges without a RoutingEval that passed its registered gates.

## Requirements

REQ-1. Measure. Extend `scripts/skill_description_budget.py` to report ListingChars per tree, and the count of skills that fit each HostBudget.
REQ-2. Gate. Add a listing-char ceiling per shipped tree. Start at the measured value. Lower it as each cut merges. Target: the HostBudget of the design point.
REQ-3. Phase 1, fewer skills. Propose a CutList from usage, overlap, and routing evidence. The owner approves it before any removal merges.
REQ-4. Phase 2, shorter descriptions. Shorten each surviving description behind the #7779 routing eval and its per-skill gate.
REQ-5. Eval under real caps. Run each RoutingEval at the host default cap and at a lifted cap. Report correct rate split by skills shown with and without a description (#7801).
REQ-6. Claude Code budget. Measure the effective Claude Code listing budget for each context window size the owner supports. Record the Claude Code version.
REQ-7. Copilot eval arm. Add a Copilot CLI arm to the routing eval, or record why it cannot run.
REQ-8. Removal hygiene. Each removal follows the DESIGN-007 checklist: source, mirrors, references, docs pages, triage fixtures, `build_all.py --check`.
REQ-9. Consumers. A removed shipped skill gets a changelog line and a named replacement or "none".
REQ-10. Cost record. Each eval run records models, query count, cap setting, token totals from the hub log, and wall time.

## Acceptance criteria

1. WHEN `skill_description_budget.py` runs THEN it SHALL print ListingChars and the fit count for each shipped tree and each HostBudget.
2. WHEN a shipped tree's ListingChars exceed its ceiling THEN the budget gate SHALL exit non-zero.
3. WHEN Phase 1 completes THEN `src/copilot-cli/skills` ListingChars SHALL be at or below 15,000, OR the owner SHALL have recorded a different design point.
4. WHEN a Skill gets merge-into, move-to-pack, or retire THEN a RoutingEval SHALL show that queries aimed at it reach the surviving owner at no worse than baseline minus the registered margin.
5. WHEN a description is shortened THEN the RoutingEval at a lifted cap SHALL pass the #7779 per-skill gate G4 for that skill.
6. WHEN a RoutingEval runs THEN its report SHALL give results at the host default cap and at a lifted cap.
7. WHEN REQ-6 completes THEN the spec SHALL state the measured Claude Code budget in chars for each supported window, with the Claude Code version.
8. WHEN a shipped skill is removed THEN `build_all.py --check` SHALL exit 0, and the orphan-reference scan SHALL report no reference to the removed name outside history files.
9. WHEN a shipped skill is removed THEN the release notes SHALL name it and its replacement or "none".
10. WHEN any RoutingEval finishes THEN its report SHALL record models, query count, cap setting, token totals, and wall time.

## Data model

- Skill: identity is (tree, name). Invariant: one description of 1 to 1,024 chars (Agent Skills spec).
- HostBudget: identity is (host, host version). Invariant: every value carries its source and date.
- CutList: identity is its commit. Invariant: every entry other than keep cites the RoutingEval that admitted it.
- RoutingEval: identity is its report path. Lifecycle: registered plan, run, report, owner verdict.

## Integrations

- Claude Code CLI and the hub (`claude-cli` route): at most 2 concurrent streams. Failure mode: rate limit; resume from the run's JSONL.
- Copilot CLI (REQ-7): run in headless mode if the CLI supports it. Failure mode: no headless mode; record and skip.
- Hub ClickHouse log (`hub-logs` skill): read-only token totals. Never copy raw prompt or response text into the repo.

## Failure modes

- Eval noise hides a real loss. Mitigation: registered margins, repeated samples, discordant-pair review as in #7779.
- A removed skill is still named by a hook, another skill, or docs. Mitigation: REQ-8 orphan scan.
- A plugin consumer loses a skill they use. Mitigation: REQ-9, and move-to-pack before retire when usage exists.
- A host changes its budget or order rule. Mitigation: HostBudget carries a version; re-run the PR #7871 probe on each Copilot bump.
- Dogfood usage misleads. Claude Code keeps used skills described, so this repo's sessions hide what a new user sees. Mitigation: REQ-5 reports both caps.
- Eval spend grows without a stop. Mitigation: REQ-10 records cost per run; the owner sets a stop per phase.

## Security

No new trust boundary, secret, or input surface.
Eval transcripts hold prompts: follow the hub log rules, counts only outside the owner's machines.
A Disposition other than keep for `security-review`, `security-scan`, `security-detection`, or `threat-modeling` needs the security agent's review.

## Observability

Proof metric: per host, the count of shipped skills that keep a description at the default cap.
Baseline at f8398e1b2d (2026-11-28): Copilot about 36 of 103 at 15,000 chars, per the PR #7871 probe.
Secondary: routing correct rate per RoutingEval, and first-turn prompt tokens per cap.

## Out of scope

- Setting `SKILL_CHAR_BUDGET` or `skillListingBudgetFraction` for plugin consumers. This repo cannot set their environment.
- Subagent definitions (`agents/`), rules, and hooks.
- Hindsight `autoInject` and `pr-review-toolkit` (held by the owner).
- Listing budgets of Codex, Cursor, Muse, and Hermes. See Deferred.

## Deferred

- Listing budgets for Codex, Cursor, Muse, and Hermes. Owner: Richard. Measure after Copilot and Claude Code.
- Setting `SKILL_CHAR_BUDGET` in this repo's own launch configuration. Owner: Richard.
- Copilot dynamic skill retrieval. The 1.0.115 runtime holds `COPILOT_DYNAMIC_RETRIEVAL_SKILLS` and `COPILOT_EMBEDDING_ONLY_SKILLS`; behavior is unread. Owner: Richard.

## Open questions

1. Which Claude Code context window is the design point: 200,000 or 1,000,000 tokens? Owner: Richard. It sets the Claude Code target (about 8,000 or 40,000 chars, INFERRED).
2. Do repo-local `ai-agents-*` skills stay in the dogfood listing, or move out of it? Owner: Richard. They take listing space in every session in this repo.
3. What fill order does Copilot use? Owner: implementing thread. It decides which skills a Copilot user loses first.
4. What margin admits a cut (REQ-3, criterion 4)? Owner: Richard, at plan registration.

## CVA summary

Common: every host lists names and drops descriptions past a budget. Every Disposition needs the same eval and removal checklist.
Varies: the budget size, the entry cost, the overflow order, and the override knob per host.
Relationship: one CutList serves all hosts. The tightest HostBudget at the design point sets the target.

## Buy-vs-build decision

Context, not core: the catalog size is a property of this repo, not a product.
Alternatives: (a) raise host budgets by config, rejected for consumers, whose environment this repo cannot set;
(b) Claude Code `skillOverrides` name-only, which helps Claude Code users who set it and does nothing for Copilot;
(c) host dynamic retrieval, deferred, behavior unread.
Recommendation: build. The cuts, the gate, and the eval arms live in this repo.

## Complexity classification

Engineering tier 4: 40 or more hours, several trees, breaking for plugin consumers. Problem domain: Complicated (measurable with evals and expert review).
Methodology: registered eval plans, phase gates, owner approval of the CutList.
ADR cross-reference: an ADR is required before the first removal merges. It records host listing budgets as a catalog constraint and the Disposition rules.
The implementing thread drafts it with `adr-generator` and runs `adr-review`.

## Spec process record

- Step 0: passed on 2026-11-28 (no hedge phrase; Q1 present-tense requester with specific Q3 and evidenced Q5).
- Step 0.5: ran on 2026-11-28, bounded search; coverage notes above.
- Not run in this session: `requirements-interview`, `threat-modeling`, `slo-designer`, `pre-mortem`, critic review.
  The implementing thread runs a critic pass on this spec before `/plan`.
