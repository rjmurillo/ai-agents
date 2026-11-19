# ADR-121 Amendment 2026-11-14: Evidence and Reviewer Asks

This file holds the detail behind the 2026-11-14 amendment to
`.project-toolkit/architecture/ADR-121-one-resolver-for-plugin-root-commands.md`.
The ADR keeps the decisions. This file keeps the measurements, the reviewer
asks, and the accepted costs, so the ADR stays under its 500-line cap. Debate
log 4 (`.project-toolkit/critique/ADR-121-debate-log-4.md`) reviewed this text
while it sat in the ADR.

## Measurements

All counts are at b5e05e9c6 (2026-11-14). `scripts/validation/skill_size.py` caps a whole
`SKILL.md` file at 24,576 bytes (`SKILL_BYTE_LIMIT`, `len(raw)`).

- The locator head (`_HEAD` in `plugin_run_launcher.py`) has 482 matches in
  authored files, 298 of them under `templates`. Count: `git grep -F -o` of
  the head over `templates` and the hand-kept `src/claude` files.
- `github/SKILL.md` is 24,557 bytes with 5 copies of the head.
- `orphan-ref-validator/SKILL.md` is 24,535 bytes with 8 copies of the head.
  A ninth line names `ptk_run.py` in prose.
- A target probe in the shell text adds 26 bytes to every site. That draft
  sets `t=TARGET;` once and adds `&& [ -f "$d/$t" ]`. The 271-byte locator for
  `new_pr.py --x` grows to 297. `github/SKILL.md` would reach 24,687 bytes and
  `orphan-ref-validator/SKILL.md` 24,743. Both exceed the cap.

## Reviewer asks decided

| Ask | Source | Decision |
|---|---|---|
| Select the root by its target too | #7340 (`fix-markdown-fences`), #7341 (`repository-completion-proof`) | Adopted as decision 11, in Python. |
| Put `.claude` first for repo-local skills | #7341 (`repository-pr-recovery`) | Rejected. A repo's `.claude` would then shadow the installed, host-rewritten copy for every skill, against decisions 4 and 10. Decision 11 already reaches `.claude` when no plugin root holds a repo-local script. |
| Add a `PLUGIN_ROOT` candidate for Hermes | #7341 (`research`) | Rejected. ADR-115 records that Hermes `PLUGIN_ROOT` reaches MCP stdio servers only, not a skill's shell. ADR-071 records the Copilot `PLUGIN_ROOT` for plugin hooks only. A probe that finds it in a skill shell reopens this. |
| Resolve `SKILLOPT_DIR` from the same root | #7341 (`skillopt`) | Adopted as decision 14. |
| Write `${CLAUDE_PLUGIN_ROOT:-}` for `set -u` | #7340 (`memory-gate`) | Rejected. Row 6 shows the host leaves `${CLAUDE_PLUGIN_ROOT:-.claude}` literal, and decision 4's absolute path depends on the rewrite. Under `set -u` the locator aborts with an unbound-variable error, which is loud. `set +u;` inside the subshell would fix it at 8 bytes a site, which the two capped files cannot take. |
| Check a plugin manifest name on env roots | debate 4, security seat | Rejected. Alternatives already rejects the manifest as a marker: `.claude/` has none, and the Hermes packs use other names. Decision 10 says the resolver is not an authentication boundary. |

## Costs and limits

- `skill-bootstrap` moves its phase command blocks into a `references/` file so
  `SKILL.md` stays under 24,576 bytes. Row 5 says the host does not rewrite
  `references/`, so those commands rely on the probe alone. This is accepted
  for the largest skill.
- `autoplan` loses its `git rev-parse --show-toplevel` anchor. From a
  subdirectory of a checkout, its locator exits 2 with the `ptk_run:` prefix
  instead of finding the repo copy. Wrapping it in
  `cd "$(git rev-parse --show-toplevel)"` was weighed and rejected: it breaks
  the installed, no-checkout case that the locator serves.
- `skillforge` drops its `cd "$HOME/.claude"` line. The validators still need
  the skill under the working directory, and the locator's `.claude`
  candidate is relative to it.
- Hermes and Codex shells stay unproven, as the Rollout section says.
