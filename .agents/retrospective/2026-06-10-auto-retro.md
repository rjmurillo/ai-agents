# Retrospective: 2026-06-10

## Session Context

Session 2381 (`claude/pre-push-gate-python-uv-7x757l`, merged as PR #2529): made
`scripts/bootstrap-vm.sh` provision the pinned Python (3.14.5) via uv instead of
a pyenv source compile, so the pre-push gate runs on fresh Claude web containers
without manual setup. Follow-ups landed via PR #2538 (Pester/powershell-yaml
install guards) and the CONTRIBUTING.md `uv sync` doc fix.

### Work Items

- Diagnose: fresh container had uv 0.8.17 (predates CPython 3.14.x downloads),
  python3 at 3.11, and a pyenv compile that blew the SessionStart hook budget.
- Implement: uv capability check plus standalone-installer refresh,
  `uv python install --default`, `uv sync --frozen --extra dev`, venv-first PATH.
- Verify: ran the real bootstrap in the failing container; the full pre-push
  gate served as the end-to-end test.
- Curate: superseded the two Serena memories that prescribed pyenv 3.12.8.

## Failure Mode Classification

Per `.agents/governance/FAILURE-MODES.md`: FM-9 Confident-incorrectness
recurrence (claims made from a mental model instead of an executed check). Two instances below, both
caught before merge. Evidence: PR #2529 review round (commits 2bfa8d7, 4a159a1,
2b6b1fa), PR #2538.

## What Went Well

- Diagnosed in the target runtime, not by analogy: the container itself had the
  exact failure state, so every fix was verified against the real contract
  (bootstrap exit 0, gate probe on 3.14.5, idempotent re-run).
- Capability check over version compare: `uv python list "$PIN"` detects a
  too-old uv without hardcoding a minimum uv version that would itself drift.
- The pre-push gate doubled as the end-to-end test for the change that fixes
  the pre-push gate; every push exercised the deliverable.
- All five review threads (Gemini, Cursor bugbot, Semgrep) closed with code
  fixes in the same round, no re-litigation.

## What Could Improve

- A "best-effort" fallback shipped briefly that could never succeed:
  `uv pip install --system --python <pin>` always fails on uv-managed
  interpreters (PEP 668). Caught only because the fallback was executed during
  verification. Execute every fallback path once before shipping it.
- The "CONTRIBUTING.md still documents pyenv" follow-up recorded in PR #2529
  was stale: the file was already uv-based. Verify doc-drift claims against
  the file before recording them as follow-ups.

## Key Learnings

- uv-managed interpreters are PEP 668 externally-managed; project deps can only
  live in a venv. The venv-first PATH pattern is the supported way to give bare
  `python3` the project environment.
- `uv self update` queries the GitHub API and gets rate-limited on shared
  container egress; the astral.sh standalone installer is the reliable refresh
  path.
- Minutes-long source compiles do not fit SessionStart hook budgets, and a
  timed-out hook fails silently downstream: everything after the timeout never
  runs.
- NodeSource publishes no rolling LTS apt path (`node_lts.x` 404s); pin the
  major version and use a signed keyring instead of curl-pipe-bash.

## Failure Patterns

- FM-9 Confident-incorrectness recurrence (see
  `.claude/rules/canonical-source-mirror.md`):
  both the doomed PEP 668 fallback and the stale CONTRIBUTING flag were claims
  written without an executed check. Counter: run the path, read the file,
  then write the claim.
- Silent wrong-target install: `uv pip install --python <pin>` quietly
  targeted the discovered `.venv` instead of the named interpreter, so the
  code did not do what its comment said. Counter: assert the post-condition
  (import from the intended interpreter), not the command's exit code.

## Remediation

- Superseded memories: `.serena/memories/ci/environment-observations.md`,
  `.serena/memories/python/python-version-compatibility.md` (landed in #2529).
- Install guards for the unconditional PSGallery round-trips: PR #2538.
- CONTRIBUTING.md setup step aligned to `uv sync --extra dev` (this branch).
- No new failure-mode class proposed; existing class covers both instances.
