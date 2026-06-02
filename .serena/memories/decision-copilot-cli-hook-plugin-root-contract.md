# Decision: Copilot CLI plugin-hook path anchoring (issue #2205)

**Question**: Which env var anchors a Copilot CLI plugin hook's script path so it
resolves when `cwd` is the user's working dir, not the plugin install dir?

**Conventional answer (docs, Layer 1/2)**: The public GitHub Copilot CLI hooks
reference (`docs.github.com/en/copilot/reference/hooks-reference`) lists hook env
vars as `GITHUB_COPILOT_API_TOKEN`, `GITHUB_COPILOT_GIT_TOKEN`,
`COPILOT_AGENT_PROMPT`, `HOME`, `COPILOT_HOME`. The cli-plugin-reference documents
only `${COPILOT_PLUGIN_DATA}` / `${CLAUDE_PLUGIN_DATA}` (a writable DATA dir, not
the install root). No `COPILOT_PLUGIN_ROOT` is documented anywhere, and one source
claims `CLAUDE_PLUGIN_ROOT` is "not available in Copilot-format plugins." Reading
the docs alone, the PR's `COPILOT_PLUGIN_ROOT` looks invented.

**First-principles position (Layer 3, empirical)**: Verified by experiment, not
docs. Installed a probe plugin and dumped the hook environment under GitHub
Copilot CLI **1.0.57** (Linux). Copilot launches a plugin hook with `cwd` = the
user's working dir (measured `PWD=/tmp`) and exports BOTH
`COPILOT_PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` (plus a bare `PLUGIN_ROOT`), all
pointing at the install dir (`~/.copilot/installed-plugins/.../<plugin>`, the dir
that contains `hooks/`). The docs are simply incomplete; the vars are real.

**Evidence**:
- Probe env dump: `COPILOT_PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` both set to the
  install dir; bare `./hooks/...` resolved NO, anchored path resolved YES.
- E2E: the exact generated command
  `python3 -u "${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}/hooks/sessionStart/x.py"`
  executed under real Copilot CLI from cwd=/tmp, exit 0.
- PowerShell `if/else` fallback subexpression tested under pwsh 7.6.2 (resolves
  with COPILOT set, and with only CLAUDE set).

**Decision**: Keep `${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT}}` for bash.
Give PowerShell the SAME fallback order via
`$(if ($env:COPILOT_PLUGIN_ROOT) {$env:COPILOT_PLUGIN_ROOT} else {$env:CLAUDE_PLUGIN_ROOT})`
(the PR shipped a no-fallback `$env:COPILOT_PLUGIN_ROOT`, an asymmetry). Lives in
`build/scripts/generate_hooks.py::_build_copilot_entry`. The contract is enforced
by `tests/build_scripts/test_generate_hooks_runtime_contract.py`, which RUNS the
generated commands under the verified contract (cwd != plugin root; var = install
dir) with a bare-path negative control, instead of string-matching the output.

**Lesson**: Public docs were wrong-by-omission here. The only reliable check for a
runtime env-var contract is to run a hook and read its environment. String-match
tests that pin generator output to itself cannot catch a wrong var name.
See `.claude/rules/canonical-source-mirror.md`.
