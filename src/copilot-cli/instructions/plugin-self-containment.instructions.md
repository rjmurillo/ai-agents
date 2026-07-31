---
applyTo: src/claude/**,src/copilot-cli/**,templates/agents/**,**/.claude-plugin/plugin.json
---

# Plugin Self-Containment

<!-- vendor-portability: contributor-facing rule for the rjmurillo/ai-agents repo itself;
     it must name upstream-only paths because naming them is the subject of the rule
     (issue #2050) -->

## The boundary

Three directories ship as installable plugins. Nothing else in this repository reaches a consumer.

| Plugin root | Plugin name | Marketplace |
|---|---|---|
| `.claude/` | `project-toolkit` | `.claude-plugin/marketplace.json` |
| `src/claude/` | `claude-agents` | `.claude-plugin/marketplace.json` |
| `src/copilot-cli/` | `project-toolkit` | `.github/plugin/marketplace.json` |

Each marketplace entry names exactly one `source` directory. A consumer who installs the plugin receives that directory and nothing above it. `docs/`, `.agents/`, `build/`, `scripts/`, `templates/`, and the repository root stay behind.

`templates/agents/**` is in scope for this rule because it is the canonical source that generates shipped agent files. An outward reference introduced there lands in a plugin root on the next build.

## Three kinds of path, only one of which is a defect

The distinction below is the whole rule. Getting it wrong in either direction is expensive.

| Kind | Example | Verdict |
|---|---|---|
| **Bundled dependency**: a file the plugin ships and must resolve at runtime | a sibling skill's script under the same plugin root | Fine. Address it through the plugin-root env vars. |
| **Consumer-workspace path**: a location in the installing repository that the agent reads or writes | an agent told to write its output to `.agents/planning/` or `docs/adr/` in the consumer's repo | Fine. This is the plugin doing its job. Not a defect. |
| **Upstream-only dependency**: a path that exists only in `rjmurillo/ai-agents` | `templates/agents/security.shared.md`, `docs/agent-catalog.md`, `build/scripts/build_all.py` | **Defect**, unless declared. Dangles for every consumer. |

A grep cannot tell these apart. A reviewer can. When the target exists only upstream and the text instructs the reader to open, run, or resolve it, that is the defect.

### Why it is invisible in development

This repository self-hosts its own plugins. `.claude/` is both the plugin source and the live configuration, so every upstream reference resolves here and the tests pass here. CI does load the shipped `src/copilot-cli/` plugin from a separate working directory in the plugin-load smoke test, so plugin isolation itself is covered. What no gate checked, until issue #3565 added the frontmatter check below, was whether the *prose inside a shipped file* names a path the consumer does not have.

## The mechanism already exists

Do not invent a new one. Issue #2050 built this stack:

- `.claude/lib/paths.py`, mirrored byte-identical at `src/copilot-cli/lib/paths.py`. The portability helper. `resolve_artifact_root` and `artifact_dir` for write paths, `resolve_skill_resource` for read paths. Route through it instead of hard-coding. Import the copy inside your own root: a Copilot-side caller reaching for the `.claude/` copy is the defect this rule describes.
- `check_vendor_portability.py`. Ratchet over Python files under skill script roots.
- `check_skill_md_portability.py`. Ratchet over upstream paths in Markdown prose.
- `check_skill_md_exec_portability.py`. Ratchet over executable invocations in `SKILL.md`.
- `check_skill_portability.py`. Ratchet over hard-coded upstream paths in skill scripts.
- `check_plugin_frontmatter_self_containment.py`. Absolute check, no baseline, over `description` and `name` in the frontmatter of every Markdown file under all three plugin roots. Added for issue #3565.
- `validate-vendor-portability.yml`. Runs the vendor ratchet in CI. The frontmatter gate runs in `validate-generated-agents.yml`.

The five ratchets live in `scripts/validation/`, the workflows in `.github/workflows/`. Both stay upstream; a consumer never runs them.

The four `check_skill_*` scripts are **regression ratchets with a baseline**, not universal enforcers. They block new offenders and grandfather existing ones. Passing them means "no new debt", not "this file is portable". The frontmatter gate is the exception: its surface is small enough to hold at zero, so it carries no baseline.

### The declaration

A file that legitimately depends on upstream paths declares it with an HTML comment, which suppresses the ratchet:

```markdown
<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo
     itself; intentionally references upstream paths because its audience is repo
     contributors, not plugin consumers (issue #2050) -->
```

Files inside the plugin roots carry it in the low hundreds. Count them when the
number matters rather than trusting a figure written here, because this line has
already been wrong once:

```bash
git ls-files .claude src/copilot-cli src/claude | xargs grep -l "vendor-portability:" | wc -l
```

`git ls-files` rather than a bare `grep -r` on purpose: a recursive walk also
descends into the nested checkouts under `.claude/worktrees/`, which is the same
trap described below.

Two structural facts hold regardless of the count. The declaration lives in skill
files, so `.claude/skills/` and its `src/copilot-cli/skills/` mirror hold nearly
all of them, and the two track each other because the mirror is generated.
`src/claude/` holds none, because it ships agents and has no `skills/` directory
at all.

Use the declaration when the reference is real and intended. Do not use it to
silence a reference you should have fixed.

## Known coverage gap

`check_skill_md_portability.py` flags only `.agents/`, `.claude/lib/`, and `.claude/review-axes/` in prose. It does not flag `templates/agents/` or `templates/platforms/`, which exist only in this repository and generate shipped output.

Do not widen that to a bare `templates/`. The directory name is overloaded three ways, and only the first is a defect:

- `templates/agents/`, `templates/platforms/`. Upstream-only. Never present inside a plugin root.
- A bundled `templates/` directory inside a skill, for example `.claude/skills/threat-modeling/templates/threat-model-template.md`. Ships with the plugin and resolves fine.
- A framework convention in prose, for example Flask's `templates/` named in a project-detection table. Not a path anyone resolves.

`assets/templates/` under a skill compounds it: a pattern matching the bare substring would flag shipped files such as `.claude/skills/codebase-documenter/assets/templates/API.template.md`.

The declaration is the wrong tool for these. In the four baselined ratchets it suppresses every portability check for the whole file, so applying it to silence a legitimate `templates/` mention would also hide a later real `.agents/` regression in the same file. Narrow the pattern instead of declaring the file.

Measured while writing this rule: 32 Markdown files inside the plugin roots carry undeclared `docs/`, `build/`, or `templates/` references. Most are consumer-workspace paths or prose collisions such as "build/buy/partner". The genuine ones point at `templates/agents/*.shared.md`.

### What is gated, and what is not

Frontmatter is gated. `check_plugin_frontmatter_self_containment.py` holds `description` and `name` at zero undeclared outward file references across all three plugin roots. A `description` loads into every consumer session whether or not the skill is invoked, so a dangling path there is the most-read and least-useful kind.

Body prose is not gated, and the ratchet that covers part of it covers less than its name suggests. `check_skill_md_portability.py` scans `.claude/skills` only, so `.claude/commands/`, `src/claude/`, and `src/copilot-cli/` are outside it entirely, and its pattern set has no `docs/` entry. That combination is how two `docs/` paths sat in shipped descriptions for months. `docs/agent-metrics.md` entered the `metrics` description on 2026-05-30 in #2136 (`817e466f82`); `docs/autonomous-pr-monitor.md` entered the `pr-autofix` description on 2026-05-25 in #2049 (`79867ca6ed`), under that command's pre-rename name `autofix-pr.md`. Both dates were wrong in an earlier draft of this rule, in both directions, and the reason generalizes: `git log -S` finds a string anywhere in a file, so a reference that lived in body prose for months reads as frontmatter provenance unless you open the historical file and look at the block. Check the field the claim is about, follow renames, and read the source file rather than its generated mirror. This rule shipped on 2026-07-26 and removed neither, because nothing in the repository read that surface until the frontmatter gate.

Outward is relative to the root that ships the file, not to the directory name. `src/copilot-cli` ships its own `docs/` directory, so `docs/copilot-instructions.md` resolves for that plugin's consumer while the identical string under `.claude` resolves to nothing. The gate resolves every candidate against its owning root before reporting it, and a `../` prefix never counts as shipped even when the file exists one level up.

The frontmatter gate reads the `vendor-portability` marker differently from the four ratchets, and the difference is deliberate. A marker suppresses a frontmatter reference only when the marker itself names that path. A file-wide reading silenced a real case while this gate was being built: `.claude/skills/metrics/SKILL.md` carries a marker written about the consumer's `.agents/` artifacts, and that marker was covering an unrelated `docs/agent-metrics.md` sitting in the same file's description. Scoping the opt-out to what it names is what keeps it an escape hatch instead of a blanket.

The remaining body surface is large. Counting it is matcher-dependent, so use the gate's own pattern and say so: 3,770 references across 417 of 901 shipped Markdown files, measured at the head of this branch. Reproduce with `OUTWARD_FILE` from `check_plugin_frontmatter_self_containment.py` applied to every `git ls-files` Markdown path under the three plugin roots. A count quoted without its matcher is not evidence: the same tree yielded 2,556 under an earlier pattern that missed repeated `../` traversal and absolute forms, and 1,902 under one whose boundary was an enumerated punctuation list rather than a negated one, which silently dropped every path written inside backticks or bold markers. Most of those references are legitimate under the three-kind table above, so the surface needs per-file classification rather than a pattern, and it stays on the reviewer.

Two counting traps, both hit while measuring this. `.claude/worktrees/` holds nested checkouts of this same repository, so a naive walk multiplies every finding by the number of live agent worktrees; the same scan returned 1,557,567 before excluding them. And that body count reads the declaration the way the ratchets do, so a declared file contributes zero no matter how many references it carries.

### Agent files are not scanned at all

Both portability gates scan skills only. `check_skill_portability.py` walks skill
scripts and `check_skill_md_portability.py` walks `SKILL.md` bodies. Neither reads
`src/claude/*.md`, `src/copilot-cli/agents/*.agent.md`, or `templates/agents/*.shared.md`,
even though the first two sit inside plugin roots and ship to consumers verbatim.

An agent prompt that tells the reader to open `.claude/agents/<name>.md` therefore
ships into `src/copilot-cli/` with a path that resolves to nothing, and no gate
objects. Issue #3465 tracks widening the ratchet and carries the per-surface
measurement; this section records the working practice to follow until it lands.

Practical rule while the gap stands: **write shared agent prose without naming a
tree-specific path.** Say "an agent registered in this install" rather than
"a file at `.claude/agents/<name>.md`". The same body is copied into six trees
across three plugin roots (`.claude/`, `src/claude/`, `src/copilot-cli/`, each of
which installs standalone), so any path you name is wrong in most of them. This is
not a style preference; it is the only way to be correct in all six copies at once.
A draft of the orchestrator capability-matrix note did name that path, shipped it
into the plugin roots, and no gate flagged it. A manual read caught it.

## MUST

1. **No undeclared upstream-only dependency in a shipped file.** A file under a plugin root, or under `templates/agents/`, MUST NOT instruct the reader to open, run, or resolve a path that exists only in this repository, unless a `vendor-portability` declaration in that file names that path. Consumer-workspace paths are exempt; they are the point.
2. **Address in-root executables through the plugin-root env vars.** Use `"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/<name>/scripts/<file>"`, never a bare `.claude/skills/...` path, which resolves only when the consumer's working directory happens to match. `check_skill_md_exec_portability.py` ratchets new violations in bodies, and `check_plugin_frontmatter_self_containment.py` blocks them outright in frontmatter. The gate identifies a path by its trailing extension, so an extensionless target is outside what it can see; no extensionless executable ships under any plugin root today, and adding one puts the reference back on the reviewer.
3. **Do not cross-reference between plugin roots.** `.claude/` and `src/copilot-cli/` install separately. Neither may reach into the other. The generator mirrors content for exactly this reason. `check_plugin_frontmatter_self_containment.py` blocks a cross-root reference in frontmatter even when the target exists here, because existing in this repository is not the same as travelling with the plugin the consumer installed.

## SHOULD

1. **Prefer inlining a short fact over copying a long document.** If a shipped file needs three lines from an ADR, quote the three lines. Copying the document creates a second copy to keep in sync.
2. **Say whose path it is when the reference is contributor-scoped.** Write "in the `rjmurillo/ai-agents` repository" so a consumer reading it knows the path is not theirs to resolve, and add the declaration.
3. **Question whether a repo-specific artifact belongs in a plugin root at all.** A skill whose entire subject is this repository's internals ships dead weight to consumers. That is the deeper fix behind most declarations. See ADR-083.

## MUST NOT

1. MUST NOT assume a path resolves because it resolves locally. Self-hosting guarantees every wrong path looks right here.
2. MUST NOT read a passing portability check as proof of portability. The checks are baselined ratchets.

## Checking a change

Scope the question to what you changed. For each file you added or edited under a plugin root or `templates/agents/`, list the paths it tells the reader to read or run, and classify each one against the three-kind table above.

```bash
git diff --name-only origin/main... -- .claude src/claude src/copilot-cli templates/agents \
  | xargs --no-run-if-empty grep -nP '(?<![\w/.-])(docs|\.agents|build|scripts|templates)/[A-Za-z0-9_./-]+'
```

Then run the ratchets that cover the change:

```bash
uv run python scripts/validation/check_skill_md_portability.py
uv run python scripts/validation/check_vendor_portability.py
```

## References

Contributor-scoped, per SHOULD 2. These paths live in the `rjmurillo/ai-agents` repository and do not ship. A consumer reading this rule inside an installed plugin cannot resolve them and does not need to.

- `.claude-plugin/marketplace.json`, `.github/plugin/marketplace.json`. The manifests that define what ships.
- `.claude/rules/plugin-version-bump.md`. Version parity across the shipping roots. This one does ship.
- `.agents/architecture/ADR-071-plugin-hook-runtime-contract-verification.md`. Defines the plugin-root env var contract and how each host exports it.
- `.agents/architecture/ADR-045-framework-extraction-via-plugin-marketplace.md`. Why the marketplace split exists.
- `.agents/architecture/ADR-083-copilot-dogfood-surface-separation.md`. Which surfaces are dogfood-only.
