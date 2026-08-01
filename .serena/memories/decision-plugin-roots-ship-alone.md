# Plugin roots ship alone

## Question

Can a file inside a plugin root reference a repository path that lives outside
that root, for example `docs/agent-catalog.md`?

No. Anything a plugin-shipped file depends on at runtime must live inside the
same plugin root, or be inlined.

## The boundary

Exactly three directories ship as installable plugins:

| Plugin root | Plugin name | Declared in |
|---|---|---|
| `.claude/` | `project-toolkit` | `.claude-plugin/marketplace.json` |
| `src/claude/` | `claude-agents` | `.claude-plugin/marketplace.json` |
| `src/copilot-cli/` | `project-toolkit` | `.github/plugin/marketplace.json` |

Each marketplace entry names one `source` directory. A consumer receives that
directory and nothing above it.

`docs/`, `.agents/`, `build/`, `scripts/`, `templates/`, `README.md`, and
`.github/workflows/` are development infrastructure for this repository only.
They never reach a consumer.

## Why it stays invisible

This repository self-hosts its own plugins. `.claude/` is simultaneously the
plugin source and the live Claude Code configuration, so every outward
reference resolves here and every local test passes. The break appears only on
a consumer's machine. No local CI reproduces that environment, so the defect
ships silently.

## Evidence (measured 2026-07-31 on `origin/main` at `088292977f`)

Outbound path references from inside the three plugin roots to `docs/`,
`.agents/`, `build/`, `scripts/`, or `templates/`:

| Metric | Count |
|---|---|
| Reference occurrences | 3,808 |
| Lines carrying at least one | 3,186 |
| Tracked files carrying at least one | 564 |

Per root, by occurrence:

- `.claude/`: 1,881 across 280 files
- `src/copilot-cli/`: 1,811 across 269 files
- `src/claude/`: 116 across 15 files

Quote the occurrence count (3,808) when the claim is "how many references."
The three numbers are all correct and measure different things, which is how a
previous revision of this memory appeared to contradict itself.

Not all are runtime dependencies, but each is a candidate. Confirmed live
instance: `docs/agent-catalog.md`, which is generated from
`templates/agents/*.shared.md`, is CI drift-checked, and does not ship. It is
referenced from `.claude/skills/ai-agents-generation-and-release/SKILL.md` and
its `src/copilot-cli/` mirror.

## Decision

Written as a binding rule at `.claude/rules/plugin-self-containment.md`, with
generated mirrors at `.github/instructions/plugin-self-containment.instructions.md`
and `src/copilot-cli/instructions/plugin-self-containment.instructions.md`.

Key obligations:

1. A plugin-shipped file must not instruct the reader to open, run, or resolve
   a path outside its own plugin root unless a `vendor-portability` declaration
   in that same file names that path. A directory prefix does not satisfy this.
   If the file cites an exact filename, the declaration must name the exact
   filename.
2. Address in-root scripts through
   `"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/<name>/scripts/<file>"`,
   never a bare `.claude/skills/...` path.
   `check_skill_md_exec_portability.py` enforces it.
3. `.claude/` and `src/copilot-cli/` install separately, so neither may reach
   into the other. Duplicate via the generator instead.
4. When a reference genuinely targets this repository, say so in the prose so a
   consumer knows the path is not theirs. Prose is additive. It does not
   replace the declaration.

## What is actually enforced

Four gates exist. Each is a frozen ratchet over a narrow scope, so "the gates
are green" is a weaker statement than "this rule is satisfied."

| Gate | Scans | Enforces |
|---|---|---|
| `check_skill_md_portability` | `.claude`, `src/claude`, `src/copilot-cli` | Markdown refs, ratcheted against a per-file baseline |
| `check_vendor_portability` | `.claude/skills` only | Declaration presence, 30 baselined offenders |
| `check_plugin_frontmatter_self_containment` | all three roots, frontmatter only | No outward frontmatter refs |
| `check_skill_md_exec_portability` | `.claude/skills` and mirrors | Executable paths only |

Two consequences worth carrying:

**Existing violations are grandfathered, not fixed.** The
`docs/agent-catalog.md` references above are not ungated. They are carried as
4 baselined entries per mirror in
`scripts/validation/skill_md_exec_portability_baseline.json`. Tracked debt,
Issue #2050. A green gate here means "no new drift," never "no violation."

**No gate checks that a declared path exists.** Measured 2026-07-31 by
reintroducing a citation to a nonexistent file into both trees: all four gates
exited 0. They validate that a declaration is present and well formed, never
that the paths it names resolve. A declaration is therefore a claim the
toolchain accepts on trust. Verify the path resolves before writing it into a
declaration. See `.agents/retrospective/2026-07-31-backticking-is-not-repair.md`.

## Detection

```bash
git ls-files .claude src/claude src/copilot-cli \
  | grep -E '\.(md|py|json)$' \
  | xargs grep -nP '(?<![\w/.-])(docs|\.agents|build|scripts|templates)/[A-Za-z0-9_./-]+'
```

For Markdown links specifically, parse with CommonMark rather than a regex. A
regex over raw text counts Python call syntax inside fenced blocks, such as
`handlers[args.command](args)`, as a link.

## Related

`mem:decision-copilot-cli-hook-plugin-root-contract`,
ADR-045 (marketplace split), ADR-083 (dogfood surface separation),
`.claude/rules/plugin-version-bump.md` (version parity across the same roots).
