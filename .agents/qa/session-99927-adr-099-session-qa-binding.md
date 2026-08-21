---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-21-session-99927-9e1ebd2b8-adr-099-session-qa-binding.json
qaCommit: 0dc7d0a254e3aa253b9c9895e008265f06f496d8
---

# ADR-102 Session QA

## Scope

Code change: `.claude/lib/qa_report.py` (`QaBinding` gains `inconsistency`,
`session_qa_binding()` replaces its field-equality raise with the diagnostic),
mirrored byte-identical to `src/copilot-cli/lib/qa_report.py`, and
`scripts/validate_session_json.py` (`validate_qa_report_evidence()` surfaces
the diagnostic into `result.warnings`). Test change:
`tests/test_validate_session_json.py` (`test_rejects_qa_commit_disagreement`
replaced, five new unit cases, two wiring tests: the disagreement-warns
wiring test and the fallback-head-path test added per Implementation Note 8,
see below). Unrelated red-CI fixes
carried on the same branch: `tests/ci/test_validate_vendor_provenance.py`
(stale setup-uv SHA pin) and `.github/workflows/pytest.yml` (pip pin moved
past PYSEC-2026-3721). Everything else on this branch is ADR-102 and its
debate log, both documentation.

## Test Results

| Command | Result |
|---|---|
| `uv run pytest tests/test_validate_session_json.py -q` | 382 passed |
| `uv run pytest -k "qa_report or qa or session_json or session_log" -q` | 568 passed, 27354 deselected |
| `uv run ruff check .claude/lib/qa_report.py scripts/validate_session_json.py tests/test_validate_session_json.py` | clean |
| `diff -q .claude/lib/qa_report.py src/copilot-cli/lib/qa_report.py` | identical |

## Discrimination Probe

Per `.claude/rules/testing.md` SHOULD 10: restored the deleted equality raise
as a mutant over `.claude/lib/qa_report.py`, cleared `__pycache__`, and
re-ran the full `tests/test_validate_session_json.py` suite. The mutant
failed exactly the three tests that assert the new precedence-and-diagnostic
behavior and left the three no-diagnostic control tests green, confirming
the suite actually distinguishes old from new behavior rather than passing
regardless.

## Corpus Blast-Radius Verification

Independently reproduced (not re-derived from the ADR's own numbers) against
`git ls-tree -r HEAD .agents/sessions/`: 1459 logs examined, 1418 with no
full-SHA `comparison.head`, 6 with a full `comparison.head` and a non-full
`endingCommit`, 35 with both fields full SHAs (34 agreeing, 1 disagreeing).
Sums to 1459. Re-running `session_qa_binding` over the corpus under the
implemented behavior: exactly one log's behavior changes, matching the
ADR's pre-implementation prediction.

Separately reproduced the debate's lockstep-history measurement against
`git log --all -- .agents/sessions/`: 50 edits to `comparison.head` across
38 single-parent commits, 44 with `endingCommit` present, 42 agreeing
(SHA-prefix-normalized), split 34 creations (fields born equal, nothing
moved) and 8 modifications (7 genuine hand-syncs, 1 no-op), plus 2 genuine
disagreements, both in commit `f7fc4ef88a5400be1c2102b40c9272c2629f0762`.
All figures match what is now committed in ADR-102 and its debate log.

## Review Process

`.claude/rules/ci-scripts.md` MUST-NOT-2 required an ADR before this code
landed; `.agents/architecture/ADR-102-session-qa-binding-field-precedence.md`
and its debate log (`.agents/critique/ADR-102-debate-log.md`) carry the
full record. The debate ran across three rounds: a disclosed single-reviewer
pass, a genuine six-agent debate (five Accept/Disagree-and-Commit, one
Block on the Context section's central claim), a Phase 2 conflict
resolution that overruled the Block against the Decision and upheld it
against the Context, and a scoped Phase 4 convergence check that caught
and corrected a second overstatement in the rewrite itself. No agent
Blocks the ADR as it now stands.

## Pre-Push Gate Evidence

`uv run python scripts/validation/pre_pr.py` reported `RESULT: All
validations passed` on this commit. The full `lefthook` pre-push suite,
including `python-tests` and `pre-pr-validation`, ran green on this commit
before the follow-up commits that only touch `.agents/sessions/` and
`.agents/qa/` (evidence-only paths per `QA_EVIDENCE_PREFIXES`).

## Post-Merge Rebind

`qaCommit` moved from `5484cc8a2` to `c6d7f388f` (a merge of `origin/main`,
which brought in PR #5219's ADR-096 frontmatter flip and an independent
setup-uv SHA-pin fix in `tests/ci/test_validate_vendor_provenance.py` that
conflicted with this branch's own generic-pattern version of the same fix).
Per `post_qa_code_changes()`'s documented merge-diff behavior (ADR-096
Negative consequence 1), a catch-up merge always reports as a code change
regardless of whether this branch's own diff changed, since `git log -m`
diffs against both parents. The merge conflict was resolved by combining
both fixes (parse the YAML structure per `testing.md` MUST 9, assert a
SHA-pattern rather than one exact SHA to avoid re-introducing the staleness
trap PR #5215 caused). `uv run pytest tests/test_validate_session_json.py -q`
re-run clean at 379 passed on the merge commit.

A second catch-up merge, `06fa514b5`, was required before the push
succeeded: `origin/main` advanced again while the first push was in flight,
landing PR #5225, which applied the exact same pip 26.1.2 to 26.2 bump this
branch had already carried in `.github/workflows/pytest.yml` (for the same
CVE, PYSEC-2026-3721) under a differently worded comment. `merge-tree-ratchet`
(a pre-push job that runs `git merge-tree` against `origin/main` and rejects
a push whose merged result would fail a registered ratchet) caught the
resulting conflict before it ever reached CI. Resolved by keeping
`origin/main`'s comment, which cites issue #5222 and is the version already
merged to main; the pin value itself (`26.2`) was identical on both sides, so
no code changed. `uv run pytest tests/test_validate_session_json.py -q`
re-run clean at 379 passed again on `06fa514b5`, and
`merge_tree_ratchet_check.py --base-ref origin/main` reported OK.

## Fallback-Head-Path Test (Implementation Note 8)

`ai-spec-validation`'s Implementation Completeness pass correctly flagged one
gap: ADR-102 Implementation Note 8 asked for a test pinning the
fallback-head-path exposure named under "The laxer direction is bounded, not
impossible", and no such test existed. Added
`test_fallback_head_masks_a_real_change_between_the_two_fields`: with
`validation_head=None`, `comparison.head` older than `endingCommit`, and
`report.commit` a genuine ancestor of `comparison.head`, the test asserts
both that the report still passes and that the two `git` commands
`post_qa_code_changes()` issues never name `endingCommit`, pinning the gap
described in the ADR rather than leaving it asserted only in prose.
`uv run pytest tests/test_validate_session_json.py -q` re-run clean at 380
passed (the new test plus all 379 prior). `qaCommit` moved to `21a23ec39`,
the commit carrying this test, since it is a real (non-evidence) change
that would otherwise correctly flag this report stale.

## Post-Review Rebind and a Cursor Bugbot Fix

After the PR was marked ready for review, Cursor Bugbot flagged a Medium
finding: this session log's `constraintsRead.Evidence` field attributed to
`session-logs.md` MUST 2 and MUST 3 the claim that `endingCommit` moves
independently of `comparison.head`, but those two MUST items only describe
`endingCommit`'s own update schedule (a follow-up commit, then re-point
after any rebase) and never mention `comparison.head` at all. Verified
against the rule file directly and confirmed the finding; fixed the
wording to describe only what the rule text actually says.

Landing that fix required merging `origin/main` again, which had advanced
by two commits (ADR-100 and ADR-101, both unrelated to this PR). Both new
files live outside `QA_EVIDENCE_PREFIXES`, so `qaCommit` moved again to
`3386b3cc5`, the commit carrying the Bugbot fix on top of the merge.
`merge_tree_ratchet_check.py --base-ref origin/main` reported OK and
`uv run pytest tests/test_validate_session_json.py -q` re-ran clean at 380
passed on this commit.

## Post-Review Rebind: Copilot Findings and a Cursor Bugbot Autofix Merge

Between the previous rebind and this one, two things landed. First, a branch
divergence: Cursor Bugbot's Autofix feature independently pushed its own fix
for the same Medium finding directly to the branch, applying different
wording to the same `constraintsRead.Evidence` field this session had just
fixed. Resolved with `git merge origin/claude/autoplan-ship-wi09a5 --no-edit`
(commit `c348f17a5`), keeping this session's more detailed wording on the
one conflicting line.

Second, GitHub Copilot's automated review of the PR returned eight
comments. One was a confirmed real bug: `QaBinding.inconsistency` was a
plain dataclass field, so the generated `__eq__`/`__hash__` compared and
hashed it along with `session_log` and `commit`, contradicting the class's
own docstring claim that it is "not part of that identity." Fixed with
`field(default=None, compare=False)`; a new test,
`test_inconsistency_is_excluded_from_binding_identity`, pins it (confirmed
to fail with the fix reverted, restored byte-identical afterward). Three
more were confirmed stale-prose survivors of the Phase 4 correction already
recorded above (the 34/8/7 split): the shipped code comment in
`session_qa_binding()`, the mirroring comment in
`scripts/validate_session_json.py`, and the comment on
`test_binds_to_comparison_head_when_commit_fields_disagree`, all still
describing the debate's refuted "42-of-44 lockstep" framing. Two more were
the same drift inside the ADR itself (Measured Incidence, Why Change Now,
Alternatives Considered). One finding was design-level pushback on the
already-debated, already-accepted fallback-head-path trade-off; answered
with a reply rather than a design reversal, per this repo's PR-stewardship
rules for a settled multi-agent-reviewed decision.

`src/copilot-cli/lib/qa_report.py` regenerated byte-identical via
`uv run python build/scripts/build_all.py`.
`uv run --frozen pytest tests/test_validate_session_json.py -q` re-ran clean
at 381 passed (380 plus the new identity test).
`uv run ruff check .claude/lib/qa_report.py scripts/validate_session_json.py tests/test_validate_session_json.py src/copilot-cli/lib/qa_report.py`
reported clean. A post-consensus entry documenting both fix classes was
added to `.agents/critique/ADR-102-debate-log.md` in the same commit as the
ADR prose fixes, since `git_hook_policy.py`'s `adr-review-policy` gate
requires a debate log staged alongside any non-frontmatter ADR change.

`qaCommit` moved from `3386b3cc5` to `9d8a6c287`, the last commit in this
batch that touches a non-evidence path;
`post_qa_code_changes('9d8a6c28755fbd673a2fce59d4727f0fdbf072c2', 'HEAD', ...)`
was run directly against the two session-log-only follow-up commits made
after it and confirmed to return `[]`.

## Post-Review Rebind: Push Retry, Thread Resolution, and a Ruff Baseline Merge

The fix batch pushed clean (`72001d139`) after one transient proxy 502/503
on the first attempt, confirmed via the agent proxy's own status endpoint
as an upstream gateway failure rather than a local misconfiguration. All
eight Copilot review threads were replied to (citing the exact commit and
file:line that fixed each) and resolved.

CI then failed one check, `pytest (bulk)`, on
`ruff_count_ratchet.py: BASELINE ABOVE BASE. This tree records 27,
FETCH_HEAD records 0 (+27)`. Diagnosed per `.claude/rules/ci-scripts.md`
MUST 14: `origin/main` had merged PR #5227, a repo-wide ruff cleanup that
lowered the baseline from 27 to 0, after this branch's base was fetched,
so the branch reported a false regression rather than a real one. Fixed
by merging `origin/main` (commit `b71f0bd77`, 80 files, no conflicts),
which picked up the lowered baseline.
`uv run --frozen pytest tests/test_validate_session_json.py -q` re-ran
clean at 381 passed on the merged tree.

`qaCommit` moves from `9d8a6c287` to `b71f0bd77`, the merge commit;
`post_qa_code_changes('b71f0bd7707275e603082970783b5e8392330bc8', 'HEAD', ...)`
confirmed empty against the two session-log-only follow-up commits made
after it.

## Post-Review Rebind: A Second Copilot Round, Three Staleness Findings

A second automated Copilot review pass on PR #5221 (after the fix-batch
push above) found three more real findings, all staleness bugs rather
than design pushback: the session log's `changesCommitted.Evidence` still
carried a frozen commit-count list the episode extractor's own SHA count
had outgrown; this report's Test Results table claimed 380 passed where
the file now has 381, and its second row restricted a keyword-filtered
run to this single file while reporting a count (565) larger than that
file's own total; and ADR-102's "Why Change Now" section stated the
fallback-path condition backwards (`binding.commit`-as-head bounded
"on the normal (non-fallback) path" when `scripts/validate_session_json.py:992`
shows it is exactly the fallback path). All three fixed: the session log's
Evidence field now describes the commit shape instead of a number,
this report's table above carries freshly re-run accurate numbers
(381 passed; 567 passed / 27354 deselected once the file restriction was
removed), and the ADR sentence now states the fallback condition directly.

`qaCommit` moves from `b71f0bd77` to `d4b017fb1`, the commit carrying the
ADR fix and its debate-log entry;
`post_qa_code_changes('d4b017fb1c093d7c26764bc07d896b92cf38374b', 'HEAD', ...)`
confirmed empty against the endingCommit follow-up made after it.

## Post-Review Rebind: ai-spec-validation FAIL on Stale Debate-Log Framing

`ai-spec-validation`'s Implementation Completeness check FAILed post-push,
quoting the debate log's Round 1 disclosure (lines 11-17, honestly stating
no independent agents ran in that round) as evidence the required
six-agent debate never happened. That reading missed Round 3, further
down the same file, which is the genuine six-agent debate that reached
consensus. The real defect was navigational: the file's own
`**Round**: 1 of up to 10` header and Round 1 section title never updated
after Round 3 concluded, so a reader (bot or human) landing on the
opening section had no forward pointer to what supersedes it. Fixed by
updating the Round line to state Round 3 concluded with consensus and
adding an explicit superseded-by-Round-3 note at the top of the Round 1
section (commit b79ed5016). No finding content changed. This edit does
not touch the ADR file itself, so `adr-review-policy`'s paired-debate-log
requirement did not apply.

`qaCommit` moves from `d4b017fb1` to `c7298e571`, the commit carrying the
debate-log fix; `post_qa_code_changes('c7298e571d0449d73f6edd9ee04e2b1023e859ed', 'HEAD', ...)`
confirmed empty against the two session-log-only follow-up commits made
after it.

## Post-Review Rebind: A Third Copilot Round

A third automated Copilot review pass found two items. One confirmed
real: the parametrized disagreement-warning wiring test only exercised a
passing report, so a regression moving the warning append after
`validate_qa_report()` would silently drop the warning on any validation
failure with every existing test staying green. Fixed by adding
`test_disagreement_warning_survives_a_subsequent_validation_failure`,
verified via discrimination probe (moving the append fails the new test
at `0 == 1` while the existing wiring test stays green either way;
mutation reverted and confirmed byte-identical). The other flagged this
session log's own creation as violating the repo's "discontinue session
log creation" policy; verified against git history and found factually
wrong: this log was first committed at `2026-08-21T15:04:24Z`
(`4a08172f5`), roughly 5.5 hours before the policy commit (`#5229`) was
even authored (`2026-08-21T20:42:37Z`), so it predates the policy and is
exactly the grandfathered "carried over from before this change" case
the rule's own text names. No code change for that finding; the reply
states the timestamps.

Test Results table above re-run and updated: 382 passed (381 plus the
new wiring test); 568 passed / 27354 deselected on the broader keyword
sweep.

`qaCommit` moves from `c7298e571` to `bd36dcf77`, the commit carrying the
new wiring test; `post_qa_code_changes('bd36dcf779365bd0ac9eac93be7b272d596e9be2', 'HEAD', ...)`
confirmed empty against the two session-log-only follow-up commits made
after it.

## Post-Review Rebind: Commit-Limit Block and Resolution

The branch hit `push-ref-policy`'s 40-commit limit at 48, then 51 after
the PR author merged a small `origin/main` update (`AGENTS.md`, no
conflicts) directly to the branch. Wrote the prescribed needs-split
retrospective, presented it to the user, and they applied the
`commit-limit-bypass` label. A second, independent block then surfaced:
this session's `gh` CLI has no working GitHub API access, so the local
pre-push hook's label check fails closed regardless of the label's
actual presence (confirmed via `gh auth status` and a direct run of
`check_pr_bypass_label.py`, exit 3). Verified via the GitHub MCP tool
(unaffected by the `gh` outage) that the label genuinely is on the PR,
meaning CI's own copy of this check will honor it correctly. With the
user's explicit authorization to skip only the `push-ref-policy` job,
pushed with `LEFTHOOK_EXCLUDE=push-ref-policy`; every other pre-push
check (tests, lint, security scan, etc.) ran normally and passed.

`qaCommit` moves from `bd36dcf77` to `0dc7d0a25`, the commit recording
this resolution; `post_qa_code_changes('0dc7d0a254e3aa253b9c9895e008265f06f496d8', 'HEAD', ...)`
confirmed empty against the endingCommit follow-up made after it.

## Verdict

VERDICT: PASS

The design is sound (verified by six independent reviewers across two
rounds), the implementation matches the accepted ADR exactly, the test
suite discriminates old from new behavior, and the corpus blast radius is
measured rather than assumed: one committed log changes behavior.
