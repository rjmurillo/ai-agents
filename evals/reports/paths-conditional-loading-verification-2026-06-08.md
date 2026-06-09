# Paths Conditional-Loading Verification (2026-06-08)

Post-fix re-run of the refactoring eval, after the `.claude/rules` frontmatter
was migrated from `applyTo` (a GitHub Copilot key Claude Code ignores) to
`paths` (Claude Code's conditional-load key). Two questions:

1. Does Claude Code actually load rules conditionally under `paths` (and did it
   really ignore `applyTo`)?
2. On a real refactoring (`.cs`) task, does the fix reduce the loaded rule
   context, and does the original quality finding still hold?

All runs use the live Claude Code CLI (`claude -p`, model sonnet), real native
`.claude/rules` loading in the working directory (NOT `--append-system-prompt`,
which is frontmatter-blind).

## 1. Mechanism: controlled A/B (same probe, flip only the key)

Three sentinel rules in a clean `.claude/rules/`, one probe: read a `.cs` file,
then report which sentinel tokens are in loaded context. Only the frontmatter
key changes between arms.

- `sentinel-cs`: scope `**/*.cs`
- `sentinel-py`: scope `**/*.py`
- `sentinel-all`: no scope (always-on)

| Frontmatter key | Sentinels loaded for a `.cs` session | Verdict |
|---|---|---|
| `paths` (the fix) | `cs` + `all`; **`py` excluded** | Conditional load works |
| `applyTo` (old) | `cs` + `py` + `all`; the non-matching `py` rule loads too | Ignored, eager-all |

Claude Code honors `paths` and ignores `applyTo`. This is the empirical basis
for the fix.

## 2. Efficiency: in-repo token delta on the kata target

Two dirs, each with the full 30-rule `.claude/rules` set (one in the `applyTo`
state from origin/main, one in the `paths` state from the fix branch) plus the
refactoring kata target `src/app/UserService.cs`. Probe: read `UserService.cs`,
measure loaded context tokens.

| Arm | Loaded context (cache_creation + cache_read + input) | Cost (2-turn probe) |
|---|---|---|
| `applyTo` (all 30 rules load) | 188,945 tokens | $0.3079 |
| `paths` (conditional) | 165,179 tokens | $0.2621 |
| Delta | -23,766 tokens (about 12.6%) | -$0.046 (about 15%) |

The `paths` arm excludes the 12 path-scoped rules that do not match a `.cs`
refactoring task (python, powershell, ci-scripts, governance, retros, templates,
claude-agents, canonical-source-mirror, generated-artifacts, secret-redaction,
testing, security). `csharp.md` still loads (it matches), as do the 8 always-on
rules and the 9 SE-book rules (still `alwaysApply: false` with no `paths`;
PR2 will address those). The per-turn rule context is paid every turn, so the
saving compounds across a real multi-turn refactoring session.

## What did NOT change: the quality finding

The original refactoring eval (2026-06-06) found that generic SE rules do not
raise the quality ceiling: sonnet and haiku solve the kata at ceiling with or
without the design rules. Conditional loading only EXCLUDES non-matching rules,
which that study already showed are dead weight on a `.cs` task. So the fix is a
pure efficiency win (fewer tokens, lower cost, same outcome), exactly the
"efficiency lever, not a quality lever" conclusion, now realized in-repo.

## Reproduce

Sentinel A/B:

```bash
D=/tmp/pathstest; mkdir -p "$D/.claude/rules"
# sentinel-cs.md: paths ["**/*.cs"]; sentinel-py.md: paths ["**/*.py"];
# sentinel-all.md: no paths. Plus a Foo.cs file.
(cd "$D" && claude -p "Read Foo.cs, then list every SENTINEL_ token in your loaded rules." \
  --dangerously-skip-permissions --model sonnet --output-format json)
# Flip the three files to applyTo and re-run for the contrast arm.
```

Token delta:

```bash
R=/tmp/refac-load
git archive origin/main .claude/rules | tar -x -C "$R/applyto/"   # applyTo state
git archive HEAD        .claude/rules | tar -x -C "$R/paths/"     # paths state
# copy the kata UserService.cs into src/app/ in each, then:
(cd "$R/<arm>" && claude -p "Read src/app/UserService.cs, then reply DONE." \
  --dangerously-skip-permissions --model sonnet --output-format json)
# Compare usage.cache_creation_input_tokens + cache_read_input_tokens.
```

## Caveats

- Token delta is a single run per arm (deterministic-ish; the direction is
  guaranteed by the sentinel A/B, the magnitude is one sample).
- The probe is a 2-turn read, not the full multi-turn kata; the per-turn saving
  compounds in a real session, so this understates the full-session reduction.

Refs: [[Instructions Move Efficiency, Not the Quality Ceiling]];
[[CLI Harness Instruction Interoperability]]; rjmurillo/ai-agents PR adding
`paths` frontmatter (Refs #1859).
