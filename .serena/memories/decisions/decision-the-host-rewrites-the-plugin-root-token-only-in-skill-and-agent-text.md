# The host rewrites the bare plugin root token in skill and agent text but leaves reference files unchanged

**Atomicity**: 90%
**Category**: Hook contract, plugin roots
**Source**: Agent session sweep, sessions dated 2026-11. Sweep ids E038. State checked on main at 1be533c496 (2026-11-26).

## Question

Does the host rewrite the plugin root token everywhere, so no foreign environment can change the resolved locator?

## Conventional answer

An ADR draft said the host rewrites plugin root tokens and that no foreign environment can change the resolved locator.

## First-principles position

A probe refuted this. Agent bodies rewrite only the bare token. Files under references/ stay literal. In references/ and hand authored files the locator reads the live environment, so a foreign CLAUDE_PLUGIN_ROOT can displace it.

## Evidence with limits

- Claude Code 2.1.322 rewrote the bare token in a `SKILL.md` fence and in agent bodies (2026-11-11). It left reference text unchanged.
- `CLAUDE_SKILL_DIR` stayed literal in agent bodies and in references.
- The reviewer marked "references/ REFUTED". 152 of 489 sites are non-rewritable (2026-11-11).
- Limits: One model sample per probe row. Rules files and YAML were not probed. The Copilot CLI probe was unavailable and Codex was not run. The references/ row was the ADR author's run. The reviewer re-ran only the SKILL.md fence and agent body rows.
- State on main at 1be533c496 (2026-11-26): fixed. ADR-121 probe table row 5 reads that the token is not rewritten in a skill references/ file and the text stays literal. ADR-121 line 73 says 152 sites get no rewrite.

## Decision

Do not claim the host rewrite protects a plugin root command outside SKILL.md text and agent bodies. In references/ and hand authored files the locator reads the live environment, so a foreign CLAUDE_PLUGIN_ROOT can displace it.

## Related

- `.serena/memories/pr-review/completion-gate-needs-uv-run-and-no-foreign-plugin-root.md`
- `.serena/memories/decision-plugin-roots-ship-alone.md`
