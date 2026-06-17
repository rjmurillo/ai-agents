# Issue #1984: E2E /review test inside vendored checkout (PR #1965 Y13)

## Outcome
Shipped `tests/e2e/test_vendored_review_e2e.py`. Closes the Y13 gap:
`tests/integration/test_vendored_install.py` covered only file-structure +
Python surface; no test invoked the Claude Code harness on `/review` inside a
vendored checkout.

## Design (decisions)
- **Opt-in via `RUN_CLI_E2E=1` + `claude` on PATH**, mirroring
  `tests/e2e/test_cli_hook_e2e.py::requires_claude`. The maintainer's 2026-06-16
  triage explicitly endorsed this model. Dissolves the "live vs mock + CI auth"
  decision the prior triage flagged as a blocker: precedent already chose live
  opt-in. Live `claude -p` needs auth + credits => genuine human/secret gate;
  the test SKIPS loudly elsewhere (a skip never reads as a pass).
- **Vendored fixture** `build_vendored_plugin` copies `.claude/{VENDORED_SUBTREE}`
  + CLAUDE.md + `.claude-plugin/plugin.json` into tmp_path. `VENDORED_SUBTREE`
  kept identical to test_vendored_install.py.
- **Synthetic diff**: real git repo with one staged one-line change
  (`make_synthetic_diff_repo`). `/review HEAD` evaluates the staged diff.
- **Axis count discovered, not hardcoded.** Issue says "9 verdict rows" (5-axis
  era). Current canonical set = 12 `references/*.md` + 3 chained skills = 15.
  `discover_axis_count` derives the expected row count from the vendored
  `references/` dir, so it tracks the SKILL.md auto-discovery contract and
  never drifts. The literal 9 is kept only as a floor assertion.
- **extract_verdict loaded from the VENDORED copy** via importlib spec, not the
  repo module, proving the merge ran end-to-end from the copied lib.

## Always-on guards (bare CI, no credits)
7 unit tests pin: fixture builder produces a loadable tree; discovered count ==
CANONICAL_ROLES + chained (cross-checked against tests/lib/test_axis_schema);
synthetic repo has the staged change; row counter + FINAL VERDICT regex; vendored
extract_verdict imports and parses. Mutation-confirmed: breaking `_VERDICT_TOKEN`
makes the row-counter guards fail (0 != 1).

## Evidence
`uv run pytest tests/e2e/test_vendored_review_e2e.py` => 7 passed, 1 skipped
(gated E2E). py_compile OK. 0 em/en dashes.

## Remaining human gate
A real green run of `test_review_runs_end_to_end_in_vendored_checkout` needs
`RUN_CLI_E2E=1` + an authenticated `claude` CLI + model credits (a nightly job
with secrets, or local dev). Cannot be exercised in this sandbox or bare CI.
