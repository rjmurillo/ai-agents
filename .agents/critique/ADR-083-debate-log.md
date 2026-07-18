# ADR-083 Multi-Agent Debate Log

**ADR**: `.agents/architecture/ADR-083-copilot-dogfood-surface-separation.md`
**Title**: Dogfood the Shipped Copilot Base and Separate Ship-vs-Internal Surface
**Date**: 2026-07-18
**Tracking issue**: #3222
**Reviewers**: architect, critic, independent-thinker, security, analyst, high-level-advisor
**Status at review**: proposed
**Rounds**: 1 (Phase 1 independent review) plus consolidation, resolution, convergence

---

## Phase 0: Related Work Research

Passed to every reviewer as context. All confirmed relevant.

- Issue #3197 (OPEN): hook ROI reduction program, 15 child issues. Deletes internal
  hooks from the vendored surface and re-homes them to `.githooks`, CI, `pre_pr.py`.
  Owns the hook surface. ADR-083 defers hooks to it.
- Issue #3216 (OPEN, blocked by #3214/#3215): purge non-customer hooks; the
  authoritative hook ship-vs-internal taxonomy.
- Issue #2892: `keepInternalGlobsFor` instruction-glob split. The pattern ADR-083
  generalizes into a per-item tag.
- ADR-079 (accepted): plugin version bump at PR time; Copilot keys freshness off
  version-string inequality; manifest-parity gate requires `.claude` and
  `src/copilot-cli` identical version strings.
- gstack (`github.com/garrytan/gstack`): `_link_or_copy` symlink-on-Unix,
  copy-on-Windows install pattern.

---

## Round 1: Independent Review (Phase 1)

### architect: ACCEPT-WITH-CHANGES

Structurally sound. Keep as one ADR (the four concerns form a genuine causal
chain; splitting would create circular forward-references). Prior-art and
alternatives sections above average.

| Finding | Priority | Issue |
|---|---|---|
| Overlay version scheme unspecified | P1 | Adding a fourth version line without stating its scheme and bump trigger leaves the gate update ambiguous; an unbumped overlay reproduces the copy-rot bug on Windows |
| No rollback strategy | P1 | Plugin topology goes 3 trees to 4; no revert path documented |
| Windows copy-refresh unspecified | P2 | "Staleness note" is a concept, not a mechanism |
| No acceptance/confirmation criteria | P2 | ADR-079 and ADR-082 both define measurable acceptance; ADR-083 had none (Zimmermann Q7 FAIL) |

### critic: NEEDS-REVISION (confidence HIGH)

Scores: completeness 3/5, alignment 4/5, feasibility 3/5, risk 3/5, testability
3/5, traceability 4/5.

| Finding | Priority | Issue |
|---|---|---|
| Overlay parity-gate contradiction | P0 | `check_plugin_manifest_parity.py` asserts `len(unique) == 1` across `_MANIFESTS`; ADR says overlay has "its own version line". Adding overlay to `_MANIFESTS` forces equality. The exclusion must be specified |
| "Base enumerates" assertion unreliable | P1 | `test_plugin_load_smoke.py` already demotes enumeration to a SECONDARY soft signal (CLI 1.0.69/1.0.70 omit `source: plugin`); ADR listed it first |
| No kill criterion for empty overlay | P1 | Building a two-plugin mechanism for a "possibly empty" set is unjustified without a reassessment trigger |
| Windows re-copy trigger unspecified | P2 | Advisory note reproduces the rot on Windows |
| Hook tag location under-specified | P2 | `hooks.json` has no `surface` frontmatter field |

### independent-thinker: DISAGREE-AND-COMMIT

Structural decision correct; challenged the motivating framing.

| Finding | Priority | Issue |
|---|---|---|
| "Form-factor bugs ship uncaught" overstated | P1 | `nightly-cli-smoke` already exercises `src/copilot-cli` (`test_plugin_load_smoke.py`, `test_cli_hook_e2e.py`). The proven gap is version rot, not an open class of uncaught bugs. Reframe as defense in depth |
| Overlay YAGNI | P2 | Adopt tag + symlink + e2e now; defer the overlay split until a concrete internal skill exists |
| Overlay creates a new drift surface | P2 | Base and overlay can disagree on a shared dependency; the overlay can become an unreviewed dumping bucket |

### security: DISAGREE-AND-COMMIT (else BLOCK). Risk 8/10 on the top finding.

| Finding | Priority | Issue |
|---|---|---|
| Security hooks may be stripped from shipped base | P0 | ADR delegates hooks to #3197 but does not constrain it from removing `invoke_security_gate` / `invoke_security_commit_gate` from the base. Customers depend on these. Must pin them `surface: ship` as a binding constraint |
| No CI enforcement of tag gate | P1 | Hard-fail described only as a build-script behavior; a contributor can bypass. Must run in CI, non-skippable |
| Tag value validation unspecified | P1 | Without strict `ship`/`internal` enum, a typo or empty value silently routes to the base |
| Symlink executes uncommitted code | P2 | Loaded plugin reflects the working tree; note the risk vs the copy model |

STRIDE table produced (information disclosure, tampering, elevation of privilege
on the overlay). Verdict BLOCKED until the P0 hook constraint is documented.

### analyst: REVISE (confidence MEDIUM). Claim verification (VERIFIED unless noted):

| Claim | Verdict |
|---|---|
| Marketplace asymmetry (`.claude` vs `src/copilot-cli`) at the cited lines | VERIFIED |
| Installed copy 0.5.248 vs shipped 0.6.70 | VERIFIED |
| `generate_rules.py` `outputDirs` emits both `.github/instructions` and `src/copilot-cli/instructions` | VERIFIED |
| Parity gate compares version strings; split does not break parity | VERIFIED |
| `src/copilot-cli/skills` ships 109 skills incl. session/pr/adr families | VERIFIED (exactly 109) |
| `OWNED_PREFIXES` snapshot/restore is prefix-agnostic and extensible | PARTIALLY VERIFIED (mechanism generic; exact prefix set unread) |
| gstack `_link_or_copy` | UNVERIFIABLE (external repo) |

| Finding | Priority | Issue |
|---|---|---|
| No concrete initial `internal` set named | P1 | Tagging obligation introduced with no immediate payoff; name the initial partition |
| `keepInternalGlobsFor` interaction unspecified | P1 | Two parallel separation mechanisms would compound complexity; state subsume-or-coexist |
| No rollback / partial-adoption path | P2 | Hard-fail gate means all 109 items tag atomically |

Process incident: the analyst accidentally corrupted `build/scripts/build_all.py`
with a DOTALL regex during investigation, disclosed it immediately, and gave the
fix. Restored via `git checkout -- build/scripts/build_all.py`; `python3 -m ast`
parse confirms integrity. No corruption reached the commit.

### high-level-advisor: RE-SEQUENCE (strategic)

| Finding | Priority | Issue |
|---|---|---|
| Empty overlay is speculative infra | P0 | Name at least one `surface: internal` skill or defer the split |
| Solo-maintainer overload | P0 | 5 phases here plus 15 child issues in #3197; no capacity plan |
| Missing rollback plan | P1 | Unwind cost of an empty overlay not specified |
| Windows dogfood gap | P2 | Staleness note is not a mechanism |

Verdict: the symlink dogfood install plus base-alone e2e is the 80/20 win. Ship
those first; defer tag/split until an internal skill is named and #3197's
foundation lands. Not wrong, premature.

---

## Phase 2: Consolidation

### Consensus (raised by 3 or more reviewers)

1. **Overlay is speculative for a possibly-empty internal set.** advisor (P0),
   critic (P1), analyst (P1), independent (P2), security (Q5). Fix: name the honest
   initial partition (all `ship`) and add a decision gate that materializes the
   overlay only when an internal skill exists.
2. **No review date / acceptance criteria (Zimmermann Q7).** Unanimous. architect,
   advisor, security, critic, independent, analyst all flagged Q7. Fix: add
   Confirmation Criteria and a 90-day Review Date.
3. **No rollback plan.** architect (P1), advisor (P1), security, critic, analyst.
   Fix: add a Reversibility section.
4. **Windows copy-staleness is advisory, not a mechanism.** All six. Fix: a
   version-compare freshness check that re-copies or blocks.

### Conflicts

- **Scope: one ADR or split?** architect says keep as one (genuine causal chain).
  advisor and analyst lean toward separating the dogfood driver from the boundary
  driver. Resolution: keep one ADR; the phase reorder plus the decision gate give
  the same risk isolation a split would, without circular references. architect is
  the tie-breaker on structural questions and holds.

### Anti-pattern self-check (Zimmermann)

- No Pass-Through: every reviewer produced substantive architectural findings.
- No Copy-Edit: findings are structural, not wording.
- No Self-Promotion: no reviewer pushed a preferred technology.
- One Groundhog-Day risk avoided: the "overlay YAGNI" point recurred across five
  reviewers but is a genuine consensus, not a repeated unresolved re-raise; it is
  resolved once via the decision gate.

---

## Phase 3: Resolution (P0/P1 mapped to ADR edits)

| Finding | Priority | Resolution in ADR-083 |
|---|---|---|
| Security hooks may be stripped from base (security) | P0 | Decision item 5: binding constraint pins `invoke_security_gate` and `invoke_security_commit_gate` to `surface: ship`; moving a security control off the base requires its own ADR |
| Overlay parity-gate contradiction (critic) | P0 | Implementation Notes: overlay NOT added to `_MANIFESTS` (parity stays two-way); overlay added to `validate_plugin_version_bump.py` `PLUGINS` as a fourth entry with an independent version line. Exact `source_dir`/`manifest` given |
| Empty-overlay YAGNI (advisor, critic, analyst, independent) | P0/P1 | New Decision item 6 (overlay decision gate): initial skill partition is all `ship`; overlay materialized only when an internal skill exists; deferred otherwise. New alternatives-table row for "tag now, defer split" |
| "Base enumerates" unreliable (critic) | P1 | Decision item 4 rewritten to the `test_plugin_load_smoke.py` hierarchy: fired hook PRIMARY, `skill list` CO-PRIMARY, enumeration SECONDARY |
| "Bugs ship uncaught" overstated (independent) | P1 | Context reframed: existing CI already exercises the base; the proven gap is rot; base-alone e2e is defense in depth |
| No CI enforcement + no enum validation (security) | P1 | Decision item 1: strict `ship`/`internal` enum (reject typo/empty/null); gate runs in CI, non-skippable |
| Overlay version scheme unspecified (architect) | P1 | Implementation Notes: overlay carries its own independent version line, bumps only on `src/copilot-cli-internal` content change |
| No rollback (architect, advisor) | P1 | New Reversibility section |
| No acceptance criteria / review date (unanimous Q7) | P1 | New Confirmation Criteria and Review Date (2026-10-18) sections |
| `keepInternalGlobsFor` interaction (analyst) | P1 | Implementation Notes: the tag subsumes `keepInternalGlobsFor` (removed, not parallel) |
| Windows re-copy trigger (all) | P2 | Decision item 3: version-compare freshness check replaces the advisory note |
| Hook tag location, name collision (critic, security) | P2 | Implementation Notes: tag in registration entry; distinct plugin `name` fields; build check rejects a name in both trees |

P2 items not fully closed (documented, non-blocking): symlink-executes-working-tree
risk (accepted for a single-user workstation; noted), `lib/` tag coverage (deferred
to the tag-reader implementation phase).

---

## Phase 4: Convergence

Re-vote after Phase 3 resolutions.

| Reviewer | Round 1 | After resolution |
|---|---|---|
| architect | ACCEPT-WITH-CHANGES | ACCEPT (all four findings addressed) |
| critic | NEEDS-REVISION | DISAGREE-AND-COMMIT (P0 parity precision and enumeration hierarchy resolved; residual: overlay complexity, accepted via the gate) |
| independent-thinker | DISAGREE-AND-COMMIT | DISAGREE-AND-COMMIT (framing corrected; maintains that the overlay may never populate, which the gate now handles) |
| security | BLOCKED | ACCEPT (P0 hook constraint documented; CI enforcement and enum validation added) |
| analyst | REVISE | ACCEPT (initial partition named; `keepInternalGlobsFor` subsumption stated) |
| high-level-advisor | RE-SEQUENCE | DISAGREE-AND-COMMIT (phases reordered so install and e2e ship first; split gated; maintains the split is the lowest-value phase) |

**Consensus reached**: 3 Accept, 3 Disagree-and-Commit. No Block remains. Meets the
6/6 Accept-or-D&C bar in a single resolution round.

### Recorded dissent (Disagree-and-Commit)

- critic and independent-thinker: the overlay adds conceptual and build surface for
  a set that may stay empty. They commit because the decision gate (item 6) means
  the tree is not materialized until an internal skill exists, and the parity/
  version-bump wiring is now precise enough that the phase-4 landmine is closed.
- high-level-advisor: the two-plugin split is the lowest-value phase. Commits
  because the ADR now sequences install and e2e first and gates the split, so the
  proven-value work is not blocked on the speculative work.

---

## Owner Decision Resolved (User Sovereignty)

Three decisions in this ADR were locked by the owner (D1/D2/D3, issue #3222). The
review's two direction-touching outputs were surfaced for owner confirmation before
the status moved to `accepted`:

1. **Overlay decision gate (defer the split until an internal skill exists).** The
   review added this; it narrows D3's timing but not its substance.
2. **Phase reorder (symlink install and base-alone e2e ship before the split).**

Owner decision (2026-07-18): **A**. The four session skills (`session-init`,
`session-end`, `session`, `session-log-fixer`) stay `surface: ship`. The initial
internal partition is therefore empty, the overlay stays deferred, and the tag plus
the base-alone e2e plus the symlink dogfood install are the work that lands now.
Status moved to `accepted`; the ADR-073 gate is satisfied by this debate-log
artifact.

---

## Post-Review Consistency Pass (bot reviewers, 2026-07-18)

After the human-agent debate reached consensus and the ADR moved to `accepted`,
the PR bot reviewers (Cursor Bugbot, Copilot, CodeRabbit) flagged six internal
consistency and staleness issues on the ADR text. All six were verified valid.
None changed a decision (D1/D2/D3/A); they tightened wording. Two were fixed by
Cursor Agent autofix commits on the branch (`cd0dc2b1a`, `a5f1be0fc`); the other
four were fixed by hand on top of those commits.

| Reviewer | Finding | Fix |
|---|---|---|
| Cursor | Deferral vs base-exclusion contradiction: item 6 said tagged items are excluded from the base, so with no overlay an internal item would drop from both surfaces | Fixed by Cursor autofix `cd0dc2b1a`: during deferral all items route to the base because the internal set is empty by hypothesis; the split activates when the first internal item is tagged |
| Cursor | Overlay e2e timing contradicts deferral: item 4 and the impact table wired the base-plus-overlay job now | Fixed by Cursor autofix `a5f1be0fc`: item 4 and the impact table land only the base-alone job; the overlay job is deferred per item 6 |
| Copilot | Machine-specific state ("this machine loads five") will rot | Removed; states the multi-plugin capability generically |
| Copilot | Version claim ("1.0.69 and 1.0.70") narrower than the repo e2e rationale (1.0.69+) | Generalized to "1.0.69 and later" with issue refs #2990/#3014/#3090/#3135, matching `test_plugin_load_smoke.py` |
| CodeRabbit | Overlay gate triggered only on an internal skill, but agents and instructions also carry `surface` tags | Item 6 gate now triggers on the first internal item of any plugin-routed type (skill, agent, instruction); hooks stay on the #3197 delete-and-re-home path |
| CodeRabbit | Security-hook requirement stated as policy, not an executable invariant | Added a Confirmation Criteria bullet: CI asserts both security hooks present and `surface: ship`, fails on missing or reclassified |

## Verdict

**ACCEPT-WITH-CHANGES, changes applied.** All P0 and P1 findings resolved in the
ADR. Consensus 3 Accept / 3 Disagree-and-Commit, dissent recorded. Owner confirmed
decision A on 2026-07-18 (session skills stay `surface: ship`, overlay deferred);
status moved to `accepted`.
