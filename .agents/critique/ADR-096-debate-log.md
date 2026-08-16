# ADR-096 debate log

Subject:
`.agents/architecture/ADR-096-trusted-vendor-provenance-gate.md`

Skill: `.claude/skills/adr-review/SKILL.md`, six-agent debate, four rounds.

## Outcome

ADR-096 is accepted. All six roles voted ACCEPT in the final round.
`implemented` remains false until PR #4846 merges.

| Role | Final vote |
|---|---|
| architect | ACCEPT |
| critic | ACCEPT |
| independent-thinker | ACCEPT |
| security | ACCEPT |
| analyst | ACCEPT |
| high-level-advisor | ACCEPT |

## Debate progression

### Round 1

The first review supported the trusted-base design but found missing decision
records and failure boundaries:

1. Explain why ADR-066's local hook valve does not apply to a hosted required
   status check, and document repository administration as break glass.
2. Make `merge_group` trust updates fail closed until originating pull request
   identity can be resolved.
3. Narrow the dual-channel claim to channel-specific failures.
4. Define rollback owner, order, and target time.
5. Record bootstrap smoke evidence before enabling the required context.
6. Tie security claims to named tests.

The ADR and implementation were revised. `merge_group` trust updates now fail
closed. Head-gate startup preserves a created Check Run ID when Commit Status
publication fails.

### Round 2

Reviewers checked the revised trust model, immutable materialization, dual head
gates, pin update authorization, rollback, and test evidence. Remaining
findings concerned governance evidence, retry classification, rollback
detection, and citations for candidate configuration rejection.

### Round 3

Five roles voted ACCEPT or Disagree-and-Commit. The critic blocked acceptance
because the ADR exceeded ADR-006's 100-line workflow target without the
Chesterton's Fence analysis required by
`.agents/governance/ADR-EXCEPTION-CRITERIA.md`.

The following changes resolved that block and the remaining P1 findings:

1. Added the verbatim ADR-006 rationale.
2. Documented two attempted alternatives.
3. Bounded the exception to
   `.github/workflows/vendor-provenance.yml`.
4. Quantified the 184 total and 128 non-comment workflow lines.
5. Recorded testing impact, precedent risk, reversibility, and a review
   trigger.
6. Made authentication, forbidden, not-logged-in, and unauthorized GitHub API
   failures stop after one attempt.
7. Added tests for one-attempt authentication failures.
8. Defined repository-wide blockage detection, alert path, and the start of
   the 30-minute mitigation target.
9. Added named confirmation tests for unpinned executables, `.npmrc`,
   `uv.toml`, and markdownlint configuration.

### Round 4

All six roles reviewed the revised ADR and implementation. Each voted ACCEPT.

One reviewer initially returned BLOCK after a project-scoped semantic tool
resolved relative paths against the wrong checkout. Direct reads of the
requested absolute worktree showed that `_start_head_gates`,
`_finish_head_gates`, and their CLI flags were present. The reviewer retracted
the finding and voted ACCEPT. The critic also rechecked the same paths and
confirmed the correction.

## Verification

From `/home/richard/sessions/pr-autofix-4846`:

```text
uv run pytest -q tests/ci/test_validate_vendor_provenance.py
224 passed in 11.12s
```

Direct file checks confirmed:

- `_start_head_gates` and `_finish_head_gates` exist in
  `scripts/ci/validate_vendor_provenance.py`.
- The validator CLI defines every flag used by
  `.github/workflows/vendor-provenance.yml`.
- Authentication failures use one GitHub API attempt.
- The ADR-006 quote matches the source ADR.
- The exception record satisfies every required analysis category.

## Dissent

No final dissent. Earlier concerns were resolved in the ADR, implementation,
or test evidence.

## Strategic assessment

- Chesterton's Fence: PASS
- Path dependence and reversibility: PASS
- Core versus context: PASS, repository trust enforcement is local policy
- Second-system effect: PASS, scope is one workflow and one validator
- Overall: APPROVED
