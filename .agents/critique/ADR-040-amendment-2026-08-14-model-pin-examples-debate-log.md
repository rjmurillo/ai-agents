# ADR-040 Amendment Debate Log: 2026-08-14 Model Pin Examples (issue #4940)

## Review Summary

| Metric | Value |
|--------|-------|
| **Date** | 2026-08-14 |
| **Amendment** | Annotate the superseded model-identifier strategy; correct copyable examples |
| **ADR under review** | ADR-040 (Skill Frontmatter Standardization and Model Identifier Strategy) |
| **Rounds** | 1 |
| **Final Verdict** | ACCEPTED |
| **Review mode** | Single-reviewer pass (see Disclosure) |

## Disclosure: Review Mode

This is **not** a six-agent debate. The implementer ran this session and cannot
delegate to subagents, so one reviewer applied the six adr-review lenses
(`.claude/skills/adr-review/SKILL.md`, "Agent Roles") in sequence. The verdicts
below are one person's findings through each lens, not six independent
opinions. A maintainer who considers the annotation a decision change, rather
than a record of one already made, should run the full skill before merge.

The change qualifies for a light pass on its face: **ADR-080 already made the
decision** (accepted 2026-07-11, PR #3028). This amendment does not decide
anything. It marks which parts of ADR-040 that decision superseded, and it
rewrites the examples so a reader who copies them does not produce a CI
failure.

## Scope of the Amendment

| Location in ADR-040 | Change | Kind |
|---------------------|--------|------|
| Status | Names the superseded sections and points at ADR-080 | Annotation |
| Section 1 (Model Identifier Format) | Superseded callout preserving the original decision in prose; examples replaced with the two conformant states | Annotation + example fix |
| Section 2 frontmatter example | `model:` line commented out with the ADR-080 rule | Example fix |
| Section 2 Field Status table | `model` row Required to Optional; `model-rationale` row added | Correction of a stale claim |
| Section 3 (Three-Tier Strategy) | Superseded callout; tier table left intact as historical reasoning | Annotation |
| Phase 1 implementation note | Correction note: `model` is no longer a required field | Correction of a stale claim |
| Verification checklist | `model` bullet restated against ADR-080 | Example fix |
| Validation Script Criteria | Regex struck through; current gates named | Correction of a stale claim |
| Related ADRs | ADR-080 entry added | Annotation |

No decision text was deleted. Every superseded statement is preserved either in
place or quoted inside the callout that supersedes it.

## Lens Findings

| Lens | Verdict | Key finding |
|------|---------|-------------|
| Architect | ACCEPT | Supersession is recorded in ADR-040 and cross-linked from Related ADRs. The in-place callout style matches the existing 2026-04-30 note in the same file, so the document keeps one convention. |
| Critic | ACCEPT (P2 noted) | The tier table in Section 3 still carries versioned ids in the Model column. Left deliberately: it is the historical tier reasoning, and the callout above it says so. Removing the ids would erase what the ADR decided. |
| Independent-thinker | ACCEPT | Challenged whether ADR-040 should be marked fully superseded instead of section-by-section. Rejected: Sections 2 and 4 onward (frontmatter structure, metadata conventions, allowed-tools) are still live and unrelated to model policy. A blanket status change would discard guidance nothing else replaces. |
| Security | ACCEPT | No security surface. `security-detection` is named in the ADR as a snapshot-pinning candidate; the amendment records that it ships `model: haiku` with a cost rationale today, which is a factual correction, not a policy change. Determinism claims tied to ADR-033 are restated, not weakened: ADR-033 is satisfied by skill logic, not by a frozen model id. |
| Analyst | ACCEPT | Every factual claim added is backed by a level-1 read this session: `scripts/validation/check_model_pins.py` (`_VERSIONED_RE`, `ROLLING_ALIASES`, `DEFAULT_MODEL`), `.claude/skills/SkillForge/scripts/_constants.py` (`REQUIRED_PROPERTIES`, `OPTIONAL_PROPERTIES`), `templates/platforms/copilot-cli.yaml` (`model_tiers`), `scripts/eval/_eval_common.py` (pricing), and the shipped frontmatter of `security-detection` and `session-log-fixer`. |
| High-level-advisor | ACCEPT | Right priority (P1 bug: the docs actively teach a CI failure), right scope (annotate and correct, do not relitigate ADR-080). |

## Issues

### P0 (Blocking)

None.

### P1 (High)

None. The one candidate, "does correcting examples inside an accepted ADR
rewrite history", is answered by the callout structure: the original decision
text is quoted in the callout that supersedes it, so `git blame` and the
callout agree.

### P2 (Documentation)

1. **Tier table retains versioned ids.** Section 3's Model column still reads
   `claude-opus-4-6` and so on. Deliberate; the callout above the table tells
   the reader not to copy them. A future editor who wants the table to be
   copy-safe should replace it with tier names, which is a larger edit than
   this issue authorizes.
2. **`metadata.subagent_model` is untouched.** `check_model_pins.py` collects
   nested pins with `if key == "model"`, so `subagent_model` is outside the
   gate, and no script reads it. Recorded as inert metadata in
   `SKILL-STANDARDS-RECONCILED.md`; a decision about whether it should exist at
   all belongs in its own issue.

## Strategic Validation

| Lens | Assessment | Note |
|------|-----------|------|
| Chesterton's Fence | PASS | The original purpose of the pin guidance (auto-updating aliases, deterministic snapshots for security-critical skills) is documented in the callout before it is superseded. ADR-080 documents why it no longer holds: the retirement CI break (#2839) and the absence of any sweep path for skills. |
| Path Dependence | PASS | Reversible. The amendment adds callouts and rewrites examples; reverting the commit restores the prior text exactly. |
| Core vs Context | N/A | Documentation correction, no build-or-buy content. |
| Second-System Effect | PASS | No new policy invented. The amendment restates ADR-080 and nothing else. |

**Overall Strategic Assessment**: APPROVED.

## Verdict

ACCEPTED. The amendment is annotation plus factual correction of an already
superseded strategy. No new decision is proposed, no live guidance is removed,
and every added claim is sourced.

## Follow-Ups

1. Serena memories `claude/claude-code-skill-frontmatter-standards` and
   `skills/skillcreator-enhancement-patterns` still teach the retired
   `claude-opus-4-5` id. Out of scope for a docs PR; needs a memory-index pass.
2. `.agents/analysis/claude-code-skill-frontmatter-2026.md` carries the same
   stale pin guidance.
3. A maintainer may want the full six-agent adr-review pass on this amendment;
   see Disclosure above.
