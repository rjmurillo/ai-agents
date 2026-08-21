---
paths:
  - "scripts/validation/**"
  - "scripts/**"
  - ".github/workflows/**"
  - ".github/actions/**"
  - "build/**"
  - ".claude/skills/**/scripts/**"
  - ".claude/skills/**/tests/**"
  - "src/copilot-cli/skills/**/scripts/**"
  - "src/copilot-cli/skills/**/tests/**"
priority: high
---

# CI and Validation Script Rules

Scripts under `scripts/validation/`, `build/`, and `.github/workflows/` gate every PR. A broken change here blocks the entire repository (see Issue #1711).

## MUST

1. **Local run before commit**. CI-critical scripts MUST be exercised locally before commit. Use `gh act` for workflows, direct `uv run python` invocation for validation scripts, and the actual test suite for helpers.
2. **Shift-left validation**. Before pushing, MUST run `uv run python scripts/validation/pre_pr.py` and resolve any failures.
3. **Python for new scripts**. New scripts MUST be Python per ADR-042. MUST NOT create new `*.sh` bash scripts.
4. **Exit codes**. Scripts MUST follow the exit code contract: `0`=ok, `1`=logic, `2`=config, `3`=external, `4`=auth (`AGENTS.md`).
5. **Tests required**. New validation scripts MUST have tests under `tests/`. Do not add CI tests to shipped skill directories.
6. **Pin Actions to SHA**. Workflow changes MUST pin every Action reference to a commit SHA.
7. **Verify worktree identity before writing**. A script that resolves the repository root and then writes to it MUST confirm the current directory is inside the resolved root before the first write (`Path.cwd().resolve().is_relative_to(top_level)`). `git rev-parse --show-toplevel` reports a claim, not a fact about where you are: a local `core.worktree` value or a `GIT_WORK_TREE` environment variable redirects it to a directory you are not standing in, and `git status` then reports every tracked file as deleted because it is looking somewhere else. Measured: an ordinary `git worktree add` sets neither, a moved worktree still resolves correctly, and a worktree whose main checkout moved away fails closed with a non-zero exit. So the redirection is always something a person or a tool set on purpose, which is exactly why a script that inherits it has no way to notice.
8. **Anchor helper resolution on the absolute top level**. A resolver that walks candidate roots to find a repository helper MUST anchor its in-repo rung on `git rev-parse --show-toplevel`, and MUST order that rung ahead of any out-of-repo root. A bare relative `.claude` rung only resolves when cwd happens to be the repository root; invoked from a subdirectory it falls through to a copy under `~/.copilot/installed-plugins` or `~/.claude/plugins/cache`, which can be arbitrarily old. `check_skill_resolver_anchoring.py` enforces this for `SKILL.md` resolvers; the same requirement binds resolvers written anywhere else, where nothing enforces it for you.
9. **Read the state you are asserting about, and name the ref**. A claim about what the repository *contains* MUST be computed from a named ref: `git ls-tree -r -z --name-only HEAD` for a path inventory, the full `git ls-tree -r -z HEAD` wherever entry mode matters, and `git log HEAD` for history. Use `-z`; paths are not newline-safe, and `--name-only` hides modes, so the tracked `memory_enhancement` symlink is indistinguishable from a regular file. Such a claim MUST NOT come from `git log --all` or from a directory walk. `--all` reads every ref the clone holds rather than the branch: at diagnosis this clone held 2054 `refs/remotes/pr/*` refs while `remote.origin.fetch` covered only branch heads, and deleting one of them flipped a shipped test from failing to passing without changing a byte of the repository (Issue #3753). Prefer `HEAD` to `origin/main`, since a guard scoped to the base branch cannot see what the current change does. Reads of the working tree, the index, and untracked files remain correct and required wherever that state is itself the subject, as in regeneration drift and pre-commit checks. A ratchet baseline is a claim about a ref, so the measurement behind it MUST NOT read untracked state: `Path.exists()` counts gitignored build output that the author happens to have generated and CI never will, so the same commit scores differently on two machines. Measured 2026-08-07: a baseline recorded with `build/audit/GENERATION-AUDIT.md` present landed one too low on four entries and turned `main` red for every open PR, while the identical command on the identical commit passed locally (Issue #4748). Their findings describe local state and MUST NOT be restated as claims about a ref: a directory walk reported three skills as unusable when what remained on disk was untracked residue from a deletion in PR #2359, and the resulting Issue #3420 was closed NOT_PLANNED.
10. **Convert every failure signal into a non-zero exit before the step ends**. When a `run:` block moves into a Python module under ADR-006, the shell semantics it is replacing MUST be preserved at the boundary: under `set -e` any non-zero command aborted the step, so the module MUST return a non-zero code to `sys.exit` for the same conditions. Returning a findings list, an error string, `None`, or `False` to a caller that ignores it converts a red step into a green one, and the extraction is then a silent-pass detector rather than a check. Six confirmed instances are tracked in Issue #4068. A green step whose behavior changed in this direction is worse than the shell it replaced, because the shell failed loudly and the module reports success. Verify by running the module against input known to be bad and reading `$?`, not by reading the log.
11. **Convert every detected violation into a non-zero exit**. A script that detects a violation and prints a message but exits 0 has the same observable behavior as a script that found nothing. Hooks and CI steps read the exit code; they do not parse output. If the script found a problem, it MUST exit non-zero. If it found nothing to check (empty input set, no files matched), it MUST exit 0 and SHOULD print a count of examined items so a caller can tell the difference between "zero violations in N items" and "zero violations because nothing was examined".
12. **Distinguish a run that did nothing from a run that succeeded**. A workflow, checker, or gate that early-returns when there is no work MUST NOT report that outcome the same way it reports completed work, or the signal inverts: the job goes green exactly when it is idle and red exactly when it acts, and the failure hides inside a mostly-green history. Always print the examined count alongside the violation count: "0 violations in 381 files" is verifiable; "OK" is not. A mutation harness MUST report DID-NOT-APPLY when the target literal is absent so that a moved or renamed target does not become an undetected surviving mutant.
13. **A PR introducing a gate MUST demonstrate the gate passing against the full corpus before merge**. A unit test over fixtures proves the checker's logic; it proves nothing about whether the existing corpus satisfies the gate. Those are separate claims and only the second determines whether main goes red. The PR body or a PR comment MUST quote the output of the gate's own command run against the full corpus on the PR branch. A gate that ships with known outstanding violations blocks every subsequent push by every contributor and must not merge. Measured cost: two violations in a single episode file blocked the entire repository for a multi-hour window after PR #4219 merged, driving three hook-bypass attempts, each of which is a policy violation under ADR-086:95-98 (Issue #4262).

14. **Merge `origin/main` and re-measure before hunting a tripped count ratchet**. The count ratchets under `scripts/ci/` compare the branch's whole tree against a baseline integer that main lowers whenever main adds an exemption or clears violations. A branch behind main therefore reports an increase indistinguishable from a self-inflicted regression, and the failure text names the branch as the party that raised the baseline. Measured on PR #4055: pre-push reported `taste count ratchet: BASELINE RAISED. 601 -> 602` and `ruff count ratchet: 326 -> 329`, and `git merge origin/main` alone returned both to `601` and `326` with no source edit, because commit `aea3a49cd9` had added `# taste-lint: ignore file-size` to `tests/validation/test_check_vendor_portability.py` while the branch still carried the pre-exemption copy of that same file. PR #4109 failed `test_the_shipped_baseline_matches_the_tracked_tree` with `baseline is 602 but current tree has 603` and passed after the same merge, again with no source edit. The merge is the first diagnostic step, not the last resort. Re-fetch immediately before measuring, and treat a `main` ref fetched earlier in the same session as already stale: this repository merges several times an hour, so a long operation is enough to fall behind. Measured in one session: four branches were rebased onto a `main` fetched fifteen minutes earlier, all four then reported `602 > 601`, and the count that looked like a shared regression in main was a suppression that had landed in `c02f61ddd2` during the rebase. Re-fetching and rebasing again returned all four to `601` with no source edit. The distinguishing check is `git rev-parse main` against the remote, not a re-run of the ratchet, which reports the same number either way. A baseline MUST NOT be raised to clear a count the branch did not introduce.
15. **Diff violations on `(file, rule)` identity, never on the rendered message**. A taste message embeds the measurement it is reporting (`File exceeds 500 lines (566 lines)`), so a text diff of two trees' violation lists reports nearly every violation as both removed and added once any file's length changes. Diffing `(file, rule)` tuples collapsed one such comparison from 16-versus-15 noise to the true signal of exactly one added violation.
16. **Size a pre-push job's timeout for a loaded machine, not an idle one.** A script's standalone wall clock does not predict its wall clock as a lefthook job. Historical observation, 2026-08-02, on `worktree-gc-report` against a checkout holding 288 registered worktrees with 0 removal candidates: 6.83s and 11.47s standalone, against 92.87s, 94.45s, 99.48s and 101.33s across four consecutive real pushes. Those figures record one machine on one date. They establish that a gap existed and repeated within that session; they say nothing about its size on any other machine, checkout, or date, so do not carry the ratio forward as a planning number. The job wiring is a fact you can check now in `lefthook.yml`: `worktree-gc-report` carries a 2m cap inside a `parallel: true` pre-push group of 24 jobs that also holds `python-tests` and `workflow-local-run` at 30m caps. Concurrent resource contention is a plausible mechanism for the gap, not an established cause: no CPU, disk, or git-lock telemetry was collected during those pushes and no run isolated the job from the group, so the causal claim is unverified and no single resource may be reasoned from. What follows regardless of mechanism is the practice: measure a candidate cap during a real push, not a standalone run, because a cap sized on an idle run is a cap a real push can exceed, at which point a job that only reports is deciding whether code can ship.
17. **Read `lefthook.yml` for a group's scheduling. Do not infer it from the run summary.** In four consecutive pushes recorded on 2026-08-02, the summary reported a group's duration as the sum of its jobs' durations, matching to the hundredth (1017.69, 950.28, 930.85, 926.49) while the longest single job sat well below it (818.73, 765.34, 738.28, 733.33). Those numbers are a dated observation from one session, not a measurement to re-derive. That arithmetic reads as proof of serial execution and is not: the group in question declares `parallel: true`, which `lefthook.yml` states outright and which you can check at any time. A summary that reports a sum reports it regardless of scheduling, so the identity carries no information about scheduling. Timeout and contention reasoning that rests on the summary's arithmetic instead of the config will be backwards.
18. **A step that invokes a script with bare `python3` may import only the standard library.** `uv run --frozen python <script>` resolves the locked environment; a bare `python3 <script>` resolves the runner's ambient interpreter, and a job whose only preceding step is `actions/checkout` has installed nothing. The script's own imports, and every module it imports transitively, must therefore be stdlib. This is not a style preference: a third-party import added to such a script fails at module load, before the first line of its logic, and takes a required check red on every PR. Six steps in `ai-spec-validation.yml` are in this shape today, at lines 126, 134, 142, 191, 209, and 242, covering `spec_extract_refs.py`, `spec_load_content.py`, `spec_prepare_context.py`, `spec_external_signal_wrapper.py`, `generate_spec_report.py`, and `check_spec_failures.py`. They feed the required check `Validate Spec Coverage`. Re-derive that list with `grep -n "run: python3" .github/workflows/ai-spec-validation.yml` rather than trusting these numbers, which drift. Confirm the trap rather than trusting this paragraph: `python3 -c "import markdown_it"` fails with `ModuleNotFoundError` while `uv run --frozen python -c "import markdown_it"` succeeds, so routing `spec_extract_refs.py` through `scripts/utils/markdown_parser.py`, whose line 16 reads `from markdown_it import MarkdownIt`, wedges the gate. The failure is invisible to local testing, because a contributor runs the script under `uv` and sees it pass. Before adding an import to any script a workflow calls with bare `python3`, run it with bare `python3` yourself, or change the step to `uv run --frozen python` in the same commit.

19. **A lefthook `timeout:` kill cannot be absorbed by a shell guard; an ordinary non-zero exit can.** Measured on lefthook v2.1.10, 2026-08-02, against a throwaway fixture repository holding one commit and one pre-push job. Four configurations produced four exit codes: `timeout: 2s` with `sleep 10 || true` exits 1, because the kill lands on the job's shell before the `||` branch runs; no `timeout:` with `sleep 3 || true` exits 0; no `timeout:` with `sh -c "exit 2" || true` exits 0; and the same command with the guard removed exits 1, which is the control proving the guard did the work in the third case. Those numbers describe one lefthook version on one date. The asymmetry they establish is the design constraint for any advisory job: a `|| echo` guard makes every failure mode non-blocking except the cap, so an advisory job's worst case has to be held under its own `timeout:` by the job's internal budget rather than by raising the cap. Rebuild the fixture instead of trusting this paragraph once the lefthook major version moves.

20. **Keep `#` out of a `run:` string unless the whole scalar is quoted.** A space followed by `#` opens a comment inside a YAML plain scalar, so `run: cmd || echo "see issue #4257 done"` loads as `cmd || echo "see issue`. The truncation leaves an unterminated quote, the shell exits non-zero on the syntax error, and a guard written to absorb failures becomes the thing that causes one. Confirmed with `yaml.safe_load` on 2026-08-02. Write the issue number without the `#`, or quote the entire scalar. `tests/ci/test_worktree_gc_wiring.py` pins the absence for the `worktree-gc-report` job.

10. **Prove the CLI exits nonzero on a failure the shell used to fail on**. A script under `scripts/ci` or `.github/scripts` that defines `main` MUST ship a test asserting a nonzero return from `main(argv)`, not only from a helper. The assertion has to sit in the same test that drives the CLI: the gate credits a nonzero assertion only where the test also calls that script's `main`, runs its path in a subprocess, or calls a local helper that does either. A `run:` block executes under `set -e`, so any command exiting nonzero fails the step. The natural Python translation returns a sentinel instead (empty string, `None`, empty list, a warning followed by `return 0`), and when no caller converts that sentinel into a nonzero exit the step goes green on a failure that used to be red. ADR-006 extraction is therefore a silent-pass generator, not only a silent-pass detector. Six instances were found in two extraction PRs, and three of them shipped tests that asserted the swallow. Every one of those tests asserted on a helper's return value, which structurally cannot catch an exit-code defect: the helper correctly reports failure, and nothing checks that the process does. `scripts/ci/cli_exit_contract_ratchet.py` enforces this as an equality ratchet from `pr-validation.yml`; the count may only fall. Refs Issue #4068.

21. **A stdin-consuming pre-push job MUST stay `piped: true`, never `parallel: true`, unless one producer job captures the ref-update stdin once into a push-scoped immutable artifact for every consumer to read instead of declaring its own `use_stdin: true`.** On Lefthook 2.1.10, parallel `use_stdin: true` jobs race the shared stream, so a consumer can receive a truncated or duplicated payload instead of the full copy `piped: true` delivers. Evidence: `.agents/sessions/2026-08-06-session-10003-profile-optimize-pre-submit-pre-commit-pre-push.json`.

22. **A job `name:` is a branch-protection identifier. Emit both names before requiring the new one.** GitHub matches a required status check against a workflow job's check-run name, which is the job `name:` or the job id when `name:` is absent. Composite-action metadata under `.github/actions/` does not create check runs by itself; only consuming workflow jobs do. Check the full protected-branch set, not one guessed ruleset: `gh api repos/OWNER/REPO/rules/branches/main --jq '[.[]|select(.type=="required_status_checks")|.parameters.required_status_checks[].context]'`. Compare it with check-run names from a fresh PR run, because `gh pr checks` cannot show a context that never ran. No-gap rename sequence: emit old and new names, merge to `main`, require the new context, remove the old requirement, then remove the old alias. The gap sequence is still valid but less safe: drop the old requirement, merge the rename, observe the new check, then require it. Requiring the new name before `main` emits it blocks every PR. Measured 2026-08-09: required `Session Protocol Results` and `AI Quality Gate Results` existed only on an unmerged PR, so `main` took no commits for five hours.

## SHOULD

1. **Thin workflows**. Workflow YAML SHOULD delegate to a testable module (ADR-006). No inline multi-step logic.
2. **Logging structure**. If another script, workflow step, or test parses a script's stdout, that script SHOULD emit JSON or `key=value` lines for the parsed fields, and the parser test SHOULD consume a real sample from that output shape. Human-only logs are exempt.
3. **Use skills when available**. SHOULD prefer `.claude/skills/<name>` over inline `gh`, `git`, or shell commands.
4. **Treat a repair to a silent failure as a silent-failure candidate.** MUST 10 through
   12 govern the original defect; this governs the fix. The tests written for the
   original exercise the original's inputs, and a repair usually changes which
   **values** the code can see rather than which branches it has, so every existing
   case keeps passing while the new value goes unexercised. After fixing one,
   enumerate the values the repaired expression can now receive and find the one the
   old code never saw. Measured across one defect in PR #5176, where four successive
   repairs each introduced a different silent failure and three were caught by a
   reviewer rather than by the suite being written for that class: redirecting stderr
   to quieten a producer also hid its parse errors; a default operator chosen without
   checking what it fires on triggered on `false` as well as `null`, collapsing a
   legitimate negative into unreadable; a coercion added to fix that did not check
   its input type, so the string `"true"` became boolean `true` and malformed
   evidence satisfied the guard built to reject it, invisible to five passing tests;
   and a new guard shipped without the comment skip its siblings had, so documenting
   the defect would have failed the gate. The third is the shape to fear: converting
   instead of validating fails open on the path the guard exists to protect.

## MUST NOT

1. MUST NOT put branching logic inside YAML workflow steps (ADR-006).
2. MUST NOT commit changes that silently change validator behavior without an ADR; validators are authoritative.
3. MUST NOT skip pre-push validation when touching CI paths.
4. MUST NOT raise a count baseline (`scripts/ci/*_count_baseline.txt`) to clear a blocked push. Those ratchets exist to refuse a new error-severity violation; raising the number defeats the gate rather than satisfying it. Fix the violation, split the file, or use the rule's documented escape (`# taste-lint: ignore <rule>` with a reason, issue #3779).

## Count ratchets

A count ratchet may only fall. Two consequences follow, and both bite in practice.

**A real improvement MUST be recorded.** An unrecorded improvement leaves slack, so the next regression up to the stale number passes silently. Lower it with the per-ratchet updater, not the shared module:

```bash
uv run --frozen --extra dev python scripts/ci/ruff_count_ratchet.py --update
```

`scripts/ci/count_ratchet.py --update <name>` reports success and changes nothing. Verify the file afterwards rather than trusting the message.

**The failure never names the offending file.** It reports a delta, and the remediation command it suggests prints the same aggregate. Locate the offender by diffing per-file counts against `origin/main`; the linter needs `--format json -- <files>` because with no file arguments it scans nothing and reports zero, which reads as a clean tree. Prove attribution instead of inferring it: `git rm --cached <suspect>` and re-run; if the ratchet returns OK, that file was the whole delta.

## Path filters gate the diff, never the tree

A path filter states that the verdict cannot change unless those paths change.
That is true for a check whose input is the diff. It is false for a check that
scores the whole tree. When the filter misses on a whole-tree check, the gated
job is skipped and its companion skip job reports success in its place. Nothing
is inherited from a previous run. A fresh green tick is manufactured, and it
asserts only that the diff was uninteresting.

Decide by the check's input, not by which paths look related:

| Check reads | Path filter | On `push` to `main` |
| --- | --- | --- |
| The diff | Correct | May skip |
| The whole tree | Wrong on the mainline | MUST run |

Delete the filter, do not force one event past it. `instruction-budget.yml`
now runs one unconditional job. Forcing only `push` leaves every PR
unmeasured, so two PRs each green against their own base still merge to a
breaching union. `determine_should_run_from_filters.py` still reads
`FORCE_RUN_EVENTS` for a diff-shaped check that wants a mainline run; no
workflow uses it today.

Do not reach for the concurrency group instead. Within one group GitHub keeps
one run in flight and one queued, and a newly queued run cancels the previously
queued one whatever `cancel-in-progress` says; that setting governs only the
running run. Measured 2026-08-02: 21 commits to `main` in 45 seconds produced 20
cancelled runs, each with `jobs=0` and a lifetime of 2 to 5 seconds.

Cancellation alone is survivable for a whole-tree check, because the surviving
run measures the tree as it now stands and nobody needs the intermediate states.
It stopped being survivable because the survivor also skipped on the path
filter. That window produced zero measurements and one green tick on a tree 201
bytes over its ceiling.

## References

- `.agents/architecture/ADR-006-thin-workflows-testable-modules.md`. Workflow pattern
- `.agents/architecture/ADR-042-python-migration-strategy.md`. Python-first
- `scripts/validation/pre_pr.py`. Canonical pre-PR runner
- `scripts/validation/check_skill_resolver_anchoring.py`. Enforces the anchoring requirement for `SKILL.md` resolvers
- `.claude/skills/validation-authority/`. Validator-authority skill
- Issue #1711. validator change that blocked all PRs
- Issue #3402. worktree identity and stale helper resolution
- Issue #3408. a linked worktree's imported session log wedging `check_branch_context`
- Issue #4262. gate merged red against its own corpus and blocked all pushes
- PR #4784. required-check rename landed after the ruleset required it, deadlocking every PR for five hours
