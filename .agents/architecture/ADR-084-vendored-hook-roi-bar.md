---
id: ADR-084
status: accepted
date: 2026-07-20
decision-makers: [rjmurillo]
supersedes: []
superseded-by: null
explainer: null
implemented: false
---

# ADR-084: Vendored-Hook ROI Bar

## Status

Accepted (repo-owner @rjmurillo, 2026-07-18). Requested by issue #3215 as part
of the issue #3197 vendored-hook ROI review. adr-review consensus recorded
(6/6 Accept, see the debate log). Blocks #3197: the hook elimination
that #3197 authorizes needs a written bar so the vendored surface does not
re-accrete.

## Date

2026-07-20

## Context

The project ships two plugin surfaces to consumers: the project-toolkit plugin
(`.claude/` and its generated `src/copilot-cli/` mirror) and the claude-agents
plugin (`src/claude/`). A consumer installs the plugin into their own repository.
The plugin's hooks then run in that consumer's repo, on that consumer's tool
calls, against that consumer's git origin and paths.

The #3197 ROI review measured the vendored hook surface against that reality and
found it is almost all cost:

- 12 of 13 push and memory hooks are dead code in any consumer repo. They gate
  on the git origin being `ai-agents` (`skip_if_consumer_repo` in
  `.claude/lib/hook_utilities/guards.py`), or on repo-root paths such as
  `build/scripts/` that the plugin never vendors. In a consumer repo they load,
  spawn, check the guard, and no-op. The per-hook enumeration and the single
  survivor are recorded in the #3197 ROI review; this ADR sets the bar, it does
  not restate that census.
- The LSP-first enforcement family (retired by the ADR-062 amendment filed under
  #3214) added one true positive in 6.5 weeks against a running tally of false
  positives, while paying a per-Read process-spawn tax on the hottest tool.
- Hooks that do carry weight ship no statement of what consumer value they
  deliver, so a plugin reader cannot tell a customer-facing hook from an
  internal-protocol enforcer that leaked into the vendored tree.

The failure mode is structural, not incidental. Without a written bar, every
future "add a hook to enforce X" request re-accretes internal dev-protocol
machinery into the surface a customer pays to load. The surface trends back
toward its current state the moment the #3197 cleanup lands.

The distinction the bar must hold is between two audiences that the current
surface conflates:

- The consumer, who installs the plugin to get value in their own repo.
- This repository's own contributors, whose dev protocol (session logs, ADR
  debate, retros, install parity, plugin version bumps, generator drift, PR
  description shape) is an internal concern that a consumer neither sees nor
  benefits from.

Internal enforcement already has a home that costs the consumer nothing:
`lefthook.yml` and CI, which run only in this repository and never ship.

## Decision

A hook may ship in a vendored plugin surface only if it delivers value in a
consumer's own repository. Internal dev-protocol enforcement stays in
Lefthook and CI. Prefer host-native declarations over process-spawning
hooks. Concretely, the bar is five rules:

1. **Consumer-repo value is required.** A vendored hook MUST state the value it
   delivers in a consumer's own repo. "Enforces our protocol" is disqualifying:
   a consumer does not run this project's protocol.
2. **Internal enforcement is not vendored.** Session logs, ADR debate, retros,
   install parity, plugin version bumps, generator drift, and PR-description
   shape are internal concerns. They live in Lefthook and CI only, never in
   a vendored surface.
3. **Prefer zero-spawn host-native surfaces.** When the host provides a
   declarative surface that achieves the same effect without spawning a process,
   use it. `permissions.allow` and `permissions.deny` in settings and static
   rules loaded as context both cost zero spawns per tool call; a PreToolUse
   hook that spawns an interpreter on every matching call does not. When the host
   surface cannot express the required logic (runtime inspection of tool
   arguments or file content, or conditional branching a static declaration
   cannot encode), a spawning hook is the right tool and this rule does not
   apply. The preference is for the declarative surface where it achieves the
   same effect, not a ban on hooks that do work no declaration can.
4. **Self-neutering hooks are banned from the vendored surface.** A hook that
   no-ops in consumer repos because it gates on the git origin
   (`skip_if_consumer_repo`) or on repo-root paths the plugin does not vendor
   delivers no consumer value by construction. It does not belong in the
   vendored surface. If the logic is genuinely internal, it moves to Lefthook
   or CI per rule 2; it is not shipped dead.
5. **Every vendored hook carries a one-line customer-value justification, and a
   planned CI check asserts its presence.** The justification lives in the
   hook's module docstring as a single line a plugin reader can find, by
   convention prefixed `Customer value:` so the check is a simple presence grep,
   not a semantic judge. That CI presence check is new surface to build (see the
   risks below; recommended for the #3216 to #3218 chain), not an existing gate.
   Once it ships it asserts the line is present on every hook in a vendored
   surface, so a new hook cannot land without stating who it helps. Until then,
   human review at ADR and PR time enforces the rule and judges whether the
   stated value is real.

## Consequences

### Positive

- The vendored surface trends toward customer value, not internal ceremony. A
  plugin reader can tell what each shipped hook does for them.
- Rule 5 is designed to make the bar mechanically enforced at the point a hook
  is added, once its CI presence check ships, rather than a convention that
  erodes. That check is the intended ratchet that stops re-accretion; until it
  lands, human review at ADR and PR time holds the line.
- Rules 3 and 4 push cost off the consumer's hot path: zero-spawn host-native
  surfaces where possible, and no dead hooks spawning per call to no-op.
- Internal enforcement does not weaken. It moves to Lefthook and CI. CI gates
  this repo's contributions unconditionally; Lefthook installs and runs the
  local Git hooks.

### Negative and risks

- Rule 5's CI check is new surface to build and maintain. The mitigation is that
  it is a presence check (grep for a docstring line), not a semantic judge of
  whether the stated value is real; the human review at ADR and PR time judges
  the value.
- Moving internal enforcement out of the vendored surface means a contributor
  who relied on a vendored hook firing locally now relies on Lefthook and CI.
  The mitigation is CI, which gates every PR unconditionally; Lefthook's native
  install command closes the local-commit gap, so the enforcement point moves
  but does not disappear.
- The bar is a policy, not a code change. It binds future additions only if
  reviewers apply it. Rule 5's CI check is what converts the policy into an
  enforced gate for the one rule that can be mechanically checked.

### What this ADR does NOT do

- It does not delete any hook. The elimination is the #3197 implementation work
  (#3216, #3217, #3218) that this bar governs. This ADR sets the standard those
  issues apply.
- It does not authorize retiring an actual security control. A hook that
  enforces a security property in consumer repos earns its place by that
  property, not by an ROI cost-benefit veto, and a future reviewer must not use
  this ADR's ROI bar to retire it. Of the two security gates current when this
  ADR was written, only the previously registered
  `invoke_security_gate.py` was consumer-effective: it was not
  `skip_if_consumer_repo` gated and ran on consumer Write/Edit.
  `invoke_security_commit_gate.py` was `skip_if_consumer_repo` gated, so it did
  not run in consumer repos; whether it should was the #3197/#3219
  security-rebuild question, not this ROI bar. Genuine security controls remain
  subject to the bar's mechanical rules (rule 5's docstring requirement applies
  to them like any vendored hook).
- It does not change any security property. The security posture of the current
  hooks is handled by the #3197 decision to rebuild a portable auth-edit hook on
  real consumer demand (#3219); this ADR governs ROI, not security controls.
- It does not retire the LSP enforcement family. That is the ADR-062 amendment
  under #3214. This ADR is the general bar; the ADR-062 amendment is the first
  application of it.

## References

- Issue #3215 (this ADR request), issue #3197 (vendored-hook ROI review).
- Issue #3216, issue #3217, issue #3218 (the elimination this bar governs).
- Issue #3219 (portable auth-edit hook, rebuilt on consumer demand).
- The ADR-062 amendment under issue #3214 (first application of this bar).
- `.claude/lib/hook_utilities/guards.py` (`skip_if_consumer_repo`, the
  self-neutering surface rule 4 addresses).
- The adr-review consensus for this ADR is recorded in
  `.agents/critique/ADR-084-debate-log.md`.
