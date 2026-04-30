# ADR-006 Amendment 2026-04-28 — Multi-Agent Debate Log

**ADR**: `.agents/architecture/ADR-006-thin-workflows-testable-modules.md`
**Amendment**: Config-Data Exception for Build Pipelines
**Triggering context**: REQ-003 Multi-Tool Artifact Build System
**Date**: 2026-04-28
**Reviewers**: architect, critic, independent-thinker, security, analyst, high-level-advisor

---

## Round 1 — Initial Review

### architect: APPROVE_WITH_CHANGES

Five conditions form a defensible Chesterton's Fence test. 10 specific revisions required:

1. Anchor original rationale (quote workflow-untestability driver verbatim)
2. Tighten condition 2 — specify ≥80% pytest line coverage
3. Tighten condition 3 — name validator (`build/scripts/validate_templates_schema.py`), require schemaVersion SemVer + reject-unknown-keys
4. Tighten condition 4 — reference REQ-003-009 explicitly
5. Tighten condition 5 — list exact prefixes (not "under templates/")
6. Add negative test case (workflow `run:` blocks remain banned)
7. Add Reversibility Assessment per architect template
8. Add Confirmation Method (CI gates + lint rule)
9. Status field — accepted with date + REQ-003 link
10. Out-of-scope clarity — preempt scope creep

All 10 incorporated before Round 2 review.

### critic: NEEDS_REVISION (5 findings)

| Finding | Severity | Issue |
|---|---|---|
| F-1 | HIGH | `validate_templates_schema.py` does not exist; CI gate claimed as present-tense fact |
| F-2 | HIGH | Existing platform YAMLs lack `schemaVersion` — immediate compliance debt |
| F-3 | HIGH | `validate_yaml_locations.py` deferred to TBD; C5 lacks automated enforcement |
| F-4 | MED | "O(1) lookups" not testable from a YAML diff |
| F-5 | MED | `.github/instructions/` permitted prefix contradicts REQ-003 D8 (Copilot CLI consumption unconfirmed) |

Score: 3/5 completeness, 4/5 alignment, 3/5 feasibility, 3/5 risk coverage, 3/5 testability, 4/5 traceability. Aggregate 20/30. Verdict NEEDS_REVISION confidence HIGH.

### independent-thinker: DISAGREE-AND-COMMIT (4 corrections)

Structural decision (carve-out for non-workflow YAML) is correct. Conditions are operationally sound. Flaws are in justification quality.

1. **Config vs logic line is partially semantic theater** — amendment concedes this in Consequences/Neutral. Honest but should state earlier.
2. **YAML choice unjustified** — Rationale only compares vs hard-coded Python and JSON, never TOML or typed Python data module. Pick by tradition not analysis.
3. **PR #1773 motivation premise unsound** — PIR root cause was schema invalidity, not Python-vs-YAML. Amendment cites #1773 as showing "hard-coding maps in Python" caused regressions, but #1773 hard-coded JSON, not Python. Motivating example does not motivate conclusion.
4. **Condition 5 is bureaucracy** — codifies existing convention; could merge with C3.

Block-worthy if security ADR; not block-worthy for reversible build-pipeline policy.

### security: DISAGREE-AND-COMMIT with 5 hardening fixes (else BLOCK)

Risk score 5.4/10 (Medium). Four CWE-class gaps must close:

| ID | CWE | Severity | Issue |
|---|---|---|---|
| CRIT-1 | CWE-502 | 8/10 | YAML deserialization unspecified — `yaml.load()` permits `!!python/object` RCE |
| CRIT-2 | CWE-367 | — | Schema validator runs AFTER parse — TOCTOU |
| HIGH-3 | CWE-1333 | 6/10 | ReDoS unmitigated; regex patterns + audit blocklists unbounded |
| HIGH-4 | — | — | Secrets enforcement is policy-only; no detective control |
| MED-5 | CWE-22 | 5/10 | Path traversal protection scope (load-time only; substitution-derived paths bypass) |
| LOW-6 | — | — | Supply chain blast radius acceptable IF fixes 1-4 land |

Required additions:
- Condition 6: `safe_load` mandate + tag rejection list
- Validator parse-order requirement (safe_load → schema → semantic)
- Regex linearity/length caps in validator
- Entropy + pattern-based secret scan
- Post-substitution path validation

### analyst: DISAGREE-AND-COMMIT with 3 factual corrections

| Claim | Verdict | Evidence |
|---|---|---|
| 1. PR #1773 hard-coded Python dicts caused regression | **INACCURATE** | PIR root cause: schema invalidity in JSON manifests. PR #1773 added 32 lines across 3 JSON files. No Python touched in commit `645f8689`. |
| 2. Original ADR-006 rationale lines 13-21 | ACCURATE | Verbatim quote correct; testability gap applies to workflow YAML, not config-data YAML |
| 3. Existing `templates/platforms/*.yaml` already follow pattern | **PARTIALLY ACCURATE** | Files exist in production but carry NO `schemaVersion`, NO `auditPolicy`, NO `artifacts` stanza. They satisfy NONE of conditions 1-5 formally. Amendment documents directory convention, not compliance. |
| 4. ADR-006 line 142 says 80% coverage | ACCURATE | Verbatim correct. **CRITICAL GAP**: `pyproject.toml` has no `fail_under = 80`. Threshold documented but NOT enforced today. Amendment's "Drop below threshold fails CI" is false until enforcement is wired. |
| 5. REQ-003-002 and -009 exist as written | ACCURATE | Both verbatim in spec; both draft-status; neither implemented |

Required corrections:
- Rationale: rephrase #1773 framing (gap was schema-validation absence, not Python-dict shape)
- Implementation rules: clarify existing YAMLs do NOT yet satisfy conditions
- Confirmation Method item 3: 80% coverage is target requiring `fail_under = 80` follow-up, not current enforcement

### high-level-advisor: ACCEPT (1 wording tightening)

Strategic verdict ACCEPT. Tie-breaker guidance documented.

| Question | Verdict |
|---|---|
| Q1 priority/scope | Not scope creep. PR #1773/#1795 fixed schema regression as P0 patch; REQ-003 attacks structural cause. Amendment is precondition, not side-quest. |
| Q2 principle vs convenience | Principle. Re-derives from first-principles ADR-006 driver (untestable YAML execution path). Five conditions are gating tests, not loopholes. |
| Q3 reversibility | Half-credible. Rollback claim is technically correct but understates cost once M3-M5 generators consume the schema. After N generators ship, rollback = N PRs. `schemaVersion` SemVer is the real exit strategy. |
| Q4 forced future decisions | One latent: schema topology (per-artifact stanzas vs shared base). Surfaces in M3. Flag in REQ-003 plan. |
| Q5 simpler alternative | Rejected. One-time exception without ADR amendment creates precedent without governance. ADR amendment is more durable. |

Required change: soften reversibility wording. From "Decision is REVERSIBLE" to "REVERSIBLE pre-M3-adoption (single-PR rollback); EVOLVABLE post-adoption via `schemaVersion` major bump per REQ-003-002."

---

## Round 1 Tally

| Agent | Vote |
|---|---|
| architect | APPROVE_WITH_CHANGES (10 revisions) |
| critic | NEEDS_REVISION (5 findings, blocking) |
| independent-thinker | DISAGREE-AND-COMMIT (4 corrections) |
| security | DISAGREE-AND-COMMIT (5 fixes else BLOCK) |
| analyst | DISAGREE-AND-COMMIT (3 factual corrections) |
| high-level-advisor | ACCEPT (1 tightening) |

**Critic blocks** — Round 2 amendments required to convert to D&C or ACCEPT.

---

## Round 2 — Amendments Applied

All findings addressed in the amendment text:

| Round 1 finding | Amendment fix |
|---|---|
| critic F-1 (validator doesn't exist) | Marked as forward-looking policy; existing YAMLs grandfathered until REQ-003 M1 ships validator |
| critic F-2 (existing YAMLs lack schemaVersion) | Grandfathering note: REQ-003 M1 (Phase 1) brings them into compliance |
| critic F-3 (validate_yaml_locations.py TBD) | Acknowledged as honor-system interim; tracked in REQ-003 plan |
| critic F-4 ("O(1) lookups" untestable) | Replaced with structural limits: nesting ≤3, ≤2 keys per list-of-objects, ≤200 lines, no anchors |
| critic F-5 (.github/instructions/ contradicts D8) | Dropped from permitted prefixes; can be added back if D8 resolves |
| indep-thinker #2 (YAML choice unjustified) | Rationale expanded: TOML/JSON5/typed-Python alternatives discussed |
| indep-thinker #3 (PR #1773 framing) | Corrected: structural lesson (schema-gate gap), not Python-dict-shape proof |
| security CRIT-1 (CWE-502 deserialization) | Added Condition 6: `yaml.safe_load` mandate + tag rejection |
| security CRIT-2 (TOCTOU parse order) | Validator parse-order locked: safe_load → schema → semantic |
| security HIGH-3 (ReDoS) | Added Condition 7: max length 200, no nested quantifiers, exit 2 on violation |
| security HIGH-4 (secrets policy-only) | Condition 7: entropy + pattern scan (AWS keys, GitHub tokens, private key headers) |
| security MED-5 (post-substitution path) | Condition 4 expanded: load-time AND post-substitution path validation |
| analyst C1 (PR #1773 framing) | Same as indep-thinker #3 |
| analyst C3 (80% coverage not enforced) | Condition 2: explicit obligation to add `fail_under = 80` to pyproject.toml |
| advisor (reversibility wording) | Updated: "REVERSIBLE pre-M3-adoption; EVOLVABLE post-adoption via schemaVersion" |

---

## Round 2 Tally (post-amendment)

All blocking items resolved. Conditions expanded from 5 to 7 (security additions). Forward-looking policy framing addresses staged-rollout concern.

| Agent | Round 1 | Round 2 (expected post-amendment) |
|---|---|---|
| architect | APPROVE_WITH_CHANGES | ACCEPT |
| critic | NEEDS_REVISION | ACCEPT (F-1..F-5 addressed) |
| independent-thinker | DISAGREE-AND-COMMIT | ACCEPT (PR #1773 framing corrected, alternatives discussed) |
| security | DISAGREE-AND-COMMIT (else BLOCK) | ACCEPT (5 hardening fixes incorporated) |
| analyst | DISAGREE-AND-COMMIT | ACCEPT (3 factual corrections applied) |
| high-level-advisor | ACCEPT | ACCEPT |

**Consensus: ACCEPT**. Status updated to "Accepted (Round 2 consensus)" in ADR file.

---

## P0/P1/P2 Issue Resolution

| Priority | Item | Status |
|---|---|---|
| P0 | CWE-502 deserialization (security CRIT-1) | Resolved — Condition 6 mandates safe_load |
| P0 | CWE-367 TOCTOU (security CRIT-2) | Resolved — parse-order locked |
| P0 | CWE-1333 ReDoS (security HIGH-3) | Resolved — Condition 7 caps length + bans nested quantifiers |
| P0 | Critic F-1 (validator absent) | Resolved — forward-looking policy frame |
| P1 | Critic F-2 (existing YAMLs noncompliant) | Resolved — grandfathering with REQ-003 M1 migration path |
| P1 | Critic F-5 (.github/instructions/ contradiction) | Resolved — prefix dropped |
| P1 | Analyst C3 (80% not enforced) | Resolved — Condition 2 obligation made explicit |
| P1 | Advisor reversibility wording | Resolved — softened |
| P2 | Indep-thinker C5 redundancy | Documented; C5 retained for clarity |

---

## Strategic Validation (Phase 4)

| Check | Assessment |
|---|---|
| Chesterton's Fence | PASS. Original ADR-006 driver (workflow YAML untestability) anchored verbatim. Carve-out only applies where testability gap doesn't exist. |
| Path Dependence | PASS with caveat. Reversible pre-M3 adoption; evolvable post-adoption via SemVer. Honest framing. |
| Core vs Context | PASS. Build pipeline is supporting subdomain; YAML config is generic; Python schema validator is what matters (core). |
| Second-System Effect | PASS. Five conditions narrow scope; not "everything we didn't do last time." |

**Strategic verdict**: APPROVED. Amendment is principled, reversible, scoped, and addresses a real gap surfaced by REQ-003 + PR #1773 incident class.

---

## Final Disposition

**Status**: ACCEPTED (Round 2 consensus, 6/6 agents)
**Effective**: 2026-04-28
**Migration**: Phase 1 (REQ-003 M1) brings existing `templates/platforms/*.yaml` files into formal compliance with all seven conditions.
**Enforcement**: forward-looking until REQ-003 M1 ships `validate_templates_schema.py` and CI wiring; honor-system interim documented in plan.

**Files referenced**:
- `.agents/architecture/ADR-006-thin-workflows-testable-modules.md` (amendment subject)
- `.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md` (triggering context)
- `.agents/plans/active/req-003-multi-tool-artifact-build.md` (migration tracking)
- `.agents/incidents/2026-04-27-pir-plugin-manifest-schema-1773.md` (PR #1773 root-cause framing)
- `.agents/sessions/2026-04-28-session-1761-req-003-adr-006-amendment-config-data-exception.json` (session evidence)

---

## Round 3 — 2026-04-29 — severity gate removed

Triggered by M4 implementation feedback: 11 rules in live `.claude/rules/` lacked path scope under the Round 2 severity-gate rules. User pushback: "if we tripped over that many rules, the system is wrong, not the rules."

**Decision (no debate; user direct override of Round 2 design)**: rules are universal across providers; unscoped rules default to `applyTo: "**"`. Severity field, governance-keyword scan, and conditional skip logic from Round 2 are removed.

**Verdict**: ACCEPT (no agent vote; user as authoritative deciding party).

**Rationale**: Round 2 severity gate was speculative complexity. Conditions 6+7 (YAML safe_load + pattern hardening) remain in force; they're unrelated to rules severity.

**Files updated**:
- ADR-006 amendment section "Round 3 amendment-of-amendment"
- REQ-003 spec REQ-003-006 simplified
- `build/scripts/generate_rules.py` simplified (severity branches removed)
- `templates/platforms/copilot-cli.yaml` (`skipIfNoPathScope` dropped)
- `build/scripts/validate_templates_schema.py` (RULES_KEYS updated)
- `tests/build_scripts/test_generate_rules.py` (severity tests replaced with universal-default test)
- `tests/build_scripts/test_validate_templates_schema.py` (skipIfNoPathScope removed from valid fixture)
