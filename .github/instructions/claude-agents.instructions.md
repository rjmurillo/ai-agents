---
applyTo: src/claude/**,.claude/agents/**,.claude/skills/**,.claude/commands/**
---

# Claude Agent and Skill Rules

`src/claude/*.md` are hand-maintained Claude agent prompts with unique Claude-specific content (a `name` field the shared template does not carry, and Claude-side tool ids). A `model:` field is no longer part of that set: ADR-080 defaults every agent to the harness-inherited model, and the 2026-09-05 migration that drained its ratchet to zero left a pin on only `code-reviewer`, which carries the `haiku` cost exception. They are NOT generated. `templates/agents/*.shared.md` holds the shared body that the Copilot and VS Code copies are generated from. **No check compares the content of `src/claude/*.md` against that shared body**, and the co-change check that exists is one-directional (see MUST-1). `.claude/agents/`, `.claude/skills/`, and `.claude/commands/` hold per-repo artifacts loaded by Claude Code.

## MUST

1. **Edit Claude agents directly, in lockstep with the shared template**. `src/claude/*.md` is hand-maintained; no generator writes it (`detect_agent_drift.py:19` "Claude agents have unique content and are NOT generated from templates."). To change shared agent behavior, edit BOTH `src/claude/<agent>.md` AND `templates/agents/<agent>.shared.md` in the same change, then run `uv run python build/generate_agents.py` to refresh the generated Copilot and VS Code copies (`src/copilot-cli/`, `src/vs-code-agents/`). `build/scripts/validate_install_parity.py` checks **co-change in a diff, not content agreement**: "reports the sibling files that should have changed together and did not" (`validate_install_parity.py:24`). Nothing compares the two files' text for agreement.

That co-change check is **asymmetric, so it does not enforce the lockstep in the direction you most need**. Measured at `origin/main`:

```bash
python3 build/scripts/validate_install_parity.py --files templates/agents/architect.shared.md; echo $?  # 1
python3 build/scripts/validate_install_parity.py --files src/claude/architect.md;          echo $?  # 0
```

A solo template edit is caught. A solo `src/claude/` edit is not: the hand-maintained copies are exempt from the required-sibling set, so you can change Claude agent behavior without touching the template and no gate objects. This carve-out is load-bearing, not vestigial: measured at `origin/main` `08f4941565`, of the 173 commits since 2025-01-01 touching a hand-maintained member of a shared-agent group, **54 (31%) did not touch the template**. A group is a stem with a `templates/agents/{stem}.shared.md`, and its hand-maintained members are all three of `src/claude/{stem}.md`, `.claude/agents/{stem}.md`, and `.github/agents/{stem}.agent.md`. Counting only `src/claude/` gives a different and narrower 26 of 142, 18%. Both figures grow as commits land, so re-measure rather than trusting the absolute counts; the ratio is the durable part. Treat the lockstep as a convention you uphold, not a rule the tooling enforces. The drift detector scores similarity against a floor, a much weaker condition than agreement; see the section below. Read both files before you edit either.
2. **Skill schema**. Every skill MUST have a `SKILL.md` with frontmatter fields `name`, `version`, `description` per `.agents/steering/claude-skills.md`.
3. **Skill tests**. New skills MUST include pytest coverage under `tests/skills/<name>/`; CI tests do not ship with skills.
4. **File cap per PR**. Skill additions SHOULD ship ≤10 files per PR (see `.agents/steering/claude-skills.md`).
5. **No internal references in `src/claude/`**. Files under `src/claude/` MUST NOT reference `.agents/` paths that will not exist for downstream installers.
6. **Python for skill scripts**. New skill scripts MUST be Python per ADR-042.
7. **Test what the prose promises**. When a `SKILL.md` names a script, an exit code, and what that code means, it has defined an executable contract, and at least one file under `tests/` MUST assert the documented exit-code behavior. Prose is not enforcement: a documented exit code that nothing asserts drifts from the script the first time someone edits the script and not the document, and the drift is invisible because the document still reads correctly. `check_skill_contract_tests.py` enforces this.

## SHOULD

1. **One skill, one purpose**. A skill SHOULD name one primary trigger family and one primary output artifact in its `description`. If a `SKILL.md` describes unrelated trigger families or unrelated output artifacts, split the skill or add a `Rationale:` paragraph that explains why one workflow owns both.
2. **Idempotent tools**. Skills that mutate state SHOULD be safe to re-run (or detect prior completion).
3. **Invoke via the Skill tool**. Claude Code agents SHOULD invoke matching skills via the `Skill` tool, not inline equivalents.

## MUST NOT

1. MUST NOT hand-edit generated agent files (`src/copilot-cli/`, `src/vs-code-agents/`) to add behavior; add it to the template and regenerate. This does NOT apply to `src/claude/*.md`, which is hand-maintained and edited directly.
2. MUST NOT bundle skill code changes with memory changes in the same PR (separate concerns).

## What the drift detector does and does not catch

A green `build/scripts/detect_agent_drift.py` is not proof that two agent copies agree. Read its scope before you rely on it.

It compares two pairs, and `templates/` is in neither:

1. `src/claude/*.md` against `src/vs-code-agents/*.agent.md`
2. `.claude/agents/*.md` against `.github/agents/*.agent.md`

`templates/agents/*.shared.md` is read for FILENAMES only, to pick which agents take part in comparison 2 (`shared_template_names`, `detect_agent_drift.py:536-544`, `frozenset(p.name.removesuffix(".shared.md") for p in templates_path.glob("*.shared.md"))`). The template body is never a comparison input.

Within a pair it scores only the sections named in `SECTIONS_TO_COMPARE` (`detect_agent_drift.py:57`), an 18-entry allowlist. Everything outside it is invisible, including a whole section present in one copy and absent from the other.

Measured on `origin/main` at `7e8d3ac2f4` (2026-08-01): across the 32 files in `src/claude/*.md`, the 18 allowlisted sections hold 48,177 of the 412,265 characters that `get_markdown_sections()` returns, 11.7%.

Both sides of that ratio exclude YAML frontmatter, because `compare_agent` strips it with `remove_yaml_frontmatter` before sectioning, so frontmatter is never a comparison input. Leaving frontmatter in the denominator alone gives 426,714 and a flattering 11.3%, which is the wrong figure: it measures the numerator and the denominator by two different rules.

A run emits 61 result records: 60 content comparisons plus one `NO COUNTERPART` for `claude-instructions.template`, which has no sibling. The script below reproduces current-tree record counts and section coverage. Check out `7e8d3ac2f4` first to reproduce the pinned 412,265-character denominator above.

```bash
uv run python - <<'PY'
import sys; sys.path.insert(0, 'build/scripts')
import detect_agent_drift as d
from pathlib import Path
a = d.run_detection(Path('src/claude'), Path('src/vs-code-agents'), 80)
b = d.run_install_detection(Path('templates/agents'), Path('.claude/agents'),
                            Path('.github/agents'), 80)
records = list(a) + list(b)
content = [r for r in records if r.status != 'NO COUNTERPART']
print(len(records), 'records;', len(content), 'content comparisons;',
      len([r for r in content if not r.sections]), 'match zero sections')

cov = tot = 0
for f in sorted(Path('src/claude').glob('*.md')):
    secs = d.get_markdown_sections(d.remove_yaml_frontmatter(f.read_text()))
    tot += sum(len(v) for v in secs.values())
    cov += sum(len(secs[s]) for s in d.SECTIONS_TO_COMPARE if s in secs)
print(cov, 'of', tot, 'chars sit in allowlisted sections')
PY
```

8 of those 60 match zero sections and return a hardcoded 100.0 via `detect_agent_drift.py:302` (`overall = round(total_similarity / compared_count, 1) if compared_count > 0 else 100.0`). They are the two comparisons each for `analyst`, `explainer`, `silent-failure-hunter`, and `type-design-analyzer`: for those four agents the check cannot fail. Replacing the entire body of `src/vs-code-agents/silent-failure-hunter.agent.md` still yields RC=0 / 100.0 / OK.

For the other agents it is a **similarity floor, not an equality check**. The score is the mean across the allowlisted sections present in **either** file, not both: `compare_agent` skips a section only when it is absent from both sides (`detect_agent_drift.py:280-281`), so a section one copy has and the other lacks is compared against the empty string and scores zero.

How forgiving the floor is depends on how many sections the agent has and on how far those sections already sit below 100. Measured across both comparison pairs at `origin/main` (60 content comparisons, 30 agents x 2 pairs), zeroing the highest-scoring sections first:

| Allowlisted sections present | Comparisons | Zero-overlap rewrites needed to breach the 80 floor |
|---|---|---|
| 0 | 8 | unreachable (hardcoded 100.0) |
| 1 | 20 | 1 |
| 2 to 5 | 14 | 1 |
| 6 to 7 | 10 | 1 for six of them, 2 for four |
| 8 | 4 | already below the floor for two, else 1 |
| 9 | 2 | 1 for one, 2 for the other |
| 10 | 2 | 2 |

So for **22 of the 26 agents that have any compared section, one wholly rewritten section is enough to trip the check**; three more need two, and `merge-resolver` already sits below the floor. Even `architect`, the widest at 10 sections, needs only two.

Do not compute this column from section counts alone. An earlier version of this rule did, assuming every section scores 100, and concluded `architect` needed three. It needs two, because its sections already average 92.5 rather than 100. The same idealized model produced "more than a fifth of an agent's allowlisted sections", generalized from `architect` alone, which was wrong for 25 of the 26. The real threshold depends on the actual per-section scores, so measure it.

The per-section score is **Jaccard on word sets** (`calculate_similarity`, `detect_agent_drift.py:213-232`): the size of the token intersection over the size of the union. Two consequences follow, and mixing them up produces a badly wrong mental model. Measured by mutation inside `## Constraints` on `src/claude/architect.md`:

| Mutation | Section score | Overall | Result |
|---|---|---|---|
| baseline | 100.0 | 92.5 | RC=0, OK |
| 1 repeated identical line | 100.0 | 92.5 | RC=0, OK |
| 60 repeated identical lines | 100.0 | 92.5 | RC=0, OK |
| 1 line of distinct vocabulary | 84.2 | 91.0 | RC=0, OK |
| 60 lines of distinct vocabulary | 8.2 | 83.3 | RC=0, OK |

The repeated line is the section's own first line, appended verbatim. The distinct-vocabulary lines are `- zzq{i} bbq{i} ddq{i}` for `i` in `range(n)`, which share no tokens with anything. Both rows depend on the exact text used, so reproduce them with that mutation or expect different numbers.

Repeated identical lines are free, and free from the very first one: the line's tokens are already in the set, so appending it adds nothing to either the intersection or the union and the score does not move at all. Distinct vocabulary is not free: 60 such lines take the section from 84.2 to 8.2. Two earlier versions of this rule got this pair wrong in opposite directions. One read the flat scores as "the score saturates" and generalized it; it does not saturate, that measurement had accidentally held vocabulary constant. The other recorded 80.0 for both repeated rows, which forced the prose into claiming repeats are free only "after the first". Nothing is charged for the first either. If a mutation adds no token the union has not already seen, Jaccard cannot move.

What survives all of this is the weaker true claim: a **contradiction that reuses the surrounding vocabulary scores high and passes**, because Jaccard sees tokens, not meaning. And note the last row: even a section scored 8.2 leaves `architect` at 83.3 overall, above the floor. On an agent with one section the same mutation would land at 8.2 overall and fail. The check's sensitivity is inversely proportional to how much of the agent it looks at.

Two further exceptions. `merge-resolver` carries a recorded 20.9 baseline for both of its comparisons (`KNOWN_BASELINE_DRIFT`, `detect_agent_drift.py:116`) and sits in `_ADVISORY_VENDORED_DRIFT` (`:601`). Because the baseline floor is applied in `_classify_overall`, it does not report drift at all: both comparisons print `OK (baselined)` at 20.9% and exit 0. Install-pair drift is advisory unless `--fail-on-install-drift` is passed (`:710-718`, `:864-867`); `.github/workflows/drift-detection.yml` does pass it.

That workflow is a **weekly and manual audit, not a PR merge gate**: its only triggers are `schedule` (Mondays 09:00 UTC) and `workflow_dispatch`, and it opens an issue when it finds drift. The PR-time workflow `agent-drift-detection.yml` runs `generate_agents.py --validate`, which regenerates and compares, and never invokes this detector.

This is the tool working as documented (`detect_agent_drift.py:29-33` names the sections it focuses on), not a defect. The error to avoid is reading its silence as parity.

## References

- `build/generate_agents.py`. Generator (emits the Copilot and VS Code copies `src/copilot-cli/`, `src/vs-code-agents/` only; does NOT write `src/claude/`)
- `build/scripts/detect_agent_drift.py`. Semantic-similarity check on two OTHER pairs (`src/claude` vs `src/vs-code-agents`; `.claude/agents` vs `.github/agents`). Does NOT read `templates/agents/*.shared.md` content.
- `build/scripts/validate_install_parity.py`. Enforces that the sibling copies move together in a diff (co-change, not content)
- `.agents/steering/agent-prompts.md`. Prompt standards
- `.agents/steering/claude-skills.md`. Skill authoring standards
- `scripts/validation/check_skill_contract_tests.py`. Enforces the executable-contract test requirement
- `.agents/architecture/ADR-042-python-migration-strategy.md`. Python-first
- Issue #3402. worktree identity and stale helper resolution
