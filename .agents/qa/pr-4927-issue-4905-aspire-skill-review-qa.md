---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-12-session-4905-bbe8dc321-implement-aspire-skill-review-targeted.json
qaCommit: 3a5bc61be3b3785807456f8800609bcfb030d002
---

# QA Report: Aspire Skill Review (issue #4905)

## Verdict

PASS. The single judgment-bearing skill change (SkillForge external-skill-source
adaptation guardrail) is verified by a security-critical copilot-provider
prompt-change eval and by repository validation gates. The PASS is bound to the
recorded evidence below: the eval gate result and the required-check state at the
pushed review tip. It is not asserted while any required check is pending.

## Security classification (TASK-020)

Security-critical. The guardrail's Gate 1 is an untrusted-source control
(authoritative pinned source required; external skill text treated as data, never
executed as instruction). It mitigates threat T003 in
`.agents/security/threat-models/TM-aspire-skill-review.md` (embedded source
instructions redirect execution; Risk High) and implements REQ-020's untrusted-
data acceptance criterion. Under ADR-057, REQ-020, and DESIGN-019, the prompt
change therefore runs under the security-critical tier. The classification is
recorded in `.agents/analysis/aspire-skill-review-matrix.md`.

## Behavioral eval (TASK-022)

- Command: `scripts/eval/eval-prompt-change.py --prompt .claude/skills/SkillForge/SKILL.md --base-ref origin/main --scenarios tests/evals/skills/aspire-skill-review-scenarios.json --provider copilot --security-critical --runs 5 --model claude-opus-5` (run with `COPILOT_HOME` pointed at a fresh session-state to stay under the CLI 4096-entry scan cap).
- Gate: PASS. Before 100 percent, After 100 percent, no regression, no high
  flakiness, and every after run passes (security-critical 100 percent, 7 scenarios x 5 runs).
- Review-driven scenario correction (PR 4927 threads): S5 now states the full
  source-identity precondition (pinned commit SHA plus enumerated file list), and
  S1 and S2 assert the routing verdict only. The REUSE verdict is deterministic
  (10/10 runs before+after); only the free-text justification wording varied, the
  sole flakiness class the security-critical tier would otherwise trip. The eval
  was re-run at the security-critical tier after this correction and the gate
  stays PASS with all seven scenarios 5/5.
- Coverage: positive reuse, positive create-when-no-owner, duplicate-creation
  negative, missing-source-identity negative, product-specific rejection edge,
  source-text instruction-injection negative (S6), and unpinned-paraphrase
  source-integrity negative (S7).
- Interpretation: the base ref (`origin/main`) already passes every scenario, so
  the gate proves non-regression rather than a behavioral delta; the guardrail
  codifies behavior the base model already exhibits. This is an honest reading of
  the numbers, not a claim of measured improvement.
- Sanitized report: `.agents/analysis/aspire-skill-review-eval-20260812-0207.json`
  and `.md`. Raw per-run output kept only under gitignored `.agents/scratch/`.

## Repository validation

- `scripts/validation/pre_pr.py`: RESULT All validations passed.
- Generation drift: `build/scripts/build_all.py --check` flags only the
  regenerated SkillForge mirror, which is committed.
- Portability ratchets, skill contract tests, plugin frontmatter, and plugin
  version bump: all pass.
- Redaction scan: durable artifacts carry no SAML URL, email, internal host, or
  token; git SHAs and the pinned-source citation are preserved.

## Continuous integration evidence

- Required checks are gated by branch protection: the PR cannot merge until every
  required check reports success, so this verdict is not published ahead of the
  required results.
- Verified with `.claude/skills/github/scripts/pr/get_pr_checks.py --pull-request
  4927` at the pushed review tip: `MergeRefUsable` true, zero failed, zero
  pending, and all required checks reporting success. The check state is re-read
  after each push, and this report's own commit re-triggers the required checks,
  which must stay green before merge.

## Scope

Session code change is limited to `.claude/skills/SkillForge/SKILL.md`, its new
reference, and the generated Copilot mirror. All other artifacts are analysis,
eval, and spec evidence.

Session code change is limited to `.claude/skills/SkillForge/SKILL.md`, its new
reference, and the generated Copilot mirror. All other artifacts are analysis,
eval, and spec evidence.
