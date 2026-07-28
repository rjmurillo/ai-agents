# Do not point the orphan-ref validator at .serena/memories and act on the raw count

## Question

The orphan-ref validator reports `CRITICAL_FAIL` with 182 findings when run against
`.serena/memories`. Should the memory corpus be repaired to green, and should the
scan be added to CI?

## Conventional answer

A `CRITICAL_FAIL` verdict means the target is broken and should be repaired until it
passes, then gated so it cannot regress. That is how `.agents/specs` and `tests/evals`
are treated, and both are in `DEFAULT_TARGETS` in
`.claude/skills/orphan-ref-validator/scripts/scan.py`.

## First-principles position

The 182 findings are two unrelated populations with opposite truth values. Acting on
the aggregate verdict is wrong in both directions: it overstates the problem by
roughly a factor of ten and it invites a bulk suppression that would bury the real
defects.

Baseline measured 2026-07-28 at commit `b6b33f3963`, on a pristine tree with this
file itself removed. 877 files scanned, 350 refs checked, 182 findings across 80
files:

| Kind | Count | Verdict |
| --- | --- | --- |
| `skill_name` | 161 | Approximately all false positives |
| `script_path` | 21 | All real |

The `skill_name` detector treats any backticked kebab-case token as a skill
reference. That inference holds for the default targets, where such tokens really
are skill names. It does not hold for prose. Sampling 14 distinct files produced
zero real skill references. What it produced instead:

- `arg-type`, `return-value`: mypy error codes
- `gpt-4o-mini`, `gpt-5-mini`, `github-models`, `anthropic-sdk`: model and provider IDs
- `if-then-else`: a jq construct
- `all-globs-to-all-files`, `any-glob-to-any-file`: GitHub labeler config keys
- `ubuntu-latest`: an Actions runner label
- `copilot-pull-request-reviewer`: a bot login
- `skill-pr-enum-001`, `skill-pr-status-001`: memory IDs
- `review-by`: a YAML frontmatter field name
- `context-mode`, `caveman`: plugins from other marketplaces, not skills in this repo

The largest single contributor is `github/github-topics-seo-optimization.md` at 24
findings. Its entire subject is kebab-case GitHub topic strings.

## Evidence

Reproduce (both the baseline and the post-repair figures come from this command):

```bash
uv run python .claude/skills/orphan-ref-validator/scripts/scan.py \
  --targets .serena/memories --output json
```

The flag is `--output json`, not `--format json`. The output is not valid JSON on
its own; the tool appends a `VERDICT:` line after the object, so split on
`VERDICT:` before parsing. Counts are at `Data.counts`, findings at
`Data.findings`, and each finding carries `kind` and `target_file`.

`.serena/memories` is not in `DEFAULT_TARGETS`, which covers `.agents/specs`,
`tests/evals`, `.claude/.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`,
and `.github/plugin/marketplace.json`. The default scan passes. Nothing in CI points
the validator at the memory corpus, which is how the `script_path` rot accumulated
silently across the ADR-042 PowerShell-to-Python migration.

## Decision

Repaired the `script_path` orphans in place (issue #3629). The count went 21 to 14;
each of the 14 that remain was read in context and is a historical record that
deliberately keeps the retired PowerShell name alongside its Python successor, so
they are correct as written.
Did not touch the `skill_name` findings and did not add suppressions for them.
Did not gate `.serena/memories` in CI: at 21 real out of 182 the signal-to-noise
ratio makes the gate unusable until the `skill_name` detector is scoped to targets
where the kebab-case-means-skill inference actually holds. Issue #3637 tracks that
scoping and carries the measurement: of the 122 distinct tokens the detector flags
here, zero have ever been a skill in this repository's git history, and a planted
reference to a genuinely deleted skill is still caught, so the detector is
miscalibrated rather than inert.

After the repair: 878 files, 390 refs, 197 findings, 183 `skill_name` and 14
`script_path`, across 76 files. Nine of the 21 baseline `script_path` findings were
retired. Two were added on purpose: the Pester memory names
`build/scripts/Invoke-PesterTests.ps1` a second time to record what was retired, and
the sentence you just read names it again to explain that. Both are the intended
behaviour of a corpus that documents dead tooling.

If you are running this scan on the memory corpus, filter to `kind == "script_path"`
and ignore the aggregate verdict. Suppressing the `skill_name` findings to reach a
green verdict would be the dishonest fix: it records a detector limitation as if it
were an intentional exception in dozens of separate files.

## Scope caveat

The validator only recognises script paths under `build/scripts/`,
`scripts/validation/`, and `scripts/`. References under `.claude-mem/scripts/` and
other prefixes are outside its detection set, so a clean `script_path` result says
nothing about those.

## This memory demonstrates its own claim

This file contributes 20 `skill_name` findings and one `script_path` finding on its
own: 15 from the bulleted example list above, three more where this section repeats
`arg-type`, `gpt-4o-mini`, and `if-then-else` a second time, and two from the closing
paragraph below. The detector reads them as skill references even though every
sentence around them says they are not skills. That is the cleanest available
evidence that the detector matches on token shape alone and reads no context.

Net across the repair the `skill_name` count rose 161 to 183: this file added 20,
and two rewritten paragraphs elsewhere added one each (`action-pin-policy` in the
SHA-pinning memory, `enable-pester` in the Pester memory). Writing accurate prose
costs findings under this detector, which is the point. The 20 are left as-is
rather than worked around; a memory that had to disguise its own examples to keep a
scanner quiet would be the wrong artifact.
