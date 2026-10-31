---
type: metrics
id: hook-latency-6734
title: Pre-commit and pre-push latency baseline at d7ae505
epic: EPIC-5456
issue: 6734
created: 2026-10-20
status: draft
---

# Pre-commit and pre-push latency baseline, d7ae505

Slice 1 of issue #6734 (owner decision 2026-10-20: option A, measure and map
ownership, move nothing). The ownership table is
`.project-toolkit/metrics/hook-ownership-6734.md`. The per-run artifacts in
`hook-latency-6734/` hold every repetition and every job sample behind the
figures below. The spec is `.project-toolkit/specs/SPEC-6734-hook-latency-and-ownership.md`.

## Method

One 4-CPU Linux container (Python 3.14.7, lefthook 2.2.2), 2026-10-20. Nothing
else ran during the capture except file reads by the measuring session. Every
figure comes from `scripts/metrics/gate_latency.py` running the whole hook,
never `--job` (`ci-scripts.md` MUST-16).

- **Pinned code.** Base commit `d7ae505961f1c03b834a4b8b219bc56fdb969841`
  (`origin/main` on 2026-10-20). Each change class gets one fixture commit on
  top of it that edits only that class's file. So the outgoing range is one
  real commit, and the hook sees the file through `--file` and through the
  pushed range:

  | Class | Kind | File | Edit | Fixture commit |
  |---|---|---|---|---|
  | `markdown` | docs-only | `README.md` | last line `MIT` becomes `MIT (see LICENSE).` | `05966ee55` |
  | `python` | code | `scripts/ci/lefthook_budget_model.py` | one trailing comment line | `90af99ede` |
  | `workflows` | security-sensitive | `.github/workflows/pytest.yml` | one trailing comment line | `d44913c9a` |

  `workflows` is the security-sensitive class. It fires the action-pin,
  workflow-validation, and actionlint checks at pre-commit and
  `workflow-local-run` at pre-push. The fixture commits exist only in the
  measuring clone. The edits above recreate them, but their SHAs will differ.
- **Pre-push input.** A first push of a new branch, the usual agent case: hook
  args `origin https://github.com/rjmurillo/ai-agents.git`, and stdin
  `refs/heads/claude/measure-6734-<class> <fixture sha> refs/heads/claude/measure-6734-<class> 0000000000000000000000000000000000000000`.
- **Repetitions.** 21 per hook and class, one hook run at a time. Repetition 0
  is the first run after `git checkout` of the fixture branch. The warm sample
  is the first 20 complete repetitions after it. A failed repetition is
  excluded from the warm figures and listed below. 5 of the pre-push workflows
  cell's 20 warm repetitions failed, which left it at n=15, so that cell got a
  7-repetition top-up with the same command after the main capture
  (`hook-latency-6734/topup-pre-push-workflows.*`). Its repetition 0 is again
  first-after-checkout and excluded, and its complete repetitions fill the
  warm sample to 20 after the main capture's. 133 runs in all. Percentiles are
  nearest rank, computed with the sampler's own `_nearest_rank_percentile`.
- **Instrument fix.** `lefthook.yml` sets `output: false`, so lefthook printed
  no summary and the sampler parsed zero jobs, keeping only the hook wall
  clock. The sampler now sets `LEFTHOOK_OUTPUT=summary,failure` on the hook it
  runs. That changes what lefthook prints, not which jobs run.
- **Load.** Each repetition records the 1-minute load average before and after
  it. The load column is the min and max of those readings. They are taken
  between runs, so they miss the peak inside a run.
- **Recorded commands.** Each artifact's `command` field is the command as it
  ran. Its `--json` and `--markdown` paths point at the scratch directory the
  run wrote to, and `--repo` reads `<repo>` (the fixture clone). That scratch
  path is replaced with `<scratch>`, the same way the sampler writes `<repo>`,
  so no session path lands in history. The markdown files are otherwise
  unchanged. The JSON files were re-serialized compactly
  (`json.dumps` with no indent, checked equal to the original with
  `json.loads`), so each is one line and stays under the taste-lint file-size
  ceiling.

## Exclusions, stated before the numbers

- **True cold setup is not measured.** Pilot runs had already warmed the `uv`
  cache, the venv, the testmon database, and the semgrep rules before
  repetition 0. That column means "first run on this tree", not "first run on
  a fresh clone". A fresh clone also pays `uv sync`, which runs outside the
  hooks.
- **`workflow-local-run` measured its degraded path.** It needs `act`, which
  this container lacks, so it passed in about a second. On a machine with
  `act` it can run up to its 30m cap. The workflows-class pre-push figure is a
  floor for that job.
- **Missing optional tools.** `actionlint` and `yamllint` are not installed
  here. Pre-commit `actionlint` skipped, and `pre_pr.py` recorded `Workflow
  YAML Validation` and `YAML Style Validation` as `BLOCKED` (`tool.absent`),
  which `scripts/validation/evidence.py` `default_pre_pr_policy` licenses as
  non-blocking.
- **One host.** These figures describe this box. MUST-16 records a job running
  much slower inside a loaded push than alone. Do not carry a figure here to
  another host as a planning number.
- **Network.** `push-ref-staleness`, `security-scan`, and `bot-cascade-advisory`
  can reach the network, which widens the tail.

## Headline

| Hook | Class | Repetition 0 (s) | Warm n | Warm p50 (s) | Warm p95 (s) | Warm max (s) | Failed | Load 1-min range |
|---|---|---|---|---|---|---|---|---|
| pre-commit | markdown | 33.2 | 20 | 34.2 | 35.5 | 35.7 | 0 | 0.69 to 1.36 |
| pre-commit | python | 29.4 | 20 | 30.1 | 32.8 | 35.0 | 0 | 1.22 to 2.22 |
| pre-commit | workflows | 32.8 | 20 | 30.2 | 33.1 | 33.4 | 0 | 1.00 to 1.68 |
| pre-push | markdown | 334.9 | 20 | 327.8 | 350.3 | 354.5 | 0 | 0.81 to 1.19 |
| pre-push | python | 308.3 | 20 | 327.0 | 367.4 | 383.4 | 0 | 0.80 to 1.19 |
| pre-push | workflows | 389.3 | 20 | 355.1 | 373.3 | 396.6 | 5 | 0.06 to 8.02 |

Repetition 0 sits inside the warm range in every row. On this box, after the
pilots, there was no cold penalty left to measure (see Exclusions).

| Hook | Class | Five most expensive jobs by warm p50 (seconds) |
|---|---|---|
| pre-commit | markdown | `agents-write-targets` 27.8, `markdown-autofix` 1.9, `markdown-check` 1.9, `context-output-check` 1.3, `taste-advisory` 0.6 |
| pre-commit | python | `agents-write-targets` 27.7, `subprocess-encoding` 15.3, `context-output-check` 1.3, `taste-advisory` 0.9, `security-suppressions-staged` 0.8 |
| pre-commit | workflows | `agents-write-targets` 27.8, `context-output-check` 1.3, `taste-advisory` 0.8, `action-pin-policy` 0.8, `yaml-advisory` 0.8 |
| pre-push | markdown | `pre-pr-validation` 251.6, `count-ratchets` 72.5, `zero-collection-tests` 42.4, `python-unreachable-statements` 42.0, `python-tests` 30.3 |
| pre-push | python | `pre-pr-validation` 231.5, `count-ratchets` 71.1, `zero-collection-tests` 42.6, `python-unreachable-statements` 42.0, `security-scan` 21.2 |
| pre-push | workflows | `pre-pr-validation` 241.0, `count-ratchets` 75.0, `python-unreachable-statements` 44.4, `zero-collection-tests` 44.0, `security-scan` 31.2 |

## Failed repetitions

Each fixture commit is a one-line change that passes every check when run on
its own, so no failure below comes from the diff. Why each gate failed is not
known: the sampler keeps job timings, not job output.

| Hook | Class | Capture | Repetition | Exit | Wall (s) | Load before | Failed job (seconds) |
|---|---|---|---|---|---|---|---|
| pre-push | workflows | main | 2 | 1 | 89.0 | 1.02 | `count-ratchets` (85.2) |
| pre-push | workflows | main | 3 | 1 | 388.2 | 7.16 | `pre-pr-validation` (268.7) |
| pre-push | workflows | main | 5 | 1 | 93.8 | 0.84 | `count-ratchets` (90.0, lefthook `timeout: 90s`) |
| pre-push | workflows | main | 8 | 1 | 90.3 | 1.05 | `count-ratchets` (86.3) |
| pre-push | workflows | main | 15 | 1 | 89.6 | 0.95 | `count-ratchets` (85.1) |

All 5 failures are in one cell: 5 of 28 pre-push workflows runs (21 main plus
7 top-up), against 0 of 42 pre-push runs in the other two classes. All 5 fell
in the main capture, which ran first; all 7 top-up runs passed. Whether the
class content or the time of the run caused the clustering is not
established, so this record gives no pooled failure rate.

Repetitions run back to back, so a killed run leaves its load on the next
one. Four repetitions of that cell started under load above 2: rep 3
(7.16, then failed), rep 6 (8.02), rep 9 (6.60), and rep 16 (4.52). Rep 3's
failure may be that spillover rather than a gate defect. Rep 6 is the
cell's 396.6s maximum. Without reps 6, 9 and 16 the cell is n=17, p50 355.1s,
p95 373.3s, max 373.3s, so the spillover moved the maximum and nothing else.
The other two pre-push cells had no start above 2.

## What the numbers say

**`count-ratchets` runs at its own deadline.**
`scripts/validation/checks_ratchet.py:177` sets `_AGGREGATE_TIMEOUT_SECONDS = 85`,
an aggregate deadline under the job's 90s lefthook cap (`lefthook.yml:542-543`). Across the 60 complete warm pre-push
repetitions, the job measured p50 72.5s, p95 80.5s, and max 82.8s. Those
figures are censored: the job was killed at its deadline in 4 of 66 warm
attempts, and a killed run has no finishing time, so its true tail runs to
85s and beyond. Read the 1.1x headroom below as an upper bound. The module's own comment
records this failure mode under load average 6.2 and says it is "not
eliminated". Here it fired with the 1-minute load near 1.0 before each run.
The readings taken when those four runs stopped, about 90s in, were 4.52 to
8.02 on 4 CPUs, while every complete run of that cell read 1.11 or less at its
end, about six minutes in. So the load at the deadline is the push's own fast stage:
`count-ratchets` shares a `parallel: true` group with six other jobs
(`lefthook.yml:540`). INFERRED, since no reading was taken inside the run.
This is the gate #6734 item 5 describes: a check that fails a clean change for
reasons unrelated to the change.

**Pre-push misses ADR-104's 300s target in every class.** Warm p95 is 350.3s
to 373.3s. ADR-104's re-evaluation trigger, "a real push measures the pre-push
hook above 300s", fired on this box. These are fixture pushes on one
container with `workflow-local-run` degraded, not a developer's push, and
ADR-104 names a maintainer comment on #5315 as the mechanism; that comment is
the owner's call. The v0.7.0 record measured 124.56s median
for the markdown class on 2026-09-16, also on a 4-CPU container. Hook
composition changed between the two SHAs, so the ratio says nothing about any
single job.

**`pre-pr-validation` is most of every push.** It ran at p50 240.4s across its
60 warm samples, against a hook p50 of 327s to 355s. One extra
diagnostic run of the python class with lefthook success output enabled
(`hook-latency-6734/diagnostic-pre-push-python-gates.txt`, every gate's timing
line unedited) shows why: `pre_pr.py` ran 115 gates
one after another in 246.4s: 104 `PASS`, 1 `ADVISORY`, 7 `SKIP` (5 of them
deferred to the pre-push job that already ran them), and 3 `BLOCKED` (the two
missing optional tools, plus the advisory `Active Plan Closeout`, which could
not reach the GitHub API from this container). No single gate dominates. The
slowest:

| `pre_pr.py` gate | Seconds | Same work elsewhere in the hooks |
|---|---|---|
| Legacy .agents Write Targets | 24.8 | pre-commit `agents-write-targets` (27.8s p50) |
| Plugin-Root Interpreter | 19.3 | none |
| Documented Interpreter Portability | 15.4 | none |
| Skill Markdown Portability | 15.2 | none |
| Subprocess Encoding Convention | 15.1 | pre-commit `subprocess-encoding` (15.3s p50) and a `count-ratchets` registry entry |
| Python Syntax (compile gate) | 12.8 | none |
| Active Plan Closeout Advisory | 12.0 | none |
| Generated Artifact Staleness | 11.9 | pre-commit `generate-agents` family |

Its warm p50 sits next to the `PRE_PR_OUTER_CAP_SECONDS=240` run budget that
`lefthook.yml` declares for it. That budget does not stop the run: it only
clamps the deadline of the Generated Artifact Staleness gate
(`scripts/validation/check_generated_staleness.py:84`), which reports
EXTERNAL instead of starting when too little time is left, and every other
gate runs to completion. So the 240s figure measures the gates, not the cap.
Whether the one `pre-pr-validation` failure (rep 3, 268.7s) was that gate is
unknown. The headroom wait is not the cause: in the
diagnostic run only semgrep waited for host headroom, 15.0s at load 4.8.

**Pre-commit is one job.** `agents-write-targets` runs on any staged file
matching its broad glob and then scans the whole index (`lefthook.yml:226`).
It costs 27.8s of the 30s to 34s pre-commit wall clock in every class, and
`pre_pr.py` runs the same scan again at push time. It entered `lefthook.yml` on
2026-09-22 (#5887), after the v0.7.0 capture. That plausibly accounts for most
of the pre-commit change since then (9.66s median then, 34.2s now, markdown
class); INFERRED, because other jobs changed between the two SHAs too.
Python commits also pay `subprocess-encoding` (15.3s), which runs again inside
`pre_pr.py` and inside `count-ratchets`.

## Proposed budgets, not enforced

Each row states its basis; not every figure comes from p95. One caveat first:
warm figures count passing repetitions only, and 5 of 28 pre-push workflows
runs failed with no cause in the diff (0 of 42 in the other classes), so the
ceiling below is a floor for a loaded push, not a bound on one. These are
proposals for the owner, not caps:
`ci-scripts.md` MUST-16 and ADR-104 both say a cap sized on an idle run is a
cap a loaded push can exceed. Nothing here changes a `timeout:`.

| Hook | Measured p95 | Proposed ceiling | Proposed target | Basis |
|---|---|---|---|---|
| pre-commit | 35.5s | 60s (ADR-104, unchanged) | 10s, conditional | The ceiling keeps 1.7x headroom over the worst class's p95. The target is not a p95 figure: it assumes the two scans (`agents-write-targets`, `subprocess-encoding`) leave the commit path in slice 3. Outside them no job's p50 exceeds 2s, but their p50s are not additive (most share one parallel group), so the target holds only if a re-measure after slice 3 confirms it. |
| pre-push | 373.3s | 400s, regression tripwire | 300s (ADR-104, unchanged) | Max-based, not p95-based: 400s sits above the worst warm run that started on a quiet box (383.4s, python) and the worst overall (396.6s, which started at load 8.02 after a killed run), so a regression past today's worst shows. A tripwire near the max of 20 runs also trips by chance, at most about once in 21 runs of an unchanged hook, so one trip is a prompt to re-measure, not proof of a regression. It is not a revised target; ADR-104 rule 5 says a check that exceeds its tier's target is replaced, not given a raised target. Reaching the target at p95 needs about 50s to 75s out of `pre-pr-validation`. The two duplicated scans above are 39.9s of it. |

Per-job headroom is the cap over the job's warm p95 pooled across the three
pre-push classes (or pre-commit classes for `agents-write-targets`):
`count-ratchets` 1.1x at most (85s deadline, censored as above), `python-unreachable-statements` 1.7x (90s),
`pre-pr-validation` 2.0x (9m cap), `agents-write-targets` 4.0x (2m),
`zero-collection-tests` 5.0x (4m), `path-normalization` 5.2x (90s). The first
two are the ones a loaded push will kill.

## Reproduce

Build the fixture clone once, from a clone of this repository with `uv sync
--frozen --extra dev` done in it. Each branch is the base plus one commit:

```bash
git -C <clone> checkout -B claude/measure-6734-markdown d7ae505961f1c03b834a4b8b219bc56fdb969841
sed -i 's/^MIT$/MIT (see LICENSE)./' <clone>/README.md
git -C <clone> commit -am "test(metrics): latency fixture for markdown change class"

git -C <clone> checkout -B claude/measure-6734-python d7ae505961f1c03b834a4b8b219bc56fdb969841
printf '\n\n# Read-only model: nothing in this module writes to lefthook.yml.\n' >> <clone>/scripts/ci/lefthook_budget_model.py
git -C <clone> commit -am "test(metrics): latency fixture for python change class"

git -C <clone> checkout -B claude/measure-6734-workflows d7ae505961f1c03b834a4b8b219bc56fdb969841
printf '      # Alert step stays last so it sees every upstream result.\n' >> <clone>/.github/workflows/pytest.yml
git -C <clone> commit -am "test(metrics): latency fixture for workflows change class"
```

Then, from a checkout carrying this change, with `<clone>` on the class
branch, run the hook one class at a time. Pre-commit takes no hook args or
stdin:

```bash
uv run --frozen python scripts/metrics/gate_latency.py --repo <clone> \
  --hook pre-commit --change-class python --repetitions 21 \
  --json pre-commit-python.json --markdown pre-commit-python.md
```

Pre-push takes the remote args and a first-push ref line:

```bash
uv run --frozen python scripts/metrics/gate_latency.py --repo <clone> \
  --hook pre-push --change-class python --repetitions 21 \
  --hook-arg origin --hook-arg https://github.com/rjmurillo/ai-agents.git \
  --stdin-ref-line "refs/heads/claude/measure-6734-python <sha> refs/heads/claude/measure-6734-python 0000000000000000000000000000000000000000" \
  --json pre-push-python.json --markdown pre-push-python.md
```

Warm statistics are the first 20 repetitions with `status == "complete"`
after repetition 0 of each JSON file. For the pre-push workflows cell that is
the 15 complete main repetitions followed by top-up repetitions 1 to 5, using `_nearest_rank_percentile` from
`scripts/metrics/gate_latency_stats.py`.
