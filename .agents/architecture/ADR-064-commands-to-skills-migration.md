# ADR-064: Retire `.claude/commands/` as a Canonical Authoring Surface; Skills Are the Single User-Invocable Surface

## Status

Proposed

status: proposed

## Date

2026-06-01

## Context

Claude Code slash commands live as Markdown files under `.claude/commands/*.md`.
Each fires as `/<name>` inside Claude Code. The GitHub Copilot CLI does not read
`.claude/commands/` (or `.github/prompts/*.prompt.md`) to build terminal slash
commands. That translation happens only in IDE chat (VS Code and Visual Studio).
The behavior is documented upstream in
[github/copilot-cli#618](https://github.com/github/copilot-cli/issues/618) and
[github/copilot-cli#1113](https://github.com/github/copilot-cli/issues/1113).

The consequence: a command is Claude-Code-only. The same workflow authored as a
skill (`.claude/skills/<name>/SKILL.md` with `user-invocable: true`) fires as
`/<name>` natively in both Claude Code and Copilot CLI. Two authoring surfaces
exist for the same concept (a user-triggered workflow), and only one of them
crosses the harness boundary. That is information leakage: a single decision
("how does a user invoke this workflow") is encoded in two places that must be
kept in sync, and one of the two silently fails on a supported platform.

This ADR is the first slice of issue #2139. It records the decision to retire
`.claude/commands/` as a canonical authoring surface and to make skills the
single user-invocable surface. It also fixes the naming decision for the
previously-namespaced `pr-quality/*` and `forgetful/*` commands, which is the
blocking question for every migration PR that follows. This ADR makes no code
changes. The migration PRs that depend on it (the skill ports, the generation
pipeline reconciliation, the prohibition guard, and the drift and eval updates)
are out of scope here and tracked separately under issue #2139.

### What Currently Exists

- `.claude/commands/` holds 22 user-invocable command files plus `CLAUDE.md`
  (an auto-generated `claude-mem` context file, not a command) and
  `pr-review-config.yaml` (a config sidecar, not a command):
  - Top-level (11): `build`, `plan`, `research`, `ship`, `spec`, `test`,
    `pr-autofix`, `pr-review`, `push-pr`, `validate-pr-description`,
    `context-hub-setup`.
  - `forgetful/` (4): `memory-explore`, `memory-list`, `memory-save`,
    `memory-search`.
  - `pr-quality/` (7): `all`, `analyst`, `architect`, `devops`, `qa`,
    `roadmap`, `security`.
- `build/scripts/generate_commands.py` bridges commands to Copilot CLI skills
  (REQ-003-001). Its docstring states the transform is intentionally narrow:
  top-level `.md` files only; sub-directories `forgetful/` and `pr-quality/`
  are skipped ("namespaced sub-commands the Copilot CLI runtime cannot model
  today"); `CLAUDE.md` excluded. Result: the 11 namespaced sub-commands are
  unreachable from Copilot CLI today.
- `templates/platforms/copilot-cli.yaml` declares the bridge under
  `artifacts.commands` with `sourceDir: ".claude/commands"`,
  `outputDir: "src/copilot-cli/skills"`, `transform: "command-to-skill"`, and
  `appendFrontmatter: { user-invocable: true }`. This keeps `.claude/commands/`
  as the canonical source.
- The previously-namespaced names overlap semantically with existing surfaces:
  - `pr-quality/{analyst,architect,devops,qa,roadmap,security}` share a stem
    with the same-named review agents under `.claude/agents/`
    (`analyst`, `architect`, `devops`, `qa`, `roadmap`, `security`).
  - `pr-quality/security` also sits near the existing `security-scan` and
    `security-detection` skills and the `security` agent.
  - `forgetful/memory-*` sit near the existing `memory`, `memory-enhancement`,
    `memory-documentary`, and `using-forgetful-memory` skills.
  - Verified at authoring time: none of the 11 namespaced names collide with an
    existing `.claude/skills/<name>/` directory. The conflict is semantic, not a
    directory clash.
- Prior art: ADR-030 (skills-pattern-superiority) establishes that skills give
  direct, scoped tool access with lower overhead than subagents. ADR-044
  (copilot-cli-frontmatter-compatibility) constrains the frontmatter fields
  Copilot CLI accepts. ADR-012 (skill-catalog-mcp) governs the skill catalog.
  `DESIGN-REVIEW-vscode-copilot-parity-plan.md` lays out the parity plan.

### Historical Rationale

- **Why commands were built this way?** Claude Code shipped `.claude/commands/`
  as the native slash-command surface before Copilot CLI was a target. The
  lifecycle command files (`/spec`, `/plan`, `/build`, `/test`, `/ship`) and the
  PR-quality batch were authored there because that was the only surface that
  fired as a slash command at the time. `/review` is already a skill, not a
  command file.
- **What alternatives were considered?** The `command-to-skill` bridge
  (REQ-003-001) was the first attempt to reach Copilot CLI: keep authoring in
  `.claude/commands/` and generate Copilot skills from it. The bridge works for
  top-level commands but cannot model the namespaced sub-directories, so it
  leaves 11 sub-commands stranded.
- **What constraints drove the design?** Copilot CLI's user-invocable skill
  surface is flat (no sub-directory namespacing). A nested command path
  (`pr-quality/security`) has no Copilot CLI representation that preserves the
  namespace, so the bridge skips it rather than collide a bare `security` skill
  with the `security` agent and the security-scanning skills.

### Why Change Now

- **Has the original problem changed?** Yes. Copilot CLI is now a shipping
  target with its own user-invocable skill surface. A command authored only in
  `.claude/commands/` is, by construction, invisible to half the platforms we
  support. The bridge papers over the top-level case and leaves the namespaced
  case broken.
- **Is there a better solution now?** Yes. Skills with `user-invocable: true`
  fire as `/<name>` in both Claude Code and Copilot CLI. One authoring surface,
  one canonical source, no bridge to keep in sync. ADR-030 already establishes
  the skill as the deeper module.
- **What are the risks of change?** The migration touches the generation
  pipeline (`generate_commands.py`, `generate_skills.py`,
  `templates/platforms/*.yaml`), drift tests
  (`tests/commands/test_lifecycle_command_drift.py`), and spec evals
  (`tests/evals/spec-scenarios.json`). Those are sequenced into later PRs under
  issue #2139. This ADR carries no code blast radius; its risk is limited to
  committing to a naming scheme that the migration PRs must then honor.

## Decision

1. **Retire `.claude/commands/` as a canonical authoring surface.** Skills
   (`.claude/skills/<name>/SKILL.md` with `user-invocable: true`) are the single
   canonical surface for every user-invocable workflow. A workflow that a user
   triggers as `/<name>` is authored as a skill, not as a command.

2. **Prohibit new `.claude/commands/*.md` entries.** No new command files may be
   added. New user-invocable workflows are skills. A prohibition guard that
   blocks new `.claude/commands/*.md` files is in scope for a later migration PR
   under issue #2139; this ADR records the rule the guard will enforce.

3. **`CLAUDE.md` is not a command and is exempt.** `.claude/commands/CLAUDE.md`
   is `claude-mem` auto-generated context. It is relocated or left as context by
   a later PR, never converted to a skill. `pr-review-config.yaml` is a config
   sidecar and is likewise not a command.

4. **Naming decision for the previously-namespaced commands.** Copilot CLI's
   user-invocable skill surface is flat, so the lost sub-directory namespace is
   reintroduced as a hyphenated prefix on the skill name. The skill name carries
   the namespace the directory used to carry:
   - `pr-quality/<name>` migrates to a skill named `pr-quality-<name>`:
     `pr-quality-all`, `pr-quality-analyst`, `pr-quality-architect`,
     `pr-quality-devops`, `pr-quality-qa`, `pr-quality-roadmap`,
     `pr-quality-security`.
   - `forgetful/<name>` migrates to a skill named `forgetful-<name>`:
     `forgetful-memory-explore`, `forgetful-memory-list`,
     `forgetful-memory-save`, `forgetful-memory-search`.
   - Top-level commands keep their bare names (`spec`, `plan`, `build`, `test`,
     `ship`, `research`, `pr-autofix`, `pr-review`, `push-pr`,
     `validate-pr-description`, `context-hub-setup`). `/review` is already a
     skill and is not part of the command migration inventory.

   The `pr-quality-` prefix disambiguates the batch-review entry points from the
   same-named review agents (`analyst`, `architect`, `devops`, `qa`, `roadmap`,
   `security`) and from the security-scanning skills (`security-scan`,
   `security-detection`). The `forgetful-` prefix disambiguates the
   memory-store entry points from the broader `memory` skill family.

5. **Preserve command semantics in skill frontmatter.** When a command migrates
   to a skill, the migration PR carries over `$ARGUMENTS`, `argument-hint`,
   `allowed-tools`, and any `@CLAUDE.md` import. The generated copilot-cli skills
   already model `user-invocable: true` plus `@CLAUDE.md`
   (see `src/copilot-cli/skills/spec/SKILL.md`), so the SKILL.md shape is
   established. ADR-044 constrains which frontmatter fields Copilot CLI accepts;
   migration PRs honor that constraint.

## Prior Art Investigation

### What Currently Exists

See the Context section above: 22 commands across one top-level set and two
namespaced sub-directories, bridged to Copilot CLI by
`build/scripts/generate_commands.py` (REQ-003-001) under the
`artifacts.commands` stanza of `templates/platforms/copilot-cli.yaml`. The
bridge skips the 11 namespaced sub-commands.

### Historical Rationale

See the Historical Rationale subsection above. `.claude/commands/` predates the
Copilot CLI target; the `command-to-skill` bridge was the first parity attempt
and cannot model namespaced sub-directories.

### Why Change Now

See the Why Change Now subsection above. Copilot CLI is a shipping target;
skills cross the harness boundary and commands do not.

## Rationale

### Alternatives Considered

| Alternative | Pros | Cons | Why Not Chosen |
|-------------|------|------|----------------|
| Keep commands canonical, widen the bridge to handle sub-directories | No re-authoring; one transform change | The bridge must invent a flat name for each nested command anyway, so it has to make the same naming decision this ADR makes, then maintain a generator that mirrors it forever; two surfaces still drift | Skills already cross the boundary natively; the bridge is the leaked decision |
| Flatten commands into `pr-quality/` and `forgetful/` skill sub-directories | Mirrors the current directory layout | Copilot CLI's user-invocable surface is flat; sub-directories have no Copilot representation, so the 11 sub-commands stay stranded | Does not solve the parity gap that motivated #2139 |
| Migrate to skills with bare names (`security`, `analyst`, `memory-save`) | Shortest names | `security`, `analyst`, `architect`, `devops`, `qa`, `roadmap` collide semantically with the review agents; `security` also overlaps the security-scanning skills; `memory-*` overlap the memory skill family | Reintroduces the ambiguity the namespace existed to prevent |
| Migrate to skills with `pr-quality-`/`forgetful-` prefixes (CHOSEN) | One canonical surface; native on both harnesses; names carry the old namespace and stay unambiguous | Skill names are longer than the bare command names | The longer name is the cost of a flat namespace; it buys disambiguation that the bare names lose |

### Trade-offs

The prefix scheme trades terseness for disambiguation. `pr-quality-security` is
longer than `security`, but `security` as a flat skill name would sit next to
the `security` agent, the `security-scan` skill, and the `security-detection`
skill, and a user typing `/security` could not tell which they meant. The
prefix encodes the namespace the sub-directory used to carry, so a reader who
learned the `.claude/commands/pr-quality/` layout already knows the
`pr-quality-` prefix means the same thing. This is information hiding by naming:
the namespace decision lives in the prefix, in one place, instead of in a
sub-directory that Copilot CLI cannot read.

## Consequences

### Positive

- One canonical user-invocable surface. A workflow is a skill, full stop. No
  reader has to learn when to author a command versus a skill.
- Native parity on Claude Code and Copilot CLI. The 11 previously-stranded
  namespaced sub-commands become reachable in Copilot CLI once migrated.
- The `command-to-skill` bridge and its generated outputs can be retired by a
  later PR, removing a generator that had to mirror a naming decision by hand.
- The naming decision is fixed once, here, so every migration PR under #2139
  ports against a stable target instead of re-litigating the prefix.

### Negative

- 22 commands must be re-authored as skills across several PRs. This ADR does
  not do that work; it unblocks it.
- Skill names for the previously-namespaced commands are longer than the bare
  command names.
- Until the migration PRs land, `.claude/commands/` still exists and the bridge
  still runs. This ADR records the target state; it does not change runtime
  behavior on its own.

### Neutral

- `CLAUDE.md` and `pr-review-config.yaml` stay where they are; they were never
  commands.
- The lifecycle command files keep their bare names (`/spec`, `/plan`,
  `/build`, `/test`, `/ship`), so muscle memory for those is unaffected.
  `/review` already remains available as a skill.

## Impact on Dependent Components

| Component | Dependency Type | Required Update | Risk |
|-----------|----------------|-----------------|------|
| `.claude/commands/*.md` (22 files) | Direct | Re-authored as `.claude/skills/<name>/SKILL.md` with `user-invocable: true` in later PRs; namespaced names take the `pr-quality-`/`forgetful-` prefix | Medium |
| `build/scripts/generate_commands.py` | Direct | Bridge retired or repointed once skills are canonical | Medium |
| `build/scripts/generate_skills.py` | Direct | Reconciled with the migrated skills | Medium |
| `templates/platforms/copilot-cli.yaml` (`artifacts.commands`) | Direct | `command-to-skill` transform removed or repointed | Medium |
| `src/copilot-cli/skills/` (generated bridge outputs) | Direct | Generated command-bridge outputs removed or repointed | Low |
| Prohibition guard (new, later PR) | Direct | Add a pre-push/CI guard blocking new `.claude/commands/*.md` | Low |
| `tests/commands/test_lifecycle_command_drift.py` | Direct | Re-keyed from command paths to skill paths | Medium |
| `tests/evals/spec-scenarios.json` | Direct | Re-keyed from command paths to skill paths | Medium |
| `CLAUDE.md` "Lifecycle commands" section | Indirect | Updated to reference skills when migration completes | Low |

## Implementation Notes

This ADR is the first slice of issue #2139 and ships no code. It unblocks the
migration PRs, each of which is a bounded slice:

1. Author this ADR and fix the naming decision (this PR).
2. Migrate the top-level commands to skills (bare names).
3. Migrate the `pr-quality/*` sub-commands to `pr-quality-*` skills.
4. Migrate the `forgetful/*` sub-commands to `forgetful-*` skills.
5. Reconcile the generation pipeline; retire or repoint the bridge.
6. Add the prohibition guard.
7. Re-key the drift tests and spec evals to skill paths.

Sequencing keeps each PR within the atomic-commit and file-cap boundaries in
`AGENTS.md`. Per the AGENTS.md ADR-review gate, this ADR fires the `adr-review`
skill and reaches Accepted only after consensus.

## Related Decisions

- [ADR-030-skills-pattern-superiority.md](ADR-030-skills-pattern-superiority.md). Skills give scoped tool access with lower overhead than subagents.
- [ADR-044-copilot-cli-frontmatter-compatibility.md](ADR-044-copilot-cli-frontmatter-compatibility.md). Frontmatter fields Copilot CLI accepts.
- [ADR-012-skill-catalog-mcp.md](ADR-012-skill-catalog-mcp.md). Skill catalog governance.
- [ADR-040-skill-frontmatter-standardization.md](ADR-040-skill-frontmatter-standardization.md). Skill frontmatter contract.
- `DESIGN-REVIEW-vscode-copilot-parity-plan.md`. The parity plan this ADR advances.

## References

- Issue #2139. Migrate `.claude/commands/` to user-invocable skills for Claude Code + Copilot CLI parity.
- Issue #2137, PR #2138. The `/autofix-pr` to `/pr-autofix` rename; this ADR is the follow-up.
- [github/copilot-cli#618](https://github.com/github/copilot-cli/issues/618). CLI does not surface project prompt/command files.
- [github/copilot-cli#1113](https://github.com/github/copilot-cli/issues/1113). Request for CLI parity with IDE prompt-file behavior.
- `build/scripts/generate_commands.py`. The current command-to-skill bridge (REQ-003-001).
- `templates/platforms/copilot-cli.yaml`. The `artifacts.commands` stanza with `transform: command-to-skill`.
