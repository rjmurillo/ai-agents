# OntologyFragment: template-first plugin distribution

Source: ADR-109. Elicited 2026-09-11 from the ADR's Decision, Context, and Implementation Notes sections, and from the ADR-108 pilot this record generalizes.

## O1 Entities and value objects

| Entity | Kind | Where it lives today |
|---|---|---|
| Class | value object | one artifact kind the plugins ship: agents, skills, rules, hooks and settings, or lib |
| Template tree | entity | `templates/<class>/`, canonical source for a migrated class; skills already exist at `templates/skills/` (ADR-108); rules, hooks, and settings do not exist yet |
| Variant template pair | value object | agents only: `templates/agents/<stem>.claude.md.tmpl` and `templates/agents/<stem>.copilot.md.tmpl`, the two per-provider templates one agent composes to, sharing text through partials under `templates/agents/partials/`; a Claude-only section stays inline in the `.claude.md.tmpl` member rather than a partial |
| Plugin tree | entity | `src/claude/` (Claude Code plugin) and `src/copilot-cli/` (Copilot CLI plugin), rendered by the compiler from a template tree |
| Install tree | entity | `.claude/` (Claude Code, repo-local) and `.github/` (`instructions/`, `agents/`, `hooks/`, `prompts/` subset; Copilot CLI, repo-local), written by the binplace step from the corresponding plugin tree |
| Binplace | entity | the compile step that copies a plugin tree into its install tree, in the same `build_all.py` invocation that renders the plugin tree |
| Binplace manifest | entity | new: a YAML file under `templates/platforms/`, one row per class, naming its template source, plugin-tree output, and install-tree output; read by the binplace step and by `assert_no_claude_writes`'s allowlist |
| Manifest row | value object | one entry in the binplace manifest: source path, plugin-tree path, install-tree path, and an optional plugin-stage flag for a surface with no plugin consumer |
| Canonical source | value object | for every class but lib, the class's `templates/<class>/` tree; for lib, `scripts/{hook_utilities,github_core,ai_review_common}/`, excepted because those packages carry absolute imports a `templates/` relocation would break |
| Compiler | entity | `build/scripts/build_all.py`, its per-class compile modules (existing: `skill_templates.py`; new: modules for agents, rules, hooks), and `generate_rules.py`, `generate_hooks.py`, `generate_dispatcher.py` |
| Drift gate | entity | per class: a `pre_pr_sequence.py` gate row, `build_all.py --check`, and the class's own compile module's validate mode |
| NO-REGEN sentinel | value object | the in-file token or `.noregen` sidecar `regen_guard.py` recognizes; exempts one target from a class's compile step, reported at WARN, never silently exit 0 |
| Symlink and containment check | value object | per class: a check that an install-tree target is not a symlink and resolves inside its class's install root, mirroring `build/scripts/skill_templates.py`'s per-skill checks |
| Migration step | value object | one of B0 through B6 in ADR-109's Implementation Notes; B0 is this ADR and its staged text; B1 through B5 migrate one class each; B6 is the marketplace switch |

## O2 Ubiquitous language (canonical names)

- **class**, never "artifact type" or "surface" alone; a class is one of the five ADR-109 enumerates.
- **template tree**, the `templates/<class>/` directory; **plugin tree** for `src/claude/` and `src/copilot-cli/`; **install tree** for `.claude/` and `.github/`. Do not use "canonical tree" for a plugin tree or an install tree; both are derived.
- **binplace**, the copy from a plugin tree into an install tree; never "deploy" or "publish".
- **binplace manifest**, the YAML data file; **manifest row**, one entry in it. Retired name: "the allowlist file" alone, without naming it as the manifest.
- **canonical source**, the one tree a class's contributors edit by hand.
- **drift gate**, the validate-mode comparison and its `pre_pr_sequence.py` row; same term ADR-108 and REQ-025 already use for skills, extended to every class.
- **migration step**, B1 through B6; never "phase" (ADR-052 used "phase" for its now-superseded Migration Plan; this record uses "step" to avoid the collision).

## O3 Relationships

- A class has exactly one canonical source: its `templates/<class>/` tree, or `scripts/` for lib.
- A manifest row names exactly one canonical source, one plugin-tree output, and one install-tree output; a row MAY carry no plugin-tree output when no plugin consumes the surface (`.claude/settings.json`, the 21 non-`pr-quality-gate` `.github/prompts/` files stay outside the manifest until templated).
- The compiler renders a canonical source into its plugin tree; the binplace step copies that plugin tree into its install tree, in the same invocation.
- A drift gate compares an install-tree (or plugin-tree) file to what the compiler would render from the canonical source; a mismatch fails the gate and blocks the write.
- `assert_no_claude_writes`'s allowlist is the union of every manifest row's `.claude/`-rooted install path; a class not yet in the manifest contributes no rows and so is not exempted.
- A NO-REGEN sentinel attaches to one install-tree target; it suspends that target's drift gate and blocks its binplace, but does not remove the target from the manifest.

## O4 Aggregate boundaries

- Aggregate root: the template tree. Its rendered plugin-tree and install-tree files are derived and own nothing.
- Aggregate root: the binplace manifest. Its rows are part of it; a row is never edited independent of the manifest file.
- The install tree is outside both aggregates for any class not yet migrated (hand-maintained, edited directly); once migrated, it moves entirely inside the template tree's aggregate as derived output.

## O5 Decision rules

- DR1: a plugin-tree file MUST equal the render of its class's canonical source, byte for byte, for every migrated class.
- DR2: an install-tree file MUST equal its plugin-tree counterpart, byte for byte, for every migrated class (the binplace step's own drift condition).
- DR3: the build writes under `.claude/` only to paths the binplace manifest names; every other write is a REQ-003-010 violation, per ADR-109's generalization of ADR-108's exception.
- DR4: an install-tree target carrying a NO-REGEN sentinel is never overwritten by the binplace step; the skip is reported at WARN and the class's gate exits nonzero, mirroring ADR-108 section 4's rule for skills.
- DR5: a class with no `templates/<class>/` tree (not yet migrated) is untouched by the compiler and the binplace step; its install-tree files stay hand-maintained.
- DR6: lib's canonical source is `scripts/{hook_utilities,github_core,ai_review_common}/`, never `templates/`; the compiler copies it directly into both plugin trees' `lib/` directories in the same run that renders every other class.
- DR7: the marketplace switch (B6) is one-way for any consumer who updates `project-toolkit` during the window between B6 landing and a rollback; reverting B6 fixes future installs only.
- DR8: each of B1 through B5 MUST implement its own drift gate, NO-REGEN handling, and symlink and containment checks for its class; these do not extend automatically from skills' implementation.
- DR9: an agent's variant template pair, on its first render, MUST equal today's `src/claude/<stem>.md` (for the `.claude.md.tmpl` member) and today's `src/copilot-cli/agents/<stem>.md` (for the `.copilot.md.tmpl` member), byte for byte; reconciling the two members' divergent content into shared partials is a later, per-agent, owner-approved change, never a side effect of the migration itself.

## O6 Bounded contexts

- Template authoring (`templates/<class>/`): for a migrated class, this is where a contributor edits; the install tree is not hand-edited.
- Generation (`build/scripts/`): gains a compile module per new class (agents, rules, hooks) and the binplace step; the lib step absorbs `scripts/sync_plugin_lib.py`'s copy logic.
- Validation (`scripts/validation/`): gains one drift-gate row per class in `pre_pr_sequence.py`.
- Plugin distribution (`.claude-plugin/`, `.github/plugin/`): B6 collapses two Claude-side plugin roots (`claude-agents`, `project-toolkit`) into one, sourced at `src/claude/`.

## O7 Open ontology questions

- Whether a future class beyond agents, skills, rules, hooks and settings, and lib exists that the plugins ship; ADR-109 enumerates exactly five and states VS Code agents are untouched. Recorded under Open questions in REQ-026.
