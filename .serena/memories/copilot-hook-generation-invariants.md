# Copilot hook generation invariants

## Generated shim cleanup

The Copilot dispatcher generator owns stale matcher-shim removal. A stale file
is eligible for deletion only when all of these conditions hold:

- The file is a Python file in a generated event directory.
- `generate_hooks_body.is_shimmed` identifies generated shim content.
- The authoritative event manifest does not register the file.
- `regen_guard.detect_reason_strict` finds no inline or sidecar `NO-REGEN`
  protection.

Do not infer generated ownership from a filename containing `__`. Event
directories can contain support modules with that naming shape. Cleanup must
also propagate scan, read, and unlink failures; silently accepting a partial
cleanup can ship stale hook behavior. Protected stale shims remain in place and
the generator emits a notice naming the protection reason.

## Orphan event cleanup

When an event leaves the active target set, cleanup remains generator-owned.
An orphan directory is eligible only when a matching valid `_manifest.json`,
signature-verified `_dispatch.py` and `_bootstrap.py`, and every
manifest-listed `is_shimmed` Python file prove generated ownership.
Matcher-free copies require a same-name canonical source with an equal Python
program after comments and docstrings are excluded. The scan is one level
below the resolved hooks root. It preserves symlinks, path escapes,
malformed manifests, unknown files, and NO-REGEN files with NOTICE output.

Verified file deletions use the same `HookGenerationTransaction` as
publication, so rollback restores them after a later failure. After commit,
cleanup uses nonrecursive `rmdir` only on empty bytecode-cache and event
directories. What-if reports candidates without deleting them.

When dispatcher artifacts are staged off-tree, stale candidates must be
discovered in the published event directory rather than the empty staging
directory. Their deletion belongs to the same `HookGenerationTransaction` as
script, dispatcher, and configuration publication so a later failure restores
the stale shim. On Windows, a fresh deletion moves the original file object
into the journal to preserve metadata; a target already backed up in the same
transaction is unlinked without replacing the immutable first backup.

## Path safety

Event names must be one path component before any staging directory is created.
Stale cleanup uses `lstat()` to reject symlinked event directories and files,
then resolves each candidate under the resolved hooks root before adding it to
the deletion transaction. Windows compares active shim names with `casefold()`
so a case-only rename cannot classify the active file as stale.

`HookGenerationTransaction.delete_many` deduplicates targets and treats missing
or repeated deletions as no-ops. If a Windows move creates the journal backup
then raises, the transaction records the mutation so rollback restores the
original file object.

## Cross-platform tests

Windows publish simulations must initialize the hook-generation transaction
using the host platform's locking implementation, then scope `_IS_WINDOWS` and
the replacement operation only around publish calls. Setting `_IS_WINDOWS`
before transaction initialization imports Windows-only locking modules on
Linux and invalidates the simulation.

Repository-root discovery for observation sync is fail closed. A timeout or
missing Git executable returns no root instead of treating the current working
directory as verified.

## Transaction lock reliability

Hook generation lock acquisition must terminate on both Windows and POSIX.
Use nonblocking platform operations under one bounded deadline. Retry only
contention errors (`EACCES`, `EAGAIN`, and `EDEADLK`), propagate unrelated
`OSError` values immediately, and retain the last contention error as the
`TimeoutError` cause. The process-serialization test proves normal waiting;
platform fakes cover retry, timeout, and non-contention branches without a
real ten-second delay.

## Protocol encoding

Session-start context output is a UTF-8 protocol. The canonical context loader
reconfigures text streams to UTF-8 and explicitly encodes the binary fallback.
Edit `.claude/hooks/SessionStart/invoke_context_loader.py`, then regenerate its
Copilot CLI mirror rather than editing the generated file.

## Host contract boundaries

Canonical generation inputs are `.claude/settings.json`,
`.claude/hooks/hooks.json`, `.claude/hooks/dispatch_groups.json`, and
`templates/platforms/copilot-cli.yaml`. A vendored registration must exist in
both `hooks.json` and the referenced `plugin-*` dispatch group. Generated outputs are
`src/copilot-cli/hooks/hooks.json` and `src/copilot-cli/hooks/<event>/`.

- Current mappings include PreCompact.
- Stop and SubagentStop remain direct if registered. Consolidating structured
  decisions can concatenate JSON objects and make Copilot ignore the result.
- PermissionRequest `ask` has no Copilot response equivalent. Emit no behavior
  so normal permission handling continues.
- The PermissionRequest adapter accepts one complete JSON document independent
  of whitespace or pretty printing and rejects trailing content. Translated
  `approve` and `deny` decisions require a string `reason`. Malformed exit-0
  output is diagnosed on stderr, suppressed, and left to the host default.
- No PermissionRequest policy hook is registered in either harness. The
  test-runner auto-approval producer was removed because runner names do not
  constrain repository-controlled code or destructive runner options. Keep the
  generic adapter and tests, but require security review for any new producer.
- PostToolUse observer stdout uses an event-specific merger: only successful
  shims contribute, registration order is preserved, and one blank line
  separates flat text inside one `additionalContext` object. Failed-shim partial
  output is discarded.
- SessionStart and PreCompact capture covers Python stdout and stderr, direct
  writes to file descriptors 1 and 2, and inherited child-process output on
  both channels. The captured content is discarded. Current producers load
  branch-controlled session state, which is not trusted model context.
- Claude grouped dispatch treats unknown JSON as context and continues later
  gates. Only `continue: false`, Stop or SubagentStop `decision: block` with a
  string reason, and nested PreToolUse `permissionDecision: deny` with a string
  reason are terminal. Malformed object-shaped JSON, allow-shaped decisions,
  unsupported fields, and invalid field types fail closed in gate modes. It
  validates nonempty shim lists, reviewed event/mode pairs, unique relative
  `.py` paths, and hooks-directory containment before execution.
- Direct SessionStart and PreCompact rollback commands suppress stdout and
  stderr at the shell boundary while preserving producer side effects.
- PostToolUseFailure remains direct because exit-2 stdout becomes recovery
  context and generic observe mode discards nonzero-shim output.
- UserPromptSubmit has no documented config-file output field. The generated
  dispatcher and direct rollback commands send its successful stdout to stderr
  and emit no host JSON. Whether stderr enters model context remains docs
  silent. Docs silence is not absence: Copilot CLI 1.0.79-6 was measured
  consuming a top-level `additionalContext` document on this event while
  discarding plain stdout (issue #4727). The dispatcher's suppression is a
  policy choice about branch-controlled producer text, not a claim that the
  channel is unavailable. A direct producer needing model reach emits that
  envelope itself, keyed on a host check that prefers `CLAUDE_CODE_ENTRYPOINT`
  over `COPILOT_CLI`. `CLAUDE_CODE_ENTRYPOINT` is the only vendor-confirmed
  half of that check; `COPILOT_CLI` is an unconfirmed heuristic (a prior
  changelog citation for it does not exist in any published `@github/copilot`
  version, per the correction in `official-hook-contracts.md`). The precedence
  is kept regardless, both because it fails safe for Claude and because, if
  `COPILOT_CLI` does turn out to be real, Copilot would export it into every
  shell it spawns and a nested Claude session would inherit it.
- Only explicitly classified events receive dispatcher modes. Unclassified
  future events remain direct until output and failure semantics are reviewed.
- A PostToolUse `modifiedResult` or pre-structured output producer changes the
  dispatcher boundary. Add a field-specific merger with positive, negative, and
  edge tests, or keep that producer direct.
- A PostToolUseFailure producer that emits repository-controlled or other
  untrusted content requires security review. Its direct exit-2 stdout becomes
  model recovery context.
- GitHub documents PascalCase aliases for Claude-compatible hook events and
  lower-camel native event names. Do not infer event support from casing alone.
- The current contract, pinned official sources, and versioned probes live in
  `agent-harness-reference`. This memory records generator invariants, not the
  complete host contract.

## Command identity guards

Treat wrapper parsing as a policy boundary, not shell emulation. The push-PR
identity guard rejects GNU `env` split-string forms, including abbreviated long
options and clustered `-S`, because `env` reparses one argument into executable
arguments after the guard runs. It also rejects shell evaluator wrappers,
including BusyBox shell applets and clustered execution flags such as `-xc`.
Unknown `env` options fail closed.

The allowed path remains one exact direct invocation after supported
non-evaluating wrappers are normalized. Runtime tests must exercise both the
canonical Claude guard and the generated Copilot shim. Cover expansion syntax,
alternate interpreters, quoting, path normalization, benign commands, nested
wrappers, and wrapper option abbreviations.

## Evidence

PR 3076 sessions 3045 and 3046 covered positive, protected, filesystem-error,
transaction rollback, symlink, path traversal, case-only Windows naming, and
partial Windows move cases. Commit `4c83b4d7` passed all 817 build-script tests
with 1 platform skip, focused Ruff, normal and Windows mypy, generated drift
checks, a real POSIX symlink reproduction, and independent correctness and
security reviews. Session 3048 bounded transaction lock waits on both platforms;
commit `11b334d5` passed 820 build-script tests with 1 platform skip, focused
Ruff, Windows-platform and test-file mypy, generation drift checks, and an
independent code review.

## Related

- [copilot-agent-frontmatter-ci-enforcement](copilot-agent-frontmatter-ci-enforcement.md)
- [copilot-agent-frontmatter-ci-review-fixes](copilot-agent-frontmatter-ci-review-fixes.md)
- [copilot-disable-all-hooks-windows](copilot-disable-all-hooks-windows.md)
- [copilot-hooks-observations](copilot-hooks-observations.md)
