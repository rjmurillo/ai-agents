# Historical issue-to-fix control subtraction: protocol v2

Issue #6814. Supersedes `PROTOCOL.md` (v1) for the primary result. Committed
before any v2 live launch.

## Why v1 was not enough

The v1 batch (`2026-10-21-pilot-v1-invalid/`) ran under a harness defect. The
runner was launched as `.venv/bin/python` instead of under `uv run`, so the
agent's `PATH` did not hold the runner's interpreter. Its `python3` resolved to a
system Python with no pytest, and `uv` is outside the Bash allowlist. In all 8
runs the agent reported it could not run the tests; the run entries'
`trajectory.bash_commands` show each attempt. That falsifies v1's premise that
the agent can run the acceptance check, so v1 is published as an invalid pilot,
not as the result.

## The one change

The runner now starts every Claude child's `PATH` at the directory of the
interpreter that runs the checks (`report.json` records it as
`provenance.agent_path_first`), so the agent's `python3` is the same
interpreter, with pytest, that grades it. Bash allowlist, tools, permission
mode, and everything else are unchanged.

## Unchanged from v1

Task, base and fix commits, seeded paths, allowed scope, the prompt, both
checks and the deselected node, `known_good` and `known_bad`, controls `full`
and `minus:.claude/rules/voice.md`, model `claude-sonnet-5-5`, 4 repetitions
per arm interleaved, 0 retries, 900 s per launch, `--max-runs 8`,
`--max-cost-usd 25`, auth flags, per-run fields, abort conditions, and the
decision rule, all as written in `PROTOCOL.md`.

The decision rule and repetition count were declared in v1 before any score
existed. v1's scores were seen before this file was written; nothing in the
rule or the repetitions changes in response to them.
