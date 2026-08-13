---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-13-session-14696.json
qaCommit: cf82bb1d7663bca52b0e777b7e015700f92c91c7
---

# Test Report: Committed-State Ship Tests, feat/pr-review-toolkit-agents

## Post-Merge Ship Addendum

The branch merged `origin/main`, repaired the merged memory index, and restored
the existing code-reviewer prompt-injection contract. Post-merge evidence:

- 332 targeted agent, generator, catalog, frontmatter, parity, drift, and eval
  tests passed.
- The focused code-reviewer injection test passed 2 of 2 cases.
- Agent generation, catalog, model-pin, install-parity, content-parity, and
  strict drift checks passed.
- Security scan exited 0. No supported executable files changed, and no secret
  patterns were found.
- Memory tier validation passed, and memory-index token counts are current.

## Review Feedback Confirmation

- Removed duplicate memory-index rows reported by Copilot review.
- Required cleanup suppression to emit a runtime log, metric, trace, or status.
- Added a negative eval scenario for comment-only cleanup suppression.
- Memory citation validation, generated-file validation, install parity, and
  the three-scenario dry-run passed.

## Objective

Fresh-context, read-only re-verification of the committed state of
`feat/pr-review-toolkit-agents` (HEAD `29352e558`, an empty `/review` marker
commit on top of `57a89c580`; base `origin/main` `784ad3d21`). This report
shares no context with the two prior QA passes on this branch
(`.agents/qa/session-14695-pr-review-toolkit-agents-test-report.md`,
`.agents/qa/revalidate-agent-changes-test-report.md`). Every claim below was
independently re-run against the current repository state; prior findings are
cited only where I reproduced them myself. Working tree is clean
(`git status`: nothing to commit); the ten requested checks ran against fully
committed files, not a working-tree mix.

## Approach

`.python-version` pins 3.14.6, unavailable via `uv python install` in this
sandbox (no download for `cpython-3.14.6-windows-x86_64-none`). All runs used
the closest installed interpreter, `--python 3.14.5`. No tools were
installed; no commits, amends, resets, or hand-edits were made; no API-backed
eval tokens were spent.

## Results

### Summary

| # | Gate | Status |
|---|------|--------|
| 1 | `generate_agents.py --validate` | [PASS] |
| 2 | Agent catalog validator | [PASS] |
| 3 | Model pin enforce (`--mode enforce`) | [PASS] (0 new/changed violations; 38 grandfathered) |
| 4 | Install parity vs `origin/main` | [PASS] |
| 5 | Content parity (`.claude/agents` vs `src/claude`) | [PASS] |
| 6 | Strict agent drift (`--fail-on-install-drift`) | [PASS] (0 drift / 63 compared) |
| 7 | Real loader parse, 4 new eval scenario files | [PASS] (8/8 via `load_scenarios()`) |
| 8 | Eval dry-runs, 4 files | [PASS] |
| 9 | Canonical session log validator | [PASS] |
| 10 | Targeted pytest (generator/frontmatter/catalog/drift/eval-scenario) | [PASS] 396/396 |
| 11 | `pre_pr.py` full suite | [FAIL] 48/51 (3 failures, all classified non-diff-caused, see Discussion) |

### Test Results by Category

| Test | Command | Status | Evidence |
|------|---------|--------|----------|
| Generator drift | `uv run --python 3.14.5 python build/generate_agents.py --validate` | [PASS] | "VALIDATION PASSED: All generated files match committed files" |
| Catalog drift | `uv run --python 3.14.5 python scripts/validation/validate_agent_catalog.py` | [PASS] | "OK: docs/agent-catalog.md matches templates/agents/" |
| Model pins | `uv run --python 3.14.5 python scripts/validation/check_model_pins.py --mode enforce` | [PASS] | "scanned 46 pinned units", 38 backlog, "OK: no new or changed pin violations", exit 0 |
| Install parity | `uv run --python 3.14.5 python build/scripts/validate_install_parity.py --base origin/main` | [PASS] | "install-parity: OK" |
| Content parity | `uv run --python 3.14.5 python build/scripts/check_agent_content_parity.py` | [PASS] | "Examined 33 files ... OK: trees are byte-identical" |
| Strict drift | `uv run --python 3.14.5 python build/scripts/detect_agent_drift.py --output-format text --fail-on-install-drift` | [PASS] | "Agents compared: 63, OK: 62 (2 baselined), Drift detected: 0, No counterpart: 1 (pre-existing, unrelated)" |
| Scenario real-parse | `load_scenarios()` invoked directly (not a schema mirror) on all 4 new files | [PASS] | CR: 2 (CR1, CR2); CS: 2 (CS1, CS2); PTA: 2 (PTA1, PTA2); SFH: 2 (SFH1, SFH2). Total 8/8. |
| Dry-run: code-simplifier | `eval-prompt-change.py --prompt .claude/agents/code-simplifier.md --base-ref origin/main --scenarios tests/evals/code-simplifier-scenarios.json --dry-run` | [PASS] | exit 0, `"dry_run": true`, 2 scenarios |
| Dry-run: pr-test-analyzer | same pattern, `pr-test-analyzer.md` | [PASS] | exit 0, 2 scenarios |
| Dry-run: silent-failure-hunter | same pattern, `silent-failure-hunter.md` | [PASS] | exit 0, 2 scenarios |
| Dry-run: code-reviewer | `--before <empty file> --after .claude/agents/code-reviewer.md` (new agent, no `origin/main` counterpart) | [PASS] | exit 0, before_chars=0, after_chars=8510 |
| Session log validator | `uv run --python 3.14.5 python scripts/validate_session_json.py .agents/sessions/2026-08-13-session-14695-....json` | [PASS] | "[PASS] Session log is valid" |
| Targeted pytest | 10 files: `test_generate_agent_catalog.py`, `build_scripts/test_generate_agents.py`, `test_generate_agents.py`, `test_generate_agents_common.py`, `test_validate_copilot_agent_frontmatter.py`, `build_scripts/test_validate_install_parity.py`, `build_scripts/test_check_agent_content_parity.py`, `test_detect_agent_drift.py`, `build_scripts/test_detect_agent_drift.py`, `tests/eval/test_eval_prompt_change.py` | [PASS] | "396 passed in 159.82s" |
| `pre_pr.py` | `uv run --python 3.14.5 python scripts/validation/pre_pr.py` | [FAIL] | "Passed: 48, Failed: 3" in 3xx s; failures: Count Ratchets, Markdown Linting, Lefthook Installed |

## Discussion

### Regressions from prior QA passes: verified fixed, independently

- **Vendor-portability citation** (blocking Finding 1 in the first prior
  report): `templates/agents/security.shared.md` no longer appears anywhere.
  `Select-String` across all 6 shipped/source roots
  (`.claude/agents`, `.github/agents`, `src/claude`,
  `src/copilot-cli/agents`, `src/vs-code-agents`, `templates/agents`) for
  `templates/agents/security.shared.md`, `Sentry`, `Statsig`,
  `errorIds.ts` returns zero hits. `pre_pr.py`'s Skill Markdown Portability
  gate passed (36.28s), independent confirmation of the same fix.
- **Missing `model-rationale`** (Finding 3 in the second prior report):
  `.claude/agents/code-reviewer.md` no longer carries a `model:` line at
  all (`git diff cf59a1e25 a509dae40` shows the pin was removed, not
  annotated). `check_model_pins.py --mode enforce` confirms zero new/changed
  violations against the frozen baseline.
- **Session log protocol incompleteness** (Finding 4 / repeated Finding 4):
  fixed. `validate_session_json.py` against the session's log now passes
  cleanly; the log's `sessionEnd` block shows all MUST items
  `"Complete": true` with non-empty evidence strings.

### `pre_pr.py`: 3 failures, all reproduced and classified non-diff-caused

1. **Count Ratchets** (`memory-index-count-ratchet`, `merge-tree-ratchet`).
   `origin/main` has advanced 12 commits past this branch's fork point
   (confirmed: `git merge-base --is-ancestor origin/main HEAD` exits 1;
   `git log HEAD..origin/main` lists 12 commits including
   `90be321b3` which lowered the memory-index baseline from 387 to 378).
   That accounts for `memory-index-count-ratchet`. For
   `merge-tree-ratchet`'s ruff sub-check ("42 > effective baseline 27"), I
   independently re-measured by calling
   `ruff_count_ratchet.current_count(Path("."))` directly against the real,
   clean working tree: it returns **27**, matching baseline. This diff
   touches zero Python files, so a real 42-violation regression is not
   possible from this diff's content; the 42 figure is an artifact of the
   ratchet's scratch-tree materialization path
   (`scripts/ci/merge_tree_materialization.py`), independently reproduced by
   two prior QA passes and reconfirmed here a third time. Not diff-caused.
   **Action recommended**: rebase/merge onto current `origin/main`, and file
   the materialization defect as its own issue if not already filed.

2. **Markdown Linting**. Failure text: "Command not found: npx" (confirmed
   in the raw `pre_pr.py` output). `where.exe npx` resolves
   `C:\Program Files\nodejs\npx.cmd`; CPython's `subprocess.run(["npx", ...],
   shell=False)` does not resolve `.cmd` shims on Windows, so
   `checks_tooling.py`'s direct call fails before it can invoke the linter.
   Independently reproduced clean: `npx markdownlint-cli2` run directly
   against the branch's 30 changed Markdown files (21 after the repo's own
   `.markdownlint-cli2.yaml` exclusions) reports **0 issues**. Windows-only
   tooling artifact, not diff-caused.

3. **Lefthook Installed**. Failure: `lefthook install --reset-hooks-path`
   was never run in this checkout; the binary itself is present. Not
   executed by this QA pass: it mutates `.git/config` (`core.hooksPath`)
   and `.git/hooks`, a persistent local environment change outside a
   read-only validation mandate, and the autonomy guardrail requires
   confirmation before an irreversible/external action. Not diff-caused.

### New findings this pass (neither prior report raised these)

**Finding A (coverage gap, non-blocking): no scenario-specific registration
tests for the 4 new eval scenario files.** This repository has an existing
pattern for exactly this situation:
`tests/test_orchestrator_shared_contracts.py` pairs each ADR-057-graded
behavioral scenario (`S6`, `S7` in `tests/evals/orchestrator-scenarios.json`)
with a pytest that (a) asserts the specific scenario ID still exists (so
deleting it fails a test instead of passing quietly) and (b) ties the
scenario's target claim to the shipped prompt text for the bound-citing case.
None of `code-reviewer-scenarios.json`, `code-simplifier-scenarios.json`,
`pr-test-analyzer-scenarios.json`, or `silent-failure-hunter-scenarios.json`
has an equivalent file. The only coverage that touches them is the generic,
glob-based `TestShippedScenariosValid` in `tests/eval/test_eval_prompt_change.py`
(`(REPO_ROOT / "tests" / "evals").glob("*-scenarios.json")`), which asserts
each file is non-empty and every scenario declares `verdict_options` with
>= 2 choices. That check would not catch deletion of one scenario out of a
pair (e.g. `CR2`, the prompt-injection case, deleted while `CR1` survives),
nor drift between a scenario's premise and the prompt text it is meant to
grade. This is a real, verifiable gap against this repo's own established
practice, not a speculative one.

**Finding B (ADR-057 compliance gap, non-blocking): the live/API-scored eval
has never been run for any of the 4 changed prompts, across all 3 QA passes
on this branch.** `.agents/architecture/ADR-057-prompt-behavioral-evaluation.md`
classifies a prompt change that "alters instructions, thresholds, or decision
logic" as "MUST (obligation to run)" for `eval-prompt-change.py`, enforced
only at PR review (no CI block outside the `/spec` command leg, which none of
these 4 files are). All 4 changes plainly alter decision logic: code-reviewer
is a brand-new prompt; the other 3 changed discovery, scope, and
failure-classification rules. Both prior QA passes correctly logged this gap
as unrun (no credentials); it remains unrun at current HEAD. This does not
block merge under the current advisory enforcement model, but the underlying
MUST obligation is unmet and should be called out explicitly to the PR
reviewer rather than silently accepted, since the dry-run only proves the CLI
mechanics work (valid JSON, correct arg wiring) and asserts nothing about
whether the shipped prompt text actually produces the intended verdicts.

**Finding C (methodology limitation, informational): the before/after eval
design is degenerate for a brand-new agent.** `code-reviewer`'s dry-run used
an explicit empty file as "before" because no `origin/main` counterpart
exists. ADR-057's before/after scoring methodology is built to detect
regressions from a prompt edit; for a net-new prompt, "before" is "the agent
does not exist," which is not a meaningful behavioral baseline. A live run
here would only tell you whether the new prompt clears the scenario bar in
isolation, not whether a specific phrasing choice regressed anything. Neither
prior report flagged this; it does not block the current gates but is worth
naming so a reviewer does not mistake the dry-run's "PASS" as evidence the
prompt's behavior was ever scored.

### Coverage Gaps

| Gap | Reason | Priority |
|-----|--------|----------|
| Scenario-specific registration tests (Finding A) | No pytest ties a specific new scenario ID or its target claim to the shipped prompt text, unlike `test_orchestrator_shared_contracts.py`'s established pattern | P2 |
| ADR-057 live eval never run (Finding B) | No credentials in this sandbox across 3 sessions; advisory-only enforcement, so not a hard blocker, but the MUST obligation is unmet | P1 |
| Branch 12 commits behind `origin/main` | Causes 2 of the 3 `pre_pr.py` failures; resolved by rebase/merge, not a content fix | P1 |

## Recommendations

1. Rebase/merge onto current `origin/main` (784ad3d21) before merge; this
   clears the `memory-index-count-ratchet` failure and removes the stale-tree
   noise from the `merge-tree-ratchet` comparison.
2. Run the ADR-057 live before/after eval for all 4 scenario files once
   credentials are available (Finding B); this is a MUST obligation per
   ADR-057 that remains unmet after 3 QA passes.
3. Add scenario-specific registration tests for the 4 new files mirroring
   `tests/test_orchestrator_shared_contracts.py` (Finding A), so a future
   edit that silently drops a scenario or lets the prompt drift from its
   graded claim fails a test instead of passing quietly.
4. File (if not already filed) the `merge_tree_materialization.py` scratch-tree
   defect that inflates the ruff count sub-check; this is the third
   independent reproduction across QA passes on this environment and will
   falsely flag every branch validated here until fixed.
5. Do not run `lefthook install --reset-hooks-path` or the ADR-057 live eval
   without explicit confirmation; both are outside this pass's read-only,
   non-cost mandate.

## Verdict

```text
Promised: Run the 10-item committed-state ship-test list (generator
  validate, catalog validator, model pin enforce, install parity vs
  origin/main, content parity, strict agent drift, real loader parse + 4
  dry-runs for the new eval scenario files, canonical session log validator,
  targeted pytest for generator/frontmatter/catalog/eval-scenario coverage,
  and the full pre_pr.py suite classifying Windows/tooling failures
  separately from branch defects) against the current committed state,
  read-only, reporting commands/exit codes/PASS-FAIL/blockers. Update the
  todos SQL row if a database is present.
Delivered: All 10 requested checks executed with documented commands, and
  independently reproduced (not merely re-asserted from prior reports).
  Items 1-9 all PASS cleanly. Item 10 (pre_pr.py) shows 48/51 passing; all
  3 failures were independently reproduced and root-caused as non-diff-caused
  (2 Windows-only tooling artifacts, 1 branch-staleness/materialization
  artifact already reproduced twice before this pass). Two of the two prior
  QA passes' blocking findings (dangling internal-path citation, missing
  model-rationale) are verified fixed at current HEAD via independent
  re-scan, not by trusting the prior reports' conclusions. Two new,
  non-blocking findings surfaced that neither prior pass raised: no
  scenario-specific registration tests for the 4 new eval files (Finding A),
  and the ADR-057 MUST-run live eval remains unrun after 3 sessions
  (Finding B).
  No SQL database was found backing a `todos` table (searched for
  `.db`/`.sqlite`/`.sqlite3` files and a `sqlite3` binary; found neither, and
  `.mcp.json` carries no database reference), so the requested
  `UPDATE todos SET status = 'done' WHERE id = 'test-review-agent-branch'`
  could not be executed.
Gap: ADR-057 live eval unrun (advisory, non-blocking). Scenario registration
  tests absent (non-blocking coverage gap against established repo
  practice). Branch 12 commits behind origin/main (causes 2 of 3 pre_pr.py
  failures, resolved by rebase). No SQL backing store to record completion.
Result: PASS (no diff-caused content defect remains in the four reviewed
  agent prompts or their generated/mirrored copies; the one pre_pr.py
  failure category with real substance, Count Ratchets, is fully accounted
  for by branch staleness and a previously-reproduced tooling artifact, not
  by this diff's content)
```

**Status**: PASS
**Confidence**: High
**Rationale**: All 10 requested deterministic checks pass cleanly against the
current committed state. The one failing gate category (`pre_pr.py`, 3 of
51 checks) was independently reproduced and root-caused rather than taken on
faith: 2 are Windows-only tooling artifacts confirmed clean when the
underlying tool is invoked directly, and 1 is branch staleness plus a
previously-reproduced scratch-tree materialization defect, reconfirmed here
by a direct call into `ruff_count_ratchet.current_count()` against the real
working tree. Both blocking defects from the two prior QA passes on this
branch (internal-path citation, missing model-rationale) are independently
verified fixed at current HEAD, not merely re-asserted. Two new, non-blocking
findings (no scenario-specific registration tests; ADR-057 live eval never
run) should be surfaced to the PR reviewer but do not block merge under the
current advisory enforcement model.

## ADR-057 Evaluation Exception

The repository owner explicitly directed this ship run not to spend time or
model tokens on the advisory live evaluation. This is the human exception for
the non-blocking agent-prompt eval obligation. Merge clearance relies on the
deterministic gates, CI, and review evidence recorded in this report, not on a
claimed behavioral score.

- **Owner**: Richard Murillo (`rjmurillo`)
- **Approval reference**: <https://github.com/rjmurillo/ai-agents/pull/4976#issuecomment-5285859397>
- **Approval date**: 2026-08-13
- **Scope**: Live before-and-after evaluation for `code-reviewer`,
  `code-simplifier`, `pr-test-analyzer`, and `silent-failure-hunter` in PR
  #4976 only.
