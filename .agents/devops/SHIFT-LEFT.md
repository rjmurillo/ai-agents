# Shift-Left Validation Strategy

**Status**: Active
**Version**: 2.0
**Last Updated**: 2026-08-19

## Overview

Shift-left validation catches defects on the developer's machine instead of in
CI review cycles. This document describes the local runner, the git hooks that
invoke it, and which checks CI repeats.

ADR-042 replaced the PowerShell validation runner with Python. Every command
below is the current one; the PowerShell entry points named in version 1.0 of
this document (`Validate-PrePR.ps1`, `Validate-Session.ps1`,
`Invoke-PesterTests.ps1`, `Validate-PathNormalization.ps1`,
`Validate-PlanningArtifacts.ps1`, `Detect-AgentDrift.ps1`) no longer exist.

## Unified Validation Runner

`scripts/validation/pre_pr.py` runs the full local gate sequence.

```bash
# Full validation
uv run --frozen python scripts/validation/pre_pr.py

# Skip the four quick-skippable gates
uv run --frozen python scripts/validation/pre_pr.py --quick

# Verbose output
uv run --frozen python scripts/validation/pre_pr.py --verbose
```

`--quick` skips YAML Style Validation, Path Normalization, Planning Artifacts,
and Agent Drift Detection. Measured 2026-08-19, those four gates cost 1.89s of
a 103.25s run, so `--quick` now saves under 2 percent. It was worth 50 to 90
seconds when the sequence had six gates; it is not a meaningful lever today.
Run the full sequence.

`--skip-tests` and its `SKIP_TESTS` environment default are parsed but inert:
no gate in `_SEQUENCE` sets `skip_flag`, so the flag skips nothing.

## Validation Sequence

The ordered gate list is `_SEQUENCE` in `scripts/validation/pre_pr_sequence.py`.
Read it there. This document deliberately keeps no second copy: version 1.0
carried a six-row table that drifted from the real sequence for months without
anything detecting it.

To list the current gates:

```bash
uv run --frozen python -c "
import sys; sys.path.insert(0, 'scripts/validation')
from pre_pr_sequence import _SEQUENCE
for gate in _SEQUENCE: print(gate.name)
"
```

57 gates as of 2026-08-19.

### Cost distribution

Measured 2026-08-19 on a 4-CPU container against a tree with no changes
against `origin/main`. Most gates scale with the diff, so treat these as the
floor, not a forecast:

| Gate | Wall |
|------|-----:|
| Count Ratchets | 38.37s |
| Skill Markdown Portability | 16.07s |
| Subprocess Encoding Convention | 7.06s |
| Unreachable Code Detection | 5.83s |
| Documented Interpreter Portability | 4.53s |
| Python Syntax (compile gate) | 3.71s |
| Remaining 51 gates | 27.68s |
| **Total** | **103.25s** |

Thirty-five of the 57 gates finish in under 0.5s each.

YAML Style Validation reported 0.00s because `yamllint` was absent from the
measuring container and the gate returns early with a warning when the binary
is missing. Its real cost is unmeasured here.

Re-measure with:

```bash
SKIP_AUTOFIX=1 uv run --frozen python scripts/validation/pre_pr.py
```

The per-gate durations print in the Detailed Results block at the end.

## Exit Codes

| Code | Meaning | Action |
|------|---------|--------|
| 0 | PASS | All gates passed |
| 1 | FAIL | One or more gates failed; fix and re-run |
| 2 | ERROR | Environment or configuration fault |

Gates that raise `MissingScriptSkip` record SKIP and do not fail the run.

## Integration with Workflows

### Pre-commit hook

Lefthook filters staged files and runs the pre-commit jobs declared in
`lefthook.yml` (46 jobs as of 2026-08-19). Consult that file for the current
list rather than maintaining a second checklist here.

### Pre-push hook

`lefthook.yml` declares 34 pre-push jobs, staged so cheap gates fail before
expensive ones start (issue #5066). The hook is `piped: true`, so a failing
job or group skips everything after it. Stage order:

1. Singleton guards: `repair-packed-refs`, `mutation-safety`,
   `push-ref-staleness`.
2. Fast stage, stdin half: a piped group of cheap ref-payload policies.
3. Fast stage, parallel half: ratchets and policy gates. Measured maximum
   21.05s (`merge-tree-ratchet`) on 2026-08-19.
4. `security-scan` (semgrep), a serialized stdin consumer. Measured 6.7s for a
   7-file push.
5. Expensive stage: `python-tests`, `pre-pr-validation`, mypy,
   `workflow-local-run`, the CLI e2e smokes, and the advisory reporters.

`python-tests` dominates: 475s across four serial partitions on a 4-CPU
container (bulk 257.9s, mutation 166.6s, safe-push 36.9s, pr-autofix 8.8s).
Reducing pre-push wall clock means reducing that job; the rest of the hook is
about 30s combined.

A job's standalone wall clock does not predict its wall clock inside the hook.
See `.claude/rules/ci-scripts.md` MUST-16 for the measured gap and why timeouts
must be sized against a real push.

### CI pipeline

No workflow runs `pre_pr.py`. CI repeats individual validators through
dedicated workflows instead:

| Local gate | CI workflow |
|------------|-------------|
| Count Ratchets | `pr-validation.yml` |
| `python-tests` | `pytest.yml` (5 parallel matrix partitions) |
| Path Normalization | `validate-paths.yml` |
| Planning Artifacts | `validate-planning-artifacts.yml` |
| Agent Drift Detection | `drift-detection.yml` |
| Generated Artifact Staleness | `validate-generated-agents.yml` |
| Rule Activation Coverage | `validate-rule-activation-coverage.yml` |
| Spec ID Uniqueness | `validate-spec-id-uniqueness.yml` |
| Vendor Portability | `validate-vendor-portability.yml` |
| Plugin Version Bump | `validate-plugin-version-bump.yml` |
| Hook Anchoring | `hook-contract-check.yml` |
| Memory index and tier | `memory-validation.yml` |

Two pre-push gates have no CI equivalent, so a local bypass is the only place
they are enforced: `security-scan` (semgrep) and `python-type-check` (mypy).
CI runs the type-ignore count ratchet, not mypy itself.

### Developer workflow

```text
1. Make changes
2. Commit (pre-commit hook runs per-file checks)
3. Push (pre-push hook runs branch-wide validation)
4. Open the PR (CI runs the workflows above)
```

Running `pre_pr.py` by hand before pushing is optional; the pre-push hook runs
the same sequence. Run it by hand when you want the failure in seconds rather
than after the test suite.

## Workflow Validation

### actionlint

Scope actionlint to the workflow files, not the repository. A bare `actionlint`
with no path argument recursively scans every `.yml` and `.yaml` file,
including composite action definitions under `.github/actions/*/action.yml`.
actionlint validates workflow files only; it parses a composite `action.yml` as
if it were a workflow and emits false errors (missing `on:` and `jobs:` keys,
unexpected `runs:` and `inputs:`). Composite actions cannot be validated with
actionlint. Pass an explicit glob:

```bash
actionlint .github/workflows/*.yml
```

Do not pass the bare directory `.github/workflows/`: actionlint rejects a
directory argument with "is a directory". The automated toolchain
(`scripts/validation/pre_pr.py`, `scripts/validation/run_workflow_local_test.py`)
already globs correctly; this note keeps manual invocations aligned.

Installation:

```bash
brew install actionlint                                    # macOS
go install github.com/rhysd/actionlint/cmd/actionlint@latest  # Go
```

### validate_workflows.py

`scripts/validate_workflows.py` checks structure, SHA pinning, ADR-006 size
limits, and permissions. See [docs/WORKFLOW-VALIDATION.md](../../docs/WORKFLOW-VALIDATION.md)
for its full contract, exit codes, and error table.

### run_workflow_local_test.py

`scripts/validation/run_workflow_local_test.py` is the pre-push gate for
changed workflows. It runs three ordered stages and short-circuits on the
first failure:

1. `actionlint`: static analysis.
2. `gh act -n`: dry run of the job graph and step wiring.
3. `gh act`: real execution in Docker.

```bash
uv run --frozen python scripts/validation/run_workflow_local_test.py \
  --files .github/workflows/pytest.yml

# Lint plus dry-run tier only
uv run --frozen python scripts/validation/run_workflow_local_test.py \
  --files .github/workflows/pytest.yml --no-full
```

Missing tools yield exit 3 on a developer machine and in CI. Inside a managed
remote container the gap degrades to exit 0 with a logged warning, because the
tools cannot be provisioned there (issues #2548 and #3064).

## YAML Style

`yamllint` checks line length, indentation, trailing spaces, comment spacing,
and end-of-file newlines against `.yamllint.yml`. Findings warn; they never
fail a commit or a push. The gate returns early with a warning when `yamllint`
is not installed.

```bash
pip install yamllint
yamllint .
```

## Local Workflow Testing with act

`act` (nektos/act) runs GitHub Actions workflows locally in Docker, which
shortens the push-check-tweak cycle.

### Prerequisites

```bash
# Install act, either standalone or as the gh extension
gh extension install https://github.com/nektos/gh-act
brew install act

# Docker is required
docker info
```

`.actrc` in the repository root sets `catthehacker/ubuntu:full-latest` images
for production parity (about 18GB), artifact storage in `.artifacts/`, caching
in `.cache/`, linux/amd64 architecture, and maps `windows-latest` to
`-self-hosted` so it runs on the host.

### Usage

```bash
# Through the repository wrapper
uv run --frozen python .claude/skills/github/scripts/test_workflow_locally.py \
  --workflow validate-paths --dry-run

# Direct act invocation
act pull_request -W .github/workflows/validate-paths.yml -n
act -l
```

Workflows requiring Copilot CLI or `BOT_PAT` cannot run locally and must rely
on CI feedback.

### Troubleshooting act

| Problem | Cause | Solution |
|---------|-------|----------|
| `act: command not found` | act not installed | Install via brew or the gh extension |
| `Cannot connect to Docker daemon` | Docker not running | Start Docker |
| `Error: image not found` | Missing image | `docker pull catthehacker/ubuntu:act-latest` |
| `Permission denied` | Docker socket permissions | Add the user to the docker group |
| `Workflow validation failed` | Workflow syntax error | Run actionlint first |
| `Unknown runner label` | Invalid `runs-on` | Use official runner labels |

act uses Linux containers, so Windows-specific path, line-ending, and
case-sensitivity behavior differs. Use `-P windows-latest=-self-hosted` to run
on the host.

## Troubleshooting

**Runner exits 2**: an environment fault. Confirm Python 3.14 through `uv`,
Node.js for markdownlint, and that the working directory is inside the
repository.

**Runner exits 1**: a gate failed. The Detailed Results block names the gate;
run that gate's script directly for the full output.

**A count ratchet fails right after `origin/main` moved**: merge or rebase onto
a freshly fetched `main` and re-measure before hunting the violation. See
`.claude/rules/ci-scripts.md` item 14.

## Related Documentation

- **Session log mechanics**: `.claude/rules/session-logs.md`
- **Git hook configuration**: `lefthook.yml`
- **Workflow validation**: [docs/WORKFLOW-VALIDATION.md](../../docs/WORKFLOW-VALIDATION.md)
- **CI script rules**: `.claude/rules/ci-scripts.md`
- **DevOps patterns**: `.agents/devops/validation-runner-pattern.md`

## References

- **Issue #325**: Unified shift-left validation runner
- **Issue #5066**: Pre-push fast-fail staging
- **ADR-006**: Thin workflows, testable modules
- **ADR-035**: Exit code standardization
- **ADR-042**: Python migration strategy (supersedes ADR-005)
