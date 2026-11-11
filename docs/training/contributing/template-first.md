# Change a rule and a skill through templates

You will add one rule and change one skill by editing `templates/`, never the rendered copies. Then you will prove the build is clean. At the end, `build_all.py --check` exits 0 on a committed branch and the rule activation check exits 0.

This page uses a throwaway branch. You delete it at the end. Nothing here ships.

## Before you start

- You have a clone of `rjmurillo/ai-agents` with the setup done. Run the one command in [CONTRIBUTING.md](../../../CONTRIBUTING.md) (Setup Steps). It installs the locked environment and the Git hooks.
- You know the rule: files under `src/`, `.github/agents`, `.github/instructions`, `.github/hooks`, and most of `.claude/` are generated. You edit the source in `templates/` and run the build. [Why this exists](#why-the-build-owns-those-files) is at the end of this page.

Make a scratch worktree. Keep it outside your clone, under `~/worktrees/<repo>/<branch>`. A worktree inside the clone slows every repo-wide scan.

```bash
git fetch origin
git worktree add -b scratch/template-first ~/worktrees/ai-agents/template-first-tutorial origin/main
cd ~/worktrees/ai-agents/template-first-tutorial
uv sync --frozen --extra dev
```

Install the Git hooks in this worktree, as in CONTRIBUTING.md:

```bash
uv run --frozen lefthook install --reset-hooks-path
```

## Steps

### 1. See what a clean tree reports

```bash
uv run python build/scripts/build_all.py --check
echo "exit=$?"
```

You should see `exit=0`. `--check` renders everything and compares it with the committed files. It restores your working tree afterward. Exit 2 means a generated file differs from what its template renders.

### 2. See what a hand edit does

Edit a rendered rule by hand, then check:

```bash
echo "- hand edit" >> src/claude/rules/lossless-queue-reads.md
uv run python build/scripts/build_all.py --check
echo "exit=$?"
```

You should see `exit=2` and these lines (trimmed, the real output repeats the first line):

```text
DRIFT: src/claude/rules/lossless-queue-reads.md differs from its template (templates/rules/lossless-queue-reads.md)
STALENESS DETECTED: uncommitted regen drift:
  src/claude/rules/lossless-queue-reads.md
SURFACE PARITY VIOLATION:
  STALE-generated: [rules-claude-plugin] src/claude/rules/lossless-queue-reads.md (authority templates/rules; regenerate via build/scripts/rule_templates.py; gate build_all.py --check)
```

The output names the template that owns the file. Undo your edit:

```bash
git checkout -- src/claude/rules/lossless-queue-reads.md
```

### 3. Add a rule

A rule lives in `templates/rules/<name>.md`. Its front matter holds a `paths:` list of globs. The rule loads only when you work on a matching file. Create the file:

```bash
cat > templates/rules/training-example.md <<'EOF'
---
paths: ["docs/training/**"]
priority: normal
---

# Training Example Rule

Training pages state the outcome in the first paragraph.
EOF
```

Use `paths:` and no other scope key. The build writes `applyTo:` and `globs:` for the hosts that need them. If you write one of those keys yourself, `uv run python scripts/validation/check_rule_scope_keys.py` fails the rendered rule with `declares 'applyTo:', which Claude Code ignores; use 'paths:'`. Claude Code ignores those keys, so the rule would load on every turn.

Run the build:

```bash
uv run python build/scripts/build_all.py
git status --short
```

The build prints a long log. The status shows the files it wrote for your one template:

```text
?? .claude/rules/training-example.md
?? .github/instructions/training-example.instructions.md
?? src/claude/rules/training-example.md
?? src/copilot-cli/instructions/training-example.instructions.md
?? src/cursor/rules/training-example.mdc
?? templates/rules/training-example.md
```

Each host gets its own copy and its own scope key:

| File | Host | Scope key |
|---|---|---|
| `src/claude/rules/training-example.md` | Claude Code | `paths:` |
| `src/copilot-cli/instructions/training-example.instructions.md` | Copilot CLI | `applyTo:` |
| `src/cursor/rules/training-example.mdc` | Cursor | `globs:` and `alwaysApply: false` |

The two paths under `.claude/` and `.github/` are symlinks to the `src/` files (ADR-119). Check one:

```bash
ls -l .claude/rules/training-example.md
```

```text
.claude/rules/training-example.md -> ../../src/claude/rules/training-example.md
```

So the `src/` file is the real copy. Editing through the symlink would still edit a generated file.

### 4. Change a skill

A skill's `SKILL.md` renders from `templates/skills/<name>.SKILL.md.tmpl`. Every other file in the skill directory (scripts, references, tests) is hand-edited in `src/claude/skills/<name>/`.

Add one sentence to the `checkpoint` skill template. Put it after the paragraph that ends "the session log keeps a reference to it.":

```bash
uv run python - <<'EOF'
p = "templates/skills/checkpoint.SKILL.md.tmpl"
s = open(p).read()
a = "file is the human-readable record; the session log keeps a reference to it.\n"
assert a in s
s = s.replace(a, a + "A checkpoint is read-only after it is written. Start a new one instead of editing it.\n", 1)
open(p, "w").write(s)
EOF
uv run python build/scripts/build_all.py
git status --short | grep checkpoint
```

```text
 M src/claude/skills/checkpoint/SKILL.md
 M src/codex/skills/checkpoint/SKILL.md
 M src/copilot-cli/skills/checkpoint/SKILL.md
 M src/cursor/skills/checkpoint/SKILL.md
 M src/hermes/project-toolkit-knowledge/skills/checkpoint/SKILL.md
 M src/muse/skills/checkpoint/SKILL.md
 M templates/skills/checkpoint.SKILL.md.tmpl
```

One template edit changed six rendered skills, one per host tree. `.claude/skills/checkpoint` is a symlink into `src/claude/`, so it shows no change of its own. Codex reads its skills through a second set of links to `src/codex/skills/`. `templates/platforms/binplace.yaml` names that install tree.

### 5. Check before you commit

```bash
uv run python build/scripts/build_all.py --check
echo "exit=$?"
```

You should see `exit=2`. This is expected. `--check` compares the rendered output with the committed files, and you have not committed yet. The `STALENESS DETECTED: uncommitted regen drift:` block lists the files from steps 3 and 4. The fix is to commit the template and its output together.

### 6. Add an activation scenario

The activation check wants every rule to have a test scenario. Run it:

```bash
uv run python scripts/validation/check_rule_activation_coverage.py
echo "exit=$?"
```

You should see `exit=1` and:

```text
FAIL: rule/skill activation coverage regressed. A documented artifact has no activation scenario and is not baselined.
  rule 'training-example' is uncovered and not in the baseline. Add a scenario at tests/evals/rule-scenarios/training-example.json.
```

Add the scenario file it names:

```bash
cat > tests/evals/rule-scenarios/training-example.json <<'EOF'
{
  "rule_path": ".claude/rules/training-example.md",
  "rule_id": "training-example",
  "scenarios": [
    {
      "id": "S1",
      "desc": "Drafting a training page that buries the outcome",
      "input": "I am writing a training page under docs/training. I plan to open with background and state the outcome in section three. Is that fine? Answer in 5 short bullets. Do not modify any files.",
      "expected_signals": ["outcome", "first paragraph"],
      "expected_gate": "outcome-first",
      "rationale": "The rule requires the first paragraph of a training page to state the outcome."
    }
  ]
}
EOF
uv run python scripts/validation/check_rule_activation_coverage.py
echo "exit=$?"
```

Now it ends with `exit=0`.

### 7. Commit and check again

```bash
git add -A
git commit -m "docs(training): throwaway tutorial commit"
uv run python build/scripts/build_all.py --check
echo "exit=$?"
```

You should see `exit=0`.

## Check your result

You are done when both of these hold on the committed branch:

| Command | Expected |
|---|---|
| `uv run python build/scripts/build_all.py --check` | exit 0 |
| `uv run python scripts/validation/check_rule_activation_coverage.py` | exit 0 and a line starting `OK:` |

The `OK:` line counts uncovered artifacts that the baseline already allows. At commit `b959011e3` (2026-11-10) it read `OK: 14 uncovered rule(s) and 80 uncovered skill(s), all within the baseline.` Your counts change as main changes. Your new rule is not among them.

### If it fails

| What you see | What it means | Fix |
|---|---|---|
| `build_all.py --check` exits 2 with `DRIFT:` lines | A generated file differs from its template. | Edit the template named on the `DRIFT:` line. Run `build_all.py`. Commit both. |
| `--check` exits 2 with only `STALENESS DETECTED` | You rendered but did not commit. | Commit the template and the output together. |
| `--check` exits 3 | Git could not answer, or an audit rule tripped. Regenerating does not help. | Read the message. Run the command inside a normal Git worktree. |
| Activation check exits 1 | A rule or skill has no scenario. | Add `tests/evals/rule-scenarios/<name>.json` (rules) or a file under `tests/evals/skill-scenarios/` (skills). |
| A real rule fails `Rule Lossless Fixtures` or an Instruction Bytes gate | A real rule adds bytes to a corpus with a fixed ceiling. | Follow `src/claude/rules/templates.md`, MUST 6. This page's rule is not real, so you skip it. |

`build_all.py --help` lists every exit code. For a real change, run `uv run python scripts/validation/pre_pr.py` before you push. It includes the staleness and template drift rows.

### Clean up

Remove the worktree and the branch from your main clone. Do not use `rm -rf`. Do not push this branch.

```bash
cd <path to your main clone>
git worktree remove --force ~/worktrees/ai-agents/template-first-tutorial
git branch -D scratch/template-first
```

## Why the build owns those files

Four decisions explain the layout. Read them for the full reasoning. This page does not copy them.

- **Templates are the source.** [ADR-109](../../../.project-toolkit/architecture/ADR-109-template-first-plugin-distribution.md) makes `templates/` the source for agents, rules, skills, hooks, and settings. Each class has a compiler named in `templates/AGENTS.md`.
- **Skill files have two owners.** [ADR-108](../../../.project-toolkit/architecture/ADR-108-template-owned-skill-files.md) makes `SKILL.md` template-owned. Scripts and references stay hand-edited under `src/claude/skills/<name>/`.
- **The `.claude/` copies are links.** [ADR-119](../../../.project-toolkit/architecture/ADR-119-symlinked-dogfood-agents-and-skills.md) turns `.claude/agents`, `.claude/skills/<name>`, and shipped `.claude/rules` into symlinks. Hooks and `settings.json` are still copied.
- **One skill reaches many hosts.** [ADR-107](../../../.project-toolkit/architecture/ADR-107-canonical-skill-contracts-and-harness-projections.md) and [ADR-115](../../../.project-toolkit/architecture/ADR-115-native-plugin-support-per-host.md) are the design record. Both are still marked `proposed`. The working source is `templates/platforms/<host>.yaml` and `templates/platforms/binplace.yaml`, which you saw produce six skill copies in step 4.

Two more places you will meet:

- **`.project-toolkit/`** holds what agents write at run time: sessions, handoffs, retrospectives, QA notes, critiques, and analysis. Issue #5887 moved those targets here from the older agent directory. That directory still holds governance files. `GENERATOR-FILES.md` in its `governance` folder lists every generator and its output.
- **`build/AGENTS.md`** is the reference for the build: the generator order, what `--check` compares, and the pre-PR rows that call it.

## Next

- Read `templates/AGENTS.md` for the class-by-class render map.
- Read `docs/SKILL-AUTHORING.md` for the skill front matter and size limits.
- Read `docs/customization.md` to add a new agent.
