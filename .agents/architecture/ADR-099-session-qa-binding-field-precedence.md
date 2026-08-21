---
id: ADR-099
status: accepted
date: 2026-08-21
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-099: Replace session_qa_binding()'s Field-Equality Raise with Documented Precedence and a Diagnostic

## Status

Accepted. Requested by issue #5217 (labels `enhancement`, `priority:P2`, `area-validation`), filed as the follow-up ADR-096 named in its "Explicitly out of scope" section and in PR #5167's Reviewer Expectations. Per `.claude/rules/ci-scripts.md` MUST-NOT-2, code lands only after this frontmatter `status` reaches `accepted`, in the same change as the status transition. That gating rule is the one ADR-096 asserted and failed to satisfy on its own first two PR heads (ADR-096 Status paragraph, and `.agents/critique/ADR-096-debate-log.md` Round 3), so it is satisfied here rather than deferred.

**Read the review-conduct disclosure before relying on this status.** Round 1 applied all six `adr-review` lenses (architect, critic, independent-thinker, security, analyst, high-level-advisor) and resolved seven findings, two of which changed the argument rather than the prose. It did **not** run six independent agents: the harness serving that session registers no subagent-spawn tool. This is a single-reviewer review, disclosed in full at the top of `.agents/critique/ADR-099-debate-log.md`, and the multi-agent bar the protocol exists to clear is not met. Re-running `adr-review` on a harness with subagent tooling is recommended before treating that bar as cleared.

## Date

2026-08-21

## Context

`session_qa_binding()` (`.claude/lib/qa_report.py:142-182`) turns a session log into the `QaBinding` that QA-report validation is checked against. Lines 170-178 read verbatim:

```python
    if isinstance(comparison_head, str) and _FULL_COMMIT_PATTERN.fullmatch(
        comparison_head
    ):
        if resolved_ending is not None and comparison_head != resolved_ending:
            raise ValueError(
                "Session log comparison head and endingCommit resolve to "
                "different commits"
            )
        return QaBinding(session_log=session_log, commit=comparison_head)
```

The raise fires whenever a session log's `episodeMetrics.comparison.head` and its resolved `endingCommit` are both full 40-character SHAs and differ. It is a plain field-equality check with no fallback, the same shape `validate_qa_report()` (`:185`) carried before ADR-096 replaced it with a code-change-aware check.

### The two fields are documented to diverge, by this repository's own schema

This is the finding that decides the ADR, and it is not the framing the issue anticipated.

`.agents/schemas/session-log.schema.json:170-174` defines a sibling field whose entire reason for existing is the divergence the raise rejects:

```json
        "commitHead": {
          "type": "string",
          "pattern": "^[0-9a-f]{7,40}$",
          "description": "Latest commit authored by this session when QA rebinding advances comparison.head"
        },
```

The episode extractor consumes it with the same understanding (`.claude/skills/memory/scripts/extract_session_episode.py:831-832`):

```python
    # commitHead separates episode ownership from a later comparison.head used
    # to bind QA evidence after another session changed the branch.
```

So the committed schema and the extractor both state that QA rebinding advances `comparison.head` past the session's own last authored commit, and that `commitHead` was added to preserve episode ownership when it does. `endingCommit` moves on a different schedule and for different reasons: `.claude/rules/session-logs.md` MUST 2 requires it to be recorded in a follow-up commit rather than an amend (issue #3618), and MUST 3 requires it to be re-pointed after any rebase. Two fields, advanced by two unrelated operations at two different times, are then compared for equality and the log is rejected when they differ.

The raise therefore does not detect a corrupt log. It detects the state the schema was extended to accommodate.

### What the binding commit is still used for after ADR-096

ADR-096 shrank the blast radius of this choice, which the issue's suggested direction does not account for. `QaBinding.commit` now has exactly two consumers, and one of them ignores it:

- `validate_qa_report()` (`:185-209`) reads `expected.session_log` and nothing else. `expected.commit` is not referenced anywhere in the function body. The commit ADR-096 checks staleness against is `report.commit`, read from the QA report's own frontmatter.
- `scripts/validate_session_json.py:983` uses it only as a fallback head: `head = validation_head if validation_head is not None else binding.commit`. On the only path that reaches this code, `validation_head` was already auto-resolved to live `HEAD` at `:1641-1642` (`if not existing_log and not args.creation_mode and validation_head is None: validation_head = _resolve_full_commit("HEAD")`), so the fallback fires only when that `git rev-parse` itself fails.

The equality raise, in other words, blocks the whole QA-evidence check in order to protect a value that is normally never read.

### The check is also the only thing touching `comparison.head`, and it is not a control

`endingCommit` carries an independent, real check: `scripts/validate_session_json.py:696-706` calls `commit_reachability_problem()` and reports an error when the recorded SHA is unreachable. Nothing equivalent exists for `comparison.head`; the schema pattern is its only other validation.

That asymmetry is what makes the equality raise look like a control and behave like a false-positive generator. It cannot say which field is wrong, only that two fields disagree, and both fields live in the same self-attested file authored by the same actor the check judges. ADR-096 recorded the same trust model for the QA report itself ("the report is plain text in the working tree, authored by the same actor the check judges, with no signature or independent proof a QA run occurred"). It applies more strongly here: an actor who wanted to defeat this check would edit the second field.

### Measured incidence

Measured against `git ls-tree -r HEAD .agents/sessions/` at `9e1ebd2b8b2de2ef1887001631fa7dfbfa10de39`:

| Population | Count |
|---|---|
| Committed session logs examined | 1458 |
| No full-SHA `comparison.head` (raise unreachable) | 1417 |
| Both fields full SHAs (raise reachable) | 35 |
| Both fields full SHAs and equal | 34 |
| Both fields full SHAs and unequal | 1 |

The single disagreeing log is `.agents/sessions/2026-08-06-session-10003-review-pending-checkout-changes-update.json`, carrying `comparison.head` `609b314e5a6ed63332fa193f4644683067740590` against `endingCommit` `bb30860ac61d4b62654653b0f6b67658d9594653`. Reproduce with the query above rather than trusting the table.

State plainly what this does and does not establish. That log's `protocolCompliance.sessionEnd.qaValidation` is `null`, and `validate_qa_report_evidence()` returns at `:937-938` when `qaValidation` is not a dict, so `session_qa_binding()` is never called for it and it does not fail today. The corpus proves the drift shape exists in committed data and that the check engages on 35 of 1458 logs. It does not prove a committed log is currently blocked. The live cost is the interactive one the issue documents: `.agents/sessions/handoffs/2026-08-15-2840-handoff.md` carries 23 occurrences of "rebind" across 15 review rounds on PR #4954 (reproduce with `grep -ci rebind` against the tracked file), and round 15 names this function as the fix that would close that chain. A 2026-08-21 session on branch `claude/qa-gate-pr-feedback-miammt` traced the still-live pattern to this same raise after finding ADR-096's merged fix landed on the other function.

The corpus also undercounts by construction, and the mechanism matters more than the number. The rebind churn is the act of editing a disagreeing log back into agreement before it is committed. Every round of that loop that succeeded left an agreeing log in the tree, so the 34 agreeing logs include an unknown number that reached agreement by paying the cost this ADR removes. A count of committed disagreements can only see the loops nobody bothered to close. Treat the 1 as a floor on incidence, not an estimate of it, and treat the handoff's 23 mentions as the measurement of what the loop costs when it runs.

Neither SHA in that log resolves, and the reason is not clone depth. This tree was a 50-commit shallow clone during the ADR's drafting, which is the limit ADR-096's review recorded. After `git fetch --unshallow origin` (2613 commits), `git log -1` on both `609b314e5a...` and `bb30860ac6...` still reports `fatal: bad object`. They are orphaned, which this repository expects: `scripts/validate_session_json.py:697-703` names squash merge as the most likely cause of an unreachable recorded SHA, because it orphans every branch SHA a session log records.

That sharpens the argument rather than weakening it. In the one committed log where the two fields disagree, neither field names a commit that exists. No ancestry or ordering claim is possible about them, so the equality check could not have adjudicated which field was right even in principle. It could only report that they differ, which is what this ADR makes it do.

### What ADR-096 already settled, and what it left

ADR-096 replaced `validate_qa_report()`'s equality raise with `post_qa_code_changes()`, which walks the commits between two SHAs, filters `QA_EVIDENCE_PREFIXES` (`.claude/lib/qa_report.py:21-25`), and returns only non-evidence paths. That fix is merged (`46049e1`, PR #5167) and is not revisited here. ADR-096 scoped this function out for two stated reasons: the invariant is different in kind, and its 50-commit sample did not observe this check firing. The first reason is upheld by this ADR and drives the design away from a mechanical copy. The second is now answered by the corpus measurement above.

## Decision

Delete the equality raise. Keep `comparison.head`'s existing precedence. Convert the disagreement from a hard failure into a non-blocking diagnostic carried on the returned binding.

`QaBinding` gains one optional field:

```python
@dataclass(frozen=True, slots=True)
class QaBinding:
    """Session and commit identity that QA evidence must match."""

    session_log: str
    commit: str
    inconsistency: str | None = None
```

`session_qa_binding()`'s selection block becomes:

```python
    if isinstance(comparison_head, str) and _FULL_COMMIT_PATTERN.fullmatch(
        comparison_head
    ):
        # comparison.head wins when both fields resolve. The two are advanced
        # by unrelated operations, so a disagreement is expected rather than
        # corrupt: QA rebinding advances comparison.head past the session's
        # own last authored commit (session-log.schema.json's commitHead
        # field exists to record ownership when it does), while endingCommit
        # advances on the follow-up commit and is re-pointed after a rebase
        # (.claude/rules/session-logs.md MUST 2 and MUST 3). Report the drift,
        # do not reject the log (issue #5217, ADR-099).
        inconsistency = None
        if resolved_ending is not None and comparison_head != resolved_ending:
            inconsistency = (
                "Session log comparison head and endingCommit resolve to "
                f"different commits ({comparison_head} != {resolved_ending}); "
                "binding QA evidence to comparison head"
            )
        return QaBinding(
            session_log=session_log,
            commit=comparison_head,
            inconsistency=inconsistency,
        )
```

`scripts/validate_session_json.py`'s `validate_qa_report_evidence()` surfaces it as a warning after the binding is computed and before the report is validated:

```python
        if binding.inconsistency is not None:
            result.warnings.append(binding.inconsistency)
```

The warning is non-blocking by construction, not by convention. `scripts/validation/models.py:20-21` documents the invariant on `ValidationResult`: "The is_valid property is derived from the errors list. A result with no errors is valid. Warnings do not affect validity." `main()` returns `0 if result.is_valid else 1` (`scripts/validate_session_json.py:1673`), so a log that previously failed this check now exits 0 with the observation printed.

Both SHAs interpolated into the message have already passed `_FULL_COMMIT_PATTERN.fullmatch` (`comparison_head` at `:170-172`, `resolved_ending` on both assignment paths at `:158-159` and `:167-168`), so the message cannot carry unvalidated session-log content.

Nothing else changes. `validate_qa_report()`, `post_qa_code_changes()`, `QA_EVIDENCE_PREFIXES`, and the staleness contract ADR-096 established are untouched.

### Why precedence, not a code-change-aware check

The issue suggests reusing `post_qa_code_changes()` here the way ADR-096 did. Three facts argue against it, and they are the analysis the issue asked for rather than a preference.

1. **It answers a question that is already answered downstream, and answers it about the wrong pair.** `post_qa_code_changes()` decides whether real code changed between a QA-validated commit and a head. `validate_qa_report()` already runs exactly that check, on `report.commit` against the live head, one call later. Running it a second time inside `session_qa_binding()` on a different pair (`comparison_head` against `resolved_ending`, two session-log fields, neither of which is the QA report's own commit) spends two more git subprocesses to decide which of two values to pass as a fallback that normally goes unread.

2. **It puts process I/O into a function that has none.** `session_qa_binding()` takes a `Mapping` and an optional `resolve_commit` callable and touches no filesystem and no subprocess. It has no `repo_root`. Reaching `post_qa_code_changes()` means threading a `repo_root` through the signature and through every one of its eight test call sites, so that a pure mapping-to-value function acquires a git dependency and two new failure modes.

3. **It inherits residuals ADR-096 accepted for a case where they were worth accepting.** `post_qa_code_changes()` raises "QA commit is not an ancestor of validation head" when the two SHAs are unrelated, naming neither. Two session-log fields advanced by unrelated operations across a rebase are exactly the pair most likely to be unrelated. The relaxation would then convert a specific error that names both SHAs into a generic one that names neither, which ADR-096 already recorded as a diagnosability regression (its Negative consequence 2) on a case it could not avoid. Here it is avoidable.

### Why the diagnostic, not a bare deletion

Deleting the raise and returning silently is the smaller diff and is rejected. `.claude/rules/ci-scripts.md` SHOULD 4 treats a repair to a silent failure as itself a silent-failure candidate, and a relaxation that removes the only signal on `comparison.head` is that shape. The warning keeps the observation the raise was making, in the one place that has a channel for it, while removing the blocking verdict the observation does not support. `result.warnings` is the established non-blocking channel in this file; `:669-673` already uses it for the adjacent `changesCommitted` and `endingCommit` case.

### The drift can run either way, and the laxer direction fails closed

The strongest objection to keeping `comparison.head` is that the drift is not always in the direction the schema describes. Two directions exist. QA rebinding advances `comparison.head` past the session's own last authored commit, which is the case `commitHead` was added for. But `.claude/rules/session-logs.md` MUST 2 and MUST 3 advance `endingCommit` on a separate schedule, so a log whose episode was extracted before the follow-up commit carries an `endingCommit` newer than `comparison.head`. Selecting `comparison.head` there selects the older SHA, and an older head means a shorter staleness range, which is the laxer choice.

That case cannot fail open. When `binding.commit` is used as the head, `post_qa_code_changes()` first runs `git merge-base --is-ancestor report.commit head` (`.claude/lib/qa_report.py:230-242`) and raises "QA commit is not an ancestor of validation head" on return code 1. A QA report validated at a commit later than the selected head is exactly the non-ancestor case, so the shorter range is rejected rather than silently accepted. The laxness is bounded to reports whose commit is genuinely an ancestor of the older field, where the range really does contain no later work.

### Why `comparison.head` keeps precedence

Preferring `endingCommit` was considered and rejected. `comparison.head` is the field the rebind workflow advances *for the purpose of binding QA evidence*, which the schema states in the `commitHead` description quoted above. It is also the current behavior on every agreeing log, so keeping it means the 34 agreeing logs and the 1417 logs with no full `comparison.head` see byte-identical behavior, and the only observable change in the whole corpus is on the disagreement case the ADR exists to fix.

### Acceptance criteria

- A session log whose `comparison.head` and resolved `endingCommit` are both full SHAs and disagree returns `QaBinding(commit=comparison_head, ...)` instead of raising, and its `inconsistency` field names both SHAs.
- The same log, validated through `validate_qa_report_evidence()`, produces a warning naming both SHAs and no error attributable to the disagreement.
- A session log whose two fields agree returns a binding with `inconsistency is None`, unchanged from today.
- A session log that resolves no full 40-character commit still raises `"Session log must resolve a full 40-character QA commit"`, unchanged (`:182`).
- A session log with an unresolvable abbreviated `endingCommit` and no `comparison.head` still raises, unchanged.
- `validate_qa_report()`'s staleness behavior is unchanged: a real non-evidence change between `report.commit` and the head still hard-fails, and an evidence-only range still passes. The existing tests for both are expected to pass without edit.
- `tests/test_validate_session_json.py::test_rejects_qa_commit_disagreement` (`:283-291`) pins the raise this ADR deletes. It is replaced, not supplemented, by a test asserting the new binding and diagnostic for the same input.
- `src/copilot-cli/lib/qa_report.py` is regenerated byte-identical via `uv run python build/scripts/build_all.py` and never hand-edited.

## Prior Art Investigation

### What Currently Exists

- **Structure being changed**: the equality raise at `.claude/lib/qa_report.py:173-177`, inside `session_qa_binding()` (`:142-182`), mirrored byte-identical at `src/copilot-cli/lib/qa_report.py:142-182` (verified with `diff -q`, which reports the two files identical).
- **When introduced**: `226bef0e4`, 2026-08-08, PR #4735, "fix(memory): replace #4707 duplicate path validator". That commit is the file's only `--diff-filter=A` entry and the only commit `git log -S "comparison head and endingCommit resolve to"` returns, so `.claude/lib/qa_report.py` arrived whole at 252 lines with this check already in it. Determined after `git fetch --unshallow` (2613 commits); an earlier draft recorded this as undeterminable from the 50-commit shallow clone.
- **Original author and context**: the check guarantees that a session log cannot bind QA evidence to a commit while a second field in the same log names a different one. It is a data-consistency check on the log, not on the QA verdict, which is why ADR-096 declined to fold it in. Worth noting what the introducing PR was about: a duplicate path validator for the memory subsystem. The QA-binding module was written as supporting work inside it, which is consistent with the equality check never having had a design pass of its own.

### Historical Rationale

- **Why was it built this way?** Field equality is the cheapest possible consistency check when two fields are believed to be redundant descriptions of one commit.
- **What alternatives were considered?** None recorded at introduction, and the introducing commit supports that rather than merely asserting it: `226bef0e4` added all 252 lines of the module in one move, inside a PR about a duplicate path validator. ADR-096 later built `post_qa_code_changes()` for the neighbouring function and explicitly declined to apply it here.
- **What constraints drove the design?** The belief that the two fields are redundant. `commitHead` (`session-log.schema.json:170-174`) is the evidence that belief was later abandoned in the schema without the check being revisited.

### Why Change Now

- **Has the original problem changed?** Yes. The schema now documents `comparison.head` advancing independently, and names the field added to accommodate it. The check contradicts the data model it validates.
- **Is there a better solution now?** Yes, and it is smaller than ADR-096's. The binding commit's only remaining consumer is a rarely-taken fallback head, so a documented precedence plus a warning covers what the raise was reaching for, with no new I/O.
- **What are the risks of change?** A genuinely corrupt log now warns instead of failing. Bounded by three things: `endingCommit` keeps its independent reachability check (`validate_session_json.py:696-706`); the schema pattern still constrains both fields; and `post_qa_code_changes()` still fails closed on ancestry whenever `binding.commit` is used as a head. The corpus above bounds the exposure at 35 of 1458 logs where the check engages at all.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Status quo (keep the raise) | Zero change; the check reads like a control | Rejects the state `session-log.schema.json:170-174` documents as normal; blocks the whole QA-evidence check to protect a value normally never read; the churn in the 23-mention, 15-round chain on PR #4954 is the measured cost | The check contradicts the schema it validates, and the issue was filed to remove it |
| Mechanically reuse `post_qa_code_changes()`, as ADR-096 did (the issue's suggested direction) | Consistent with the sibling function; reuses tested code; would tolerate evidence-only drift | Adds two git subprocesses and a `repo_root` parameter to a function that touches no process today; re-answers a staleness question `validate_qa_report()` already answers one call later, about a different pair of commits; inherits the unrelated-SHA ancestry raise that names neither commit, on the pair most likely to be unrelated | Answers the wrong question at the wrong layer for a value that is a fallback; the issue explicitly offered this as a suggestion to be justified, and it does not survive the justification |
| Prefer `endingCommit` over `comparison.head` on disagreement | `endingCommit` has an independent reachability check, so the chosen SHA would be verified | Contradicts the schema's stated purpose for `comparison.head` during rebinding; changes which SHA is selected on a case where today's code selects the other; no corpus evidence that `endingCommit` is the more accurate field | Reverses the documented intent of the rebind workflow to gain a check that applies to a fallback value |
| Delete the raise with no diagnostic | Smallest possible diff | Removes the only signal on `comparison.head` and leaves nothing in its place; this is the silent-relaxation shape `.claude/rules/ci-scripts.md` SHOULD 4 names | Keeps the false positive's cost while discarding its one true observation |
| Widen the schema to forbid `endingCommit` when `comparison.head` is present | Removes the ambiguity at the source | Breaks 34 agreeing logs and every producer that writes both; a schema change is a larger blast radius than the validator change it would justify | Disproportionate to a check that engages on 35 of 1458 logs |
| **Documented precedence plus a warning on the binding (chosen)** | Removes the false positive; keeps the observation; no new I/O, no new parameter on the function; identical behavior on 1451 of 1458 committed logs | Adds a field to a value object for a diagnostic; a genuinely inconsistent log now warns rather than fails | Matches the invariant's real strength: two self-attested fields disagreeing is worth reporting and is not worth rejecting a log over |

### Trade-offs

The design trades a hard verdict for an accurate one. The raise asserted that a disagreement means the log is wrong; the schema says a disagreement means a rebind happened. Downgrading to a warning gives up the ability to block on that state, which was never a state worth blocking on, and buys back the 35-log surface where the check engages plus the interactive rebind churn the issue documents. The one real cost is that a log corrupted by a hand-edit into disagreement now proceeds with a warning. That cost is bounded by `endingCommit` keeping its own reachability check and by `post_qa_code_changes()` failing closed on ancestry when the selected commit is used as a head.

## Consequences

### Positive

- Removes a hard failure on a state the committed schema documents as expected, which is the churn source PR #4954 round 15 identified.
- Adds no git subprocess calls; `session_qa_binding()` stays a pure mapping-to-value function with no `repo_root`.
- Keeps the disagreement visible. The reader gets both SHAs and the selection made, which the previous message did not include.
- Byte-identical behavior on 1451 of the 1458 committed session logs (1417 where the raise is unreachable plus 34 where the fields agree).

### Negative

- A session log made inconsistent by a hand-edit or a broken producer is no longer rejected. It warns and binds to `comparison.head`.
- `QaBinding` grows a field that exists only to carry a diagnostic, which mixes an observation about provenance into a value object describing identity.
- The warning only appears on the fresh-validation path, since `validate_session_log()` gates the whole QA-evidence block behind `not existing_log and not creation_mode` (`scripts/validate_session_json.py:1169,1178`). A committed log validated with `--existing-log` never reaches the function and never emits it. This matches ADR-096's scope and is not widened here.
- An abbreviated `comparison.head` stays invisible to this function. The schema allows 7 to 40 characters (`session-log.schema.json` `comparison.head` pattern `^[0-9a-f]{7,40}$`), but `:170-172` tests `_FULL_COMMIT_PATTERN` and falls through to `endingCommit` on anything shorter, with no attempt to resolve it through the `resolve_commit` callable the way `endingCommit` gets at `:160-168`. That asymmetry predates this ADR and is not changed by it. It is named here because the corpus figure above depends on it: 1417 of 1458 logs are counted as "raise unreachable" partly for this reason.
- The residuals ADR-096 recorded and left open are untouched: `post_qa_code_changes()` still reports every path a catch-up merge picked up, and the `QA_EVIDENCE_PREFIXES` boundary gaps (instruction-prose coverage, the self-referential `.agents/qa/` entry, `AI_AGENTS_ARTIFACT_ROOT` desync) remain a separate follow-up.

### Neutral

- No change to `load_qa_report()`, `validate_qa_report()`, `post_qa_code_changes()`, `non_evidence_paths()`, or `QA_EVIDENCE_PREFIXES`.
- No schema change. `commitHead` is cited as evidence for the decision and is not read by this code.
- The selected commit on an agreeing log is unchanged, so no committed QA report needs rebinding as a result of this change.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.claude/lib/qa_report.py` `QaBinding` (`:28-34`) | Direct | Add `inconsistency: str \| None = None` as the last field, so existing two-argument construction is unaffected | Low |
| `.claude/lib/qa_report.py` `session_qa_binding()` (`:142-182`) | Direct | Replace the raise at `:173-177` with the diagnostic; precedence and both other raises unchanged | Medium |
| `scripts/validate_session_json.py` `validate_qa_report_evidence()` (`:960-986`) | Direct (only production caller) | Append `binding.inconsistency` to `result.warnings` when set | Low |
| `src/copilot-cli/lib/qa_report.py` | Direct (generated mirror) | Regenerate with `uv run python build/scripts/build_all.py`; never hand-edited. The generator is `_build_lib` (`build/scripts/build_all.py:316-335`), which copies the whole of `.claude/lib/` to the platform's lib output. `scripts/sync_plugin_lib.py` is not involved: neither `SYNC_PAIRS` (`:27-31`) nor `SYNC_FILE_PAIRS` (`:41-47`) names `qa_report.py` | Low |
| `tests/test_validate_session_json.py::test_rejects_qa_commit_disagreement` (`:283-291`) | Direct | Replace with a test asserting the binding and the diagnostic for the same input | Medium |
| `tests/test_validate_session_json.py`, other seven `session_qa_binding` call sites (`:262, 275, 301, 313, 322, 330`) | Direct | No change. Equality against a two-field `QaBinding` still holds because `inconsistency` defaults to `None` | Low |
| `.claude/skills/session-end/scripts/complete_session_log.py` | None | Does not exist. ADR-096 named it as a second caller on 2026-08-19; `find . -name complete_session_log.py` returns nothing at `9e1ebd2b8`, and `.claude/skills/session-end/` is absent. Re-verify at merge time | Low |
| `.agents/schemas/session-log.schema.json` | Cited only | None. `commitHead` is evidence for this decision, not a subject of it | Low |

## Implementation Notes

1. Add `inconsistency: str | None = None` to `QaBinding` as the final field, and extend its docstring so the class no longer claims to describe identity alone. The field carries an observation about how that identity was selected, and a reader who finds it undocumented will reasonably assume it is part of the identity contract.
2. Replace `.claude/lib/qa_report.py:173-177` per the Decision section. Leave the `resolved_ending` fallback at `:179-180` and the terminal raise at `:182` as they are.
3. Append the diagnostic to `result.warnings` in `validate_qa_report_evidence()`, between the `session_qa_binding()` call and the `validate_qa_report()` call, so a disagreement is reported even when the report validation later fails for an unrelated reason.
4. Replace `test_rejects_qa_commit_disagreement`. Add positive, negative, and edge cases per `.agents/governance/TESTING-RIGOR.md`: fields disagree (binds to `comparison.head`, diagnostic set); fields agree (diagnostic `None`); `comparison.head` present and `endingCommit` absent (diagnostic `None`, existing precedence); abbreviated `endingCommit` resolving to a value that disagrees with `comparison.head` (diagnostic set, exercising the resolver path at `:160-168`); and a wiring test driving `validate_qa_report_evidence()` end to end so the warning is proven to reach `result.warnings` rather than only to be produced (`.claude/rules/testing.md` SHOULD 6).
5. Regenerate the mirror with `uv run python build/scripts/build_all.py` and confirm `diff -q` reports the two `qa_report.py` copies identical.
6. Re-run the corpus query from Context against the branch head and quote the result in the PR. `.claude/rules/ci-scripts.md` MUST 13 governs a PR that introduces a gate; this PR removes one, so the corpus figure is offered as the blast-radius measurement rather than as MUST-13 compliance.
7. Grep for `session_qa_binding` and `QaBinding(` before merging and re-verify the caller inventory in the Impact table against the branch's actual diff.

## Related Decisions

- ADR-096. Relaxed `validate_qa_report()`'s equality to a code-change-aware check and scoped this function out; this ADR is the follow-up it named.
- Issue #5217. The issue this ADR resolves.
- Issue #2840, PR #4954 round 15. Identified this function's equality as the fix that would close a 15-round rebind chain.
- Issue #5164, PR #5167. ADR-096's issue and implementing PR, whose Reviewer Expectations named this follow-up.
- ADR-034. QA skip semantics, which decide when the QA-evidence block runs at all.

## References

- `.claude/lib/qa_report.py:142-182`. `session_qa_binding` and the raise at `:173-177`.
- `.claude/lib/qa_report.py:185-209`. `validate_qa_report`, which reads `expected.session_log` and not `expected.commit`.
- `scripts/validate_session_json.py:960-986`. `validate_qa_report_evidence`, the only production caller.
- `scripts/validate_session_json.py:1641-1642`. Live-`HEAD` resolution that makes `binding.commit` a fallback rather than the normal head.
- `scripts/validate_session_json.py:696-706`. `endingCommit`'s independent reachability check.
- `.agents/schemas/session-log.schema.json:170-174`. `commitHead`, and its statement that QA rebinding advances `comparison.head`.
- `.claude/skills/memory/scripts/extract_session_episode.py:831-832`. The extractor comment carrying the same understanding.
- `.claude/rules/session-logs.md` MUST 2, MUST 3. Why `endingCommit` moves on a separate schedule.
- `.claude/rules/ci-scripts.md` MUST-NOT-2, SHOULD 4. Validator-change ADR requirement; repairs to silent failures.
- `.agents/critique/ADR-096-debate-log.md`. The review pattern this ADR follows.
- `.agents/sessions/handoffs/2026-08-15-2840-handoff.md`. The 23-mention, 15-round rebind evidence.
