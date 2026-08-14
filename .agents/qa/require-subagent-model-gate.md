---
qaVerdict: PASS
qaSessionLog: .agents/sessions/2026-08-11-session-14681-b71853e6d-vendor-require-subagent-model-pretooluse-hook-gate.json
qaCommit: e9e471db4c29d09fa3d986ec8ad36253a69f5eee
---

# QA: require-subagent-model gate (issue #4874)

## Scope

Cross-harness PreToolUse gate denying sub-agent spawns with no model and no
definition file, plus the ADR metric refresh it forced.

## Evidence

- PR review fix suite: 489 passed, 3 skipped across the model gate,
  markdown target filtering, hook generation, dispatcher, shipped artifact,
  and CLI hook end-to-end tests.
- Matcher-union regression suite: 19 passed after the main refresh.
- Final thread-fix suite: 397 passed, 3 skipped. It covers explicit-model
  validation, host matcher filtering, generated fail-open behavior, dispatcher
  generation, committed artifacts, and CLI hook execution.
- Unit and contract suites: 1852 passed across tests/hooks,
  tests/test_hook_dispatch.py, and tests/build_scripts/test_hook_contract_knowledge.py
  (final run after the round-6 dissent fixes; full-suite run earlier in the
  session: 1981 passed, 1 skipped).
- Canonical script matrix: 11 payload cases both harness spellings (Claude
  tool_name/tool_input, Copilot toolName/toolArgs dict and JSON string),
  definition hits in all six search roots, env escape hatch, empty and
  malformed stdin fail-open, glob-metacharacter spoof denial (parametrized
  over *, **, ?, [a], ../me, backslash form).
- Process boundary, executed directly: canonical script exits 0 on malformed
  stdin and 2 on the deny path with remediation text; generated Copilot shim
  exits 2 on deny for tool_name Agent, 0 on non-matching tools, and 0 on
  malformed stdin per the source hook's fail-open policy.
- Registration surfaces: dispatch-group parity suite green (settings twin
  correctly absent per the duplicate-entry contract); .github/hooks JSON
  validated against the documented version-1 command-hook shape; host matcher
  union verified as Bash|Agent|Task in the generated hooks.json.
- Copilot payload contract grounded in a real session log (CLI 1.0.79
  toolRequests carrying agent_type and model), not inferred.
- Deny-path wall clock 0.37 seconds against a 10-second budget.
- Post-refresh pre-push tests: 27,886 passed, 37 skipped.
- Merge-tree ratchet, mypy, build generation, and hook gates passed.
- Post-refresh pre-PR validation passed every check.
- Complete-frontmatter regression suites passed 54 and 89 tests.
- adr-review converged round 6: 2 Accept, 4 Disagree-and-Commit, 0 Block;
  all dissent conditions applied in-tree.

## Residuals

- Agent/Task host-matcher behavior on a live Copilot host is unprobed;
  recorded in ADR-071 with shim and script self-filtering as the layered
  defense.
- Cloud-agent coverage begins when .github/hooks/require-subagent-model.json
  reaches the default branch.
