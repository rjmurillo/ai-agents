# Host-Contention and `.venv` Poisoning Analysis (2026-11-26)

Supporting empirical record for the 2026-11-26 amendment to
[ADR-104](../architecture/ADR-104-gate-tier-placement-and-budgets.md).

## 1. Host-Contention Telemetry (Poisoned-Fleet Incident Window)

Captured on 2026-11-26 on the owner's shared 48-vCPU Linux workstation running
multiple concurrent git-worktree agent sessions (144 samples at 5 s intervals
across a 715 s window, `20:48:50Z` to `21:00:45Z`; raw artifacts archived
outside the repository).

| Metric | Measured Value | Scope / Notes |
|---|---|---|
| Total host CPU utilization | 90.4% busy (user 69.2% = 33.2 CPUs, system 21.0% = 10.1 CPUs) | 144 samples over 715 s |
| 1-minute load average (`load1`) | min 40.9, median 117.2, p90 181.1, max 208.7 | Median load exceeded the 48-vCPU count |
| `hook:python-tests` CPU share | 19.99 CPUs (41.6% of all 48 vCPUs) | >10x `hook:pre-pr-validation` (1.81 CPUs, 3.8%) |
| Peak concurrent pytest processes (`20:50:10Z`) | 34 pytest controllers (31 under lefthook), 106 xdist workers | 102 of 142 distinct pytest invocations under lefthook; only 14 ran with `--testmon` |
| 180 s selection budget overruns (6 h, 621 session/task logs) | 108 occurrences across 22 files | 36x ADR-104's `> 3/month` re-evaluation trigger in 6 hours |
| Headroom wait timeouts (`headroom_timeout_run_anyway`, 6 h) | 51 occurrences across 10 files | Load never cleared before wait expiry; fail-open remediation tracked separately |
| Signal kills & load-retry storms (6 h) | 59 `signal_killed` (11 files), 59 `load_note_retry` (15 files) | Suite item counts reached 81,060 |
| Explicit full-suite opt-in (8 h, 678 transcripts) | 35 sessions passed `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1` | Triggered after 180 s overruns blocked pushes |

## 2. Root Cause of Testmon Degradation (`.venv` Poisoning)

Audit across 121 worktree `.venv` directories on 2026-11-26:

1. `validate_unused_dependencies` in `scripts/validation/checks_ci_parity.py`
   invoked:
   `uv run --frozen --extra dev --extra eval python scripts/validation/check_unused_dependencies.py`
   during `pre-pr-validation` without `--isolated`.
2. `pyproject.toml` declares `openai>=2.45.0` under `[project.optional-dependencies] eval`.
   Because `uv run` mutates the project `.venv` in place unless `--isolated` is
   passed, running `pre_pr.py` installed `openai==3.51.0` (and transitives) into
   the worktree's `.venv`.
3. **Contamination count**: 44 of 121 worktree `.venv`s contained `openai-3.51.0`
   (38 mutated on 2026-11-26, 4 on 2026-11-25, 1 on 2026-11-24, 1 on 2026-11-03).
4. **Testmon mismatch**: CI's `testmon-seed` job (`.github/workflows/pytest.yml`)
   builds `.testmondata` via `setup-code-env` (`install_locked_deps.py`,
   `EXTRA = "dev"` only, omitting `eval`). All 16 of 16 worktrees containing
   both `openai` and `.testmondata` hit a pytest-testmon package-version
   mismatch (`venv-only=['openai 3.51'] db-only=[]`), discarded selection, and
   fell back to running all 81,060 tests locally.

### Isolated Deptry Verification (2026-11-26)

Adding `--isolated` to `validate_unused_dependencies` runs `deptry` in an
ephemeral `uv` environment locked to `uv.lock` without touching `.venv`.

- **Measured warm wall-clock cost** (3 consecutive runs on the 48-vCPU host):
  `2.26 s`, `2.45 s`, `2.21 s` real (`Installed 123 packages in 82-112 ms`).
- **Verification**: `check_unused_dependencies.py` exited 0 (`34` declared
  packages checked across 3 manifests in `.github/dependency-hygiene/policy.toml`),
  and full `pre_pr.py --compact` completed with `openai` absent from `.venv`
  (`importlib.metadata` check returned `[]`).
- **Offline / cold-cache behavior**: `--frozen` requires locked wheels from the
  uv cache or PyPI; if offline with no cached `eval` wheels, `uv run --isolated`
  exits non-zero and `validate_unused_dependencies` fails closed (`False`).
- **Existing worktree cleanup**: `--isolated` stops future contamination; clean
  already-contaminated `.venv`s with `uv sync --frozen --extra dev`.

## 3. Structural Contention Independent of `.venv` Poisoning

The incident numbers in Section 1 were amplified by `.venv` poisoning (only
14/102 lefthook pytest invocations ran with `--testmon`). Even with `--isolated`
fixed and clean `.venv`s, running pytest or whole-tree collection on every
`git push` remains structurally unsuitable on a shared multi-worktree host:

1. **Suite scale & collection floor**: The suite grew ~3x from ~27,900 tests
   (2026-08-25) to 49,808 (2026-10-13) to 81,060 items (2026-11-26). Measuring
   `scripts/validation/check_zero_collection_tests.py` alone on the same 48-vCPU
   host when idle (`load1 = 1.94`) across 2,697 test files cost **`34.23 s` warm**
   (`32.78 s` user, `1.45 s` sys) and **`87.48 s` cold `.venv`**. Whole-tree
   collection under `pytest --testmon` pays a comparable floor on every push.
   Multiplied across 15-30 concurrent agent worktrees, even healthy collection
   creates sustained CPU saturation.
2. **Whole-tree contract for `zero-collection-tests`**: `zero-collection-tests`
   cannot be diff-scoped or glob-gated (`rule-ci-scripts.md` forbids filtering a
   whole-tree guard to changed files, and CI's `zero-collection-guard` already
   runs unconditionally in `.github/workflows/pytest.yml` and gates required
   `Run Python Tests`).
3. **Brittle lockfile invalidation & retry cascade**: Any `uv.lock` or
   `pyproject.toml` change (2 of 8 replayed main commits in the 2026-10-08 trial)
   or cold/expired seed forces full-suite re-selection across every active
   worktree, hitting the 180 s step budget and driving agents to pass
   `AI_AGENTS_PYTEST_FULL_SUITE_LOCALLY=1`.
4. **Rule 4 & Context-vs-Core duplication**: CI `.github/workflows/pytest.yml`
   runs `zero-collection-guard` and all 8 pytest partitions unconditionally
   (no `needs:`, no job-level `if:`) on `push` to `main`, `pull_request`, and
   `merge_group`, gating required context `Run Python Tests`. Local pre-push
   pytest duplicates that required CI gate at higher shared-host contention cost.
