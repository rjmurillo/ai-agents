# Feedback: runtime-verify customer-facing generated artifacts

**Origin:** PR #2205 customer-wedge incident. See `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md` and `.claude/rules/generated-artifacts.md`.

## What happened

The generator emitted `src/copilot-cli/hooks/hooks.json` with bare `./hooks/<event>/<script>.py` command paths and `cwd: "."`. Copilot CLI runs plugin hooks with cwd = the user's working directory, not the plugin install dir. Every hook failed at launch with "No such file or directory". The failure is at the LAUNCHER (`python3` cannot open the file) so the in-script fail-open shim never runs. Result: customer environments wedged; only recovery was uninstalling the plugin. Shipped 33 days across v0.3.0 to v0.5.6.

## The rule (now binding)

For any generator that emits a customer-facing artifact (plugin hooks.json, copied hook scripts, agent/skill files a CLI loads, MCP config):

1. Verify the runtime contract by RUNNING the target tool and reading its environment (cwd, env vars, version). Never assume a contract from docs or analogy. The first fix assumed `COPILOT_PLUGIN_ROOT` by analogy to `CLAUDE_PLUGIN_ROOT` and shipped it unverified. Record the verified contract: `mem:decision-copilot-cli-hook-plugin-root-contract`.
2. Ship a runtime-contract test that EXECUTES the artifact under that contract (the cwd and env the host sets) with a negative control. A string-match test of the generator's own output does NOT count (self-referential; canonical-source-mirror anti-pattern at the test layer).
3. Gate the COMMITTED artifact with a validator (`scripts/validation/validate_hook_anchoring.py` in `pre_pr.py`), not just the generator on a fixture. Derive expected shape from the generator.
4. Smoke-test in the real CLI; force it locally in pre-push when CI lacks auth (`tests/e2e/test_cli_hook_e2e.py`). Skipped smoke must be loud.

## How to apply

Before merging a generator or generated-artifact change, ask: if this artifact is wrong, does the customer get a degraded feature or a wedged environment? If wedged, the four steps above are mandatory.

Related: `mem:decision-copilot-cli-hook-plugin-root-contract`.
