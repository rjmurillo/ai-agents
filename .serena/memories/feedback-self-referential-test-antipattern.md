# Feedback: the self-referential-test anti-pattern

**Origin:** PR #2205 customer-wedge incident, retrospective Phase 4 RC8 item 3. See `.agents/retrospective/2026-06-02-pr-2205-customer-wedge-incident.md` and `.claude/rules/canonical-source-mirror.md`.

## Definition

A test is self-referential when it calls a generator (or any producer) and asserts on that producer's own output. It pins the output to itself. It confirms the producer is internally consistent. It does NOT verify the output against the canonical contract the output is supposed to honor.

The classic shape: assert the generator emits string X, then check the generator emitted string X. Both halves come from the same source, so the test passes whenever the generator agrees with itself, which is always.

## Why it proves nothing about the contract

The canonical contract lives outside the generator: it is the target runtime's behavior (the cwd the host sets, the env vars it exports, the exit-code convention it expects, the wire format a reader parses). A string-match test never touches that runtime. It cannot catch a wrong variable name, a wrong path, a wrong exit code, or a wrong env-var contract, because the "expected" value it compares against was produced by the very code under test. If the generator is wrong, the assertion is wrong in the same direction, and the test stays green.

This is the canonical-source-mirror anti-pattern applied at the test layer. The producer mirrors itself instead of mirroring the canonical source.

## The evidence

PR #2205 shipped `tests/build_scripts/test_generate_hooks_plugin_root.py`, a string-match test against `generate_hooks._build_copilot_entry`. It asserted the generator produced specific command strings, then checked the generator produced those strings. It passed on every CI run.

Meanwhile the generated `hooks.json` used bare `./hooks/...` paths with `cwd: "."`. Copilot CLI runs plugin hooks with cwd = the user's working directory, not the plugin install dir, so every hook failed at launch with "No such file or directory". The self-referential test was green while customer environments were wedged for 33 days (v0.3.0 to v0.5.6). The only recovery was uninstalling the plugin. The test never exercised the one thing that mattered: whether the artifact resolves under the host's real cwd and environment.

## How to write the correct test

Exercise the contract independently. Run the artifact under the real runtime conditions and assert the intended effect:

1. Set the cwd the host actually sets. For a plugin hook, that is a directory that is NOT the plugin root.
2. Set the env vars the host actually exports (verified by running the target tool, not assumed from docs or analogy).
3. Run the command and assert the intended effect (the script is found and runs, the exit code matches, the side effect happens).
4. Add a negative control: prove the test FAILS when the artifact is wrong. A bare relative path must fail the same harness. Without the negative control you cannot tell a passing test from a test that cannot fail.

The replacement for the PR #2205 test is `tests/build_scripts/test_generate_hooks_runtime_contract.py`, which runs the generated commands under the verified contract (cwd != plugin root; var = install dir) with a bare-path negative control, instead of string-matching the generator output.

## How to apply

Before trusting a test that guards a generated artifact, ask: does the assertion compare the output against the producer, or against the canonical contract? If both sides trace to the generator, the test is self-referential. Replace it with a runtime-contract test plus a negative control.

Related: `mem:feedback-generated-artifact-runtime-verification`, `mem:decision-copilot-cli-hook-plugin-root-contract`, `.claude/rules/canonical-source-mirror.md`, `.claude/rules/generated-artifacts.md`.
