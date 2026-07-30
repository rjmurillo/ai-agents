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

## What happened next: this decision was narrowed by production evidence

On 2026-07-29 the recommendation above was implemented and then partly
overruled. Recording both, because the reversal is the useful part.

PR #3735 did what this memory asked. It stopped treating every backticked kebab
token as a reference, required evidence before a token becomes a candidate, and
only then gated the corpus. Four and a half minutes earlier PR #3741 had merged
a memory describing how the parser separates a documented route from a live one.
To describe the live form, the prose wrote the live form. The gate read it as a
reference to a skill that does not exist and `main` went red.

Both pull requests were green. Each ran against a tree that did not contain the
other, so the collision first existed in the merge result. Two agent sessions
then opened duplicate fixes 25 seconds apart, #3751 and #3752.

### The reversal, stated plainly

This memory says above that suppressing `skill_name` findings "would be the
dishonest fix", and that its own examples were left in place "rather than worked
around". Fix #3752 added a line-scoped ignore directive. That is a suppression,
and it contradicts the earlier position rather than fulfilling it.

The position still holds at the scale it was written for: bulk-suppressing 161
findings across dozens of files to buy a green verdict would record a detector
limitation as if it were intent. One reviewed exception on one line is a
different trade. The prose there is not a mislabelled example; it is a sentence
whose subject is route syntax, so it must contain route syntax. No rewording
preserves it.

Two costs to keep visible. The directive is line-scoped, not token-scoped: it
hides every reference candidate on that line, so a later edit to the same line
is unguarded. And while suppressed references are retained with file and line
rather than dropped, no gate reviews that list or bounds its growth, so the
audit trail exists only when a human reads the scanner output.

### What would and would not have prevented this

Not a path filter. `main` uses branch protection without strict status checks,
so each pull request was validated against the base it branched from rather
than the tip it would land on. Nothing in either check set could observe the
other change. Serializing the merge, by strict status checks or a merge queue,
is the control that matches this failure. That is a repository governance
decision, not a per-change one.

A separate and genuinely open gap sits next to it: the corpus gate is not
triggered by the corpus. `.github/workflows/pytest.yml` selects the Python
suite by changed path and `.serena/memories/**` is not among those paths, so a
memory-only change does not run the gate that reads memories. Local pre-push
hooks run the full suite, which is the only reason such an edit is caught at
all. Closing it is not free: that filter also gates the Windows job and the
security scans, so adding the corpus there makes a one-word memory fix pay for
the whole matrix. A job scoped to the single test is the cheaper shape. Left
open deliberately rather than fixed in passing.

### Standing exposure

The one-line fix landed without the regression tests written for it, so the
suppression directive is currently protected by nothing. Deleting that comment
turns `main` red again with no test failing first, and the next reader has no
signal that the line is load-bearing. Treat the directive as unguarded until a
test asserts it.

Filed as issue #3749. A separate clone-dependency defect found in the same
investigation is issue #3753.
