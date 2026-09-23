# Retrospective: agent-first docs rewrite shipped two red checks and one masked failure

**Date**: 2026-09-11
**Scope**: PR #5713 (issue #5712), branch `claude/agent-first-docs-alfdkl`
**Failure mode classification**: #4 False completion markers and #9 Confident-incorrectness recurrence (`.agents/governance/FAILURE-MODES.md` lines 22 and 27)

## What happened

Nine per-directory agent guides were rewritten into one template by sonnet writers, checked by haiku verifiers, and reviewed by an opus reviewer. Three failures reached CI or nearly did:

1. **Routing strings dropped.** `tests/build_scripts/test_hook_contract_knowledge.py` requires every authoring surface to name `agent-harness-reference` and `ai-agents-portability-campaign`. The first hand rewrite dropped them from `src/claude/AGENTS.md`; the sonnet rewrite dropped them again from `src/claude/AGENTS.md` and `templates/AGENTS.md`. CI run 34555807167 went red once; the second loss was caught locally only because the test was re-run after the writers finished. Fixes: `c8d429bd7`, `2b3a377a0`.
2. **A chained command masked a red test.** Commit `8ff9f604e` was created by `pytest ... | tail -1 && lint && git commit`. The pipe's exit status was `tail`'s, so the commit landed with one failing test in its own output. Caught on the next read of the output; fixed in `2b3a377a0`.
3. **A new guide collided with a root marker.** `tests/test_workspace_limits.py` located the repo root by walking up to the first directory containing `AGENTS.md`. Adding `tests/AGENTS.md` made `tests/` the root, and the guide (9647 bytes) was measured against the 3000 byte root budget. CI run 34559697139 went red. A repository-wide search found exactly one resolver keyed on that name; fix in `ac7ab64a5` anchors on `pyproject.toml` plus `AGENTS.md`.

The opus review also returned 13 blocking factual corrections across the two rounds (drift checker allowlist size and one-sided-heading semantics inverted, gate counts, stripped script paths that turned a plugin-safety fix into three broken commands, a false absence claim). All were real; none had been caught by the per-file haiku verifiers, whose checks were existence and lint, not meaning.

## Impact

| Area | Severity | Effect |
|---|---|---|
| CI on the PR | Medium | Two red pushes, each fixed within the hour; no red `main` |
| Doc accuracy | High | Without the opus pass, four inverted or wrong facts would have shipped in guides agents read first |
| Review trust | Medium | A commit whose own gate output showed a failure |

## Root cause (five whys)

1. Why did routing strings vanish twice? The writers were told to keep load-bearing facts, not which strings a test asserts.
2. Why was the second loss not caught before commit? The gate ran, but its exit code was replaced by `tail`'s.
3. Why did the marker collision reach CI? The new file name was chosen for discovery, and nobody searched for resolvers that treat that name as unique.
4. Why did the haiku verifiers pass wrong facts? Their contract was existence and lint. Meaning was only checked by the opus reviewer, once, at the end.
5. Why did that ordering hold? Cheap checks first, expensive review last, is the right default; the miss was treating a green haiku pass as evidence about semantics.

Root cause: **verification was scoped to what is cheap to check, and the chain that reported it could not fail.**

## Remediation

- [x] Writer prompts now name the test-asserted strings and the plugin-safety ratchets explicitly (workflow scripts in this session; carry into any future doc-rewrite workflow).
- [x] Root-marker fix landed in `tests/test_workspace_limits.py` (`ac7ab64a5`).
- [ ] Rule: never chain `<gate> | tail -n && git commit`; capture the gate's own exit status (`PIPESTATUS` or a redirect) before the commit. Owner: this session's operator; candidate addition to `.claude/rules/ci-scripts.md`.
- [ ] Follow-up: the generator-order comment in `build/scripts/build_all.py` (around lines 491 to 496) still lists a retired `commands` step; `.agents/governance/test-location-standards.md` still describes Pester layouts. Both noted in PR #5713.

## Learning

A verifier that checks existence is not a verifier of meaning. Budget one semantic pass by a stronger model per rewrite, and treat every green from a weaker pass as scope-limited evidence.
