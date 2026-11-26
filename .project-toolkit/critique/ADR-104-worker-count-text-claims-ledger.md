# ADR-104 claims ledger: worker count text accuracy

This ledger was verified on 2026-11-26 against the working tree at base `dff887317c`.
It covers the 2026-11-26 amendment. That amendment fixes text only and changes no decision.

| Claim | Kind | Check | Result |
| --- | --- | --- | --- |
| PR #6364 set the hook cap to `scaled` on 2026-10-12. | quote | `git log -1 --format='%h %cs %s' 2c11076096` | `2c11076096 2026-10-12 perf(hooks): scale the pre-push pytest worker cap to the host (#6364)`. VERIFIED |
| PR #6295 added the CPU reserve on 2026-10-12. | quote | `git log -1 --format='%h %cs %s' 91b29a20c6` | `91b29a20c6 2026-10-12 perf(hooks): reserve a CPU for sibling jobs in the pre-push pytest run (#6295)`. VERIFIED |
| `lefthook.yml` sets `scaled` and a reserve of 3. | path | `grep -n` on `lefthook.yml` | Line 798 is `AI_AGENTS_PYTEST_WORKER_CAP: "scaled"`, and line 817 is `AI_AGENTS_PYTEST_CPU_RESERVE: "3"`. VERIFIED |
| The seed job pins a fixed cap of 4 and sets no reserve. | path | Read the `Build the testmon database` step env in `.github/workflows/pytest.yml` | The env has `AI_AGENTS_PYTEST_WORKER_CAP: "4"` and no reserve key. VERIFIED |
| PR #6364 kept the seed's integer cap on purpose. | quote | `git show -s --format=%B 2c11076096` | The body says: "The CI testmon seed workflow and the ADR-104 container recipe set an integer, so they do not change." VERIFIED |
| The seed runner has 4 vCPUs. | behavior | `.project-toolkit/analysis/testmon-prepush-measurements.md:65` and `runs-on: ubuntu-latest` | The analysis records "4-vCPU runners" for run 38015601869. The runner size is set by the host, not this repository. INFERRED |
| The scaled cap is half the CPUs, at least 4 and at most 16, and never above the CPU count. | behavior | Read `scaled_worker_cap` and `PYTEST_SCALED_WORKERS_MIN`/`MAX` in `scripts/validation/git_hook_policy.py` | `max(4, min(n // 2, 16))`, then `min(.., n)`. VERIFIED |
| Workers are 1 at 4 threads, 2 at 5, 3 at 6, 4 at 7 or 8, and 16 at 48. | count | `local_worker_budget(scaled_worker_cap(n), n, 3)` for each n | 4:1, 5:2, 6:3, 7:4, 8:4, 48:16. VERIFIED |
| A reserve of 3 on a 4-vCPU runner leaves one worker. | count | `local_worker_budget(4, 4, 3)` | 1. VERIFIED |
| `AI_AGENTS_PYTEST_WORKERS=auto` wins over the cap and the reserve. | behavior | Read `_pytest_parallel_flags` and `_pytest_cpu_reserve` | Both skip the cap and the reserve when the override is set. VERIFIED |
| `tests/workflows/test_testmon_seed_job_build.py` pins the seed cap and the missing reserve. | path | Run the test. Plant a reserve in the seed env, then run it again. | 7 tests pass. With the planted reserve, 1 test fails on the reserve assertion. VERIFIED |

## Exit gates

| Gate | Result |
| --- | --- |
| 1. Claims ledger | VERIFIED. Eleven rows above. One row is INFERRED: the host sets the runner size. |
| 2. Documentation accuracy (doc-accuracy Phase 4, one Sonnet agent) | VERIFIED. Fifteen claims were checked against the code, and none was wrong. No contradiction with unchanged text was found. |
| 3. Self-consistency | VERIFIED. The amendment changes no decision. The seed paragraph, the gap bullet, and the Implementation Notes give the same formula and numbers. |
| 4. Refuting seat (analyst, Haiku) | VERIFIED. Factual findings: 0. Rows 1, 2, and 5 were UNAVAILABLE to the seat, which could not run git. The writer's `git log` output above covers them. |
