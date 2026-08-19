---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-19-session-99919-bf1cf3993-analyze-pre-push-hook-duration-dora.json
qaCommit: a75c1d1614a85b2ea143f2daad6b3856915476b2
---

# QA Report: SHIFT-LEFT.md accuracy rewrite (issue #5158)

- **Branch**: `claude/pre-push-hook-duration-vru1ti`
- **Session log**: `.agents/sessions/2026-08-19-session-99919-bf1cf3993-analyze-pre-push-hook-duration-dora.json`
- **Scope**: `.agents/devops/SHIFT-LEFT.md`, 682 lines to 320

## Why this is not a docs-only skip

`test_docs_only_eligibility.py` disqualifies the change because the code-block
content changed. That verdict is correct and is the reason this report exists:
the document's code blocks are commands a contributor is told to run, and the
defect being fixed is that those commands named removed scripts. Changed
executable instructions need verification, not an exemption.

## What was verified, and how

### Every command in the document resolves

Each path referenced by the rewritten document was checked for existence on
disk. Eighteen paths were checked in the original; the eight that did not
exist are gone from the rewrite:

| Removed reference | Replacement |
|---|---|
| `scripts/Validate-PrePR.ps1` | `scripts/validation/pre_pr.py` |
| `scripts/Validate-Session.ps1` | dropped; no separate gate |
| `build/scripts/Invoke-PesterTests.ps1` | dropped; Pester is gone |
| `build/scripts/Validate-PathNormalization.ps1` | `build/scripts/validate_path_normalization.py` |
| `build/scripts/Validate-PlanningArtifacts.ps1` | `build/scripts/validate_planning_artifacts.py` |
| `build/scripts/Detect-AgentDrift.ps1` | `build/scripts/detect_agent_drift.py` |
| `.claude/skills/github/scripts/Test-WorkflowLocally.ps1` | `.claude/skills/github/scripts/test_workflow_locally.py` |
| `.github/workflows/shift-left-validation.yml` | dropped; no workflow runs `pre_pr.py` |

Positive control: the nine paths the document still references
(`build/scripts/validate_path_normalization.py`,
`build/scripts/validate_planning_artifacts.py`,
`build/scripts/detect_agent_drift.py`,
`scripts/validation/run_workflow_local_test.py`, `scripts/validate_workflows.py`,
`docs/WORKFLOW-VALIDATION.md`, `.agents/devops/validation-runner-pattern.md`,
`.yamllint.yml`, `.actrc`) all exist.

### Flag behavior claims are measured, not assumed

| Claim in the rewrite | Command | Result |
|---|---|---|
| Full run is 57 gates at 103.25s | `SKIP_AUTOFIX=1 uv run --frozen python scripts/validation/pre_pr.py` | 57 validations, 103.25s, 0 failed |
| `--quick` saves 1.89s | same command with `--quick` | 97.40s, 53 passed, 4 skipped |
| The four quick gates cost 1.89s | per-gate output of the full run | YAML Style 0.00s, Path Normalization 1.72s, Planning Artifacts 0.06s, Agent Drift 0.11s |
| `--skip-tests` is inert | `grep -n "skip_flag" scripts/validation/pre_pr_sequence.py` | the field is declared and read at line 393, and no `_Gate` sets it |

The YAML Style figure is 0.00s because `yamllint` is absent from this
container and the gate returns early with a warning. The document states that
caveat rather than publishing 0.00s as the gate's cost.

### Pre-push figures come from a real push, not a standalone run

`ci-scripts.md` MUST-16 requires timing evidence from a real push. The push of
this branch supplied it, exit 0:

```text
fast parallel stage       56.21s   (max member merge-tree-ratchet 22.17s)
security-scan              0.41s
expensive parallel group 620.03s
  python-tests           498.52s
  pre-pr-validation      110.12s
```

The document's `python-tests` partition breakdown (475s total: bulk 257.90s,
mutation 166.64s, safe-push 36.89s, pr-autofix 8.84s) comes from running the
hook's own command in isolation:
`AI_AGENTS_PYTEST_WORKER_CAP=4 uv run --frozen python scripts/validation/git_hook_policy.py pytest`.

### Gate results on the change

| Gate | Result |
|---|---|
| `pre_pr.py` full sequence | 57 passed, 0 failed, 0 skipped |
| Full pre-push hook on the real push | exit 0, all jobs green |
| taste-lints on the file | 0 errors, 1 warning (320/500 lines) |
| taste count ratchet | 579 <= baseline 583, down from the error this file carried |
| `validate_path_normalization.py` | 4298 files, no absolute paths |
| em/en dash scan | none |
| markdownlint | not applicable; `.agents/**` is excluded by the repository config |

## Negative controls

The claims discriminate. Before the rewrite, taste-lints reported
`[ERROR] authored file-size: .agents/devops/SHIFT-LEFT.md:682` and the count
ratchet measured 583; after, the error is gone and the count is 579. The
`--quick` measurement discriminates too: had the document's original claim
been true, the quick run would have finished 50 to 90 seconds faster than the
full run instead of 5.85 seconds faster.

## Limits of this report

Measured on one 4-CPU container on 2026-08-19 against a tree with no changes
against `origin/main`. Gate costs scale with the diff, so these are a floor.
Per MUST-16, do not carry the ratios to another machine; the document says so
and gives the re-measure command.
