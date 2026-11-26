# code-qualities-assessment

Scores code on five design qualities: cohesion, coupling, encapsulation, testability, and non-redundancy. You get a report with scores from 1 to 10, remediation guidance, and a pass or fail gate for CI.

## When to use it

- You want to assess maintainability or score cohesion, coupling, or testability on specific code.
- You need refactoring priorities or a quality baseline.
- You want a CI gate that flags quality regressions in changed files.
- You say `assess code quality`, `evaluate maintainability`, `check code qualities`, `testability review`, or `run quality assessment`.

## When not to use it

- You want a full pre-merge review: use [`review`](review.md) instead.
- You want repository-wide domain grading: use [`quality-grades`](quality-grades.md) instead.
- You want a broad investigation, a security assessment, or an architecture review: use [`analyze`](analyze.md) instead.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:code-qualities-assessment`. The agent loads it when your request matches. To ask for it by name, say:

```text
Use the code-qualities-assessment skill to assess src/services/auth.py.
```

The skill runs `assess.py` on the target and returns a markdown report with five scores and remediation links for low scores.

> [!NOTE]
> `assess.py` scores source code only. Rules, skills, and agents are assessed by hand against the same qualities, using [`references/executable-nl-artifacts.md`](../../src/claude/skills/code-qualities-assessment/references/executable-nl-artifacts.md).

## What you get

| Quality | Question |
| --- | --- |
| Cohesion | How related are the responsibilities? |
| Coupling | How dependent is it on other code? |
| Encapsulation | How well are internals hidden? |
| Testability | How easily can you verify it in isolation? |
| Non-redundancy | How unique is each piece of knowledge? |

A score of 10 is the best and 1 to 3 is poor. The report comes as markdown, JSON, or HTML. Full language support covers Python, TypeScript and JavaScript, C#, Java, and Go. C# needs `tree-sitter==0.26.1` and `tree-sitter-c-sharp==0.23.5` in the scanner's Python environment; see the [C# parser reference](../../src/claude/skills/code-qualities-assessment/references/csharp-parser.md). TypeScript needs `tree-sitter==0.26.1` and `tree-sitter-typescript==0.23.2`; see the [TypeScript parser reference](../../src/claude/skills/code-qualities-assessment/references/typescript-parser.md). JavaScript (`.js`, `.jsx`, `.mjs`, `.cjs`) uses the same TSX grammar and packages. Python needs `tree-sitter==0.26.1` and `tree-sitter-python==0.25.0`; see the [Python parser reference](../../src/claude/skills/code-qualities-assessment/references/python-parser.md). PowerShell (`.ps1`, `.psm1`, `.psd1`) gets coupling and non-redundancy scores and needs PowerShell 7 (`pwsh`) on PATH; see the [PowerShell parser reference](../../src/claude/skills/code-qualities-assessment/references/powershell-parser.md). Ruby, Rust, PHP, and Kotlin get heuristic support.

## Advanced use

Run the script from the root of a checkout of this repository:

```bash
uv run python .claude/skills/code-qualities-assessment/scripts/assess.py --target src --changed-only --base origin/main --format json
```

| Flag | Meaning |
| --- | --- |
| `--target` | Required. File, directory, or glob. |
| `--context` | Force `production`, `test`, or `generated` thresholds for every file. Omit it so each file uses its own category. |
| `--changed-only` | Assess only changed files. With `--base`, files changed from that revision. A changed path that is a symlink to a directory is skipped with a `SKIPPED (directory)` line on stderr. |
| `--base` | Base revision for `--changed-only`, such as `origin/main`. |
| `--gate-mode` | `auto` (default), `regression`, or `absolute`. |
| `--regression-tolerance` | Score drop tolerated before a quality counts as regressed. Default 0.5. |
| `--format` | `markdown`, `json`, or `html`. |
| `--config` | Path to a config file. |
| `--output` | Output file path. Default is stdout. |
| `--use-serena` | `auto`, `yes`, or `no`. |

Gate modes answer two different questions:

| Mode | Question | Selected when |
| --- | --- | --- |
| `regression` | Did this change make anything worse? | `--gate-mode regression`, or `auto` with both `--changed-only` and `--base` |
| `absolute` | Is the code above the configured thresholds? | `--gate-mode absolute`, or `auto` otherwise |

`--gate-mode regression` needs both `--changed-only` and `--base`. It exits 1 without them and never falls back to absolute thresholds. Each changed file is scored at the merge base and at head, and qualities are compared one by one. A file new in the change is gated absolutely.

| Exit code | Meaning |
| --- | --- |
| 0 | Gate passed, or nothing changed in regression mode. It can also carry one explicitly admitted regression, listed under `csharp_parser_dependency_admission`, `typescript_parser_dependency_admission`, or `python_parser_dependency_admission`; the review adapter reports that as WARN. The scanner accepts only the fixed records for rjmurillo/ai-agents issues #7406, #7435, and #7436; any other config value fails with exit 1. It can also carry `rule_admissions` (issue #7525): a non-redundancy drop with no new duplicated line, or, when the config sets `firstPartyCouplingAdmission`, a Python coupling drop with no new third-party import root. In a `test_*.py` or `conftest.py` file under a `tests` folder, `pytest` does not count as a new root. The review adapter reports those as WARN. |
| 1 | Invalid target, config error, or no files to assess. For C#, TypeScript, JavaScript, and Python it also means the parser package is missing, the parser failed to start, or the pinned grammar could not parse a file. For PowerShell it also means `pwsh` is missing from PATH, the PowerShell parser failed or timed out, or PowerShell reports a syntax error |
| 10 | Regression: a quality regressed or scored evidence was lost |
| 11 | A file is below the configured thresholds. The scanner checks every file and quality first, so stderr names each failure in one run |

In the JSON report, each file has a `threshold_gate` object. It holds `failed`, `unscored_supported_source`, and a `below_threshold` list with the `quality`, `score`, `minimum`, `confidence`, and `advisory` of each miss. It is null when the absolute gate did not check the file, such as a regression-mode file with a comparable base.

Scores are size-derived, so growth alone can lower cohesion. Read the named delta before you act on an exit 10. Test modules (a `tests` directory in the path or a `test_` file name) get no cohesion score, and the Markdown report shows it as `unscored (n/a)`, because each test case counts as a definition (issue #7410). Other test naming, such as Go `*_test.go`, TypeScript `*.test.ts`, or a singular `test/` directory, is still classified as authored and still gets a cohesion score.

Set thresholds in `.qualityrc.json`. The config accepts `thresholds` per quality, `context` overrides, `minConfidence`, and `ignore` globs. Lower-confidence misses warn only in absolute mode.

[`review`](review.md) runs this skill as one of its four local quality axes.

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`analyze`](analyze.md): broad multi-file investigation.
- [`review`](review.md): the full pre-merge review that calls this skill.
- [`quality-grades`](quality-grades.md): repository-wide domain grading.
- Source: [`SKILL.md`](../../src/claude/skills/code-qualities-assessment/SKILL.md)
- References: [`calibration-examples.md`](../../src/claude/skills/code-qualities-assessment/references/calibration-examples.md), [`calibration-advanced-notes.md`](../../src/claude/skills/code-qualities-assessment/references/calibration-advanced-notes.md), [`refactoring-patterns.md`](../../src/claude/skills/code-qualities-assessment/references/refactoring-patterns.md), [`csharp-parser.md`](../../src/claude/skills/code-qualities-assessment/references/csharp-parser.md), [`typescript-parser.md`](../../src/claude/skills/code-qualities-assessment/references/typescript-parser.md), [`python-parser.md`](../../src/claude/skills/code-qualities-assessment/references/python-parser.md), [`powershell-parser.md`](../../src/claude/skills/code-qualities-assessment/references/powershell-parser.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
