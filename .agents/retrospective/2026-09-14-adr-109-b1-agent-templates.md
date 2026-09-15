# Retrospective: ADR-109 B1 shipped a no-op gate, a rejected model pin, and a stray output tree before review caught them

**Date**: 2026-09-14
**Scope**: PR #5758 (ADR-109 step B1, TASK-031), branch `feat/adr-109-b1-agents-clean`; supporting PRs #5745 (ADR-109) and #5755 (spec set)
**Failure mode classification**: false completion markers and confident-incorrectness recurrence (`.agents/governance/FAILURE-MODES.md`)

## What happened

The agent class moved to template ownership: 62 templates and 138 partials, a compile module, a binplace manifest, and a layout move from `src/claude/<stem>.md` to `src/claude/agents/<stem>.md`. Sonnet agents built the first cut, hit the monthly spend limit mid-task, and the work finished on Haiku for mechanical edits with judgement calls made inline. Six defects reached the branch before an independent Opus review or CI caught them:

1. **A gate that could not fail kept reporting PASS.** Delegating shared-agent co-change to `build_all.py --check` left `find_violations` in `build/scripts/validate_install_parity.py` with a `continue` for both group kinds, so the `Install Parity (agents and rules)` pre-PR row passed every input. The Opus review probed nine asymmetric diffs and got `[]` for all of them. Fix: the gate row is retired and the module docstring says the function cannot return a violation.
2. **A byte copy of `src/copilot-cli/agents` into `.github/agents` reintroduced a pin GitHub rejects.** ADR-109 described `.github/agents` as a binplace copy. The Copilot render carries `model: claude-haiku-4.5` on `code-reviewer`, and PR #5040 (issue #4938) had removed exactly that class of pin from `.github/agents` because the coding agent refuses it. `tests/validation/test_check_model_pins.py` caught it. Fix: `templates/platforms/github.yaml`, a platform without `model_tiers`, renders `.github/agents` directly.
3. **The manifest was read as a platform.** `templates/platforms/binplace.yaml` matched every `platforms/*.yaml` glob (`build_all.py`, `build/generate_agents.py`, `build/scripts/validate_templates_schema.py`), producing 31 "output directory is not allowlisted" errors. Fix: each glob skips a file with no `provider:` key.
4. **The github platform wrote to `src/.github/agents/`.** `generate_agents.py` joins `outputDir` onto the `src/` output root. The first render landed in a stray tree and the real `.github/agents` kept its old bytes, which read as "no change" until a diff against the Copilot render showed the missing tools array too. Fix: `.github/` output directories resolve against the repository root, and the github platform declares `toolsFrom: "copilot-cli"`.
5. **Moving `src/claude/security/references/` under `agents/` polluted every agent-tree scanner.** Frontmatter checks and matrix validators read `agents/` as agent files only. Fix: the references stay at the plugin root.
6. **Test path consumers were found in three passes, not one.** A plain grep for `src/claude/<stem>.md` missed paths built from parts (`Path("src") / "claude" / f"{name}.md"`, `("src/claude", "{name}.md")` tuples, helper constants). CI's bulk pytest reported 100 failures across root-level tests after the local build-script and validation suites had passed.

Two process slips, neither shipped: a `wip` checkpoint commit was created with `--no-verify` on a scratch branch (rebuilt into 27 hook-verified commits on a clean branch before anything was pushed), and `gh` wrote `.local/state/gh/device-id` inside the worktree, which `git add -A` staged until a status check caught it.

## Impact

| Area | Severity | Effect |
|---|---|---|
| Pre-PR gates | High | One gate reported green while checking nothing; found by review, not by tooling |
| Copilot coding agent | High | A byte-copy design would have shipped a rejected `model:` field to `.github/agents` |
| CI on the PR | Medium | Two red pushes (root-level test paths, provenance token) |
| Wall clock | Medium | Three local pushes rejected: a `gh act` run over an edited workflow timed out at 600s, a `pre-pr-validation` job timed out at 240s under concurrent test load, and the retrospective policy required this file |

## Root cause (five whys)

1. Why did the parity gate go silent? Delegating SHARED_AGENT to `--check` mirrored the existing RULE delegation, and nobody asked what the function could still return.
2. Why was the `.github/agents` contract missed at ADR time? The ADR reasoned from tree shapes, not from the consumer's frontmatter rules; the incident that set the rule lived in a test, not in the ADR's references.
3. Why did the manifest collide with platform globs? The design put the manifest beside platform configs for discoverability without listing the readers of that directory.
4. Why did the stray output tree go unnoticed for a build cycle? The build exit code was 0 and `git status` on the intended tree was empty; absence of change read as success.
5. Why did test paths need three passes? Local runs covered the suites nearest the change; the repository has more than 33,000 tests and the ones that build paths from parts live at the root.

Root cause: **each check answered the question it was asked, and the questions were scoped to the change instead of to the consumers of the change.**

## Remediation

- [x] Parity gate retired with the reason in the module docstring; the Opus review's nine-input probe is the evidence.
- [x] `templates/platforms/github.yaml` renders `.github/agents` without `model_tiers`; `tests/validation/test_check_model_pins.py` keeps `.github/agents` in scope.
- [x] Every `platforms/*.yaml` reader skips files without a `provider:` key.
- [x] `.github/` output directories resolve against the repository root in `build/generate_agents.py`.
- [x] Full suite (33,546 tests) and the complete pre-PR sequence run before push.
- [ ] Before the next class PR (B2, rules): list every reader of the directory a new file lands in, and every consumer contract of the install tree it writes, in the task file before building.
- [ ] Keep workflow edits out of large PRs on this machine; the local `gh act` run times out at 600s.

## Learning

A gate that cannot fail is worse than no gate. When a change delegates a check elsewhere, prove the old check can still fail on some input, or retire it in the same commit and say why. Install trees have consumer contracts (GitHub's `.github/agents` frontmatter rules) that a byte-copy design cannot see; read the tests guarding a tree before declaring it a copy target.
