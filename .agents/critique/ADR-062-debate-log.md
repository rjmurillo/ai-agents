# ADR-062 Review Debate Log: Conditional LSP-First Navigation Enforcement

**Artifact**: `.agents/architecture/ADR-062-conditional-lsp-first-enforcement.md` (Proposed)
**Protocol**: ADR Review Protocol, 6-agent debate (architect, critic, independent-thinker, security, analyst, high-level-advisor)
**Date**: 2026-05-31
**Synthesis lead**: high-level-advisor

## Rounds

- **Round 1** reviewed the design intent (a workflow args bug left the draft path unreadable to the agents). It surfaced two real precedent conflicts and a scope concern. Verdict: NEEDS-REVISION.
- **Round 2** (this log) reviewed the revised ADR text directly, framed as verification against Round 1's three blocking P0s.

## Per-Agent Vote and Position (Round 2)

| Agent | Vote | Core position |
|-------|------|---------------|
| architect | Accept | All three prior P0s resolved in text and verified on disk. #1993 quote verbatim at lines 16-29 confirmed; deep-vs-shallow split clean; ADR-033/061/008/035 relationships correct. 3 P1s. No new P0. |
| critic | Accept | All 3 P0s resolved by dedicated verifiable sections, not just named. Material concern: Impact-table path citation hygiene. 5 implementation-detail P1s. Escalates LSP-reachability mechanism P1 to P0 only if it cannot be a bounded non-blocking probe. |
| independent-thinker | Disagree-and-Commit | Design sound, every prior P0 resolved, facts verified. Residual disagreement is timing (hard-block vs measure-then-flip); recorded, mitigated, User Sovereignty. Commits. |
| security | Accept | STRIDE: fail-open correct (8 modes + ANY exception to exit 0), detection injection-free (CWE-78/77 eliminated), paths CWE-22-safe (Path.resolve + repo-root + allowlist), gate-state single-SoR sound. Risk 2/10 Low. 3 P1s. |
| analyst | Block | Revision resolves all three prior P0s; every factual claim verified. One new P0: Section 3 Read-gate does not locally restate the Decision's "relevant capability" binding, so an unbound "reachable" could trip the Warmup BLOCK on md/json/yaml/toml. Narrow; one sentence locks it. |
| high-level-advisor | Accept | All 3 P0s resolved, facts verified. Scope right, reversibility credible (LSP_GATE_MODE=warn, SKIP_LSP_GATE, single revert), residual hard-block risk bounded to one redirected turn. Records warn-first dissent under User Sovereignty. |

## Consolidated Resolution Table: Prior P0s

| Prior P0 | Resolved? | Evidence |
|----------|-----------|----------|
| P0-1 ADR artifact missing | YES (6/6) | ADR exists, repo-standard structure. |
| P0-2 altitude/scope (do not hard-block the 79% non-code corpus) | YES for symbol-grep guards (6/6); Read-gate seam flagged by analyst | Section 2 binds symbol-grep BLOCK to symbol-level navigation; never fires on md/json/yaml/toml. Corpus verified: 6031 tracked, 3566 .md, 1070 .json, 1146 .py, 25 .ts. Read-gate capability seam resolved below. |
| P0-3 precedent conflict (#1993) + safety | YES (6/6) | #1993 quote matches invoke_serena_reassertion.py:16-29 verbatim including "marker-branch can be added later if a real activation surface is introduced." ADR introduces that surface (PostToolUse tracker as single SoR). Fail-open 8 paths; injection-safe pure-regex; Path.resolve; SessionStart-only idempotent reset. ADR-061-hook-matcher-shims Withdrawn 2026-05-27 verified; ADR-062 number free. |

## Strategic Checklist Verdict

- Scope: Lake (1 ADR + 7 hooks + shared lib + tests + tri-tree rule). PASS.
- Reversibility: Layered (LSP_GATE_MODE=warn, SKIP_LSP_GATE, single revert, audit.log). PASS.
- Blast radius of the disputed P0: fail-open caps the worst case at one redirected turn, not a deadlock. PASS on severity.
- Evidence quality: load-bearing claims verified; citation corrections applied (plugin.json path, gate count, generator/parity paths). PASS with corrections.
- User Sovereignty: warn-first/defer dissent recorded and overridden by explicit user directive; all six commit. PASS.

## Synthesis Resolution of the Analyst P0 (recorded honestly)

The analyst's standing Block was a real textual seam: Section 3 did not define what capability the Read gate keys on. The reviewers' suggested fix was to **exempt** md/json/yaml/toml from the Read gate (treat them as "no reachable LSP").

The user directive is the opposite: gate **all** Serena-configured languages on the Read path ("literally all items Serena can support... if there is a native LSP, why use grep"). Under User Sovereignty, the seam is closed in the user's direction, not by exemption:

- **Symbol-grep guards** key on go-to-definition / find-references capability. Programming languages only. md/json/yaml/toml never qualify (no symbol search replaces grep there).
- **Read gate** keys on `get_symbols_overview` capability, which Serena provides for all 8 configured languages. md/json/yaml/toml therefore ARE gated, by design, with the graduated ramp (one overview call front-loaded), fail-open, and the SKIP_LSP_GATE kill switch as the safety net.

This is a principled capability split, not an exemption. It removes the ambiguity the analyst flagged (Section 3 now names the exact capability and `detect_lsp_provider.py` returns providers per the relevant capability per guard). The analyst's and independent-thinker's preference (exempt non-symbol-navigable types / warn-first rollout) is recorded as dissent.

## Final Consensus

**ACCEPTED-WITH-DC.** 5 of 6 cleared (4 Accept, 1 Disagree-and-Commit); zero unresolved prior P0s. The analyst's single new P0 (Read-gate capability binding) is closed by explicitly defining the Read-gate capability as `get_symbols_overview` (gating all 8 configured languages per user directive), with the exclusion preference recorded as dissent. Implementation-detail P1s (detection as pure config check not live probe, nav_required=2, repo-relative path citations, verbatim kit regex in module docstrings, gate-state outside the working tree, gate count 23 to 21, git-grep-allowed + bash-grep-sequencing tests, sub-100ms with cached detection) are folded into the ADR and the implementation plan. The warn-first timing dissent stands under User Sovereignty and is not re-litigated.
