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

Ten adversarial rounds, every one of which falsified something, converged on this sentence. Use it verbatim; it is the most expensive result of the session.

> A consultation-budgeted comparison over a public benchmark, relying on a cooperating optimizer not to inspect accessible task definitions or result files. It is not yet held-out validation of unseen tasks.

Three separate reasons it is not the stronger thing, all verified at source, all recorded in ADR-087:

1. **Outcomes are not withheld.** `cmd_extract` emits the full mapping and has no group argument, and the documented workflow has the optimizer call it. Held-out results are already in the optimizer's own files, uncharged (#3452).
2. **Membership is public and sufficient.** Task ids resolve to readable definitions carrying their own grading criteria: a fixture's expected verdict, a scenario's expected vocabulary, a pytest assertion. Naming a held-out task is enough to hand-tune for it.
3. **The budget bounds gate comparisons, not selection pressure.** `extract` and `score` reach results without touching the ledger, so nothing counts the loop's other reads.

The reflex to resist: "the loop cannot edit toward a group it cannot name" is backwards. An optimizer edits toward `opt` and needs no knowledge of `sel` at all. Only `opt` must be exposed for the discipline to work, which is exactly why exposing `sel` costs nothing to fix and everything to leave. Dwork's reusable holdout (arXiv:1506.02629) assumes the analyst reaches the holdout only through the mechanism; a controller the optimizing agent cannot write to is the missing prerequisite, tracked as ADR-087 Open Requirement 1.

## Gotchas

- Coverage must be `--cov=scripts/eval` (the directory). `--cov=scripts/eval/_optimizer_core` collects nothing because the CLI module name is hyphenated.
- `mcnemar_exact` is reported, never enforced. A single discordant gain yields `p_value: 0.5` and still ACCEPTs, because a three-task held-out group cannot reach 0.05 and enforcing a conventional floor would make the common case unpassable.
- Only `rule_results` is single-shot against an LLM judge; `agent_results` reduces over runs and `pytest_results` is deterministic. Noise arithmetic that treats all three as single-shot overstates spurious rejection (#3445).

## The rule that generalizes past this file

Ten rounds, nine of them the same shape: any part of a budget the caller can restate, or move by renaming something else, is not part of the budget; and any path by which the withheld thing is readable is not withholding it. The last three rounds are the useful ones to remember, because each found a defect inside the previous round's fix:

- Round 8: a pathless `OSError` fell past a redaction branch that was also the branch converting it to a type `main` catches, so it escaped as a traceback.
- Round 9: a redacted message chained the unredacted original with `raise ... from exc`, and `__cause__` is exactly where a printed traceback goes. Separately, cleanup in a `finally` ran after the decision was on stdout, so a failure there printed a second JSON document and overwrote a successful exit code.
- Round 10: the first line of the lock helper, `lock.parent.mkdir(...)`, sat one line above the scrub covering everything below it. A seam is only a seam from its first line.

Two operational lessons worth more than the defect list. First, a workaround that stops a symptom appearing in tests is not a finding closed: the round-9 double-document bug had already been seen while writing round-7 tests and recorded as a test-harness quirk. Second, hand-written redaction sites are where rounds 9 and 10 both found defects, which is why redaction now has one definition, `_scrub`, rather than a `.replace` per site.

Evidence: issue #3422, PR #3430, PR #3458, branch `fix/eval-holdout-gate-digest-leak`, ADR-087, debate log `.agents/analysis/2026-07-26-adr-087-holdout-gate-debate.md`, session log `.agents/sessions/2026-07-26-session-3422-eval-holdout-gate.json`.
