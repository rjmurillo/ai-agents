---
# taste-lint: ignore file-size, accepted append-only record; splitting breaks audit continuity.
id: ADR-068
status: accepted
date: 2026-07-31
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-068: Consolidated Per-Event Hook Dispatcher

## Status

Accepted (2026-07-19). The implementation shipped before the decision record
completed its lifecycle transition. The mandatory six-agent adr-review reached
consensus after two rounds: 3 Accept, 3 Disagree-and-Commit, and 0 Block.
Round 1 P0/P1 accuracy and provenance findings were corrected before the final
vote. Review evidence and dissent are recorded in
`.agents/critique/ADR-068-debate-log.md`.

Six later amendments received their own six-role convergence reviews. The
contract-hardening amendment closed at 6 Accept. The observer-output amendment
also closed at 6 Accept after failed-observer output, merge semantics,
alternatives, and residuals were made explicit. The security-policy amendment
closed at 6 Accept after evidence, rejected replacements, human-governance
limits, permission-prompt friction, and ADR-085 reconciliation were recorded.
The observer-suppression and state-isolation amendment closed at 6 Accept after
UserPromptSubmit output, SessionStart field provenance, cross-harness counter
isolation, retirement triggers, and accepted dispatcher residuals were aligned
with the implementation.

The post-purge rebaseline also closed at 6 Accept after current economics,
closed issue state, the ADR-082 dependency, and the retirement endpoint were
made explicit.

Amended 2026-08-11 (issue #4874): re-evaluation triggers 2 and 3 fired. The
require-subagent-model gate joined the consolidated PreToolUse path, growing
the active manifest to three shims and 110 seconds of summed timeout. A
six-role adr-review re-affirmed consolidation; the dispatcher is retained and
the trigger thresholds below then read three shims and 110 seconds (issue
#5013 later re-baselined them; see the 2026-08-14 amendment below). The new gate's matcher is `^(Agent|Task)$`; matcher
disjointness bounds which shims deny, not which spawn, because the Copilot
dispatcher spawns every timed shim before the shim's own matcher check
(debate log:
`.agents/critique/ADR-068-071-085-metric-refresh-debate-log.md`). The same
review corrected the benefit claim: consolidation does not save process starts
on matched calls since #4706, and is retained for the reasons restated in the
paragraph below.

The decision remains active after the 2026-07-22 hook purge, with its cost
model corrected on 2026-08-11: on the Copilot dispatcher each timed gate shim
runs in a child interpreter since issue #4706, so a matched call there starts
the dispatcher plus one child per timed shim (three starts on a `git push`
today, down from four before issue #5013 excluded
`push_pr_script_identity_guard` from the generated Copilot inventory only)
where direct registration would start at most one. The Claude-side
dispatcher runs its single-shim groups in process, so a `git push` there
starts two dispatcher processes, matching direct registration. Consolidation is retained for one host entry per
event, the matcher-union zero-spawn path for non-matching calls, and one
reviewed dispatch and output policy, not for matched-call process savings.
The one-shim PostToolUse dispatcher saves none. Issue #3218
closed on 2026-07-28 after verification showed its
retirement premise was wrong: `_expand_dispatch_groups` and
`event_matcher_union` remain live generation paths, while parity tests cover
the generated surfaces. Removing or replacing the generated dispatcher
requires a new architecture decision that marks this ADR deprecated or
superseded and updates ADR-082's dependency.

The 2026-07-31 factual amendment received a six-role adr-review. All six roles
accepted the correction. The amendment changed no runtime behavior or accepted
design outcome. It replaced stale issue ownership with a re-evaluation trigger
that can fire and preserved the low process-savings finding.

The security-policy amendment removes test-runner auto-approval from both
harnesses. Test runners execute repository-controlled code, so an exact command
name cannot establish a safe approval boundary. No `permissions.allow` rule
replaces the hook. Normal host permission handling remains authoritative.
Safety-audit findings 19 and 48 record the original over-broad command pattern
and missing object-shape check. The full-context review at
`.serena/memories/reviews/fix-copilot-hook-contract-213f3af.md` recorded
CRITICAL_FAIL for distributing that policy to Copilot CLI. Generic
PermissionRequest translation remains available and tested for a future
reviewed policy.

Amended 2026-08-14 (issue #5013): ADR-085 Decision 7 is the policy authority
for this exclusion. It records the containment incident, the eligibility test
applied to it, and the eight reintroduction gates; this ADR records only the
derived dispatcher metrics that follow from that decision. Issue #5013
excluded `push_pr_script_identity_guard` from the generated Copilot inventory
only. `.claude/hooks/dispatch_groups.json` marks that group
`copilotExclude: true`. The same file still lists the guard in Claude Code's
canonical dispatch group, and `.claude/hooks/hooks.json` still registers that
group. The active Copilot PreToolUse manifest now contains two shims,
`markdownlint_guard` and `require_subagent_model`, summing to 100 seconds of
configured timeout, so the generated host entry requests 105 seconds. The
dispatcher, its matcher union, and its gate, observe, and advise modes are
unchanged; only the Copilot-side shim inventory and its configured timeout
sum moved. This is a scoped derived-metrics update, not a re-evaluation of the
consolidated-dispatcher decision, and the manifest shrank rather than grew, so
re-evaluation trigger 2 does not fire. Debate log:
`.agents/critique/ADR-068-071-085-5013-debate-log.md`.

Amended 2026-08-18 (issue #5061): a new PreToolUse gate,
`serena_memory_scope_guard`, joined the consolidated path to block Serena
memory writes aimed at a git worktree other than the calling agent's own.
Its matcher, `mcp__serena__(write|delete)_memory|serena-(write|delete)_memory`,
does not reduce to a documented Claude core tool name, so
`event_matcher_union` fails open for `PreToolUse` per Decision point 2: the
generated host entry now carries no `matcher` field at all, where it
previously carried `Bash|Agent|Task`. The active Copilot PreToolUse manifest
now contains three shims, `markdownlint_guard`, `require_subagent_model`, and
`serena_memory_scope_guard`, summing to 110 seconds of configured timeout, so
the generated host entry requests 115 seconds. The vendored Claude plugin
source now contains five registrations across two events: four PreToolUse
shims and one PostToolUse shim. This growth from two to three Copilot
PreToolUse shims meets re-evaluation trigger 2 below, and a new blocking gate
joining the consolidated path meets re-evaluation trigger 3. Before this
amendment, a supporting host spawned the Copilot dispatcher only on a Bash,
Agent, or Task call; after it, every PreToolUse-eligible tool call spawns the
dispatcher, since no host matcher is emitted at all. No current measurement
in this repository quantifies that frequency multiplier or the per-spawn
latency it costs; the "246 ms Windows cold start" figure elsewhere in this
ADR is explicitly a HISTORICAL, superseded number. ADR-071's 2026-08-18
amendment records why a direct, non-consolidated host entry and full
exclusion from the generated Copilot inventory were both considered and set
aside rather than adopted. A six-role adr-review re-affirmation of the
consolidated-dispatcher decision under this new load, and under the loss of
the PreToolUse host matcher union, is not recorded as part of this amendment;
issue #5151 tracks it, including the unquantified regression above, rather
than asserting the review happened here. Unlike the 2026-08-11 (#4874) and
2026-08-14 (#5013) firings of the same triggers, which each closed with a
same-change re-affirmation, this amendment defers it to #5151 instead.

## Date

2026-06-02; amended 2026-07-22, 2026-07-31, 2026-08-11, 2026-08-14, and
2026-08-18

## Context

Issue #2295 records a HISTORICAL Copilot CLI 1.0.57-era incident. Three of
197 `preToolUse` invocations were killed after 2 to 3 seconds and the host
denied the tool as `hook errored`. The other 194 invocations completed. The
incident isolated process startup and aggregate latency as the defect, not the
guard decisions.

The proposal-era measurements were:

- HISTORICAL N=40 `PreToolUse` shim registrations.
- HISTORICAL Windows cold start of about 246 ms for
  `py -3 -u <shim>`.
- HISTORICAL sequential aggregate of about 8.7 seconds.

Those numbers explain the original decision but do not describe the current
tree. PR #3295 completed the hook purge on 2026-07-22. Issue #4764 later added
the push-pr script identity gate. Issue #4874 added the require-subagent-model
gate. Issue #5013 (2026-08-14) then excluded `push_pr_script_identity_guard`
from the generated Copilot inventory only, and issue #5061 (2026-08-18) added
the Serena memory worktree-scope guard to both the vendored Claude source and
the generated Copilot inventory. The vendored Claude plugin source now
contains five registrations across two events: four PreToolUse shims and one
PostToolUse shim. The generated Copilot manifest now contains four
registrations across two events: three PreToolUse shims and one PostToolUse
shim. The generated Copilot plugin exposes one dispatcher entry for each event.
On the Copilot dispatcher, consolidation now costs interpreter starts on
matched calls (#4706 child processes); its retained value is registration
shape and the zero-spawn non-matching path.

Repository-local `.github/hooks/require-subagent-model.json` direct-registers
the sub-agent model gate for Copilot outside the dispatcher: local runs now,
cloud agent once the file reaches the default branch. That is a deliberate
repo-local exception to the consolidated path, not a plugin surface.

Local `.claude/settings.json` is a separate repository-only surface. It contains
seven registrations across SessionStart, UserPromptSubmit, PostToolUse,
PostToolUseFailure, SessionEnd, and PreCompact. The Copilot plugin generator
reads the vendored plugin source, not these local settings.

The current PostToolUse producer, `invoke_markdown_auto_lint.py`, emits
plaintext diagnostics rather than `modifiedResult` or pre-structured hook
JSON. The observer merger handles that current text contract only. A
field-bearing producer changes the dispatcher boundary.

Copilot CLI 1.0.72-1 changed two relevant host behaviors:

1. A PascalCase `PreToolUse` matcher was empirically observed to suppress a
   nonmatching host spawn.
2. A `timeoutSec: 2` probe timed out and failed open, then executed the tool.

The host still owns command lifetime. A generated `timeoutSec` value is
metadata supplied to the host, not an in-process deadline controlled by this
repository.

## Decision

Generate one dispatcher host entry per active, safely consolidatable Copilot
hook event. Keep decision events direct when independent structured outputs
must reach the host. Retain every generated per-matcher shim for consolidated
events and execute those shims in process through
`.claude/lib/hook_dispatch.py`. The canonical implementation is split across
`build/scripts/generate_dispatcher.py`, which emits dispatcher artifacts, and
`build/scripts/generate_hooks_events.py`, which stages and publishes them.

1. **One host entry per consolidatable event.** The generated manifest preserves
   registered shim order. `_dispatch.py` reads stdin once and delegates each
   named shim to `hook_dispatch.py`, which uses
   `runpy.run_path(str(shim_path), run_name="__main__")`. Configured `Stop` and
   `SubagentStop` targets bypass consolidation. The current vendored source has
   neither event. Native `agentStop` and `subagentStop` names are defensive
   exclusions if future mappings target them. Copilot removes progress records,
   concatenates remaining stdout, then parses one JSON document per command
   hook. A dispatcher that passes through multiple Stop decisions would produce
   invalid JSON and discard them.

2. **Host matcher union plus per-shim self-filtering.** For `PreToolUse`,
   `PostToolUse`, and `PermissionRequest`, the generator emits a host-side
   matcher only when every registered Claude matcher can be reduced safely to
   known tool names. It emits the ordered `|` union. If any matcher is empty,
   wildcarded, unknown, or otherwise not safely reducible, it emits no host
   matcher. A supporting host can then avoid nonmatching dispatcher spawns.
   A host that ignores the field, and every no-matcher fallback, still invokes
   the dispatcher. The retained generated shims remain the final matcher
   authority and self-filter in process. Closed issue #3075 delivered the
   host-union optimization.

   Manifest order preserves canonical registration order. The dispatcher does
   not infer a security priority from file names or reorder guards.
   Risk-prioritized ordering has no stable policy contract and can only move,
   not remove, the later-shim bypass. Any isolation change belongs to the
   measured hybrid alternative below.

3. **Three execution modes with distinct exit behavior.**

   - `gate`, used by `PreToolUse`, runs shims in manifest order. It stops on
     the first nonzero exit and returns that exit unchanged. A missing shim,
     empty shim list, malformed manifest, invalid timeout metadata, or
     unexpected dispatcher exception returns 2. If every registered shim
     returns 0, the dispatcher returns 0.
   - `observe`, used only by the explicit PostToolUse, PreCompact,
     SessionStart, and UserPromptSubmit allowlist, runs every shim. Only
     PostToolUse has active vendored registrations. The other adapters remain
     tested but dormant. Missing shims and nonzero exits are
     reported to stderr, but do not stop siblings. Normal observer dispatch
     returns 0. Entrypoint or manifest validation failure still returns 2,
     after which the host applies that event's policy. PostToolUse captures
     nonblank stdout only from successful shims, preserves registration order,
     and emits one documented `additionalContext` object. The merger creates
     flat text separated by one blank line. It does not preserve per-shim
     attribution. SessionStart, PreCompact, and UserPromptSubmit capture Python
     stream output, direct writes to file descriptor 1, inherited child-process
     stdout, Python stderr, direct writes to file descriptor 2, and inherited
     child-process stderr, then discard the raw content. SessionStart has a
     documented `additionalContext` field, but repository policy rejects the
     current branch-controlled producer text as model context. PreCompact and
     UserPromptSubmit have no documented config-file output field. Normal
     discard diagnostics name the lifecycle event and never repeat the content
     if a future vendored source activates one of these adapters.
     Capture-failure and observer-exit diagnostics are fixed but can be generic.
     Silent observers emit nothing. Partial output from a failing observer is
     discarded.
     Static instructions own equivalent Copilot guidance. Any event outside the
     explicit mode allowlists stays as direct host registrations until its output
     and failure contracts are reviewed. A future `modifiedResult` or
     pre-structured JSON producer must add a field-specific merger or remain
     direct.
   - `advise`, used by `PermissionRequest`, requires exactly one decision
     producer. A recognized exit-0 Claude object
     `{"decision":"approve|deny|ask","reason":"R"}` becomes
     `{"behavior":"allow|deny","message":"R","interrupt":false}` for approve
     or deny. Claude `ask` emits no Copilot output because Copilot accepts no
     `behavior: "ask"` value. Empty output invokes the host's normal permission
     handling. A 1.0.72-1 noninteractive probe denied in that mode, but this ADR
     does not treat empty output as a universal deny contract.
     Blank exit-0 output remains blank. Malformed or unrecognized exit-0
     output is suppressed with a stderr diagnostic. Every nonzero producer
     exit propagates unchanged. A missing or multiple producer returns 2.

4. **No in-process budget watchdog.** The manifest records positive,
   non-boolean integer timeout metadata. The consolidated host entry uses the
   sum of per-shim timeout values plus five seconds of dispatcher headroom. The
   current PreToolUse manifest has three shims with 110 seconds of configured
   timeout, so the generated host entry requests 115 seconds. The sum spans all
   shims because the dispatcher spawns every timed shim before the shim's own
   matcher check runs, so any matched call can consume the full configured sum.
   The Copilot dispatcher enforces per-shim bounds in child processes (#4706);
   the Claude-side dispatcher drops per-shim timeouts and each group's host
   entry bounds it. The host owns the
   aggregate process timeout. The 1.0.72-1 probe tested only a 2-second timeout.
   No evidence proves the host grants, caps, or enforces the requested 115
   seconds.
   There is no `COPILOT_HOOK_DISPATCH_BUDGET_MS`, 1500 ms default, `SIGALRM`,
   watchdog thread, or structured `budget_exceeded` result.
   In-process termination was rejected because a watchdog thread cannot safely
   kill a running Python thread, while an asynchronous signal can interrupt a
   guard in arbitrary interpreter state and is not a cross-platform contract.
   Killing the dispatcher process would duplicate the host kill and would not
   preserve later guards.

5. **PermissionRequest translation is a dormant, tested capability.** Copilot
   CLI 1.0.72-1 empirically ignored the canonical Claude decision shape and
   accepted the Copilot `behavior` shape. No PermissionRequest producer is
   registered now. The prior test-runner approval was removed because runners
   can execute repository-controlled code and destructive runner options. Any
   future producer needs security review and this adapter or an equivalent
   translation. The protected assets are the developer workstation, repository
   state, and the user's approval decision. Human ADR and PR review is the
   current compensating control. No mechanical CI gate proves that review
   occurred. A future producer must also refresh the host contract and add
   cross-harness positive, negative, edge, and destructive-option tests.

   The ADR owner is accountable for approving any future producer. Registering
   `PermissionRequest` without the same-change review, probe, and tests violates
   this decision even though no mechanical gate currently proves the review
   occurred.

   The adapter remains because it is inert, tested, and has no registration.
   Deleting it would reduce no current runtime risk and would add reconstruction
   cost for a future reviewed producer. ADR-085 initially ratified
   `test_auto_approval` as keep-as-hook. Its later security amendment supersedes
   that D-B ruling and now aligns with this decision: a runner-name allow rule or
   hook does not qualify because the runner still executes repository-controlled
   code.

6. **Publication and cleanup are transactional.**
   `build/scripts/generate_hooks_events.py` generates dispatcher files in a
   staging directory, discovers stale generated matcher shims in the published
   tree, and routes deletion and publication through
   `HookGenerationTransaction`. Orphan event cleanup removes only files whose
   ownership is proven by a matching manifest, dispatcher and bootstrap
   signatures, and generated or canonical-equivalent shim bodies. Symlinks,
   path escapes, malformed manifests, unknown files, and NO-REGEN files are
   preserved. Empty orphan directories are removed with nonrecursive `rmdir`
   only after commit.

7. **Direct decision-event cleanup is ownership-proven.** When an event changes
   from dispatcher mode to direct registrations, the generator removes only
   signature-verified `_manifest.json`, `_dispatch.py`, and `_bootstrap.py`
   files. It does not hand-delete or infer ownership from names.

8. **Generated artifacts remain authoritative.** The committed
   `src/copilot-cli/hooks/` tree is regenerated from canonical sources. Manual
   edits to generated mirrors are not accepted.

## Why the In-Process Kill Was Rejected

The dispatcher deliberately executed guards in one interpreter, trading
process isolation between guards for fewer process startups; #4706 has since
moved timed gate shims into child processes, so on Copilot the isolation
trade no longer buys startup savings for the current all-timed inventory.
Python provides no safe, portable operation that terminates one running guard
and leaves the shared interpreter trustworthy. A thread can request
cancellation but cannot force it. `SIGALRM` is POSIX-specific and can arrive
while a guard mutates process-global state. Starting each guard in a child process restores termination isolation at a
spawn cost, which #4706 accepted for every shim carrying timeout metadata;
untimed shims keep the in-process path.

The remaining timeout boundary is therefore the host process. On the measured
Copilot CLI 1.0.72-1 behavior, a host timeout fails open. The current
PreToolUse manifest has three shims. On the Copilot dispatcher a shim carrying
timeout metadata runs in a child process and a timeout denies (issue #4706), so
a hung timed shim cannot bypass later gates there. On the Claude side each
PreToolUse group holds exactly one shim and registers its own host entry, so no
shim runs behind another in one process today; the in-process bypass is latent
and becomes real when any group gains a second shim. The host can still allow
the tool when a gate never completes. The host
fail-open residual remains.

## Prior Art and Current Rationale

ADR-061 retained deterministic per-matcher shim generation and a drift gate.
That layout remains inside the event dispatcher. ADR-068 changes host
registration count, not canonical guard authorship or matcher semantics.

The current reasons to keep the dispatcher are:

1. One implementation path preserves reviewed dispatch and output policy for
   active events, at the cost of extra interpreter starts on matched calls
   since #4706 moved timed gate shims into child processes.
2. Per-shim self-filtering provides a fallback for old hosts and matchers that
   cannot be represented safely as a host union.
3. Generic PermissionRequest translation prevents future policy producers from
   sending Claude-only output to Copilot.

## Alternatives Considered

| Alternative | Result |
|-------------|--------|
| Keep one host entry per shim | Kept as the rollback shape. Its original rejection rationale (repeated interpreter startup) inverted when #4706 moved timed gate shims into child processes; on Copilot, direct registration would now start fewer interpreters on matched calls. Simplification requires a new architecture decision. |
| Depend only on host matchers | Rejected because matcher support is version-sensitive and not every Claude matcher reduces safely. |
| Add an in-process watchdog | Rejected because safe cross-platform termination of one in-process guard is unavailable. |
| Run each guard in a child process | Adopted on the Copilot dispatcher for shims carrying timeout metadata, where a timeout denies (#4706). Rejected as the universal model because it restores the process-spawn cost for untimed shims and on the Claude side. |
| Persistent daemon | Rejected because lifecycle, IPC, stale state, and recovery exceed the current need. |
| Keep output-bearing observers direct | Required unless an event-specific merger preserves one valid JSON document. |
| Keep PreCompact direct with shell suppression | Rejected as the normal mode when a vendored source exists because it restores repeated startup. Retained as a tested rollback shape. |
| Keep UserPromptSubmit direct | Rejected when a vendored source exists because plaintext output has no documented host field and direct entries restore repeated startup. |
| Discard observer stdout by default | Rejected. Dormant SessionStart, PreCompact, and UserPromptSubmit adapters have reviewed discard policies. Active PostToolUse uses `additionalContext`, and unclassified events stay direct. |
| Consolidate observers but direct-register every PreToolUse gate | The current PreToolUse inventory is three shims, every one timed, so on Copilot direct registration would start fewer interpreters per matched call than the dispatcher plus its children (#4706). The dispatcher remains on the live generation path; simplification requires a new architecture decision. |
| Reorder guards by perceived risk, or split selected critical gates | No stable criticality contract exists, and reordering only changes which later guards a hang bypasses. A split is a narrower form of the hybrid and needs the same measurement. |
| Tighten test-runner command matching | Rejected because a narrower pattern keeps the same trust flaw. A command name cannot prove the code executed by the runner is safe. |
| Replace the hook with `permissions.allow` (#3192, #3217) | Rejected for test runners because it recreates the same trust flaw on a declarative surface. |
| Delete the dormant PermissionRequest adapter | Rejected because it has no runtime registration, and deletion would add reconstruction cost without reducing current risk. |
| Add a mechanical security-review gate in this amendment | Deferred because no machine-verifiable review artifact exists. This ADR states the human control without claiming an unbuilt gate. |
| Consolidated per-event dispatcher | Chosen, with the host-timeout bypass recorded as residual risk. |

## Consequences

### Positive

- The current vendored tree keeps one host entry per active event and
  preserves one generation path for future safely consolidatable events.
- Hosts that support matchers can skip a dispatcher spawn for safely reduced
  nonmatching tool calls.
- Retained self-filtering keeps the generated shim matcher grammar as the
  fallback authority.
- A future reviewed PermissionRequest producer can receive the Copilot response
  shape without changing its canonical Claude output. Claude `ask` falls through
  to normal host permission handling. No permission policy is currently active.
- Removing test-runner approval restores the user's decision before
  repository-controlled test code executes.
- Stop hooks remain independent, so each structured decision reaches Copilot
  as one valid JSON document.
- One transaction owns dispatcher publication, stale matcher-shim deletion,
  and ownership-proven orphan file cleanup.

### Negative

- One dispatcher defect affects every shim registered for that event.
- The current complexity-to-value ratio remains low. A matched call now costs
  more interpreter starts than direct registration would (dispatcher plus one
  child per timed shim, #4706). Issue #3218 closed
  without removing the live generation machinery. Simplification requires a
  new architecture decision.
- A hung dispatcher process outside any timed child can still reach the host
  timeout, which fails open on the measured 1.0.72-1 host. Timed shims
  themselves deny on overrun (#4706), and each Claude group holds one shim, so
  no gate skips another today.
- In-process guards share interpreter state, stdin replay, and module state.
- The require-subagent-model script converts its own internal errors to allow
  (#4672 spend-gate policy). That guarantee holds end to end on the direct
  `.github/hooks` path and on the Claude plugin path, where the host matcher
  filters and the script runs directly (measured: malformed stdin exits 0).
  On the Copilot plugin path the generated matcher shim preserves that
  fail-open source policy for pre-dispatch input errors (malformed stdin,
  missing tool name). The dispatcher still fails closed on nonzero shim
  results and timed-shim timeouts.
- Issue #5061 (2026-08-18) added a PreToolUse gate whose matcher
  (`mcp__serena__(write|delete)_memory|...`) does not reduce to a known Claude
  core tool name, so `event_matcher_union` now fails open for `PreToolUse` and
  the generated host entry carries no `matcher` field at all. Before this
  change, the generated Copilot host matcher union included Agent and Task
  alongside Bash, so a supporting host could skip the dispatcher spawn for a
  nonmatching call. That host-side filtering is now lost for PreToolUse: every
  tool call, not only Bash and Agent/Task, spawns the dispatcher on a
  supporting host, per Decision point 2's no-matcher fallback. Per Decision
  point 2, each shim self-filters in process regardless of the host union,
  and `markdownlint_guard` and `require_subagent_model`'s own code is
  unchanged by this amendment, so only the host-side dispatcher-spawn
  optimization is lost, not any shim's guard decision.
  The repository-local lowercase `task` registration stays direct, outside the
  plugin dispatcher. Issue #5013 excluded `push_pr_script_identity_guard` from
  the generated Copilot inventory only, so a matched call that previously
  spawned the dispatcher plus two children (three starts total) now spawns the
  dispatcher plus three children, four starts total, on every PreToolUse-
  eligible tool call rather than only Bash and Agent/Task calls.
  The Claude side registers the gate as its own host entry, so Bash calls gain
  no spawn there.
- The current PreToolUse manifest sums to 110 seconds. The generated host entry
  requests 115 seconds after five seconds of dispatcher headroom. The dispatcher
  spawns every timed shim before the shim's own matcher check runs, so any
  matched call can consume up to the 110-second sum: five seconds of real
  headroom. On the Claude side per-shim timeouts are dropped and each group's
  own host entry (300, 60, and 60 seconds) bounds it. No
  current evidence shows whether the host grants, caps, or enforces it.
- The observer merger treats PostToolUse stdout as context text. The flat
  blank-line merge loses per-shim attribution. It does not merge
  `modifiedResult` or pre-structured JSON.
- Dormant SessionStart, PreCompact, and UserPromptSubmit adapters discard stdout
  and stderr if a future vendored source activates them. Capture covers Python
  streams, direct writes to file descriptors 1 and 2, and inherited
  child-process output on both channels.
- PostToolUseFailure remains direct. Generic observe mode discards nonzero-shim
  stdout, but the host converts exit-2 stdout for this event into recovery
  context.
- Observer capture uses temporary files and has no per-shim output ceiling.
  Registered shims are trusted executable plugin content, but a defective shim
  can fill local storage or produce an oversized PostToolUse host response.
- The dispatcher does not pin a shim inode between the manifest check and
  `runpy`. A same-user writer who can replace a plugin shim can also replace its
  imported modules, so file identity is not a separate security boundary.
- Discard telemetry records content-free stderr metadata and the real exit code.
  The dispatcher does not emit per-shim start, finish, or duration events.
  Sending one event per successful shim through host stderr would add noise to
  every tool call without a documented diagnostics side channel.
- Unclassified future events remain direct. This preserves host-defined output
  and exit semantics until an event-specific review authorizes consolidation.
- Test-runner commands now use normal host permission prompts. This is accepted
  friction because no automated command-name boundary safely replaces the user
  decision.

### Neutral

- Claude Code continues to use its canonical registration and matcher behavior,
  except that test-runner PermissionRequest approval is removed from both
  harnesses.
- Guard nonzero exits keep their values in gate and advise modes.
- Observer shim failures remain diagnostics rather than gates during normal
  dispatch.
- PreCompact remains a supported dormant adapter based on the official event
  contract. The 1.0.72-1 trigger probe was inconclusive.

## Reversibility and Rollback

The decision owns no persistent data. Setting `artifacts.hooks.dispatcher` to
false and regenerating restores per-shim `hooks.json` registrations. Direct
SessionStart, PreCompact, and UserPromptSubmit test fixtures retain side effects,
but the generator appends shell-level stdout and stderr redirection before the
Python process starts. This also suppresses direct file-descriptor and inherited
child-process output. The generation-level rollback test creates a dormant
SessionStart source, executes its direct command, proves its file side effect,
and proves both captured channels are empty.
Existing dispatcher support files become unregistered artifacts and must be
removed only through an ownership-proven generator change, not a hand deletion.

Stop uses the rollback shape because direct registration is its accepted
policy. SubagentStop will use the same shape if a source registration is added.

Rollback restores process isolation and repeated startup. No PermissionRequest
producer is currently registered, so rollback does not change active permission
handling. A future producer would require replacement translation or explicit
event removal before rollback. Re-enabling dispatcher mode and regenerating
restores the current layout.

## Re-evaluation Triggers

Reopen this decision when any of these occurs:

1. A material Copilot CLI version changes matcher, timeout, nonzero-exit, or
   structured-output behavior.
2. The active PreToolUse manifest grows beyond three shims or its summed
   configured shim timeout grows beyond 110 seconds (the host entry requests
   115), or in any state grows beyond five shims or 150 configured seconds.
   The five-shim, 150-second ceiling is absolute; amendments re-baseline the
   per-increment thresholds, never the ceiling. Issue #5013 (2026-08-14)
   re-baselined this per-increment threshold down from three shims and 110
   seconds after excluding `push_pr_script_identity_guard` from the generated
   Copilot inventory only. Issue #5061 (2026-08-18) re-baselined it back up to
   three shims and 110 seconds after adding `serena_memory_scope_guard`.
3. A new PermissionRequest producer or a new blocking gate joins the
   consolidated path.
   Relative to the 2026-08-11 baseline (Copilot `git push` four starts versus
   two direct, measured; sub-agent call four versus one, derived from the
   documented task-to-Agent mapping, not probed; union `Bash|Agent|Task`):
   interpreter starts per matched call grow further, or the union widens to
   additional tool names or collapses to no host matcher at all. Issue #5061
   (2026-08-18) fired this trigger: `serena_memory_scope_guard` joined the
   consolidated PreToolUse path and its matcher does not reduce to a known
   Claude core tool name, so the union collapsed from `Bash|Agent|Task` to no
   matcher, and every matched call now starts the dispatcher plus three
   children instead of two.
4. A PostToolUseFailure producer emits repository-controlled or other untrusted
   content. Its direct exit-2 stdout becomes model recovery context and requires
   security review.
5. A proposal removes or simplifies dispatcher, translation, parity, or drift
   machinery. The proposal requires a new architecture decision that maps
   active consumers, preserves or replaces live generation paths, and proves
   generated-surface parity before implementation.
6. Untrusted extension authors gain write access to the packaged hook tree, or
   observer output requires a hard storage quota.
7. The host adds a diagnostics side channel that can carry per-shim duration
   events without entering model context.

Live GitHub verification on 2026-07-31 confirms that #3295 and #3218 are
closed. Issue #3218 closed on 2026-07-28 after verification showed the
expansion seam and matcher union remain live, while parity tests cover
generated surfaces. Sources:
<https://github.com/rjmurillo/ai-agents/issues/3295> and
<https://github.com/rjmurillo/ai-agents/issues/3218>.

## Impact on Dependent Components

| Component | Owner and required behavior | Risk |
|-----------|-----------------------------|------|
| `build/scripts/generate_dispatcher.py` | Emits matcher unions, manifests, entrypoints, and dispatcher host entries | High |
| `build/scripts/generate_hooks_events.py` | Integrates consolidation and owns transaction-backed publication and deletion | High |
| `.claude/lib/hook_dispatch.py` | Canonical in-process gate, observe, and advise runtime | High |
| `src/copilot-cli/lib/hook_dispatch.py` | Generated runtime mirror, regenerated from `.claude/lib/hook_dispatch.py` | High |
| `build/scripts/generate_hooks.py` | CLI facade and module-level generation contract | Medium |
| `src/copilot-cli/hooks/**` | Generated manifests, entrypoints, bootstrap copies, and retained shims | Medium |
| `.claude/settings.json` | Repository-only Claude registrations; not an input to Copilot plugin generation | Medium |
| `.claude/hooks/hooks.json` | Four vendored plugin registrations; must not carry removed or local-only hooks | Medium |
| `.claude/hooks/dispatch_groups.json` | Grouped hook source; must not carry the removed approval producer | Medium |
| `.github/hooks/require-subagent-model.json` | Repo-local direct registration of the same canonical script (matcher `task`, repo-root cwd); cloud coverage begins at default-branch merge; matcher or failure-semantic changes bind both surfaces | Medium |
| `.claude/rules/lsp-first.md` | Static cross-harness source for Serena symbolic-tool steering | Medium |
| `.claude/skills/agent-harness-reference/references/official-hook-contracts.md` | Pinned output-field authority and docs-silent ledger | High |
| `tests/test_hook_dispatch.py` | In-process output-policy and merger contract tests | High |
| `tests/build_scripts/test_copilot_dispatcher_artifact.py` | Proves the producer, generated event directory, and all permission allow rules remain absent | High |
| `tests/build_scripts/test_generate_dispatcher.py` | Generated-entrypoint, mode, manifest, and security contract tests | High |
| `tests/build_scripts/test_generate_hooks.py` | Transaction, rollback, stale-shim, and orphan cleanup tests | High |
| `tests/build_scripts/test_dispatcher_matcher_union.py` | Host matcher union and no-matcher fallback tests for #3075 | Medium |
| `.agents/governance/GENERATOR-FILES.md` | Generator ownership inventory | Low |

## Implementation Notes

The shipped implementation differs from the original proposal in these
important ways:

1. Per-matcher wrappers are retained for consolidated events. Stop and
   SubagentStop remain direct host registrations.
2. `event_matcher_union` adds an optional host-side matcher union and omits it
   when reduction is unsafe.
3. `hook_dispatch.py` owns the mode behavior. The generated entrypoint validates
   event identity, mode, shim basenames, timeout metadata, and stdin size before
   delegation.
4. Timeout values are enforced per shim on the Copilot dispatcher since
   #4706 (child process, deny on overrun). The Claude dispatcher drops them;
   each group's host entry is its bound.
5. Stale generated matcher shims are discovered by
   `generate_dispatcher.find_stale_matcher_shims` but deleted only by
   `HookGenerationTransaction` in `generate_hooks_events.py`.
6. Runtime-contract subprocess tests execute generated entrypoints. The
   Copilot 1.0.72-1 claims come from isolated probes recorded by ADR-071, not
   from an assertion that the committed authenticated E2E was run.
7. Generic PermissionRequest tests translate approve and deny. Ask produces no
   output. No PermissionRequest producer is registered in either harness.
8. PreCompact is a supported but dormant generated observe event based on the
   official contract. The 1.0.72-1 trigger probe was inconclusive.
9. Observe mode merges PostToolUse text into one `additionalContext` response.
   Only successful shims contribute; failed-shim partial output is discarded.
   Dormant SessionStart and PreCompact adapters capture Python stdout and
   stderr, direct writes to file descriptors 1 and 2, and inherited
   child-process output on both channels. Their text is discarded. Normal
   discard diagnostics name the actual event and never repeat captured content.
   Content-bearing discarded stderr emits a fixed `EVENT=` record with the
   observer exit code and no raw content. Capture-failure and observer-exit
   diagnostics remain fixed but can be event-neutral. The dormant
   UserPromptSubmit adapter also discards both channels because no output field
   is documented and stderr model reach is docs silent.
   PostToolUseFailure stays direct so exit-2 recovery context reaches the host.
   Every unclassified event stays direct. A new field-bearing producer requires
   a field-specific merger or direct registration.
10. The focused removal regression ran on 2026-07-20:
    `uv run pytest tests/test_hook_dispatch.py
    tests/build_scripts/test_copilot_dispatcher_artifact.py
    tests/build_scripts/test_generate_dispatcher.py
    tests/build_scripts/test_generate_hooks.py
    tests/build_scripts/test_dispatcher_matcher_union.py -q`.
    Result: 370 passed, 1 skipped.

## Related Decisions

- ADR-061: deterministic matcher shim generation and drift discipline.
- ADR-066: prevention-first launcher policy. It does not override measured
  host timeout behavior.
- ADR-071: version-scoped hook runtime contract and evidence.
- ADR-082: Claude-side grouped dispatch reuses dispatcher helpers. Any
  retirement change must preserve or replace that dependency.
- ADR-035: repository exit-code categories.
- ADR-084: host-native mechanism preference applies only when the effect is
  equivalent.
- ADR-085: permission-surface asymmetry, the superseding D-B deletion, and
  Decision 7's policy authority over the 2026-08-14 Copilot-only
  `push_pr_script_identity_guard` exclusion.

## References

- Issue #2295: historical process-spawn incident.
- Issue #2342: observer consolidation and continuation, later narrowed to
  events whose structured outputs can be merged safely.
- Issue #3075: host matcher union and Windows spawn reduction.
- Issue #3192: closed prior proposal to replace test approval with
  `permissions.allow`.
- Issue #3217: ADR-085 implementation issue; superseding D-B removes test-runner
  auto-approval.
- Issue #5013: Copilot-only `push_pr_script_identity_guard` exclusion; policy
  owned by ADR-085 Decision 7.
- `build/scripts/generate_dispatcher.py`: dispatcher artifact owner.
- `build/scripts/generate_hooks_events.py`: transaction and cleanup owner.
- `.claude/lib/hook_dispatch.py`: canonical runtime.
- `.agents/audits/2026-07-02-safety-audit.md`: findings 19 and 48 on the
  removed producer.
- `.serena/memories/reviews/fix-copilot-hook-contract-213f3af.md`:
  CRITICAL_FAIL review record that triggered removal.
- `tests/build_scripts/test_copilot_dispatcher_artifact.py`: absence
  regressions for the producer, generated event, and allow rules.
- `tests/build_scripts/test_generate_dispatcher.py`: generated runtime tests.
- `tests/build_scripts/test_generate_hooks.py`: transaction and rollback tests.
- `.claude/skills/agent-harness-reference/references/probe-evidence.md`:
  version-scoped curated probe summary.
- `.agents/critique/ADR-068-debate-log.md`: six-agent acceptance review,
  corrections, residuals, and dissent.
- `.agents/critique/ADR-068-071-085-5013-debate-log.md`: issue #5013
  containment and exclusion review.

---

*Template Version: 1.1*
*Created: 2026-06-02*
*GitHub Issue: #2295*
