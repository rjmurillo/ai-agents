# ai-agents-validation-and-qa

Defines what counts as evidence for a change in this repository and how to produce it: the positive, negative, and edge test bar, where tests live, coverage proof, and the QA skip rules.

> [!NOTE]
> This skill works only inside a checkout of `rjmurillo/ai-agents`. It is for people who
> maintain this repository. A plugin install does not include it.

## When to use it

- You ask what counts as evidence: `what counts as evidence`.
- You need to test or run tests: `how do I test this change`, `run skill tests`.
- You wonder whether QA can be skipped: `can I skip QA`.
- You write or review Python or tests here and want the repo's conventions for subprocess text, paths, and test isolation.
- You review a pull request here and want the list of findings maintainers dismiss.

## When not to use it

- You need to triage a red CI check: use [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md) instead.
- You need measurement tooling: use [`ai-agents-diagnostics-toolkit`](ai-agents-diagnostics-toolkit.md) instead.

## Quick start

The agent usually loads this skill for you when your request matches. In a Claude Code session inside this repository, you can also type `/ai-agents-validation-and-qa`. To ask for it by name, say:

```text
Use the ai-agents-validation-and-qa skill to tell me which tests and coverage proof I need for my change to a validation script.
```

The agent applies the evidence bar to your change, names where the tests go, and gives the coverage command.

## What you get

A test plan that meets the bar: a positive, negative, and edge test per changed function, 100% block coverage on changed files, and runtime-contract tests with negative controls. The skill also lists the QA skip verdicts defined by ADR-034 and the anti-pattern canon.

Three reference files go deeper. `rule-ci-scripts.md` covers CI workflows and validation scripts. `python-and-test-conventions.md` covers Python and test patterns, each with a site to copy. `reviewer-guidance.md` lists review findings to skip, with the reason for each.

## Advanced use

Pytest collects only `tests/` by default; anything else runs explicitly. New skill tests go under `tests/skills/<name>/`, never inside the shipped skill tree.

`test_layout.py` has two subcommands: `pester` (counts `*.Tests.ps1` files and checks stale-doc prose) and `skill-tests <name>` (lists test files collected for a skill; `--no-pytest` walks the filesystem). `instruments.py` ids include `citation-freshness`, `investigation-allowlist`, `qa-skip-evidence`, `pester-count`, `skill-tests`, and `drift-self-check`.

Run the dispatcher from the root of a checkout of this repository:

```bash
uv run python .claude/skills/ai-agents-validation-and-qa/scripts/test_layout.py --repo . skill-tests ai-agents-change-control
uv run python .claude/skills/ai-agents-validation-and-qa/scripts/instruments.py --repo . list
uv run python .claude/skills/ai-agents-validation-and-qa/scripts/instruments.py --repo . run citation-freshness
```

Replace `citation-freshness` with any instrument id. The ids are `citation-freshness`, `investigation-allowlist`, `qa-skip-evidence`, `pester-count`, `skill-tests`, `drift-self-check`. `list` prints each one with the question it answers.

`citation-freshness` checks citations on added lines against their cited content.
The skill cites the `Run pytest` step in `.github/workflows/pytest.yml`.
That step documents the workflow's flaky-test reruns.

## Where it runs

This skill ships only in a checkout of `rjmurillo/ai-agents`. It is not part of any plugin install.

## Related

- [`ai-agents-debugging-playbook`](ai-agents-debugging-playbook.md): CI triage.
- [`ai-agents-diagnostics-toolkit`](ai-agents-diagnostics-toolkit.md): measurement tools.
- [`ai-agents-empirical-probe-toolkit`](ai-agents-empirical-probe-toolkit.md): negative-control test design.
- [`ai-agents-change-control`](ai-agents-change-control.md): which gates a change triggers.
- Source: [`SKILL.md`](../../.claude/skills/ai-agents-validation-and-qa/SKILL.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
