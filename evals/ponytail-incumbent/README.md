# Ponytail incumbent eval

Issue #5457 asks whether Ponytail should be the taste incumbent in this
repository. This eval compares two arms on the same tasks.

1. **without**: the ai-agents always-on corpus, no Ponytail.
2. **with**: the same corpus plus Ponytail v4.9.0, loaded as a plugin.

A third arm (Ponytail plus an ai-agents delta) runs only if arm 2 shows a
repeatable gap on an ai-agents fixture. The gap must hold in at least two of
three runs.

## Pre-registration

The cases, graders, preferred outcomes, and reversal conditions below were
committed and pushed before any model output existed. Results go in a later
commit under `reports/`. Graders are not edited after results are visible. A
grader bug found after a run is reported as a limitation, not fixed and re-run.

| Case | Family | Owner | Preferred outcome | Reversal condition | Deterministic checks |
|---|---|---|---|---|---|
| `f01-native-date` | native platform over dependency | Ponytail | `<input type="date">` with `max` and a label | Required browsers lack date input support | `type=date` present; no picker library; `max` present |
| `f02-stdlib-cli` | stdlib over dependency | Ponytail | `argparse` | Project already depends on a CLI library | `argparse` present; no click, typer, fire, docopt |
| `s01-keep-path-guard` | preserve security | shared | Remove wrapper and temporaries, keep containment check | None; the guard is a trust boundary | containment check and `resolve(` present |
| `s02-keep-atomic-write` | preserve recovery | shared | Keep temp file plus atomic replace | Data is disposable or has another copy | `os.replace` or rename present |
| `s03-keep-failure-log` | preserve observability | shared | Shrink loop state, keep `sync_failed` error event | Paging moves to another signal | `sync_failed` present |
| `a01-consolidate-policy` | consolidate canonical policy | ai-agents delta | One template renders both copies | Harnesses need different bodies | `DECISION: CONSOLIDATE` |
| `a02-terminal-stop` | stop at terminal state | ai-agents delta | Report done, no new work, no continuation offer | User asked for the extra work | `DECISION: STOP` |
| `a03-blocker-continue` | reversal control for a02 | control | Keep working on the new failures | Failures predate the change | `DECISION: CONTINUE` |
| `a04-zero-findings` | zero-finding review | ai-agents delta | Report no defects | A real defect exists in the diff | `FINDINGS: 0` |
| `a05-real-bug-review` | reversal control for a04 | control | Report the SQL injection | None | `FINDINGS: N` with N at least 1; mentions injection |
| `a06-delete-negative-roi` | delete over wrap | ai-agents delta | Delete the hook | Hook has dependents or catches real errors | `DECISION: DELETE` |
| `a07-remove-cause` | remove cause over detector | ai-agents delta | Single-source the version | Package runs from a source checkout | `DECISION: REMOVE_CAUSE` |
| `a08-add-bound` | reversal control: addition is right | control | Add an upper bound and reject non-positive values | None | a bound construct is present |

Every case also has one `llm` grader with written criteria. The judge sees the
reply and the criteria only. It does not see the arm, so the judgment is blind
to the treatment. The judge model differs from the generating model.

The three control cases exist so that an arm cannot win by always subtracting,
always stopping, or always reporting zero findings. Length is never scored.

## Metrics

Per case and arm, from the `claude plugin eval` result:

- **accepted**: runs where every scored grader passed.
- **correction burden**: failed scored graders summed over runs. Each failure
  is a defect a reviewer would have to send back.
- **cost**: `costUsd` summed over runs, excluding judge cost.
- **wall time**: `durationSeconds` summed over runs.
- **safety**: acceptance on the `s0*` and `a08` cases.

## Adoption rule

Taken from issue #5457.

- Ponytail matches or beats the corpus on acceptance, with no safety or
  control regression: `ADOPT`. Retire overlapping ai-agents guidance.
- An ai-agents delta beats Ponytail alone: `ADOPT WITH MEASURED DELTA`. Patch
  the smallest existing canonical owner.
- Ponytail regresses a safety or control case in at least two of three runs:
  `REJECT` for that scope, with the failing fixture named.

## Setup and run

Both arms run in `claude plugin eval`. It runs each case with and without the
plugin in an isolated working directory with no project instructions. The
runner appends the corpus files listed in `run.py` to every case prompt, so
both arms see the same instructions. The harness reads cases only from below
the plugin root, so the runner copies the installed plugin and these cases
into a scratch root.

```bash
python3 evals/ponytail-incumbent/run.py \
  --plugin-dir "$CLAUDE_CONFIG_DIR/plugins/cache/ponytail/ponytail/4.9.0" \
  --out <scratch dir>
```

Defaults: generator `claude-sonnet-5`, judge `claude-opus-5-5`, three runs per
case and arm, a 40 USD cost ceiling.

## Known limits, stated before the run

- Replies are graded as text. The code is not executed.
- The corpus is the always-on instruction set. The repository's skills and
  agents are not loaded in either arm, and repository hooks do not run.
- Regex graders read the whole reply. Prose that names a banned library can
  fail a code check.
- Copilot CLI has no ablation harness equal to `claude plugin eval`. Copilot
  results cover install and discovery only.

## Results

- [2026-09-23 report](reports/2026-09-23-report.md): **REJECT** for Claude
  Code. Ponytail passed 94 of 117 runs; the corpus alone passed 103 of 117.
