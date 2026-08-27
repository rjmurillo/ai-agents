---
applyTo: build/scripts/**,templates/**,src/copilot-cli/**,.github/agents/**,.github/prompts/**,.github/skills/**,.github/instructions/**,tests/build_scripts/**,tests/e2e/**
---

# Customer-Facing Generated Artifacts

This rule exists because of a P0 incident. A generator produced the Copilot CLI
plugin's `hooks.json` with a bare `./hooks/...` command path and explicit
`cwd: "."`. Copilot CLI 1.0.57 resolved that path from the user's working
directory, not the plugin install directory, so every hook failed at launch
with "No such file or directory". The failure happened before any in-script
handler could run. The only recovery was to uninstall the plugin. The broken
form shipped for 33 days across six releases (v0.3.0 to v0.5.6). See
`.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md`.

Current official docs define hook `cwd` relative to the repository root or as
an absolute path. The Copilot CLI changelog documents plugin-root variables.
The historical incident still controls our design: generated launchers anchor
plugin files explicitly and never depend on ambient cwd.

The root cause was not the wrong path. It was that a customer-facing artifact
shipped without ever being executed in its target runtime. Every test validated
the artifact's structure (valid JSON, correct fields). None ran the artifact
under the real runtime contract.

This rule binds any generator that emits an artifact installed into a customer's
environment: plugin manifests and `hooks.json`, copied hook scripts, agent and
skill files a CLI loads, MCP configs, instruction mirrors. It does not bind
artifacts consumed only inside this repo's own CI.

The `paths` globs target every authoring, generated, and verification surface:
agents, skills, commands, prompts, rules, hooks, templates, generators, plugin
trees, and runtime-contract tests. This ensures future work loads the settled
harness contract before changing any artifact class.

## The runtime contract is part of the artifact

Every customer-facing artifact depends on a runtime contract: the working
directory the host sets, the environment variables it exports, the process model
(shell, interpreter on PATH), and the target tool and version. That contract is
as load-bearing as the artifact's bytes.

### MUST

1. **Load the settled harness contract before researching or changing it.**
   Read `agent-harness-reference` and its
   `references/official-hook-contracts.md` sidecar first. Re-probe only a
   docs-silent row, a version-sensitive row after a CLI change, or an observed
   contradiction. Do not infer one harness from another. Record a new result
   with its tool version, date, official source, and negative control.

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

5. **Preserve one valid structured output per command hook.** Copilot CLI parses
   at most one final JSON document from each command hook. Before consolidating
   several source hooks, classify every stdout producer. If more than one source
   emits `decision`, `additionalContext`, `modifiedResult`, or another documented
   structured field, either merge those fields with event-specific semantics and
   positive, negative, and edge tests, or keep the sources as direct host
   registrations. Byte passthrough is not output merging. The current Copilot
   adapter merges successful PostToolUse observer text into one
   `additionalContext` object and discards partial text from failed observers.
   It captures SessionStart and PreCompact Python stdout and stderr, direct
   writes to file descriptors 1 and 2, and inherited child-process output on
   both channels, then discards the content because current producers include
   branch-controlled repository prose.
   Their direct rollback commands suppress stdout and stderr while preserving
   side effects. It also suppresses UserPromptSubmit stdout and stderr, and
   direct rollback commands preserve that choice. Read that suppression as a
   docs-silence policy, not as a measurement: the official config-file
   contract documents no output field for the event and does not document
   stderr as a model-context channel, and both remain silent. The runtime is
   no longer silent. Issue #4727 probed Copilot CLI 1.0.79-6 on the
   `.claude/settings.json` surface with a matched pair, plain stdout against a
   top-level `{"additionalContext": "..."}` document, and only the envelope
   reached the model. A UserPromptSubmit producer that needs model reach
   therefore emits that envelope itself, keyed on `COPILOT_CLI`, which is what
   the memory-recall hook now does. Version-scoped empirical behavior on
   1.0.79-6, not a vendor guarantee.
   PostToolUseFailure and unclassified future events remain direct because their
   host output semantics have no reviewed generic merger. Do not invent or erase
   event semantics. Claude grouped gates may terminate only on a validated,
   event-specific blocking shape. Generic JSON with no protocol keys is context
   and later guards continue. Malformed object-shaped JSON, allow-shaped
   decisions, unsupported decision fields, and invalid field types fail closed
   in gate modes. Empty gate manifests also fail closed. Test every terminal
   shape with a later blocking guard as the negative control.

### MUST NOT

1. **Self-referential tests do not count.** See the sibling rule file
   `canonical-source-mirror.md` (mirrored across trees under different names;
   look it up by name in whichever tree you're reading this from), Anti-patterns
   section ("Self-referential test that mirrors the producer's own output"), for
   the full rule and the PR #2205 example. Applied here: a test asserting the
   generator produces a specific string, then checking the generator produced that
   string, proves nothing about runtime behavior.

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

## Generator order: sync before build

The plugin library is mirrored twice, in a chain, by two scripts that do not
call each other:

```text
scripts/{hook_utilities,github_core,ai_review_common}
    |  scripts/sync_plugin_lib.py   (SYNC_PAIRS)
    v
.claude/lib/*
    |  build/scripts/build_all.py   (copy_lib_to_platform)
    v
src/copilot-cli/lib/*
```

`build_all.py` reads `.claude/lib/` and never populates it. So a change under
`scripts/github_core/` reaches the Copilot tree only if `sync_plugin_lib.py`
runs first.

### MUST

**Run `scripts/sync_plugin_lib.py` before `build/scripts/build_all.py`.**

Running them in the other order leaves `src/copilot-cli/lib/` mirroring the
previous contents of `.claude/lib/`, and **both scripts exit 0**. There is no
local signal. The stale mirror surfaces only when
`scripts/ci/check_plugin_lib_mirrors.py` runs, which for most contributors
means after the push, in CI.

The ordering is currently implicit. `build_all.py` refers to a "legitimate
pre-build sync of .claude/lib" in a comment on `assert_no_claude_writes`
(issue #2613), and its `.claude/` write guard is deliberately scoped so that a
sync performed *before* the build does not trip it. That guard is evidence the
sync is expected to run first; it is not an enforcement of it, and nothing
fails when you skip it.

Do not resolve this by having `build_all.py` invoke `sync_plugin_lib.py`.
REQ-003-010 forbids generators from writing under `.claude/`, and the sync
writes there by design. The two stay separate; the order is the contract.

## Quick Self-Review

Before you merge a change to a generator or customer-facing artifact:

- Did you read the settled contract before changing the artifact?
- If the change touches a mirrored library (`scripts/hook_utilities`,
  `scripts/github_core`, `scripts/ai_review_common`), did you run
  `sync_plugin_lib.py` before `build_all.py`, and confirm all three copies
  match rather than trusting the exit codes?
- If you re-probed, did a refresh condition require it, and did you record the
  version, official source, and negative control?
- Is there a runtime-contract test that executes the artifact under that contract,
  with a negative control?
- Is the committed artifact (not just the generator) gated?
- If several source hooks share one host command, does it emit at most one
  event-valid JSON document?
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
- `.claude/skills/agent-harness-reference/SKILL.md`. Operational contract.
- `.claude/skills/agent-harness-reference/references/official-hook-contracts.md`. Official sources and refresh procedure.
- `.claude/skills/ai-agents-portability-campaign/SKILL.md`. Contract change workflow.
- `.claude/rules/canonical-source-mirror.md`. Self-referential test anti-pattern.
- `.claude/skills/software-engineering-library/references/release-it.md`. Fail fast and loud; bound the blast radius by prevention, not by silently swallowing failures.
- `scripts/validation/validate_hook_anchoring.py`. The committed-artifact gate.
- `scripts/sync_plugin_lib.py`. Populates `.claude/lib/` from `scripts/`. Run before `build_all.py`.
- `scripts/ci/check_plugin_lib_mirrors.py`. The gate that catches a stale Copilot lib mirror.
- `tests/build_scripts/test_generate_hooks_runtime_contract.py`. Runtime-contract test pattern.
- `tests/e2e/test_cli_hook_e2e.py`. Real-CLI smoke.
