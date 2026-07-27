---
paths:
  - ".claude/**"
  - "src/claude/**"
  - "src/copilot-cli/**"
  - "templates/agents/**"
  - "**/.claude-plugin/plugin.json"
priority: high
---

# Plugin Self-Containment

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

This repository self-hosts its own plugins. `.claude/` is both the plugin source and the live configuration, so every upstream reference resolves here and the tests pass here. CI does load the shipped `src/copilot-cli/` plugin from a separate working directory in the plugin-load smoke test, so plugin isolation itself is covered. What no gate checks is whether the *prose inside a shipped file* names a path the consumer does not have.

## The mechanism already exists

Do not invent a new one. Issue #2050 built this stack:

- `.claude/lib/paths.py`. The portability helper. `resolve_artifact_root` and `artifact_dir` for write paths, `resolve_skill_resource` for read paths. Route through it instead of hard-coding.
- `check_vendor_portability.py`. Ratchet over Python files under skill script roots.
- `check_skill_md_portability.py`. Ratchet over upstream paths in Markdown prose.
- `check_skill_md_exec_portability.py`. Ratchet over executable invocations in `SKILL.md`.
- `check_skill_portability.py`. Ratchet over hard-coded upstream paths in skill scripts.
- `validate-vendor-portability.yml`. Runs the vendor ratchet in CI.

Every one is a **regression ratchet with a baseline**, not a universal enforcer. They block new offenders and grandfather existing ones. Passing them means "no new debt", not "this file is portable".

### The declaration

A file that legitimately depends on upstream paths declares it with an HTML comment, which suppresses the ratchet:

```markdown
<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo
     itself; intentionally references upstream paths because its audience is repo
     contributors, not plugin consumers (issue #2050) -->
```

170 files inside the plugin roots carry it. Use it when the reference is real and intended. Do not use it to silence a reference you should have fixed.

## Known coverage gap

`check_skill_md_portability.py` flags only `.agents/`, `.claude/lib/`, and `.claude/review-axes/` in prose. It does not flag `templates/agents/` or `templates/platforms/`, which exist only in this repository and generate shipped output.

Do not widen that to a bare `templates/`. The directory name is overloaded three ways, and only the first is a defect:

- `templates/agents/`, `templates/platforms/`. Upstream-only. Never present inside a plugin root.
- A bundled `templates/` directory inside a skill, for example `.claude/skills/threat-modeling/templates/threat-model-template.md`. Ships with the plugin and resolves fine.
- A framework convention in prose, for example Flask's `templates/` named in a project-detection table. Not a path anyone resolves.

`assets/templates/` under a skill compounds it: a pattern matching the bare substring would flag shipped files such as `.claude/skills/codebase-documenter/assets/templates/API.template.md`.

The declaration is the wrong tool for these. It suppresses every portability check for the whole file, so applying it to silence a legitimate `templates/` mention would also hide a later real `.agents/` regression in the same file. Narrow the pattern instead of declaring the file.

Measured while writing this rule: 32 Markdown files inside the plugin roots carry undeclared `docs/`, `build/`, or `templates/` references. Most are consumer-workspace paths or prose collisions such as "build/buy/partner". The genuine ones point at `templates/agents/*.shared.md`.

Until those two patterns are added, such references are on the reviewer, not the gate.

## MUST

1. **No undeclared upstream-only dependency in a shipped file.** A file under a plugin root, or under `templates/agents/`, MUST NOT instruct the reader to open, run, or resolve a path that exists only in this repository, unless it carries the `vendor-portability` declaration. Consumer-workspace paths are exempt; they are the point.
2. **Address in-root executables through the plugin-root env vars.** Use `"${COPILOT_PLUGIN_ROOT:-${CLAUDE_PLUGIN_ROOT:-.claude}}/skills/<name>/scripts/<file>"`, never a bare `.claude/skills/...` path, which resolves only when the consumer's working directory happens to match. `check_skill_md_exec_portability.py` ratchets new violations.
3. **Do not cross-reference between plugin roots.** `.claude/` and `src/copilot-cli/` install separately. Neither may reach into the other. The generator mirrors content for exactly this reason.

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
