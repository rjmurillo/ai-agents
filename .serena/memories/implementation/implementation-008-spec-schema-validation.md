---
name: implementation-008-spec-schema-validation
description: Constraints for writing spec artifacts (REQ/DESIGN/TASK) — read spec-schemas.md first; validate enums before committing
type: feedback
---

# Implementation: Spec Schema Validation

**Session**: 2026-05-10 (PR #1995 REQ-010 docs PR)
**Confidence**: HIGH on all constraints.

---

## Constraints (HIGH confidence)

**Read `.agents/governance/spec-schemas.md` BEFORE writing or delegating any spec artifact.**
The schema defines required enum values for every frontmatter field across all three types. Delegating to spec-generator WITHOUT first loading the schema produces invalid frontmatter on every invocation. PR #1995 drew 9 of 13 bot threads solely from frontmatter violations: wrong `priority`, missing `status`, wrong `category`, wrong `status`, wrong `complexity`. Same class as PR #1989.
Source: 3 bots (devin, copilot, coderabbit) converged within minutes of PR #1995 opening, 2026-05-10.

**spec-generator agent does NOT self-validate against the schema.** Do not assume generated frontmatter is correct. After any spec-generator run, verify:
- `priority`: must be `P0` / `P1` / `P2` (never `medium`, `high`, `low`)
- `status`: requirement/design uses `draft|review|approved|implemented|rejected`; task uses `todo|in-progress|blocked|done|cancelled` (never `ready`)
- `category` (requirement only): `functional|non-functional|constraint` (never `tooling`, `security`, etc.)
- `complexity` (task only): `XS|S|M|L|XL`; XS=1-2h, S=2-4h, M=4-8h, L=8-16h, XL=16+h — must match `estimate` field
Source: Every spec PR since REQ-009 has had schema violations on first push. Issue #2001 tracks the fix.

---

## Edge Cases (MED confidence)

**PR description validator flags inline file paths as claimed changes.**
Any `.agents/...` or `scripts/...` path in the PR body's prose or "Refs" sections triggers "file mentioned but not in diff" CRITICAL failures. Use "see tracking issue" or "see commit history" instead of raw paths in the body.
Source: PR #1995 first CI run FAIL — 3 CRITICAL on retro/memory file paths in the original body, 2026-05-10.

**Table-format false positive.** Bots sometimes claim `||` double-pipe table rows when the real issue is `|---|---|---|` separator lines being parsed. Verify with `grep -n "||"` before modifying.
Source: PR #1995 copilot thread PRRT_kwDOQoWRls6A74Rd, 2026-05-10.

---

## Preferences (MED confidence)

**Use P1 for specs that establish calibration methodology reused by future detectors.** Use P2 for pure maintenance/cleanup. P1 = high impact on future work; P2 = normal improvement.
Source: PR #1995 devin suggested P2; P1 chosen for REQ-010 because threshold-calibration approach is load-bearing for M4/M5 follow-ons, 2026-05-10.

---

## Notes (LOW confidence)

spec-generator should be a Skill (not an agent) with spec-schemas.md as bundled resource so enum validation is always in scope. Issue #2001 tracks the conversion.

---

## Quick reference: valid enum values

### All spec types
- `priority`: P0 | P1 | P2

### Requirements
- `status`: draft | review | approved | implemented | rejected
- `category`: functional | non-functional | constraint

### Design
- `status`: draft | review | approved | implemented | rejected

### Tasks
- `status`: todo | in-progress | blocked | done | cancelled
- `complexity`: XS (1-2h) | S (2-4h) | M (4-8h) | L (8-16h) | XL (16+h)

## History

| Date | PR | Finding |
|------|----|---------|
| 2026-05-10 | #1995 REQ-010 | 9/13 threads from frontmatter schema violations on first push |
| 2026-05-10 | #1989 REQ-009 | Similar drift caught by coderabbit, listed as deferred |
