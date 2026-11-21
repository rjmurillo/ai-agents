# doc-accuracy

Checks documentation against the code, treating the code as the truth. It finds code examples that name symbols that do not exist, behavioral claims the implementation contradicts, facts that differ across files, and public API members that no doc mentions.

## When to use it

- Docs may contain code examples that do not compile or name missing symbols.
- A behavioral claim in the docs may contradict the implementation.
- The same number (a limit, a performance figure) appears in several files with different values.
- You are preparing a release and want a documentation audit.
- Trigger phrases: `check documentation accuracy`, `verify code examples compile`, `audit docs vs code`, `check doc consistency`, `run doc-accuracy`.

## When not to use it

- You want broad codebase analysis: use [`analyze`](analyze.md) instead.
- You want to fix broken code fences: use [`fix-markdown-fences`](fix-markdown-fences.md) instead.
- You already know the one inaccuracy: fix it directly with a code review.

## Quick start

This skill has no short slash command, so the agent usually loads it for you. In Claude Code you can still type `/project-toolkit:doc-accuracy`. The [`review`](review.md) skill invokes it as one of its quality axes, and the agent loads it when your request matches. To ask for it by name, say:

```text
Use the doc-accuracy skill to check the docs in this repository against the code, and report anything at high severity or above.
```

The agent runs the deterministic script first, then dispatches agents for behavioral checks. It shows proposed fixes and waits for your approval before it edits a file.

## What you get

The script writes JSON artifacts to an output directory (default `<target>/.doc-accuracy`):

| File | Contents |
| --- | --- |
| `assessment.json` | Phase 1: doc and source inventory with a symbol index |
| `claims.json` | Phase 2: verifiable claims extracted from docs |
| `compilability-findings.json` | Phase 3: run status and symbol resolution findings |
| `gate-result.json` | Gate verdict, the reason when inconclusive, and severity counts |
| `report.md` | Markdown summary, when you pass `--format markdown` |
| `same-pr-findings.json` | With `--same-pr`: findings from rules R1 to R4 and what was examined |
| `same-pr-checklist.json` | With `--same-pr`: changed prose claims with the code changed beside them, for Phase 4 |

Every finding carries a file path, line number, severity, and evidence. Severities are Critical, High, Medium, and Low.

Exit codes of `doc_accuracy.py`:

| Code | Meaning |
| --- | --- |
| `0` | No findings at or above the severity threshold |
| `1` | Error or inconclusive run, including no source symbols for Phase 3 |
| `2` | Configuration error, including an invalid `--diff-base`, or `--same-pr` without `--diff-base` |
| `3` | External dependency failure, including unavailable or failed Git |
| `10` | Findings at or above the severity threshold |

When Phase 1 finds no source symbols, Phase 3 reports `DID_NOT_RUN` with zero findings instead of flagging every reference.

## Advanced use

From the root of a checkout of this repository:

```bash
uv run python .claude/skills/doc-accuracy/scripts/doc_accuracy.py --help
uv run python .claude/skills/doc-accuracy/scripts/doc_accuracy.py --target . --format summary
uv run python .claude/skills/doc-accuracy/scripts/doc_accuracy.py --target . --diff-base origin/main --severity-threshold critical
uv run python .claude/skills/doc-accuracy/scripts/doc_accuracy.py --target . --diff-base origin/main --same-pr
uv run python .claude/skills/doc-accuracy/scripts/pr_snapshot.py --help
```

The six phases:

| Phase | Mode | Output |
| --- | --- | --- |
| 1 Assessment | script | `assessment.json` |
| 2 Claim extraction | script | `claims.json` |
| 3 Compilability | script | `compilability-findings.json` |
| 4 Behavioral | Sonnet agents, one per file group | `behavioral-findings.json` |
| 5 Cross-document | script plus Sonnet agent | `consistency-findings.json` |
| 6 Structure | Sonnet agent | `structure-findings.json` |

Your trigger picks the phases: a full audit runs 1 to 6, `verify code examples` runs 1 to 3, `audit docs vs code` runs 1 to 4, and `check doc consistency` runs 1, 2, and 5. Use `--phases` to select phases and `--format json|gate|summary|markdown` to pick the output.

`--diff-base REF` limits the run to files changed since `HEAD` forked from `REF`, and only claims on changed lines block. See [`references/diff-scoping.md`](../../src/claude/skills/doc-accuracy/references/diff-scoping.md).

`--same-pr` (needs `--diff-base`) catches prose that drifts from code changed in the same diff, before a PR exists. Run it when a branch changes both prose and code. It reads changed Markdown and `.tmpl` lines, Python docstrings and comments, and JSON or YAML string values, and pairs each with the code symbols changed in the same diff. The deterministic rules contribute findings to the gate:

| Rule | Catches |
| --- | --- |
| R1 | A touched exit table omits a literal process exit. Dynamic exits remain unjudged. |
| R2 | A closed language or path enumeration omits a collection member. A path list binds only when its line names the collection or its script, or sits in that script. |
| R3 | A named JSON key receives identifiers that contradict its claimed contents. |
| R4 | A count beside a backticked collection name differs from its literal length. |
| Repository cardinality | Changed prose counts disagree with enumerations, tables, or sibling JSON/YAML arrays. |

Other claims enter `same-pr-checklist.json` with paired code locations.
Unchanged prose naming changed functions, flags, or deleted headings also enters this checklist.
Explicit script paths can resolve unchanged literal collections.
Other behavioral contradictions require Phase 4 review.
The pre-PR sequence runs this scan as `Doc Accuracy Same-PR (advisory)`.
The repository cardinality integration also checks branches containing only documentation or structured data.
Installed plugins use R1 through R4 without this repository integration.

In C# code blocks, Phase 3 skips names that appear only inside string or char literals, format specifiers, or attribute named arguments. For example, `DEBUG` in `[Conditional("DEBUG")]` is not reported. Attribute type names, code inside interpolation holes, and comments are still checked. When a string never closes, or a verbatim string spans lines, the whole code block is scanned without blanking. Its close may be a later string's quote, so guessing could hide real code. The block can then over-report literal words but never hides one. The scanners in `csharp_literals.py` and `csharp_holes.py` do this work, and their docstrings list the known limits.

`pr_snapshot.py` captures an immutable head and base snapshot of a pull request for review. Its flags include `--owner`, `--repo`, `--pull-request`, `--output-dir`, `--check-stale`, `--identity-file`, and `--run-scanner`. Exit `0` is ok, `1` is a verification or stale result, `2` config, `3` external, `4` auth.

The skill states that Haiku agents are too shallow for Phase 4 and requires Sonnet agents, one per file group, so each agent keeps cross-cutting context. It replaces the earlier `incoherence`, `doc-coverage`, and `doc-sync` skills. <!-- orphan-ref-ignore -->

## Where it runs

| Host | Available |
| --- | --- |
| Claude Code | Yes |
| GitHub Copilot CLI | Yes |
| Codex | Yes |
| Cursor | Yes |
| Muse | Yes |

## Related

- [`review`](review.md): invokes this skill as a review axis.
- [`fix-markdown-fences`](fix-markdown-fences.md): repairs malformed code fences it finds.
- [`analyze`](analyze.md): broader codebase analysis.
- [`api-doc-authoring`](api-doc-authoring.md): authors API docs and defers claim checking here.
- [`style-enforcement`](style-enforcement.md): code style checks.
- Source: [`SKILL.md`](../../src/claude/skills/doc-accuracy/SKILL.md)
- Diff scoping: [`diff-scoping.md`](../../src/claude/skills/doc-accuracy/references/diff-scoping.md)
- How to call skills on each host: [Call agents and skills](../call-agents-and-skills.md)
