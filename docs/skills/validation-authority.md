# validation-authority

Tells you to change your local config when an upstream validator fails you, not the validator's code. In the build workflow it also checks a decision record that says which file may be edited and why.

## When to use it

- Validation fails unexpectedly.
- You are about to change validator behavior or configuration.
- You are tempted to edit an upstream tool's source.
- You are adding an external validator, or suppressing a warning without a reason.
- Trigger phrases: `validation failed unexpectedly`, `should I change the validator`, `is this validator authoritative`.

## When not to use it

- You want to know who owns a file before you edit it: use [`analysis-provenance`](analysis-provenance.md). This skill uses its result.
- You want to enforce style rules: use [`style-enforcement`](style-enforcement.md).
- You want a quality assessment of code: use [`code-qualities-assessment`](code-qualities-assessment.md).
- You want to decide whether evidence is independent: use [`evidence-provenance`](evidence-provenance.md).

## Quick start

In Claude Code, after a plugin install, run:

```text
/project-toolkit:validation-authority markdownlint fails MD013 on docs/generated/api.md
```

This skill has no short slash command, so the agent usually loads it on its own when a validator fails. On other hosts, ask for it by name:

```text
Use the validation-authority skill to fix the markdownlint MD013 failure on docs/generated/api.md.
```

The skill classifies the validator, finds the conflicting rule, reads the tool's defaults, and changes your local config to match. It records why in a config comment.

## What you get

A decision for each failure:

| Scenario | Action | Example |
| --- | --- | --- |
| PSScriptAnalyzer rule fails | Update `.psscriptanalyzerrc.psd1` | Suppress `PSAvoidUsingWriteHost` with a rationale. |
| markdownlint rule fails | Update `.markdownlint.yaml` | Disable `MD013` line length for generated docs. |
| ESLint rule conflicts | Update `.eslintrc` | Override `no-console` for CLI tools. |
| Upstream tool has a bug | Flag it to the owner with a repro, add a workaround in config | Pin the tool version, suppress one rule. |
| Tool default changed after an upgrade | Align local config to the new default | Update config after a major version bump. |

If the validator is local and project-owned, you may change the tool. If it is upstream, change only local config and document each override. Suppress specific rules, not whole categories. After the change, paste the validator's exit status line. A claim that validation passes needs that pasted output.

## Advanced use

In the [`build`](build.md) workflow, Phase 2b calls this skill after `analysis-provenance` classifies each validation target. The skill then writes a decision record. For each target, the record combines the provenance category (`LOCAL`, `GENERATED`, `VENDOR`, `UPSTREAM`, `UNKNOWN`) with a diagnosis:

| Diagnosis | Meaning |
| --- | --- |
| `implementation-defect` | The local check has a real bug. |
| `local-config-defect` | Only the project's config needs to change. |
| `stale-generated-output` | A generated mirror drifted from its source. |
| `baseline-update` | A ratchet or baseline needs new entries. |
| `upstream-defect` | The vendored or upstream tool is wrong. |
| `relocation-no-semantic-change` | A test file moved or split under `tests/` with the same collected tests. |
| `unknown` | Evidence is insufficient. |

The record names the one `permitted_change_location` Phase 3 may edit. `GENERATED` permits only the canonical source. `VENDOR` and `UPSTREAM` never permit the target itself. An `unknown` category or diagnosis permits nothing and blocks further semantic edits until ownership evidence exists. A `baseline-update` must cite an existing policy file and justify every added entry.

Check the record from the root of a checkout of this repository:

```bash
uv run python .claude/skills/validation-authority/scripts/validation_record.py --record validation-authority-record.json --changed-path scripts/lint.py
```

| Flag | Meaning |
| --- | --- |
| `--record` | Decision record JSON. Required. |
| `--changed-path` | A path from the current changed-path list. Repeatable. |
| `--repo-root` | Repository root override. |
| `--trigger` | Path to a `validation_trigger.py` override. |

| Exit code | Meaning |
| --- | --- |
| 0 | The record passed. Phase 3 may edit the permitted locations. |
| 1 | The record has defects. The output names the blocking targets. |
| 2 | Configuration error: unreadable file, invalid JSON, the sibling `build` trigger could not load, or pytest is not installed. |

The script reports every field and coverage defect in one run. For `relocation-no-semantic-change`, it runs `pytest --collect-only -q` over the moved files and compares real test ids with the record. That collection imports test modules, `conftest.py` files, and installed pytest plugins, so run it only on a checkout you trust. The record file lives in a scratch directory, and the PR body carries its summary.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`analysis-provenance`](analysis-provenance.md): classifies each validation target before this skill decides.
- [`build`](build.md): invokes this skill in Phase 2b.
- [`style-enforcement`](style-enforcement.md): enforces the style rules this skill governs.
- [`doc-accuracy`](doc-accuracy.md): detects contradictions between docs, config, and behavior.
- Source: [`SKILL.md`](../../src/claude/skills/validation-authority/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
