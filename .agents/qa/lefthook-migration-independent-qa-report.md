# Independent QA Report: Lefthook Migration

**Branch**: chore/lefthook-migration
**Range**: ffecc861ad..464503c1c940 (41 commits)
**Validator**: QA Agent (independent re-execution, read-only)
**Date**: 2026-07-19

## Reconciliation

```text
Promised: Lefthook is the only local hook manager; scripts/hooks holds canonical
  payload behavior; custom installer and .githooks are gone; bootstrap/docs/CI use
  Lefthook; plugin versions and generated artifacts correct; every commit <=5 paths;
  targeted and full gates pass; pre-commit/commit-msg/pre-push behavior preserved
  (restaging, raw stdin, push ranges, worktrees, env controls, blocking/advisory exits).
Delivered: All of the above, independently re-verified by direct execution (not
  documentation review). Full pytest, targeted hooks suite, integration suite,
  pre-PR gate, and live hook invocations all reproduce the reported evidence.
Gap: "target 239" figure from the reported summary could not be reproduced under
  any test-selection I could infer (see Acceptance Criteria table, row 8). No
  functional gap found; this is a reporting-label ambiguity only.
Result: PASS
```

## Status
**QA COMPLETE**

## Acceptance Criteria Matrix

| # | Criterion | Evidence | Verdict |
|---|-----------|----------|---------|
| 1 | Lefthook is the only local hook manager | `.githooks` absent; `lefthook.yml` present with pre-commit/commit-msg/pre-push wired to `scripts/hooks/*`; `git config --get core.hooksPath` empty after `lefthook install --reset-hooks-path` (hooks land in `.git/hooks`, not a custom path) | [PASS] |
| 2 | `scripts/hooks` contains canonical existing payload behavior | `diff` of each payload against its pre-migration `.githooks/*` counterpart (commit ffecc861ad) shows only header-comment changes (2, 4, and 2 lines respectively); zero logic diff | [PASS] |
| 3 | Custom installer / dead support removed | `scripts/install_git_hooks.py` and `tests/test_install_git_hooks.py` absent; `git grep` for `install_git_hooks` in active reference roots returns none (only historical `.agents/audits`, `.agents/memory`, `.serena/memories`, `.claude-mem` archives, which are out of scope by design) | [PASS] |
| 4 | Bootstrap/docs/CI use Lefthook | `scripts/bootstrap-vm.sh:117-120` runs `lefthook install --reset-hooks-path` + `check-install`; `README.md:500`, `CONTRIBUTING.md:44,511-521`, `docs/technical-guardrails.md:317-321` document Lefthook setup; `.github/actions/setup-code-env/action.yml:127-131,181-182` installs and verifies Lefthook on both bash and pwsh steps | [PASS] |
| 5 | Generated artifacts and plugin versions correct | `plugin.json` versions: `project-toolkit` 0.6.78→0.6.80, `claude-agents` 0.3.38→0.3.39, matching commit `75c1c3613c`; `pre_pr.py` "Plugin Version Bump" and "Agent Catalog Drift" gates both [PASS] on re-run | [PASS] |
| 6 | Every commit touches <=5 paths | Counted `git show --name-only` for all 41 commits; max observed = 5, most are 1-5 | [PASS] |
| 7 | Targeted hooks suite passes | `pytest tests/hooks -q` → **947 passed** (exact match to reported figure) | [PASS] |
| 8 | "target 239" figure | Reran every test file touched by the migration (per `git diff --name-only` across the range, 37 files) → **569 passed**, not 239. No test-selection I constructed reproduces 239. No failures found under any selection; treat as a labeling ambiguity in the original report, not a defect | [PARTIAL - see Gap] |
| 9 | Integration suite passes | `pytest tests/test_lefthook_integration.py tests/integration -q` → **33 passed** (5 in the lefthook-specific file, matching reported "integration 5") | [PASS] |
| 10 | Pre-PR gate passes | `python3 scripts/validation/pre_pr.py` (full, no `--quick`) → **30 passed, 0 failed, 4 skipped** (exact match); includes explicit `[PASS] Lefthook Installed` gate | [PASS] |
| 11 | Full pytest suite passes | `pytest -q` (full repo) → **14091 passed, 22 skipped, 45 xfailed** in 190.97s (exact match); 0 FAILED/ERROR lines in log | [PASS] |
| 12 | pre-commit restaging preserved | `scripts/hooks/pre-commit` retains `git add --` restaging calls at markdown auto-fix, causal-graph, memory-index, and session-log sites (12 call sites); covered by `tests/hooks/test_markdown_auto_lint.py` (28 passed) | [PASS] |
| 13 | commit-msg raw stdin / arg passing preserved | Live test: created scratch repo, ran real `lefthook install`, committed with an em-dash message on a feature branch → blocked with exact original error text; committed clean message → passed. Automated `test_dispatch_preserves_argument_stdin_and_exit_status` also passed | [PASS] |
| 14 | pre-push ranges preserved | Live push to a bare remote via installed Lefthook hook correctly parsed stdin `local_ref local_sha remote_ref remote_sha` and evaluated the range (advisory warning for missing merge-base, non-blocking) | [PASS] |
| 15 | Worktree support preserved | Created a linked worktree (`git worktree add --detach`) from the real repo HEAD; `lefthook.yml` and `scripts/hooks/*` present (tracked files check out normally); ran `lefthook run pre-commit` from inside the worktree → passed with a graceful detached-HEAD warning. Automated `test_installed_hooks_work_from_linked_worktree` also passed | [PASS] |
| 16 | Env controls preserved | `SKIP_WORKFLOW_LOCAL_TEST` and `SKIP_CLI_E2E` bypass switches present and referenced in `scripts/hooks/pre-push` (lines 910-1030, 1441-1475) | [PASS] |
| 17 | Blocking vs advisory exits preserved | pre-commit branch-protection violation blocked the commit (`exit status 2`, git aborts); commit-msg dash violation blocked (`exit 1`); pre-push missing-merge-base produced a WARNING and still allowed the push (advisory, exit 0) | [PASS] |
| 18 | No active stale references to old hook manager | `git grep` for `.githooks` and `install_git_hooks.py` across `ACTIVE_REFERENCE_ROOTS` (README, CONTRIBUTING, .config, scripts, .github, docs, templates, build, .claude, src/claude, src/copilot-cli, src/vs-code-agents) returns only the two explicitly-excluded `ai-agents-failure-archaeology/references/incidents.md` historical files | [PASS] |

## Independent Commands Run

```bash
git log --oneline ffecc861ad..464503c1c940 | wc -l                 # 41
for c in <41 commits>; git show --name-only --format="" $c | wc -l # max 5

git show ffecc861ad:.githooks/pre-commit > /tmp/old; diff /tmp/old scripts/hooks/pre-commit   # 2-line diff, header only
git show ffecc861ad:.githooks/commit-msg > /tmp/old; diff /tmp/old scripts/hooks/commit-msg   # 4-line diff, header only
git show ffecc861ad:.githooks/pre-push  > /tmp/old; diff /tmp/old scripts/hooks/pre-push      # 2-line diff, header only

uv run --frozen lefthook install --reset-hooks-path
uv run --frozen lefthook check-install                              # exit 0, silent

# scratch repo commit-msg / pre-commit / commit-msg dispatch (real git commit, not mocked)
git init scratch; lefthook install; git commit -F message-with-prohibited-dash.txt  # blocked
git commit -m "clean message"                                       # passed both hooks

# scratch repo pre-push against a bare remote
git push origin feat/test-hooks                                     # advisory warning, exit 0

# linked worktree from the real repo HEAD
git worktree add --detach /tmp/qa-worktrees/wt1 HEAD
lefthook run pre-commit                                              # passed, detached-HEAD warning only

pytest tests/hooks -q                                                # 947 passed
pytest tests/test_lefthook_integration.py tests/integration -q       # 33 passed
pytest tests/test_validation_pre_pr.py tests/test_bootstrap.py -q    # 103 passed
python3 scripts/validation/pre_pr.py                                 # 30 passed, 0 failed, 4 skipped
pytest -q                                                            # 14091 passed, 22 skipped, 45 xfailed, 190.97s

git grep -ln "\.githooks" -- README.md CONTRIBUTING.md .config scripts .github \
  docs templates build .claude src/claude src/copilot-cli src/vs-code-agents
  # only the 2 historical failure-archaeology reference files
```

## Test Quality Notes

The migration's own regression coverage (`tests/test_lefthook_integration.py`) is
behavioral, not structural: it spins up real scratch git repos, runs the real
`lefthook` binary via `subprocess.run`, and asserts on actual dispatch output
(argument file contents, stdin capture, exit-status propagation, worktree
execution). This matches the required test pattern (function execution, real
invocation, output validation) rather than pattern-matching source text. My
independent live reproductions of the same scenarios (commit-msg blocking,
pre-push advisory warning, worktree dispatch) produced identical results using
a separate scratch setup, corroborating the automated tests rather than merely
re-running them.

## Coverage Metrics

| Metric | Value |
|--------|-------|
| Full suite pass rate | 14091/14158 collected (99.5%), 22 skipped, 45 xfailed |
| Hooks-targeted pass rate | 947/947 (100%) |
| Integration pass rate | 33/33 (100%) |
| Pre-PR gate pass rate | 30/34 non-skip-eligible (100% of runnable gates), 4 skipped (Session End, Pester, Path Normalization, Planning Artifacts - none touch Lefthook) |
| Commits exceeding 5-path limit | 0/41 |
| Payload logic drift (pre-commit/commit-msg/pre-push vs pre-migration) | 0 lines (comments only) |

## Skipped-Test Disposition

- Full-suite 22 skipped / 45 xfailed: none fall inside `tests/hooks`, the
  Lefthook integration test, or the pre-PR/bootstrap suites (confirmed via a
  scoped `-rs` rerun of those directories showing zero SKIPPED lines). The
  skips observed in the full run (`test_conftest_git_signing.py`,
  `test_context_retrieval_decision.py`, etc.) are pre-existing
  environment-conditional skips unrelated to this migration.
- Pre-PR gate's 4 skips (Session End Validation, Pester Unit Tests, Path
  Normalization, Planning Artifacts) are standard no-op skips for a non-PR,
  non-Windows, no-plan-diff local run context; none represent a lost
  enforcement path for Lefthook itself ("Lefthook Installed" ran and passed).

## Blockers

None.

## Minor Finding (non-blocking)

The reported "target 239" test count could not be independently reproduced.
Every test-file-based selection I constructed from the actual diff (37 files,
excluding the intentionally-deleted `test_install_git_hooks.py`) produced 569
passed, and the pre-existing `tests/hooks` directory alone produced 947. No
failing or missing test was found under any selection attempted. Recommend
the implementer clarify what "target" pytest invocation was used, but this
does not block sign-off: coverage under every selection tried was 100% pass.

## Recommendations

1. Clarify the "target 239" selection command in future validation reports so
   the specific invocation is reproducible without guessing.
2. Consider committing `.agents/security/SR-lefthook-prepush-relocation-2026-07-19.md`
   (currently untracked in the working tree) if it documents the pre-push
   relocation's security review; an untracked security artifact does not
   travel with the branch.

## Final Verdict

**PASS**. Lefthook is the sole local hook manager, payload behavior is
byte-for-byte preserved apart from documentation comments, the custom
installer and `.githooks` are fully removed with no active stale references,
bootstrap/docs/CI all install and verify Lefthook, plugin versions match the
migration commit, every commit is within the 5-path limit, and every gate
re-run (targeted, integration, pre-PR, full suite) reproduces the reported
numbers exactly except for the unreproducible "239" label, which carries no
functional risk. No enforcement was silently lost: branch-protection,
em/en-dash blocking, and advisory pre-push warnings all fired correctly
against live, unmocked hook invocations in both a scratch repo and a real
linked worktree of this repository.
