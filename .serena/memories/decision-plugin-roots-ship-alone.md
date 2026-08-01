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
a consumer's machine. The nightly real-CLI smoke loads `.claude` and
`src/copilot-cli` from the checkout while running from a neutral working
directory. It does not cover `src/claude`, isolated package contents, or every
prose reference. A broken citation can still ship silently.

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

Four baselined ratchets and one absolute frontmatter gate exist. "The gates are
green" is still weaker than "this rule is satisfied."

| Gate | Scans | Enforces |
|---|---|---|
| `check_skill_portability` | scripts under `.claude/skills` | Counts upstream-only runtime paths |
| `check_vendor_portability` | Python under `.claude/skills` | Requires helper routing unless the file is in the offender baseline |
| `check_skill_md_portability` | Markdown under each plugin root's `skills` directory | Counts prose refs; a file marker suppresses the file |
| `check_skill_md_exec_portability` | `SKILL.md`, references, and script READMEs under `.claude` and `src/copilot-cli` | Counts bare executable paths |
| `check_plugin_frontmatter_self_containment` | Markdown under all three roots | Rejects outward files in `name` or `description`; no baseline |

Two consequences worth carrying:

**Existing violations are grandfathered, not fixed.** The
`docs/agent-catalog.md` references above sit outside all five matchers. The
Markdown prose ratchet matches `.agents/`, `.claude/lib/`, and
`.claude/review-axes/`, not `docs/`. The file-level `vendor-portability` marker
documents intent but does not cause the green result. Issue #2050 tracks this
declared debt.

**No gate checks that a declared path exists.** Measured 2026-07-31 by
adding `.agents/this-path-does-not-exist.md` to both shipped copies of a skill
with a file-level declaration: all five gates exited 0. The Markdown prose gate
matched the path, then suppressed the declared file. The other four scan
scripts, executable paths, or frontmatter, not body prose. None resolves paths
named by a declaration. Verify the path resolves before writing it into a
declaration. See
`.agents/retrospective/2026-07-31-backticking-is-not-repair.md`.

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
