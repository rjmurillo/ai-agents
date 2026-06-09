# Instruction context moves efficiency, not the quality ceiling

Empirical, clean-room A/B study (2026-06-06, this repo) on whether agent
instruction context improves coding outcomes. Method: headless `claude -p` in
dirs outside the repo (so `.claude/rules` do not auto-load); vary only the
appended instruction context; score by compiler + test outcomes (no LLM judge)
+ a hidden oracle.

## Findings (objective)

- **Generic SE rules are dead weight on in-distribution coding, any model tier.**
  Refactoring kata: sonnet control = 8/8 (easy, K=5), 14/14 hidden oracle (hard);
  +56KB design rules = identical outcome, +27% cost. haiku control = 14/14 too.
- **Codebase-specific instructions help efficiency, not the quality ceiling.**
  moq.analyzers golden-reproduction (real PR #1088; spec = issue #579, NOT the
  PR-generated doc, which leaks the answer): control 112/120, treatment
  (+34KB copilot-instructions) 112/120 (same 8 `It.Ref` cases fail
  deterministically); treatment ~42% fewer turns at ~same cost.
- **Hard gates change behavior; passive prose does not.** The repo's
  false-completion PreToolUse gate blocked an unverified commit this session,
  while 252KB of always-on prose rules changed nothing measurable.
- **252KB of `.claude/rules` load unconditionally because of a frontmatter-key
  mismatch, not a harness bug.** The rules carry `applyTo`/`alwaysApply` (GitHub
  Copilot and Cursor keys). Claude Code's conditional-load key is `paths` (a YAML
  list of globs; Claude Code memory docs, "Path-specific rules"). A rule with no
  `paths` field loads unconditionally, so all of them do (powershell.md and
  csharp.md present in a .py-only session). The Copilot mirrors honor `applyTo`;
  only the Claude tree is mis-keyed.
- **LLM-judge scalars are unreliable even cross-class** (opus scored a baseline
  anti-pattern answer 5/5). Use objective outcomes, not judge scalars.

## Consequences

- Real fix (replaces the withdrawn ADR-070 "assembly-layer" framing): add
  `paths:` frontmatter to `.claude/rules/*.md` so Claude Code loads topic/path
  rules conditionally. Caveat: `paths` is purely file-glob based and Claude Code
  has no agent-requested mode (unlike Cursor), so topic rules with no natural
  path glob (the SE-book rules) cannot be perfectly gated; they stay
  unconditional or take best-effort globs. Keep the corpus (ADR-069).
- AGENTS.md v2 applied (PR #2499): harness-runnable commit gate, verifier-backed
  Never items, exact commands, primacy/recency edges.
- Reusable: scripts/eval/analyze-pr-churn.py (deterministic churn classifier).

## Per-harness rule frontmatter (keys are NOT interchangeable)

- Claude Code: `.claude/rules/*.md`, key `paths:` (YAML list of globs); no
  `paths` = loaded unconditionally. CLAUDE.md / AGENTS.md = always-on.
- GitHub Copilot: `.github/instructions/*.instructions.md`, key
  `applyTo: "glob,glob"` (comma-separated globs); `.github/copilot-instructions.md`
  = always-on, no frontmatter.
- Cursor: `.cursor/rules/*.mdc`, keys `globs`, `alwaysApply`, `description`
  (rule types: Always / Auto Attached / Agent Requested / Manual).

## Post-fix verification (2026-06-08, controlled A/B, live claude -p)

Confirmed the `applyTo` -> `paths` fix empirically (full report:
`evals/reports/paths-conditional-loading-verification-2026-06-08.md`).

- **Mechanism A/B** (3 sentinel rules, same probe reads a `.cs` file, flip only
  the key): `paths` arm loads `cs` + `all`, EXCLUDES the `**/*.py` rule;
  `applyTo` arm loads all three (cs + py + all). So Claude Code honors `paths`
  and ignores `applyTo`. This is the proof, not inference.
- **Token delta** (two dirs, full 30-rule set, applyTo-state vs paths-state,
  read the kata `UserService.cs`): applyTo = 188,945 loaded tokens / $0.3079;
  paths = 165,179 / $0.2621. Delta -23,766 tokens (~12.6%), -$0.046 (~15%) for a
  2-turn probe; compounds per turn in a real session. Quality finding unchanged
  (conditional loading only excludes non-matching rules, already shown to be
  dead weight on a `.cs` task).

## Harness lessons (cost real budget to learn)

Never run concurrent agent batches (API rate limits + dotnet build-lock
contention corrupt results); hidden-oracle TFM must be >= the agent app TFM;
the eval spec must be the PRE-work input (the issue), never a PR-generated doc;
`dotnet test -v q` suppresses the summary the parser needs; pass absolute paths
to scorers; keep work dirs until scores are verified. A `cd` into a subdir
wedges relative-path PreToolUse hooks (they resolve the hook script against cwd),
which blocks Bash/Read/Agent; avoid cd, use absolute paths.

Refs: [[exploring-knowledge-graph]] wiki concept "Instructions Move Efficiency
Not the Quality Ceiling"; Arize Prompt Learning; IFScale (arXiv:2507.11538);
Reporails 30K-repo study.
