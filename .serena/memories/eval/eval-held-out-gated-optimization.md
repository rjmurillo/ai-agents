# Eval held-out gated optimization

`scripts/eval/optimize-artifact.py` plus `_optimizer_core.py` and `_optimizer_adapters.py` add the one thing the rest of `scripts/eval/` never had: a comparison the party making the edit cannot repeat without a budget. Every other evaluator scores an artifact against its whole eval set while the author reads the failures, so the score stops estimating behavior on unseen cases and starts estimating how well the author answered these cases. The two diverge exactly as the loop gets better.

## The seam

Adapters converge three unlike scorers onto `{task_id: bool}`: `agent_results` from an agent-vs-baseline report, `rule_results` from rule scenario scores, `pytest_results` from JUnit XML. That boolean mapping is what generalizes the discipline past skills. A fixture id, a scenario id, and a pytest node id are the same kind of thing to the decider, so agents, rules, and hooks all reach the same gate. Whether to widen the seam to `{task_id: float}` is open (#3437); both code reviewers and both ADR reviewers argued for it, and it is a redesign rather than a tweak.

## The lesson worth carrying elsewhere

Any part of a budget the caller restates on every invocation is not part of the budget. Three adversarial rounds each fixed the piece under review and left the rest on the command line, where the identical defect reappeared:

1. The count. `--consultations` defaulted to 0 every call, so a loop that passed zero each time had an unlimited budget while looking capped. Review reproduced two ACCEPTs under a cap of one.
2. The cap. `--max-consultations` defaulted to unlimited, so the ordinary invocation had no budget, and a caller that did hit the cap could raise it on the next call.
3. The ledger path. `--ledger PATH` looked like discipline, but a missing ledger starts at zero, so naming a fresh path restored the whole budget without editing anything.
4. The split path the ledger derived from. Deriving the ledger name from the split file's path meant copying the split to a new name reset the budget, with the identical membership inside.
5. The fingerprint. It hashed the split's inputs rather than its drawn result, so it caught an added or removed task but not a task moved between groups. Catching the move needs the redraw comparison as well, and crediting the fingerprint alone was wrong.
6. The digest printed in uncharged error paths, then the digest reachable from *generic* I/O failures. Every ledger filename ends in the digest of the held-out membership, so any error interpolating a path leaked the thing being withheld. Closing it per call site missed lock release, which runs after the decision is already emitted.

What holds now: count and cap are recorded at the first decision in `<split>.ledger`, a later cap change is refused, and the path is derived from the split so resetting means deleting a file. `--incumbent-fingerprint` is required for the same reason; optional integrity checks are integrity checks nobody runs.

## Framing that must not be softened

Twelve adversarial rounds, every one of which falsified something, converged on this sentence. Use it verbatim; it is the most expensive result of the session.

> A consultation-budgeted comparison over a public benchmark, relying on a cooperating optimizer not to inspect accessible task definitions or result files. It is not yet held-out validation of unseen tasks.

Three separate reasons it is not the stronger thing, all verified at source, all recorded in ADR-087:

1. **Outcomes are not withheld.** `cmd_extract` emits the full mapping and has no group argument, and the documented workflow has the optimizer call it. Held-out results are already in the optimizer's own files, uncharged (#3452).
2. **Membership is public and sufficient.** Task ids resolve to readable definitions carrying their own grading criteria: a fixture's expected verdict, a scenario's expected vocabulary, a pytest assertion. Naming a held-out task is enough to hand-tune for it.
3. **The budget bounds gate comparisons, not selection pressure.** `extract` and `score` reach results without touching the ledger, so nothing counts the loop's other reads.

The reflex to resist: "the loop cannot edit toward a group it cannot name" is backwards. An optimizer edits toward `opt` and needs no knowledge of `sel` at all. Only `opt` must be exposed for the discipline to work, which is exactly why exposing `sel` costs nothing to fix and everything to leave. Dwork's reusable holdout (arXiv:1506.02629) assumes the analyst reaches the holdout only through the mechanism; a controller the optimizing agent cannot write to is the missing prerequisite, tracked as ADR-087 Open Requirement 1.

## Gotchas

- Coverage must be `--cov=scripts/eval` (the directory). `--cov=scripts/eval/_optimizer_core` collects nothing because the CLI module name is hyphenated.
- `mcnemar_exact` is reported always and enforced only with `--max-p`, which defaults to absent. A single discordant gain yields `p_value: 0.5` and still ACCEPTs by default, because a three-task held-out group cannot reach 0.05 and enforcing a conventional floor would make the common case unpassable. When supplied, `--max-p` is the FAMILY bar and is Bonferroni-divided by `--max-consultations`: five looks at 0.05 each is a family-wise 0.226, not 0.05. So raising the budget buys more looks at a stricter bar, never a cheaper one. The bar is pinned in the ledger like the cap, absence included, so a candidate refused at 0.05 cannot be re-gated at 0.1.
- Only `rule_results` is single-shot against an LLM judge; `agent_results` reduces over runs and `pytest_results` is deterministic. Noise arithmetic that treats all three as single-shot overstates spurious rejection (#3445).

## The rule that generalizes past this file

Twelve rounds, eleven of them the same shape: any part of a budget the caller can restate, or move by renaming something else, is not part of the budget; and any path by which the withheld thing is readable is not withholding it. The last three rounds are the useful ones to remember, because each found a defect inside the previous round's fix:

- Round 8: a pathless `OSError` fell past a redaction branch that was also the branch converting it to a type `main` catches, so it escaped as a traceback.
- Round 9: a redacted message chained the unredacted original with `raise ... from exc`, and `__cause__` is exactly where a printed traceback goes. Separately, cleanup in a `finally` ran after the decision was on stdout, so a failure there printed a second JSON document and overwrote a successful exit code.
- Round 10: the first line of the lock helper, `lock.parent.mkdir(...)`, sat one line above the scrub covering everything below it. A seam is only a seam from its first line.
- Round 12: `_scrub` learned to fold case in round 11 and the `if holdout_key in text` deciding whether to call it did not, so the exact input the fix was written for skipped the fix. One definition has to cover the predicate, not just the replacement.
- Round 11: moving that `mkdir` inward left `_ledger_root()` as the new first line, and it resolves the home directory, which raises `RuntimeError` when `$HOME` is unset and the uid has no passwd entry. That is an ordinary container running as a numeric user, and it fires on the default configuration. Fixing a boundary by moving one line inward leaves whatever was above that line as the new boundary.

Round 11 is also the first round partly declined: its double-resolution finding reproduced only by mutating `$EVAL_LEDGER_DIR` mid-process, and no in-process environment mutation exists in any of the three modules. Accepting every reported finding is not reviewing either; the decline and its reason are in the debate log so nobody re-litigates it.

Four operational lessons worth more than the defect list. First, a workaround that stops a symptom appearing in tests is not a finding closed: the round-9 double-document bug had already been seen while writing round-7 tests and recorded as a test-harness quirk. Second, hand-written redaction sites are where rounds 9 and 10 both found defects, which is why redaction now has one definition, `_scrub`, rather than a `.replace` per site. Third, when a review is asked to find a defect, give it explicit permission to return ACCEPT and tell it a false finding costs more than a missed one; rounds 10, 11, and 12 all got that instruction and all still returned real findings, which is what makes the streak evidence rather than an artifact of the prompt. Fourth, and this is the one that generalizes furthest: test the property through the seam, not the unit you edited. Round 11 added four passing tests for case folding and every one called `_scrub` directly, so they confirmed the edit while the CLI still printed the digest. A test aimed at the function you just changed will agree with you. Only a test aimed at the property can disagree.

Evidence: issue #3422, PR #3430, PR #3458, branch `fix/eval-holdout-gate-digest-leak`, ADR-087, debate log `.agents/analysis/2026-07-26-adr-087-holdout-gate-debate.md`, session log `.agents/sessions/2026-07-26-session-3422-eval-holdout-gate.json`.

## The live run, and the lesson that outranks the defect list

2026-07-27, first end-to-end live run against a real scorer (24 rule-activation tasks, `gpt-4o-mini` via GitHub Models). The gate returned ACCEPT: held-out 0.6 to 0.8, two gains, zero losses, p=0.25.

It was wrong. A null control, restoring the artifact byte-for-byte and re-running the identical scorer, reproduced both gains from a no-op. The ACCEPT was rejected only because noise also broke a third task and the pre-existing no-regression clause caught it. On a different roll the loop would have accepted a change that did nothing.

Measured on that one paired re-run: 13 of 24 tasks changed score at all on byte-identical input; mean absolute movement 0.49 on a 5-point scale, max 3.00; 5 crossed the 3.5 pass line. The sharpest fact is not the count. The two held-out gains that earned the ACCEPT were the two largest excursions in the whole benchmark, +3.00 and +2.00. The accept rode the two biggest noise events out of 24 tasks. These are counts from one replication, not a rate: 5 of 24 carries a 95% interval of roughly 7% to 42%, so do not quote a percentage.

**Run a null control before believing any ACCEPT from a nondeterministic scorer.** It costs one extra scorer run and it is the only thing that caught this. Two signals made the suspicion actionable before the control finished: the edited artifact's own tasks had not moved, and every flip landed in artifacts the edit could not have touched. If the tasks that move are not the tasks you touched, you are measuring variance.

Two follow-on cautions. The measured variance is the pipeline's, compounding the response model and the judge, both `gpt-4o-mini` at temperature 0; the harness sets no seed and records no `system_fingerprint`, so it cannot separate them (#3475). And `rule_results` maps an errored or judge-failed scenario to `False`, which is right for one run and wrong for a paired one: an error on the incumbent side and a success on the candidate side reads as a discordant gain that is pure infrastructure artifact (#3474).

## Round fourteen, and how to consume an adversarial review

Two non-Claude reviewers in parallel on the `--max-p` change, both REJECT. All four code findings were real, and the load-bearing one was a statistical error I had argued myself into: a per-comparison threshold does not bound a family. Same shape as the eleven rounds above. A bar you can spend five times is not that bar, exactly as a budget you can restate is not a budget.

The ADR reviewer's headline finding was false. It claimed the null-control flips were HTTP 429s recorded as task failures, reasoning from a code path that genuinely exists (`max_retries=0`, no retry loop, errors mapped to `False`). Checking the three live reports directly: zero errored mechanism-runs out of 216, no `FAIL_JUDGE_ERRORS` verdict anywhere. Had it been accepted, the debate log would now carry a false explanation for its central finding and the null control's real lesson would have been buried.

**A finding can be wrong about what happened and right about what can happen.** Verify a confident review against data before acting on it, and when the mechanism is real but did not fire, file it (#3474) rather than folding it in or dismissing it. Accepting every finding is not reviewing, and neither is dismissing the ones that turn out to be misattributed.

Evidence: PR #3478, branch `feat/eval-gate-significance-bar`, commits `684060149` and `a5791784c`, session log `.agents/sessions/2026-07-27-session-3468-eval-gate-significance.json`.
