# ADR Debate Log: Claude-Side Consolidated Hook Group Dispatch

## Summary

- **ADR**: `.agents/architecture/ADR-082-claude-hook-group-dispatch.md`
- **Review date**: 2026-07-20
- **Scope**: Cross-harness hook output, rollback, security, and grouped dispatch
- **Rounds completed**: 6
- **Outcome**: Accepted, six Accept votes
- **Current status**: accepted

## Phase 0: Related Work

| Item | State on 2026-07-20 | Relevance |
|------|---------------------|-----------|
| #2295 | Closed | Original Copilot matcher and process-spawn incident |
| #2342 | Closed | Gate and observe dispatcher modes |
| #3075 | Closed | Claude grouped-dispatch performance work |
| #3098 | Closed | Prior grouped-dispatch follow-up |
| #3192 | Closed | Permission surface investigation |
| #3197 | Open, blocked | Vendored-hook reduction program |
| #3217 | Open | Remaining permission-surface disposition |
| #3218 | Open, blocked | Dispatcher and hook retirement criteria |
| PR #3280 | Merged | Upstream permission-profile citation |
| github/copilot-cli#3176 | Open | Proposed permission profiles and `denyTools` |

## Round 1

### Agent Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Disagree-and-Commit | Stale metrics and contradictory lifecycle output wording |
| critic | Disagree-and-Commit | Rollback and capture boundaries needed stronger evidence |
| independent-thinker | Block | Output capture and finite permission markers could hide unsafe behavior |
| security | Accept | No unresolved security blocker in the reviewed shape |
| analyst | Accept | Core claims traced to code and versioned evidence |
| high-level-advisor | Accept | Direction was correct after bounded corrections |

Round 1 tally: **3 Accept, 2 Disagree-and-Commit, 1 Block**.

### Corrections

- Corrected the current PreToolUse inventory to 16 shims and 555 requested
  seconds.
- Removed finite runner-name permission markers and required
  `permissions.allow` to remain empty.
- Added process-level stdout capture for Python streams, direct writes to file
  descriptor 1, and inherited child processes.
- Separated PostToolUse context merging from SessionStart discard.
- Strengthened lifecycle rollback so producer side effects remain active.
- Updated ADR-068, ADR-071, ADR-085, rules, skills, tests, and memories.

## Round 2

### Agent Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Accept | Round 1 structure and evidence findings were resolved |
| critic | Block | Four output and rollback defects remained |
| independent-thinker | Accept | No unresolved P0 outside the critic findings |
| security | Accept | Security boundary was acceptable after the listed fixes |
| analyst | Accept | Evidence and implementation aligned |
| high-level-advisor | Accept | Remaining work was bounded and actionable |

Round 2 tally: **5 Accept, 0 Disagree-and-Commit, 1 Block**.

### Critic Findings and Resolutions

| Finding | Priority | Resolution |
|---------|----------|------------|
| PreCompact sent branch-controlled prose to stderr | P0 | Added PreCompact to the lifecycle discard policy |
| Claude grouping captured only `sys.stdout` | P0 | Reused file-descriptor-level process capture |
| Unknown Copilot events defaulted to observe mode | P0 | Added explicit safe-event allowlists; unknown events stay direct |
| Rollback could remove SessionStart side effects | P0 | Direct rollback retains producers and suppresses output at the shell boundary |

The implementation also retired the stale `.agents/hooks/hooks.yaml` inventory
and documented the live canonical and generated surfaces.

## Round 3

### Agent Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Accept | Architecture and ownership were coherent |
| critic | Block | Two fail-open paths remained in Claude grouped dispatch |
| independent-thinker | Accept | No additional blocking issue |
| security | Accept | Threat boundary and permission changes were sound |
| analyst | Disagree-and-Commit | Accepted with evidence and lifecycle residuals recorded |
| high-level-advisor | Accept | Direction remained the smallest complete correction |

Round 3 tally: **4 Accept, 1 Disagree-and-Commit, 1 Block**.

### Critic P0 Findings

1. Unknown exit-zero JSON was treated as a terminal decision. An advisory shim
   could emit `{"error":"timeout"}`, stop the group, and skip a later exit-2
   guard while the dispatcher returned 0.
2. Empty or malformed group manifests could execute no guards and return 0.
   Event/mode mismatch and path traversal also lacked strict entry validation.

### Corrections Before Round 4

- Unknown JSON now becomes context with a fixed stderr warning. Later gates
  continue. A regression proves an unknown object cannot skip a following
  exit-2 guard.
- Claude groups now reject empty shim lists, wrong field types, unknown events,
  event/mode mismatch, duplicate paths, absolute or escaping paths, and
  non-`.py` entries before execution.
- Runtime containment checks reject a resolved shim path outside the hooks
  directory.
- SessionStart and PreCompact now capture and discard Python stdout and stderr,
  direct writes to file descriptors 1 and 2, and inherited child-process output
  on both channels.
- Fixed diagnostics name the actual lifecycle event and never repeat captured
  branch content.
- A prior focused run reported 727 passed and 1 skipped. Its exact command was
  not recorded, so Round 4 did not treat that count as acceptance evidence.

## Round 4

### Agent Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Block | Nested and malformed decision shapes could still skip later guards |
| critic | Block | Allow-shaped output and path-resolution errors retained fail-open paths |
| independent-thinker | Block | Nested output, empty Copilot gates, and path failures remained |
| security | Accept | Reviewed security controls were acceptable, with residual tests requested |
| analyst | Block | Terminal classification used key presence instead of complete schemas |
| high-level-advisor | Accept | Round 3 corrections were directionally complete |

Round 4 tally: **2 Accept, 0 Disagree-and-Commit, 4 Block**.

### P0 Findings

1. Nested `hookSpecificOutput`, malformed recognized-key objects, and
   allow-shaped decisions were terminal. They could skip a later exit-2 guard
   while the grouped dispatcher returned 0.
2. `Path.resolve()` failures could escape the grouped runtime and produce a
   nonblocking exit.
3. A generated Copilot gate manifest with zero shims returned 0. Normal
   generation avoids that shape, so an empty runtime gate is drift and must
   deny.

### Corrections Before Round 5

- Terminal output now requires an event-valid blocking schema: top-level
  `continue: false`; Stop or SubagentStop `decision: block` with a string
  reason; or nested PreToolUse `permissionDecision: deny` with a string reason.
- Malformed object-shaped JSON, allow-shaped decisions, unsupported fields,
  missing reasons, and invalid common-field types fail closed in gate modes.
  Generic JSON with no protocol keys remains context and later guards run.
- Runtime path resolution and containment errors return 2. The Claude entry
  point also catches unexpected execution errors and returns 2.
- The emitted Copilot entrypoint rejects an empty shim list in every mode.
  The lower-level runtime rejects empty gates but permits an explicit empty
  observe call as a no-op. Normal generation never emits an empty manifest.
- Claude grouped execution restores `sys.argv` and `sys.path` around each shim.
  Imported modules, environment variables, and other process state remain
  shared.
- Tests now cover malformed, nested, allow-shaped, and invalid typed outputs;
  duplicate, absolute, backslash, non-Python, and escaping paths; path-resolution
  exceptions; empty Copilot gates; and `sys.argv` or `sys.path` mutation.
- Lifecycle discard claims now apply only to Copilot. Claude lifecycle groups
  retain Claude's stdout semantics.
- Exact hook and generator contract command:
  `uv run pytest -q tests/hooks/test_claude_hook_dispatch.py
  tests/hooks/test_dispatch_groups_parity.py tests/test_hook_dispatch.py
  tests/build_scripts/test_generate_dispatcher.py
  tests/build_scripts/test_generate_hooks.py
  tests/build_scripts/test_generate_hooks_injection.py
  tests/build_scripts/test_generate_hooks_runtime_contract.py
  tests/build_scripts/test_copilot_dispatcher_artifact.py
  tests/build_scripts/test_dispatch_expansion.py
  tests/build_scripts/test_dispatcher_matcher_union.py
  tests/build_scripts/test_hook_contract_knowledge.py`.
  Result before Round 5 review: 739 passed, 1 skipped.

## Round 5

### Agent Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Block | Invalid common fields and non-object nested output still returned 0 |
| critic | Block | The same classifier gap plus self-host preflight exceptions remained |
| independent-thinker | Block | Typed output and preflight error coverage were incomplete |
| security | Block | Invalid typed protocol output retained a high-risk bypass |
| analyst | Block | Implementation and evidence did not fully enforce the ADR claim |
| high-level-advisor | Block | Typed output remained fail-open despite the prior schema hardening |

Round 5 tally: **0 Accept, 0 Disagree-and-Commit, 6 Block**.

### Findings

1. Standalone invalid common fields such as `systemMessage: 7` or
   `suppressOutput: "yes"` bypassed blocker validation.
2. A present but non-object `hookSpecificOutput` became generic context.
3. Self-host detection and unexpected manifest-loader failures sat outside the
   complete exit-2 preflight boundary.
4. The empty-observe wording did not distinguish the generated entrypoint from
   the lower-level runtime helper.
5. The tests lacked valid `continue: false`, SubagentStop, wrong-event blocker,
   and observe-mode invalid-output controls.

### Corrections Before Round 6

- Common-field types are validated for every JSON object before output
  classification.
- Any present non-object `hookSpecificOutput` is invalid structured output.
- Self-host detection, manifest loading, stdin reading, and grouped execution
  each have an explicit fail-closed exception boundary.
- Tests cover standalone invalid common fields, null, numeric, and list nested
  output; `continue: false`; Stop and SubagentStop blockers; wrong-event
  blockers; observe-mode suppression; and preflight, manifest, and runtime
  exceptions.
- The empty-manifest record now states that generated entrypoints reject every
  empty manifest, while only the lower-level explicit observe call is a no-op.
- The same 11-file hook and generator command reports 764 passed and 1 skipped
  after the Round 6 null-field, later-gate, and path corrections.

## Round 6

### Initial Positions

| Agent | Position | Main finding |
|-------|----------|--------------|
| architect | Accept | No P0 or P1 finding on the first Round 6 tree |
| critic | Block | Exit-1 bypasses and path-alias validation remained |
| independent-thinker | Block | Present-null typed fields remained terminal |
| security | Block | Exit 1 could skip later gates |
| analyst | Accept | Runtime and record aligned on the first Round 6 tree |
| high-level-advisor | Accept | No P0 or P1 finding on the first Round 6 tree |

Initial Round 6 tally: **3 Accept, 0 Disagree-and-Commit, 3 Block**.

### Findings and Corrections

1. Present-null `stopReason` and `additionalContext` fields were accepted as
   absent. Presence-aware validation now rejects them. Three regressions cover
   top-level, context-only, and deny-document forms.
2. Gate mode stopped on exit 1, but Claude lets the action proceed on exit 1.
   Only exit 2 now short-circuits. Other errors run later gates. A later exit 2
   wins, and a later validated blocker document is emitted at exit 0.
3. The decision text still described the superseded first-nonzero behavior. It
   now matches ADR-035, the runtime, and the tests.
4. Claude group validation now rejects case-insensitive duplicate names and
   resolved aliases before a shim can run twice.
5. Generated Copilot entrypoints now reject drive-relative paths, non-Python
   basenames, exact duplicates, and case-insensitive duplicates.
6. Every `gate_all` blocking branch now overrides an earlier exit-1 error,
   including direct shim exit 2, unsafe paths, aliases, missing shims, and
   invalid output.
7. Exit-1 and exit-2 order is tested both ways. Resolved aliases are tested in
   `gate`, `gate_all`, and `observe`. The surviving-error context loss is
   tested and recorded as an accepted consequence.
8. Entrypoint path resolution and dispatcher import now sit inside a top-level
   exit-2 boundary. Subprocess tests inject RuntimeError, SystemExit(0), and
   SystemExit(1) during dispatcher import.
9. The exact 11-file command reports 771 passed and 1 skipped.

### Final Convergence Vote

| Agent | Position | Final finding |
|-------|----------|---------------|
| architect | Accept | No P0 or P1 finding |
| critic | Accept | No P0 or P1 finding |
| independent-thinker | Accept | No P0 or P1 finding |
| security | Accept | No P0 or P1 finding |
| analyst | Accept | No P0 or P1 finding |
| high-level-advisor | Accept | No P0 or P1 finding |

Final Round 6 tally: **6 Accept, 0 Disagree-and-Commit, 0 Block**.
ADR-082 transitioned from proposed to accepted on 2026-07-20.

## Residuals Presented for Final Vote

- Claude Code group-timeout failure behavior remains unmeasured. The host owns
  the cumulative group timeout.
- Direct lifecycle rollback suppresses launcher errors with producer output.
  This is an explicit security and behavior-preservation trade.
- `sys.stdin` replay is a Python stream and has no real file descriptor.
- In-process shims still share modules, environment variables, and other
  process-global state. `sys.argv` and `sys.path` are isolated per shim.
- Exit-2 gate shims preserve raw stdout and stop the group. Other nonzero
  errors run later gates; the first error propagates only when no later blocker
  supersedes it.
- A surviving nonblocking error makes Claude ignore merged group stdout, so
  successful sibling context is lost. The hook failure remains visible on
  stderr.
- The self-host plugin bail uses project plugin-name equality. It is a
  performance dedupe, not a security boundary, because trusted project hook
  configuration can already execute arbitrary commands.

## Strategic Assessment

- **Chesterton's Fence**: Pass. The prior per-hook isolation and output behavior
  are documented before consolidation.
- **Path dependence**: Pass. Direct registrations remain the rollback shape.
- **Core vs context**: Pass. The dispatcher reduces repeated runtime cost while
  keeping vendor-specific protocol translation at the boundary.
- **Second-system effect**: Pass. The change reuses existing hook sources and
  does not add a daemon, IPC layer, or new permission framework.
