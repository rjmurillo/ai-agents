---
id: ADR-096
status: accepted
date: 2026-08-19
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-096: Relax QA-Evidence Commit Equality to a Code-Change-Aware Check

## Status

Accepted. Requested by issue #5164 (labels `enhancement`, `priority:P2`, `area-validation`; see the priority note at the end of this document). Round 1 of the standard 6-agent `adr-review` debate (architect, critic, independent-thinker, security, analyst, high-level-advisor) returned 6/6 ACCEPT-WITH-CHANGES; debate log at `.agents/critique/ADR-096-debate-log.md`. This text is the Phase 3 resolution incorporating the required changes, plus a Round 2 correction (see the debate log's Round 2 entry) fixing a Decision-section claim that contradicted this ADR's own correction note. Per `.claude/rules/ci-scripts.md` MUST-NOT-2 and the `adr-review-policy` lefthook hook, code was implemented only after this ADR's frontmatter `status` transitioned to `accepted` in the same change as this status update, per the `adr-review` skill's own acceptance-transition gate (debate-log evidence at `.agents/critique/ADR-096-debate-log.md`). The frontmatter `status` transition was found missing from this PR's first two heads by the AI Spec Validator workflow on PR #5167; corrected here rather than disputed, since the ADR's own text already asserted the gating rule it had failed to satisfy.

## Date

2026-08-19

## Context

`.claude/lib/qa_report.py`'s `validate_qa_report()` (line 185) hard-fails whenever a QA report's frontmatter `qaCommit` does not exactly equal the current session's resolved commit (`QaBinding.commit`, computed by `session_qa_binding()`, line 142). This equality check runs and raises before either caller ever reaches the code-change-aware check the module already implements, `post_qa_code_changes()` (line 210), which walks the commits between the QA-validated SHA and the current head, filters out `QA_EVIDENCE_PREFIXES` (`.agents/memory/episodes/`, `.agents/qa/`, `.agents/sessions/`), and returns only the non-evidence paths, empty when nothing but bookkeeping changed.

Both call sites hit this ordering problem:

- `scripts/validate_session_json.py:930-992` (`validate_qa_report_evidence`) calls `validate_qa_report()` (line 971) and, only if that does not raise, calls `post_qa_code_changes()` (line 979). A pure rebind commit still hard-fails at line 971-974 before the smarter check ever runs.
- `.claude/skills/session-end/scripts/complete_session_log.py:547` (`_qa_report_evidence`) calls `validate_qa_report()` directly, with no `post_qa_code_changes` fallback at all.

### Evidence this is a real, quantified cost

This session ran a 5-agent evidence audit (`.agents/sessions/2026-08-19-session-99919-bc967748c-critical-review-open-issues-prs.json`) that found:

- **20+ process-only "rebind" commits**, measured via `git log --all --format="%H %s" | grep -i rebind` against a full clone. This command returns 0 on a shallow checkout (confirmed during this ADR's own review: this working tree is a 50-commit shallow clone), which is a clone-depth artifact, not evidence the underlying commits do not exist; re-run against a full fetch to reproduce. One example: `de036ab94` "docs: rebind QA evidence to suppressed-Copilot-findings fix commit (11th rebind)."
- `.agents/sessions/handoffs/2026-08-15-2840-handoff.md` (issue #2840, PR #4954): **23 occurrences of "rebind" across 15 review rounds** on a single PR (independently reproducible with `grep -ci rebind` against the tracked file, confirmed during this ADR's review). Round 15 names the fix that would close this specific chain: relaxing `session_qa_binding()`'s enforced `endingCommit`/`comparison.head` equality (`.claude/lib/qa_report.py:170-178`), a **different function** from the one this ADR changes (`validate_qa_report()`, line 193-197). See "Explicitly out of scope" below.
- The maintainers already agreed on the general direction and acted on it twice in 24 hours: `ca7fcd46f` ("refactor(validation): retire committed QA evidence gate #5125") and `e6c196d03` ("retire mandatory session-log gates #5135") retired the *mandatory* existence requirement for a session log or QA report. Neither touched `session_qa_binding()` or `validate_qa_report()`, so the strict-equality trap still fires in full on the now-optional, validate-if-present path.
- This session hit this exact trap firsthand while landing PR #5161 in this same critical-review session: a manual `qaCommit` rebind was required after `--refresh-ending-commit` moved `endingCommit` forward, even though the QA-validated code had not changed.

**What the pre-retirement counts do and do not establish.** The 20+ rebind commits and the 11-rebind, 23-mention chains all predate the #5125/#5135 mandatory-gate retirement (2026-08-16/17). They establish the mechanism is real and costly under repeated use; they do not establish the current rate, since the mandatory requirement that drove that volume is gone. The opt-in path remains standard practice regardless: this session confirmed QA reports continued to be authored in the days immediately following the retirement (`session-end`'s own recommended flow still attaches one for a PASS verdict), so the fix addresses live, ongoing traffic on the now-optional path, not a closed chapter. This session hit the trap once, directly, three days after the retirements landed.

### What #5125/#5135 did NOT fix

Those two PRs retired the *mandatory* existence requirement. Neither touched `session_qa_binding()` or `validate_qa_report()`, so the strict-equality trap still fires in full on the now-optional, validate-if-present path, which is exactly the path anyone who opts into QA evidence hits.

### Explicitly out of scope: `session_qa_binding()`'s own equality

`session_qa_binding()` (`.claude/lib/qa_report.py:170-178`) separately raises when `episodeMetrics.comparison.head` and the resolved `endingCommit` disagree. This is the function PR #4954 round 15 identified as needing relaxation, not `validate_qa_report()`. This ADR does not change it. Two reasons: first, it is a data-consistency invariant on the session log itself (are these two fields, which are supposed to describe the same commit, actually consistent), a different kind of check from "is this QA verdict stale," and deserves its own analysis rather than being folded into this change under time pressure. Second, measured against the repository history available during this review (a 50-commit sample), this specific check was not observed to be the actual failure mode in any of the sampled commits, so there is no evidence pressure to widen this ADR's scope to include it. The round-15 chain's specific pain is not fully resolved by this ADR; a follow-up issue should be filed against `session_qa_binding()` separately, citing round 15 directly.

## Decision

Redesign `validate_qa_report()` to require an explicit `head` argument and to perform the staleness check itself, rather than leaving staleness detection as a second call a caller can forget:

```python
def validate_qa_report(
    path: Path, expected: QaBinding, *, head: str, repo_root: Path
) -> QaReport:
    """Require a passing QA report bound to the expected session, and not stale.

    ``head`` is the commit to check staleness against. A real (non-evidence-
    path) change between ``report.commit`` and ``head`` is a hard failure
    (unchanged behavior). A commit range containing only paths under
    ``QA_EVIDENCE_PREFIXES`` is not (issue #5164).
    """
    report = load_qa_report(path)
    if report.session_log != expected.session_log:
        raise ValueError(
            "QA report session log does not match current session: "
            f"{report.session_log} != {expected.session_log}"
        )
    changed = post_qa_code_changes(report.commit, head, repo_root=repo_root)
    if changed:
        raise ValueError(
            "QA report is stale; code changed after its commit: "
            + ", ".join(changed)
        )
    return report
```

`head` is a required keyword-only parameter, not an optional one with a `None` default. This is the direct fix for the round-1 debate's single most convergent finding: `scripts/validate_session_json.py`'s `validate_qa_report_evidence()` silently skipped *all* staleness checking whenever its own `validation_head` resolved to `None` (`:976-977`, before this fix). **Correction to the round-1 finding's stated severity, made during implementation:** the round-1 reviewers (architect, critic, independent-thinker, security, analyst) characterized this as reachable on the `--existing-log` path "every real committed-log caller uses." That overstates it: `validate_session_log()` gates the call to `validate_qa_report_evidence()` behind `not existing_log and not creation_mode` one level up (`scripts/validate_session_json.py:1169,1178`), so the `--existing-log` CLI path never reaches this function at all, by design (a deliberate record-vs-compliance-claim split, issue #3385), not because of the `validation_head is None` gap. The gap was still real and worth closing: it fires on the *fresh* validation path (`not existing_log and not creation_mode`) whenever live-`HEAD` resolution fails for any reason (a transient git error, a validation run against a checkout `_resolve_full_commit` cannot parse), silently skipping staleness detection on exactly the case that path exists to enforce. That narrower, still-real case is what this fix closes. Making `head` required means the gap cannot exist by construction: a caller that has no better value must still supply one, and the two call sites below both have one readily available. A caller that fails to pass `head` gets an immediate `TypeError` at the call site, not a silently-skipped check: the loud-failure property multiple round-1 reviewers asked for instead of a docstring-only warning.

`QaBinding.commit`, produced by `session_qa_binding()`, becomes the natural default for `head` at both call sites (see Implementation Notes), rather than being compared directly for equality as it is today. The `report.session_log != expected.session_log` identity check stays exactly as strict as it is today; that check is not the source of the rebind churn.

### Choosing the head value at each call site

- **`scripts/validate_session_json.py`**: on the fresh-validation path (`not existing_log and not creation_mode`), the CLI already auto-resolves `validation_head` to live `HEAD` unless resolution itself fails (`scripts/validate_session_json.py:1642`, `_resolve_full_commit("HEAD")`). Pass that resolved value when it succeeds, since it catches staleness introduced by commits after the session log's own recorded end state; when resolution fails (`validation_head` is `None`: a transient git error, or a checkout `_resolve_full_commit` cannot parse), pass `binding.commit` (the session's own resolved ending commit, already computed one line above) instead of skipping the check entirely. This is strictly better than today's `None`-triggers-skip behavior in every case it can occur, and identical in effect to today's behavior in the common case where `binding.commit` and a would-be live HEAD coincide. This fallback never applies on the `--existing-log` path: as the correction note above states, `validate_session_log()` gates the whole QA-evidence block behind `not existing_log and not creation_mode` one level up (`scripts/validate_session_json.py:1169`), so `--existing-log` never reaches `validate_qa_report_evidence()` regardless of what `head` would resolve to. `--existing-log` is out of scope for this ADR: this change neither adds nor removes staleness checking on that path.
- **`.claude/skills/session-end/scripts/complete_session_log.py`**: pass `binding.commit` directly. No new git call is needed. `_get_ending_commit()` already runs at `complete_session_log.py:815` (a `git rev-parse HEAD` equivalent), before the QA-evidence block, and its result already flows into `QaBinding(commit=ending_commit)` at line 891. `binding.commit` and `ending_commit` are the same value at this call site by construction, so no ambiguity exists here about which head to use.

### Acceptance criteria

- A QA report whose `qaCommit` differs from the current head, but where `post_qa_code_changes` between them is empty (pure evidence-bookkeeping commits only), passes without a rebind, at **both** call sites, on the fresh-validation path each covers (`not existing_log and not creation_mode` for `validate_session_json.py`; unconditional for `complete_session_log.py`, which has no `--existing-log` concept).
- A QA report whose validated commit precedes a real code change reports staleness exactly as it does today, at both call sites, on the fresh-validation path each covers (the specific scenario the round-1 P0 finding named: real code change, no fail-open).
- `--existing-log` is out of scope: it never reaches `validate_qa_report_evidence()` before or after this change (see the correction note in Decision), so no test asserts staleness detection on that path. `tests/test_validate_session_json.py::test_existing_log_ignores_explicit_validation_head` pins the opposite: even an explicit `--validation-head` that would fail the check is never inspected, because the call never happens.
- `complete_session_log.py`'s `_qa_report_evidence` gets the same code-change-aware staleness check as `validate_session_json.py`, using `binding.commit` as `head`, not a silent removal of staleness detection.
- A test replaces (not merely supplements) `tests/test_validate_session_json.py::test_rejects_qa_report_for_stale_commit`, since that test currently pins the exact raise this ADR removes; the replacement asserts the new code-change-aware behavior for the same scenario.
- The four existing tests in `.claude/skills/session-end/tests/test_complete_session_log.py` (lines ~255-325) that exercise `_qa_report_evidence` against a `tmp_path` that is not a git repository need a real git fixture or a mocked `subprocess.run`, since they will now reach `post_qa_code_changes`'s git subprocess calls, which fail outside a repository.
- Mirror updated in `src/copilot-cli/` via the standard sync-then-build pipeline, and its own test mirrors updated identically.
- Per `.claude/rules/ci-scripts.md` MUST-13, the PR introducing this changed gate at `complete_session_log.py` (a call site that had no staleness gate before) must run it against the full corpus of committed session logs and QA reports and quote the output in the PR description.

## Prior Art Investigation

### What Currently Exists

- **Structure/pattern being changed**: `validate_qa_report()` (`.claude/lib/qa_report.py:185-198`). `post_qa_code_changes()` (lines 210-252) and `QA_EVIDENCE_PREFIXES` (line 21) already exist in the same module and already implement code-change-aware staleness semantics; they are simply unreachable from one call site and absent from the other.
- **When introduced**: `validate_qa_report`'s strict-equality contract predates PR #5125/#5135. `post_qa_code_changes` and `QA_EVIDENCE_PREFIXES` were added to address the rebind-churn complaints in issues #5080 and #5064, but only one of the two `validate_qa_report()` callers was wired to reach them, and even there only after the equality check already succeeded.
- **Original author and context**: the strict equality check exists to guarantee a QA report's PASS verdict cannot be silently reused against code it never saw. That guarantee is sound as a carelessness check on an honest actor. It is not, and was never, an adversarial control: the report is plain text in the working tree, authored by the same actor the check judges, with no signature or independent proof a QA run occurred. Nothing in this ADR changes that trust model in either direction.

### Historical Rationale

- **Why was it built this way?** SHA equality is the cheapest possible staleness check.
- **What alternatives were considered?** None recorded at introduction. `post_qa_code_changes` was added later, specifically to soften the equality check's false positives, but was never connected to the check it was built to soften.
- **What constraints drove the design?** None beyond simplicity.

### Why Change Now

- **Has the original problem changed?** No. A stale QA verdict reused against changed code is still the risk this guards against, and real code changes still hard-fail after this change, at both call sites, including the path where they previously did not (see Decision).
- **Is there a better solution now?** Yes. `post_qa_code_changes` already exists and is already directly unit-tested (`tests/test_validate_session_json.py:399-505`), not merely indirectly exercised.
- **What are the risks of change?** Requiring `head` is a breaking signature change for `validate_qa_report()`'s two callers, both within this repository and audited exhaustively (see Impact table); a bug in `post_qa_code_changes` or `QA_EVIDENCE_PREFIXES` is now load-bearing for every QA-report validation rather than a subset. Mitigated by the acceptance criteria above requiring explicit test coverage of both outcomes at both call sites, on each site's fresh-validation path, which is the scenario the round-1 fail-open finding was actually reachable from (see the correction note in Decision).

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Status quo (strict equality) | Zero change | Confirmed rebind churn under the mandatory regime; the opt-in path still hits it today, three days after retirement, in this same session | The cost is measured and ongoing, and the fix already exists in the module, unreachable |
| Drop the commit check entirely (trust `qaSessionLog` alone) | Simplest possible relaxation | Removes real protection: a QA report validated against old code could be reused after a real behavior-changing edit with nobody noticing | Rejected outright by the acceptance criteria; real code changes must still hard-fail |
| Keep `validate_qa_report()`'s original split contract (identity-only, optional `post_qa_code_changes` call left to callers) | Smaller diff | This is what shipped today and is the exact shape that produced the `complete_session_log.py` gap in the first place (identity checked, staleness forgotten) and, per round-1 review, the `validate_session_json.py` fail-open gap; a docstring is not a gate | Repeats a defect this ADR exists to fix; folding the check into one required call closes it structurally instead of by caller discipline |
| Add a `--refresh-qa-commit` sibling to the existing `--refresh-ending-commit` flag (make the rebind free instead of unnecessary) | Smaller change; no validator contract change; composes with a flag operators already know | Still costs a commit per rebind, just a mechanical one; does not address the `complete_session_log.py` gap at all, since that call site has no refresh flow | Genuinely smaller, but strictly weaker: it reduces the cost of the churn without removing the false-positive trigger, and leaves the more severe `complete_session_log.py` gap untouched |
| **Require `head`; fold staleness into `validate_qa_report()` itself (chosen)** | Closes the round-1 fail-open finding structurally, not by convention; no caller can validate identity while silently skipping staleness; `post_qa_code_changes` already exists and is tested | Both call sites need updating for a signature change, not just a reorder; `QaBinding.commit`'s role shifts from "the value directly compared" to "the default `head` value" | Correctly closes the gap #5125/#5135 left open at both call sites, and closes the fail-open gap round 1 found, which a pure reorder (the original draft of this ADR) would not have |

### Trade-offs

The chosen design accepts a breaking signature change to `validate_qa_report()`, a required `head` keyword argument where none existed before, in exchange for making the "staleness was checked" guarantee structural rather than conventional. This trades a slightly larger diff (both call sites' call expressions change, not just their control flow) for eliminating the specific failure mode (a caller that validates identity and forgets staleness) that had already occurred once in this codebase before this ADR was written.

## Consequences

### Positive

- Eliminates the measured false-positive failure mode: a pure evidence-bookkeeping commit between QA validation and the current head no longer forces a rebind cycle, at both call sites.
- Closes the round-1 debate's most severe finding structurally: a caller cannot construct a call that skips staleness checking, because `head` is required.
- `complete_session_log.py`'s QA-evidence check gains the same staleness precision `validate_session_json.py` already has (and now has correctly, on all paths).

### Negative

- Catch-up merges from `main` still force a rebind: `post_qa_code_changes` walks `git log -m`, which correctly (per the round-1 security review's verification, including an evil-merge test) diffs a merge against both parents, so any real change `main` picked up since the QA commit appears in the range regardless of whether the branch's own authored diff changed. This is an accepted, unfixed residual, not a defect introduced by this ADR; it is the correct security-preserving behavior (over-reporting rather than under-reporting), traded against continued churn on this specific pattern.
- A rebase that orphans the recorded `qaCommit` still forces a rebind, now with a less specific error (`post_qa_code_changes` raises "QA commit is not an ancestor of validation head," naming neither SHA, versus today's message which names both). This is a diagnosability regression on an already-unfixed case, not a new failure.
- `session_qa_binding()`'s own equality raise, the function PR #4954 round 15 actually identified, is untouched; the specific rebind chain round 15 documents is not fully resolved by this ADR (see "Explicitly out of scope").
- `QA_EVIDENCE_PREFIXES`'s boundary is inherited without re-examination: it classifies some agent-instruction prose (session-log handoffs, the episode store) as evidence-only, disagrees with a second, independently-maintained bookkeeping-path list in `scripts/validation/git_hook_policy.py`, and is not resolved through `artifact_dir`'s `AI_AGENTS_ARTIFACT_ROOT` override, so an override desyncs the allowlist from the actual QA-artifact location. None of these were observed to be reachable in the sampled history, but none are examined or fixed by this ADR; both should be filed as a separate follow-up issue given the memory-poisoning-adjacent risk on the instruction-prose paths.

### Neutral

- No change to `load_qa_report()`'s frontmatter contract.
- `QaBinding.commit`'s role changes from "the value compared for equality" to "the default `head` value passed by callers"; the field itself is unchanged.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.claude/lib/qa_report.py` `validate_qa_report()` | Direct | Add required `head: str` and `repo_root: Path` keyword-only parameters; fold in the `post_qa_code_changes` call; drop the `report.commit != expected.commit` raise; add `timeout=10` to both `subprocess.run` calls inside `post_qa_code_changes` (matching `_resolve_full_commit`'s existing pattern, currently missing) | Medium |
| `scripts/validate_session_json.py` `validate_qa_report_evidence()` | Direct | Pass `head=validation_head if validation_head is not None else binding.commit`; remove the now-redundant separate `post_qa_code_changes` call (folded into `validate_qa_report`); add the `--existing-log`-with-real-change test named in Acceptance Criteria | Medium |
| `.claude/skills/session-end/scripts/complete_session_log.py` `_qa_report_evidence()` / `main()` | Direct | Pass `head=binding.commit` (no new git call; `ending_commit` is already in scope at line 815/891); update the four tests exercising this path with a git fixture or mocked `subprocess.run` | Medium |
| `src/copilot-cli/lib/qa_report.py`, `src/copilot-cli/skills/session-end/scripts/complete_session_log.py` and their test mirrors | Direct (mirror) | Byte-identical mirror via `scripts/sync_plugin_lib.py` then `build/scripts/build_all.py` | Low |
| `tests/test_validate_session_json.py::test_rejects_qa_report_for_stale_commit` | Direct | Replace with a test asserting the new code-change-aware behavior for the same scenario (equality-mismatch-but-not-stale now passes; real staleness still fails) | Medium |
| `.claude/skills/session-end/tests/test_complete_session_log.py` (4 tests, ~lines 255-325) | Direct | Add a git fixture or mock `subprocess.run`, since these tests currently run against a non-git `tmp_path` and would newly fail for an unrelated reason (git subprocess failure, not the behavior under test) | Medium |
| `session_qa_binding()` and its own equality raise | Explicitly out of scope | None in this ADR; file a follow-up issue citing PR #4954 round 15 directly | Low (deferred) |
| `QA_EVIDENCE_PREFIXES` boundary (instruction-prose coverage, self-referential `.agents/qa/`, `AI_AGENTS_ARTIFACT_ROOT` desync) | Explicitly out of scope | None in this ADR; file a follow-up issue given the memory-poisoning-adjacent risk on instruction-prose paths | Low (deferred) |

## Implementation Notes

1. Change `validate_qa_report()`'s signature to `(path: Path, expected: QaBinding, *, head: str, repo_root: Path) -> QaReport`, folding the `post_qa_code_changes` call in as described in Decision. Add `timeout=10` to both `subprocess.run` calls inside `post_qa_code_changes`.
2. Update `validate_qa_report_evidence()` in `scripts/validate_session_json.py` to compute `head = validation_head if validation_head is not None else binding.commit` and pass it, removing the now-redundant standalone `post_qa_code_changes` call this function used to make itself.
3. Update `complete_session_log.py`'s QA-evidence path to pass `head=binding.commit` (already in scope via `ending_commit`, no new git call).
4. Tests per Acceptance Criteria above, including the replacement for the now-deleted equality-raise test and fixtures for the four `complete_session_log.py` tests that will newly reach a git subprocess.
5. Mirror to `src/copilot-cli/` via the standard sync-then-build pipeline.
6. Grep for any other caller of `validate_qa_report()` before merging; this ADR's review confirmed exactly two production callers plus their two mirror copies, but re-verify against the branch's actual diff at merge time.
7. Run the modified gate against the full corpus of committed `.agents/sessions/*.json` and QA reports and quote the output in the PR, per `.claude/rules/ci-scripts.md` MUST-13, since `complete_session_log.py` gains a staleness gate it did not have before.

## Related Decisions

- Issue #5164: the shovel-ready issue this ADR resolves.
- Issue #5080, #5064: the original rebind-churn complaints that motivated building `post_qa_code_changes` in the first place.
- Issue #2840, PR #4954 (round 15): identified `session_qa_binding()`'s equality (not `validate_qa_report()`'s) as needing relaxation; explicitly out of scope here, tracked as a follow-up.
- PR #5125 (`ca7fcd46f`), PR #5135 (`e6c196d03`): retired the *mandatory* QA-evidence gates; this ADR fixes the *validate-if-present* path both left brittle, including a fail-open gap round 1 review found that a naive reorder would not have closed.

## References

- `.claude/lib/qa_report.py`. `validate_qa_report`, `session_qa_binding`, `post_qa_code_changes`, `QA_EVIDENCE_PREFIXES`.
- `scripts/validate_session_json.py:930-992`. `validate_qa_report_evidence`, the first call site.
- `.claude/skills/session-end/scripts/complete_session_log.py:526-547,884-901`. `_qa_report_evidence` and its caller, the second call site.
- `.claude/rules/ci-scripts.md` MUST-NOT-2, MUST-13. Validator-behavior-change ADR requirement; corpus-demonstration requirement for a newly-introduced gate.
- `.agents/sessions/handoffs/2026-08-15-2840-handoff.md`. The 23-mention, 15-round rebind evidence, and the round-15 citation this ADR corrects.
- `.agents/critique/ADR-096-debate-log.md`. Round 1 debate log.

## Priority note

The originating issue #5164 carries `priority:P2`. The round-1 high-level-advisor review recommended re-scoring to P1, citing continued QA-report traffic on the opt-in path in the days immediately following the #5125/#5135 retirement (this session independently hit the trap once, three days after). This ADR does not change the issue's label; that is an issue-tracker action for the repo owner, noted here so it is not lost.
