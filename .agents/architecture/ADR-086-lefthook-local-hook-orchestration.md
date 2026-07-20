---
id: ADR-086
status: accepted
date: 2026-07-20
decision-makers: [rjmurillo]
supersedes: [ADR-004]
superseded-by: null
explainer: null
implemented: true
---

# ADR-086: Lefthook for Local Git Hook Orchestration

## Status

Accepted. The repository owner directed the migration in PR #3259. Six-role
adr-review consensus approved this record on 2026-07-20. ADR-086 supersedes
ADR-004. Implementation is included in PR #3259.

## Date

2026-07-20

## Context

`origin/main` entered this migration with `.githooks/` Git entry points and a
delegated `scripts/hooks/pre-push` payload. The migration branch briefly
normalized wrappers under `scripts/hooks/` for all three hook events before
deleting both roots. Repository code owned installation, activation, job
selection, ordering, parallel execution, changed-file filters, standard input
forwarding, skip conditions, generated-file staging, and documentation.

That design duplicated work owned by established hook managers. It also created
repository-specific failure modes:

- A clone could contain every policy script but run no hooks until
  `core.hooksPath` was configured.
- Worktrees and moved virtual environments could retain stale activation state.
- Shell wrappers carried scheduling logic that Python policy tests could not
  exercise directly.
- Contributors needed custom setup and repair guidance.
- PR #3244 added more activation machinery to repair the framework instead of
  removing the need for that machinery.

The policy checks remain repository-specific. Their scheduling and installation
do not.

## Decision Drivers

- Remove repository-owned hook installation, activation, and orchestration.
- Use one declarative scheduler for all local Git hook events.
- Preserve fast local feedback, auto-fix behavior, and generated-file staging.
- Run a deterministic, pinned scheduler from the locked development environment.
- Make timeout and failure behavior observable through automated tests.
- Support cross-platform operation without custom payload wrappers.
- Keep protected CI checks as the remote enforcement backstop.

## Decision

Use Lefthook 2.1.10 as the only local Git hook orchestrator.

1. `lefthook.yml` is the source of truth for `commit-msg`, `pre-commit`, and
   `pre-push` scheduling.
2. Lefthook owns job scheduling, filters, groups and order, native
   `stage_fixed` for same-file formatter changes, standard input forwarding,
   skip conditions, and outer job timeouts.
3. `pyproject.toml` pins `lefthook==2.1.10` in both development dependency
   tables. `uv.lock` freezes the resolved artifact.
4. `lefthook.yml` `min_version` is a runtime compatibility floor. It does not
   own installation or select the repository's Lefthook artifact.
5. `lefthook.yml` sets the top-level `lefthook` command to
   `uv run --frozen lefthook`. Lefthook bakes this command into generated shims
   ahead of generic `PATH` lookup, so a generic `PATH` binary cannot silently
   replace the configured runtime.
6. Installation uses Lefthook's native command:
   `uv run --frozen lefthook install --reset-hooks-path`.
7. Repository policy stays in Python. The
   `scripts/validation/git_hook_policy.py stage-generated` command owns the
   generated-output allowlist, path safety checks, and `git add` for outputs
   whose paths differ from the staged inputs. Lefthook schedules those policy
   jobs but does not perform their `git add` itself.
8. PR #3259 deletes both custom framework roots. On `origin/main`, `.githooks/`
   contained the Git entry points and delegated pre-push work to
   `scripts/hooks/pre-push`. The migration branch briefly normalized wrappers
   for all three hook events before deleting both roots. Their installers,
   activation guards, tests, and setup instructions are removed with them.
9. Each Python subprocess invocation receives an inner timeout shorter than
   Lefthook's outer job timeout. Exit code 3 and captured diagnostics are
   guaranteed only when the inner timeout fires first. The Timeout Hierarchy
   section documents the outer-first limitation.
10. Explicit `LEFTHOOK_BIN`, `LEFTHOOK=0`, Git `--no-verify`, configuration
    overrides, and direct hook edits remain local bypasses. Repository policy
    forbids using them to skip required checks. Protected CI remains the
    authoritative remote backstop.

Earlier ADR text that names `.githooks/` or `scripts/hooks/` remains historical
evidence only. It does not authorize restoring either deleted framework root.

## Prior Art Investigation

### What Existed Before PR #3259

- ADR-004 selected one custom pre-commit script as the local orchestration point
  in December 2025.
- The design later expanded to `commit-msg` and `pre-push`, plus installation,
  activation, worktree repair, payload wrappers, and documentation.
- Issue #3182 and PR #3244 addressed deterministic activation because a correct
  policy tree could still be inert when Git did not point at it.
- PR #3259 replaces that scheduler with `lefthook.yml` while retaining Python
  policy functions and their tests.

### Historical Rationale

ADR-004 required immediate feedback, auto-fix, and one discoverable local entry
point. Those goals remain valid. The custom implementation predated a pinned hook
manager that covered the repository's pre-commit and pre-push behavior.

### Why Change Now

Lefthook 2.1.10 covers the scheduler responsibilities previously implemented in
this repository. Integration tests cover changed-file filters, group ordering,
standard input broadcast, native same-file staging, policy-driven
generated-output staging, installation, and process timeouts.

Keeping the custom scheduler after that coverage would retain framework
maintenance without retaining a repository-specific capability.

## Rationale

### Alternatives Considered

| Alternative | Benefit | Cost | Decision |
|-------------|---------|------|----------|
| Keep `.githooks/` and `scripts/hooks/` | No new runtime and full scheduler control | Retains installers, activation repair, wrappers, scheduling, and custom documentation | Rejected because these are commodity framework duties |
| Use CI only | No local installation and one remote environment | Delays feedback, loses pre-commit auto-staging, and spends CI time on local errors | Rejected because fast local feedback remains required |
| Use the Python `pre-commit` framework | Large hook ecosystem and established pre-commit support | Existing pre-push stdin, job graph, and staging behavior need adapters | Rejected because Lefthook matches all three current hook events directly |
| Use Husky and lint-staged | Simple staged-file linting in Node repositories | Adds Node-owned installation and provides less pre-push orchestration | Rejected for this Python-first, multi-event workflow |
| Install a standalone pinned Lefthook binary | Avoids uv startup for each hook invocation | Creates separate installation, pin, upgrade, and validation ownership | Rejected because the locked uv environment already owns development tools |

### Trade-offs

The repository adds one pinned third-party runtime and a larger declarative
configuration file. In exchange, PR #3259 removes repository code and
documentation for custom installation, activation, scheduling, and repair.

The Python policy module remains large because it contains repository rules.
Splitting it is a separate decision. This ADR removes scheduler knowledge from
that module rather than moving policy into Lefthook YAML.

## Consequences

### Positive

- One native installation activates all three Git hook events.
- One declarative file exposes job filters, groups, order, native same-file
  staging, generated-output policy jobs, and budgets.
- Two timeout layers bound each job. Python diagnostics are preserved when the
  inner subprocess timeout fires before the outer job timeout.
- Worktrees and clones no longer depend on custom `core.hooksPath` repair code.
- Integration tests exercise the pinned scheduler instead of payload copies.
- Removing shell payload wrappers reduces repository-owned platform-specific
  orchestration.

### Negative

- Contributors must restore the frozen uv environment before Lefthook can run.
- A Lefthook version change can alter scheduler behavior and requires integration
  tests on supported platforms.
- `lefthook.yml` repeats timeout values because Lefthook applies them per job.
- Direct policy invocations still need Python timeouts, so two reliability layers
  remain necessary.

### Neutral

- Python remains the language for repository-specific validation.
- Git `--no-verify`, Lefthook disable or configuration override mechanisms, and
  direct `.git/hooks` changes can bypass local feedback.
- Repository policy still forbids bypassing required hooks. Protected CI is the
  authoritative remote enforcement backstop.
- Lefthook is a local feedback scheduler, not a security boundary.
- `npx markdownlint-cli2` in `lefthook.yml` and
  `.github/actions/setup-code-env/action.yml` do not pin the npm package. This
  inherited supply-chain risk is outside this scheduler migration. Remediation
  is tracked by issue #3279. The risk is not covered by Lefthook or its version
  pin.

## Impact on Dependent Components

Every row records work completed by PR #3259.

| Component | Completed change | Risk |
|-----------|------------------|------|
| `.githooks/` and `scripts/hooks/` | Deleted entry points, payload wrappers, scheduling support, installers, and related tests | High |
| `lefthook.yml` | Added all local jobs, filters, groups, native `stage_fixed`, generated-output policy jobs, stdin handling, and outer timeouts | High |
| `pyproject.toml` and `uv.lock` | Pinned Lefthook 2.1.10 in both dev tables and froze its resolved artifact | Medium |
| `scripts/validation/git_hook_policy.py` | Retained repository policy, including generated-output allowlists, path checks, and `git add` for allowlisted additions, modifications, and tracked deletions, and added bounded child-process execution | High |
| `tests/test_lefthook_integration.py` | Added pinned scheduler, installation, filtering, stdin, native staging, policy-driven staging of allowlisted additions, modifications, and tracked deletions, order, and timeout coverage | Medium |
| `scripts/validation/checks_plugin.py` | Replaced custom activation checks with frozen uv-backed Lefthook validation | Medium |
| `CONTRIBUTING.md` | Replaced custom setup and repair instructions with native Lefthook commands | Medium |
| ADR-004 | Marked superseded by ADR-086 in the same change | Low |
| ADR-014 | Updated handoff enforcement configuration to use Lefthook pre-commit jobs and staging exclusions | Low |
| ADR-016 | Updated workflow path-filter guidance to remove the deleted Git-hook path dependency | Low |
| ADR-036 | Updated agent generation guidance to use Lefthook generation and generated-file staging jobs | Low |
| ADR-037 | Updated memory synchronization status to name the Lefthook `memory-sync-advisory` job | Low |
| ADR-054 | Updated Semgrep guidance to use the Lefthook pre-push `security-scan` job | Low |
| ADR-062 | Updated obsolete `.githooks` wording only. The per-turn Serena reassertion has no Lefthook Git-event equivalent, and PR #3259 completes no LSP hook relocation | Low |
| ADR-075 | Updated the content-controlled eval fixture exemption to name the Lefthook `skillforge` job | Low |
| ADR-083, ADR-084, and ADR-085 | Updated internal enforcement homes to Lefthook, CI, and `pre_pr.py` where each record applies | Low |
| `CITATION-SCHEMA.md` | Updated citation pre-commit guidance to add the verification command as a Lefthook job | Low |

## Implementation Notes

### Installation and Version Ownership

`pyproject.toml` owns the direct version pin in
`[project.optional-dependencies].dev` and `[dependency-groups].dev`. `uv.lock`
owns the resolved artifact. `uv sync --frozen --extra dev` restores that locked
environment without dependency resolution.

`lefthook.yml` sets `min_version: 2.1.10` only to reject incompatible runtimes.
It does not install Lefthook or own the version pin. The top-level
`lefthook: uv run --frozen lefthook` command is baked into generated shims after
explicit `LEFTHOOK_BIN` and before generic `PATH` lookup. Repository setup and
installation checks also invoke `uv run --frozen lefthook`.

### Staging Ownership

Lefthook owns job scheduling, filters, groups and order, native `stage_fixed`
for same-file formatter changes, standard input forwarding, skip conditions, and
outer timeouts. The `scripts/validation/git_hook_policy.py stage-generated`
command owns the repository-specific generated-output allowlist, path safety
checks, and `git add` for allowlisted additions, modifications, and tracked
deletions whose paths differ from staged inputs. Lefthook schedules those policy
jobs but does not perform their `git add` itself. Allowlisted generated additions,
modifications, and tracked deletions remain staged automatically without custom
hook installation or scheduling code.

### Timeout Hierarchy

`lefthook.yml` provides the outer kill boundary for the whole job. Python policy
commands give each subprocess invocation a shorter inner budget. For commands
that start sequential or batched child processes, a later child can reach the
outer boundary before consuming its full per-child budget. Exit code 3 and
captured diagnostics are guaranteed only when the inner timeout fires first.
This outer-first case is a documented limitation, not a blocker, because the
outer timeout still bounds the whole job.

The current per-invocation Python budgets are:

| Child process class | Inner budget | Applicable outer budget |
|---------------------|-------------:|------------------------:|
| Default | 90 seconds | At least 120 seconds |
| Semgrep | 840 seconds | 900 seconds |
| mypy | 840 seconds | 900 seconds |
| Full tests | 1,740 seconds | 1,800 seconds |
| Workflow emulation | 1,740 seconds | 1,800 seconds |
| CLI end-to-end tests | 1,140 seconds | 1,200 seconds |

`tests/test_lefthook_integration.py` requires at least 30 seconds between every
configured per-subprocess budget and its Lefthook boundary. This verifies
per-child configured budget headroom, not whole-command completion. The
30-second commit-message outer timeout is excluded from the child-margin check
because that policy path spawns no child process; adding one is a review
trigger. The separate hung-process test requires Lefthook to stop a one-second
test job before ten seconds elapse.

## Confirmation

These commands define acceptance. This ADR does not record that they were run.
Run acceptance from the primary clone.

```bash
uv sync --frozen --extra dev
uv run --frozen lefthook version
uv run --frozen lefthook check-install
uv run --frozen pytest tests/test_lefthook_integration.py -q
git diff --quiet
git diff --cached --quiet
uv run --frozen lefthook run pre-commit --force
git diff --quiet
git diff --cached --quiet
uv run --frozen python build/scripts/build_all.py --check
uv run --frozen python scripts/validation/pre_pr.py
git diff --quiet
git diff --cached --quiet
git diff --check
git diff --cached --check
git status --short
```

Acceptance requires all commands to exit zero. Lefthook must report version
2.1.10. `lefthook check-install` must confirm installed shims in the primary
clone. A linked worktree retains the non-blocking warning documented under
issue #2374, so it is not the acceptance environment for this check. The full
integration file must pass, including per-child timeout headroom, stdin,
filtering, native same-file staging, policy-driven staging of allowlisted
additions, modifications, and tracked deletions, installation, and failure
propagation.

The primary-clone verification must start and end with no tracked working-tree
or index changes. Untracked files are allowed. The forced pre-commit run must
execute the configured jobs and propagate any job failure. Clean-tree gates
must pass before and after that run, then pass again after generator drift and
pre-PR validation. These gates make every tracked hook or validator mutation
fail instead of relying on status inspection. Both whitespace checks must pass.
The final short status remains an extra diagnostic.

## Rollback Plan

The repository owner authorizes a revert PR. Trigger rollback only when
Lefthook cannot install or run on supported Windows or Linux, corrupts hook
ownership, or blocks commit or push with no prompt forward fix available.

Rollback must revert PR #3259 as one atomic change. The revert must restore both
`.githooks/` and `scripts/hooks/`, including their installers, tests, payloads,
scheduling support, activation logic, and documentation. After the revert, run
the restored commands:

```bash
uv run --frozen python scripts/install_git_hooks.py
uv run --frozen python scripts/install_git_hooks.py --check
uv run --frozen pytest tests/test_install_git_hooks.py tests/hooks/test_git_hooks_activation.py -q
uv run --frozen python build/scripts/build_all.py --check
uv run --frozen python scripts/validation/pre_pr.py
```

A partial rollback is invalid. Mixed installers, shims, configuration, and
payloads create a torn state with uncertain hook execution.

## Review Triggers

Review this decision when any of these conditions occurs:

- The pinned Lefthook version changes.
- Standard input semantics, staging, filtering, group order, or timeouts change.
- The repository adds another Git hook event.
- Hook execution stops using the frozen uv environment.
- Supported platforms report installation or execution failures.
- Evidence shows an internal policy requires an enforcement home other than
  Lefthook or CI.

## Update History

| Date | Update |
|------|--------|
| 2026-07-20 | Proposed the owner-directed migration in PR #3259. |
| 2026-07-20 | Revised version ownership, shim precedence, timeout, confirmation, rollback, and staging details through adr-review. |
| 2026-07-20 | Accepted by 6/6 Approve consensus. Implementation is included in PR #3259. |

## Related Decisions

- [ADR-004: Pre-Commit Hook as Validation Orchestration Point](ADR-004-pre-commit-hook-architecture.md)
- [ADR-006: Thin Workflows](ADR-006-thin-workflows-testable-modules.md)
- [ADR-042: Python Migration Strategy](ADR-042-python-migration-strategy.md)
- [ADR-054: Local Security Scanning](ADR-054-local-security-scanning.md)
- [ADR-084: Vendored-Hook ROI Bar](ADR-084-vendored-hook-roi-bar.md)

## References

- PR #3259, Lefthook migration.
- PR #3244, custom activation mechanism removed by this decision.
- Lefthook configuration: <https://lefthook.dev/configuration/>.
- Git hooks: <https://git-scm.com/docs/githooks>.
