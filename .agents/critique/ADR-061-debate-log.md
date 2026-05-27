# ADR-061 Debate Log

**ADR**: [ADR-061: Hook Matcher Shims Delegate to Canonical Body](../architecture/ADR-061-hook-matcher-shims-delegate-pattern.md)

**Status**: Withdrawn before acceptance (2026-05-27, session 1837)

**Session**: 1837 (`.agents/sessions/2026-05-27-session-1837-delegate-shim-refactor-req-003-007-spec-amendment.json`)

**Branch**: `feat/req-003-007-delegate-shim`

## Outcome

**Verdict: WITHDRAW + ship Alternative B (deterministic full-tree regeneration + drift CI gate)**

Tally:

| Agent | Position |
|-------|----------|
| architect | ACCEPT |
| security | ACCEPT |
| critic | DISAGREE_AND_COMMIT |
| independent-thinker | DISAGREE_AND_COMMIT |
| analyst | DISAGREE_AND_COMMIT |
| high-level-advisor | WITHDRAW (option B in tie-breaker) |

User decision (session 1837): Withdraw ADR-061, ship Alternative B today.

## Phase 0: Related Work

Prior art investigation surfaced during ADR drafting:

- REQ-003-007 step 5 (`.agents/specs/requirements/REQ-003-multi-tool-artifact-build.md:281-305`) — current inline-body mandate.
- Plan M5-T2 + M7-T3 (`.agents/plans/active/req-003-multi-tool-artifact-build.md:79,114`) — M7-T3 explicitly anticipates the "one-body-many-matchers" alternative.
- Install-parity validator (PR 2095, merged 2026-05-26) — analogous canonical-plus-thin pattern at the agent layer.
- `architecture/install-parity` Serena memory — confirms hooks are intentionally out of scope for install-parity (build-all check covers them).

## Phase 1: Independent Review

### Architect: ACCEPT

Zimmermann 7-question assessment all PASS. Drift evidence concrete and falsifiable. Prior Art section satisfies Chesterton's Fence. Implementation phasing correctly puts BLOCKER spike first. Aligns with install-parity idiom.

P1 weaknesses:

- Missing MADR 4.0 frontmatter (status, date, decision-makers).
- No explicit review-date / expiration trigger.

P2 weaknesses:

- Phase 1 spike acceptance criteria could be sharper (specific commands per install mode).
- `_impl/` leading-underscore convention justification missing.

Question: has Copilot CLI runtime team confirmed subdirectory preservation during install?

Position: **ACCEPT** — weaknesses are P1/P2 documentation gaps, not design flaws.

### Security: ACCEPT

Findings:

- **MEDIUM (CWE-426 Untrusted Search Path)**: Attack surface widens from 1 file per hook to 3 files per hook. `_shim_runtime.py` is shared across all matchers in an event dir — single-file-compromise-all vector. Trust boundary (filesystem permissions) unchanged, but file-level attack surface 3x. ADR's "no new attack surface" claim is imprecise; should read "same trust boundary, wider file-level attack surface, no new privilege escalation."
- **LOW (CWE-400 stdin cap)**: Preserved if delegate sequences `cap → import → call` correctly. ADR should add MUST: "stdin MUST be fully consumed and capped before any `_impl/` import executes."
- **LOW (CWE-94 code injection)**: Same risk as modifying any inline shim today; generator is sole writer.
- **INFO (rollback flag confusion)**: `--legacy-inline-body` flag is build-time, not runtime; install-parity validator detects layout mismatch.
- **INFO (exit code preservation)**: Crash policy must be preserved across delegation chain; ADR states it correctly.

Position: **ACCEPT** with two revisions: refine attack-surface wording; add stdin MUST clause.

### Critic: DISAGREE_AND_COMMIT

P0 weaknesses:

- **Drift evidence is not independently verifiable on main.** The central drift table references PR 1763, which is unmerged. On main, multi-matcher shims of `branch_protection_guard` have identical bodies. The 4-shim divergent-body claim for `false_completion_gate` depends on PR 1763. An ADR motivating a multi-day refactor on unmerged-PR evidence is building on an assumption.
- **88% byte reduction claim is unverifiable and likely wrong.** Today only 4 of 22 hooks are multi-matcher. The 88% claim requires either "all hooks become multi-matcher" (not projected) or a different denominator.

P1 weaknesses:

- Alternative B dismissed without cost comparison. Should include frequency of failure, structural-fix cost, procedural-fix cost, projected multi-matcher growth.
- BLOCKER (Copilot CLI install modes) identified but no evidence it has been investigated. ADR should not be "Proposed" with an uninvestigated binary blocker.

P2 weaknesses:

- Security section understates the change (shared `_shim_runtime.py` is single-point-of-compromise vs. N independent targets).
- Confirmation Rule 2 misspecified (thin shims do not contain body bytes after refactor — rule becomes a tautology).

Recommendations: demote to Draft until Phase 1 spike completes; add math; strengthen alt B rejection with data; correct security wording; fix Rule 2.

Position: **DISAGREE_AND_COMMIT** — structural direction sound, but uninvestigated blocker + unverifiable motivating claim + incorrect quantitative claim are fixable without changing decision. Complete the spike, verify the math, resubmit. If Alt B is sufficient near-term while spike runs, say so.

### Independent-Thinker: DISAGREE_AND_COMMIT

Contrarian arguments:

- **Problem does not exist on main today.** Diffed every multi-matcher hook pair on main. Zero body drift. The drift evidence is from PR 1763, unmerged. ADR presents PR-workflow failure as structural deficiency.
- **Alternative B dismissed too quickly.** The cause is non-atomic regeneration. A CI gate that diffs all shim bodies catches this class of bug in seconds. Cost: one validator function. ADR rejects a 2-hour fix for a multi-day refactor.
- **`_impl/` import creates a genuine NEW failure mode.** Today each shim is self-contained — missing-file impossible. With delegate shims, missing `_impl/` directory or broken `sys.path` fails every hook in event dir simultaneously. Writing an ADR for a design with an untested binary blocker is premature.
- **"88% byte reduction" is a vanity metric.** Install tree is generated artifacts. Disk is cheap. Real cost is behavioral drift, zero on main.
- **Only 3 hooks with 2 matchers each on main.** No evidence growth is imminent. Premature abstraction.

Alternative proposal: **Deterministic full-tree regeneration + `git diff --exit-code` CI gate.** Zero structural change. Zero import surface. Zero spec amendment. Completeness: 8/10. Revisit delegate when multi-matcher count exceeds 8.

Position: **DISAGREE_AND_COMMIT** — solves projected problem not current one; deterministic-regen achieves same safety at 10% cost.

### Analyst: DISAGREE_AND_COMMIT

Evidence assessment:

- Drift evidence: structural mechanism confirmed on main (`inject_shim` wraps body per matcher; partial regeneration structurally produces drift). Specific divergence table on PR 1763 unverifiable (branch unavailable locally during review). L1/L2 not L1.
- Cost: 7.9x and 5.5x verified on disk; 4.9x for `false_completion_gate` extrapolated from 5.8x (one shim on main). Minor discrepancy, not material.
- Root cause: HIGH confidence correctly identified.
- BLOCKER: real, correctly classified as binary go/no-go.
- **Confirmation Rule 2 becomes tautology** post-refactor (body bytes live only in `_impl/`, thin shims have no body to diverge).
- **Gap**: validator does not check `_impl/invoke_X.py` matches canonical `.claude/hooks/<Event>/<hook>.py`. New failure mode: direct `_impl/` edit passes all 3 rules while drifting from canonical.

Required addition before implementation: **Rule 4 — `_impl/invoke_X.py` MUST be byte-equal to `.claude/hooks/<Event>/<hook>.py`.** Without this, the refactor eliminates the old drift vector but introduces a new one the validator cannot catch.

Position: **DISAGREE_AND_COMMIT** with required addition (Rule 4).

### High-Level-Advisor: WITHDRAW (Option B)

> Three independent agents (critic, independent-thinker, analyst) converged on the same evidence: **zero drift exists on main today**. The drift the ADR cites is from unmerged PR 1763's workflow failure. You are proposing a multi-day structural refactor against a projected problem, not an observed one.
>
> The math kills it:
>
> - Alt B: 2 hours. Deterministic regen + `git diff --exit-code` CI gate. Addresses root cause (drift detection) at the source.
> - ADR-061: 3-5 days. PR 1763 held. Opportunity cost on 2029. New attack surface (security: 3x file count). New drift vector (analyst's Rule 4 — shims must byte-match originals, which is the same problem one layer deeper).
> - Multi-matcher hooks today: under 8. Threshold for structural fix not crossed.
>
> Critic is right that "88% drift reduction" is wrong math against a zero baseline. Independent-thinker is right that this is premature abstraction (philosophy-of-software-design.md: "speculative generality"). Analyst's Rule 4 requirement proves the shim pattern reintroduces drift it claims to solve.
>
> Do this:
>
> 1. Withdraw ADR-061.
> 2. Implement alt B today, unblock PR 1763.
> 3. Open issue: "Revisit delegate-shim when multi-matcher hooks exceed 8 OR when CI drift gate fires 3+ times in a quarter."
>
> You picked delegate-shim before you had the 2-hour alternative on the table. You have it now. Ship the cheap fix.

## Phase 2: Consolidation

Convergent message from 3 D&C agents + advisor: structural fix right LONG-TERM; urgency framing on main unsupported; alt B is the right NEAR-term action.

Anti-pattern check (Zimmermann 7):

- No Pass Through (all agents produced substantive findings).
- No Copy Edit (all findings architectural, not editorial).
- No Siding/Dead End (all stayed on the decision).
- No Self Promotion (no agent pushed personal preference; alt B emerged from evidence).
- No Power Game (all positions backed by evidence).
- No Offended Reaction (architect and security accepted; D&C agents disagreed without defensiveness).
- No Groundhog Day (single round; no repeated issues).

## Phase 3: Resolution

Surfaced to user with the convergent recommendation. User chose option 1: withdraw + ship alt B today.

## Phase 4: Convergence

Consensus achieved in one round:

- 2 ACCEPT (architect, security)
- 3 DISAGREE_AND_COMMIT (critic, independent-thinker, analyst) — willing to commit to delegate-shim direction long-term but not now
- 1 WITHDRAW recommendation (high-level-advisor)
- 1 USER decision: WITHDRAW + alt B

No P0 unresolved. No agent BLOCK. Disagree-and-Commit positions documented above for institutional record.

## Lessons

- **Authority Boundary worked.** User had picked delegate-shim earlier without alt-B-is-2-hours framing. The 6-agent debate surfaced the cheaper alternative; the user got the call.
- **Premature abstraction is a real cost.** ADR-061 was structurally well-designed but solved a projected problem. The PoSD speculative-generality rule fired.
- **Independent-thinker is essential.** Without the contrarian voice, the architect + security ACCEPT votes could have looked like consensus. Independent-thinker named the unmerged-PR evidence problem, which then surfaced in critic and analyst analyses.
- **Analyst's Rule 4 finding is the kicker.** Even if the ADR were accepted, the proposed parity rules would not catch the new drift vector. The shim pattern moves the problem, doesn't eliminate it.

## Follow-up

- Issue: "Revisit ADR-061 delegate-shim refactor when (a) multi-matcher hook count exceeds 8, OR (b) alt B CI gate fires 3+ times per quarter."
- Implementation: alt B (deterministic full-tree regeneration + `git diff --exit-code` CI gate).
- PR title: `refactor(generate_hooks): deterministic full-tree regeneration + drift CI gate`.
