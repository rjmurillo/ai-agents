---
paths:
  - "build/scripts/**"
  - "templates/**"
  - "src/copilot-cli/**"
  - ".github/instructions/**"
  - ".claude/hooks/**"
  - ".claude/rules/**"
  - "tests/build_scripts/**"
  - "tests/e2e/**"
priority: high
---

# Customer-Facing Generated Artifacts

This rule exists because of a P0 incident. A generator produced the Copilot CLI
plugin's `hooks.json` with a bare `./hooks/...` command path. Copilot CLI runs a
plugin hook with `cwd` set to the user's working directory, not the plugin
install dir, so every hook failed at launch with "No such file or directory".
The failure happened at the launcher, before any in-script fail-open handler
could run, so it wedged the customer's environment. The only recovery was to
uninstall the plugin. The broken form shipped for 33 days across six releases
(v0.3.0 to v0.5.6). See `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md`.

The root cause was not the wrong path. It was that a customer-facing artifact
shipped without ever being executed in its target runtime. Every test validated
the artifact's structure (valid JSON, correct fields). None ran the artifact
under the real runtime contract.

This rule binds any generator that emits an artifact installed into a customer's
environment: plugin manifests and `hooks.json`, copied hook scripts, agent and
skill files a CLI loads, MCP configs, instruction mirrors. It does not bind
artifacts consumed only inside this repo's own CI.

The `applyTo` globs target the surfaces where these artifacts are authored,
generated, and verified: the generator scripts, the templates they read, the
Copilot CLI plugin tree, the instruction mirrors, the hook sources, and the
runtime-contract tests. It is intentionally narrower than the full set of
artifact classes named above. Already-generated agent, skill, and command
outputs are governed at generation time by their own generators plus the
canonical-source-mirror drift checks (see `.claude/rules/canonical-source-mirror.md`);
this rule does not re-list every generated output tree in `applyTo`.

## The runtime contract is part of the artifact

Every customer-facing artifact depends on a runtime contract: the working
directory the host sets, the environment variables it exports, the process model
(shell, interpreter on PATH), and the target tool and version. That contract is
as load-bearing as the artifact's bytes.

### MUST

1. **Verify the contract empirically, not by analogy.** Before you depend on a
   runtime behavior (an env var name, the cwd, an exit-code convention), run the
   target tool and observe it. Do not infer a contract from another tool's
   docs or from a similarly named variable. The incident's first fix assumed
   `COPILOT_PLUGIN_ROOT` by analogy to `CLAUDE_PLUGIN_ROOT`; it happened to be
   right, but the method could just as easily have shipped a wrong name that no
   test would catch. Record the verified contract in a decision memory or ADR
   with the tool version you measured against (example:
   `decision-copilot-cli-hook-plugin-root-contract`).

2. **Ship a runtime-contract test.** The artifact MUST have a test that executes
   it under the verified contract: set the cwd the host sets (for a plugin hook,
   a directory that is NOT the plugin root), set the env vars the host exports,
   run the command, and assert the intended effect (the script is found and
   runs). Include a negative control that proves the test fails when the artifact
   is wrong (a bare relative path must fail the same harness). See
   `tests/build_scripts/test_generate_hooks_runtime_contract.py`.

3. **Gate the shipped artifact, not only the generator.** A test that exercises
   the generator on a fixture is necessary but not sufficient; a hand-edit or a
   merge can desync the committed artifact. Add a validator over the committed
   artifact (example: `scripts/validation/validate_hook_anchoring.py`, wired into
   `scripts/validation/pre_pr.py`). Derive the expected shape from the generator,
   not a hardcoded copy.

4. **Smoke-test in the real target runtime where feasible.** Install the vendored
   artifact into the actual CLI and run it end to end. When the runtime needs
   auth or credits that bare CI lacks, force the smoke locally (the pre-push hook
   runs `tests/e2e/test_cli_hook_e2e.py` on hook-path changes) and document a
   release or nightly smoke for the platforms CI cannot cover. A skipped smoke
   MUST be loud, never silent.

### MUST NOT

1. **Self-referential tests do not count.** A test that asserts the generator
   produces a specific string, then checks the generator produced that string,
   proves nothing about runtime behavior and cannot catch a wrong contract. This
   is the canonical-source-mirror anti-pattern at the test layer. See
   `.claude/rules/canonical-source-mirror.md`.

2. **Do not ship an artifact you never executed in its target runtime.** "It
   regenerated cleanly" and "the schema validates" are not evidence the artifact
   works.

## Blast radius: a launcher failure must fail loud, not silently degrade

A hook's in-script handler protects against exceptions raised by the
script. It does nothing when the launcher (`python3 -u "<path>"`) fails before
the script runs, which is exactly what a wrong path causes. For any artifact the
host invokes as a command, a resolution failure is not a degraded feature; it can
block the host entirely.

The defense is prevention, not launcher-level fail-open. The MUST gates above
(verify the contract, runtime-contract test, gate the committed artifact, real
runtime smoke) stop a broken launcher from shipping in the first place. Making a
broken launcher silently exit 0 does not fix the bug; it converts a loud,
learnable failure into a silently disabled hook, so the customer's protection is
gone and no one finds out. That is the silent-failure anti-pattern.

### SHOULD

1. **Prevent the bad launcher; if one escapes, fail loud.** The launcher shape is
   fixed at generation time and verified by the gates above, so a path bug is
   caught before release. If a novel launcher failure still escapes, it must fail
   loud (surface the error) so it is detected and fixed, never masked by a silent
   exit 0 that hides a disabled hook. Do not add a launcher wrapper that swallows
   its own resolution failure. Treat any change to the launcher shape as
   architecture (it is the exact surface that caused the incident); route it
   through architect review before shipping.

2. **Size the blast radius before you ship.** Ask: if this artifact is wrong, what
   breaks for the customer, and how do they recover? If the answer is "everything"
   or "uninstall", the verification bar in this rule is mandatory, not optional.

## Quick Self-Review

Before you merge a change to a generator or a customer-facing generated artifact:

- Did you run the target tool to verify the runtime contract, and record it?
- Is there a runtime-contract test that executes the artifact under that contract,
  with a negative control?
- Is the committed artifact (not just the generator) gated?
- Did the artifact run end to end in the real runtime, or is the smoke documented
  and loud where CI cannot run it?
- If this artifact is wrong, does the customer get a degraded feature or a wedged
  environment? If the latter, are the MUST gates above in place so the bad
  artifact cannot ship, and does a launcher failure fail loud rather than degrade
  silently?

If any answer is "no" or "not sure", fix it before review. A customer should
never have to uninstall to recover from an artifact we generated.

## References

- `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md`. The incident.
- `.claude/rules/canonical-source-mirror.md`. Self-referential test anti-pattern.
- `.claude/rules/release-it.md`. Fail fast and loud; bound the blast radius by prevention, not by silently swallowing failures.
- `scripts/validation/validate_hook_anchoring.py`. The committed-artifact gate.
- `tests/build_scripts/test_generate_hooks_runtime_contract.py`. Runtime-contract test pattern.
- `tests/e2e/test_cli_hook_e2e.py`. Real-CLI smoke.
