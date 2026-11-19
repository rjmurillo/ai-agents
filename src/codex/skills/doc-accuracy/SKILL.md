---
name: doc-accuracy
version: 1.0.0
description: >-
  Multi-phase documentation verification treating code as source of truth. Use
  when you say "check documentation accuracy", "verify code examples compile",
  "audit docs vs code", "check doc consistency", or "run doc-accuracy". Use for
  pre-release doc audits and checking behavioral claims. Do NOT use for broad
  codebase analysis (use analyze) or fixing markdown fence syntax (use
  fix-markdown-fences).
license: MIT
metadata:
  routing:
    role: lifecycle
    invoker: review
    trigger: review invokes doc-accuracy as one of its four local quality axes
    user-facing: false
---

# Documentation Accuracy Skill

Verify documentation claims against actual code behavior. Code is truth; docs are the subject under test.

## Triggers

| Trigger Phrase | Operation |
|----------------|-----------|
| `check documentation accuracy` | Full audit (Phases 1-6) |
| `verify code examples` | Compilability check (Phases 1-3) |
| `audit docs vs code` | Behavioral verification (Phases 1-4) |
| `check doc consistency` | Cross-document consistency (Phases 1-2, 5) |
| `run doc-accuracy` | Full audit (Phases 1-6) |

---

## When to Use

Use this skill when:

- Documentation may contain non-compilable code examples
- Behavioral claims in docs may contradict implementation
- Quantitative claims (performance, limits) appear in multiple files with different values
- Preparing for a release and need a documentation accuracy audit
- API reference may be missing public members

Use direct code review instead when:

- Investigating a single known documentation error
- The inaccuracy is already identified and needs a fix

---

## Replaces

| Skill | Reason |
|-------|--------|
| `incoherence` | 15.8% recall on critical issues; Haiku agents too shallow |
| `doc-coverage` | 0% recall on actionable issues; checks presence, not correctness |
| `doc-sync` | No scripts, purely manual LLM workflow |
| `comment-analyzer` | Advisory only, single-file scope |

---

## Architecture

### Asymmetric Verification

Code compiles and runs. Documentation describes what code does. When they disagree, the code is right. This skill reads code first, builds a verified model, then checks documentation claims against that model.

### Phase Overview

```text
Phase 1: Assessment        (script-only, <30s)  -> assessment.json
Phase 2: Claim Extraction  (script-only, <15s)  -> claims.json
Phase 3: Compilability     (script-only, <60s)  -> compilability-findings.json
Phase 4: Behavioral        (Sonnet agents, 3-7m) -> behavioral-findings.json
Phase 5: Cross-Document    (script + Sonnet, 1-2m) -> consistency-findings.json
Phase 6: Structure         (Sonnet agent, 1-2m)  -> structure-findings.json
```

---

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/doc_accuracy.py` | Phases 1-3: Assessment, claim extraction, compilability check |
| `same_pr.py` (same directory as the row above) | Same-PR mode, loaded by `doc_accuracy.py --same-pr`: prose against code changed in the same diff. Not run on its own |
| `pr_snapshot.py` (same directory as the row above) | Capture an immutable head and base snapshot of a PR for review, or re-check it with `--check-stale`. Exit 0 ok, 1 verification or stale, 2 config, 3 external, 4 auth. Flags: `--owner`, `--repo`, `--pull-request`, `--output-dir`, `--identity-file`, `--run-scanner` |

## Invocation

```bash
# Full deterministic scan (Phases 1-3)
python3 scripts/doc_accuracy.py --target /path/to/repo

# Compilability only
python3 scripts/doc_accuracy.py --target /path/to/repo --phases 3

# Incremental (files changed since HEAD forked from main, as in main...HEAD)
python3 scripts/doc_accuracy.py --target /path/to/repo --diff-base main

# JSON output to specific directory
python3 scripts/doc_accuracy.py --target /path/to/repo --output-dir .doc-accuracy

# Set severity threshold for exit code
python3 scripts/doc_accuracy.py --target /path/to/repo --severity-threshold critical

# Markdown report output
python3 scripts/doc_accuracy.py --target /path/to/repo --format markdown

# Text summary to stdout
python3 scripts/doc_accuracy.py --target /path/to/repo --format summary

# Before opening a PR that changes prose and code (see Same-PR mode)
python3 scripts/doc_accuracy.py --target . --diff-base origin/main --same-pr
```

### Line scoping with `--diff-base`

With `--diff-base`, only claims on changed lines block. See
`references/diff-scoping.md`.

### Same-PR mode

A PR that changes prose and code can leave the prose wrong about the code beside
it, and the scan above never sees that: it reads documentation files and checks
code examples. Same-PR mode runs when you pass `--same-pr`, which needs
`--diff-base` (without it the script exits 2). Run it before you open a PR
whenever the branch changes both prose and code:

```bash
python3 scripts/doc_accuracy.py --target . --diff-base origin/main --same-pr
```

**What it reads.** The changed hunks of every text file in the diff, not only
documentation globs. A changed line is prose when it is a Markdown or `.tmpl`
line (table rows included), a Python docstring or comment, or a JSON or YAML
string value. Every other changed line of a source file is code, tagged with the
function or class that holds it. Each prose line is paired with the code symbols
changed in the same diff: the same file first, then other changed files, nearest
path first. The scan reads the working tree, so commit before you run it.

**Rules.** Each rule needs a paired script or record it can identify, and stays
quiet when it cannot judge. A finding carries the rule id, the prose file and
line, the paired code file and line, evidence, and a severity.

| Rule | Fires when | Severity |
|------|------------|----------|
| R1 exit-code set | A touched Exit Codes table or docstring block lists a different code set than the literal `return N`, `sys.exit(N)`, or `exit(N)` integers in the paired script. Returns count only inside `main`-like functions | high when the code has a literal the doc lacks, medium when only the doc has an extra code |
| R2 enumeration subset | One clause names two or more, but not all, members of a closed set (values passed as `language_name=` or `error=` in the paired code) for a cause that every member shares: the code raises it from one function that takes the record. Clause and raise site match by keyword overlap | high |
| R3 JSON key contents | A line of the form "noun under `key`" or "`key` holds noun" names a noun that no identifier on the assigned right-hand side shares a stem with. A key with no assignment goes to the checklist instead | high |

**Checklist.** Any other changed prose that looks like a verifiable claim (a
number or count word, "only", "identical", "every", "never", a backticked symbol,
Exit, JSON, raises, or returns vocabulary) is written to `same-pr-checklist.json`
with its reasons and paired code locations. Nothing that looks checkable is
dropped. The Phase 4 prompt takes this file as input: verify each entry against
its paired code, and read the unchanged files the prose depends on. The scan
cannot see a contradiction that lives in a file the diff did not touch, so the
checklist file says so in its `limits` list.

**Artifacts and gate.** `same-pr-findings.json` and `same-pr-checklist.json` land
in the output directory, and `--format summary` prints their counts. A finding at
or above `--severity-threshold` makes the gate FAIL (exit 10), like any other
finding.

### Documenting another product's SDK

Phase 3 checks CamelCase symbols in code examples of supported languages
against this repository, so vendored docs for a foreign SDK fail on every API
name. Declare the file with one HTML comment:

```text
<!-- doc-accuracy: external-sdk <name> -- <reason> -->
```

- `<name>` is required. A missing `<reason>` stays valid and records "".
- Put it right after the H1. It is honored only when `<!--` starts at column 0
  and no earlier line contains three backticks or tildes. A marker below any
  code fence is ignored. The first valid marker wins.
- It silences `unresolved_symbol` for that file only. Other checks still run.
- A missing, `-`-led, or placeholder name suppresses nothing and yields a
  high `invalid_external_sdk_marker` finding.
- `claims.json` records `sdk`, `reason`, and `line`. Phase 3 counts suppressed
  symbols, and `summary` and `markdown` print one exemption line per file.

---

## Output Artifacts

| File | Description |
|------|-------------|
| `assessment.json` | Phase 1: doc/source inventory with symbol index |
| `claims.json` | Phase 2: verifiable claims extracted from docs |
| `compilability-findings.json` | Phase 3: run status and symbol resolution findings |
| `gate-result.json` | Gate verdict, reason when inconclusive, and severity counts |
| `same-pr-findings.json` | `--same-pr`: R1 to R3 findings and what was examined |
| `same-pr-checklist.json` | `--same-pr`: changed prose claims with paired code, for Phase 4 |
| `report.md` | Markdown summary (when `--format markdown`) |

---

## Process

### Phases 1-3: Deterministic (Script)

Run `doc_accuracy.py` to produce JSON artifacts. No LLM calls.

1. **Phase 1 (Assessment)**: Enumerate documentation and source files. Extract public symbols via regex. Build doc-to-source mapping.
2. **Phase 2 (Claim Extraction)**: Parse markdown files. Extract verifiable claims with file path, line number, claim type, and referenced symbols.
3. **Phase 3 (Compilability)**: Verify type names, method names, parameter names in code examples exist in the codebase via symbol index lookup. If Phase 1 finds no source symbols, report `DID_NOT_RUN` with zero findings instead of treating every documentation reference as unresolved.

### Phase 4: Behavioral Verification (Agent)

Dispatch one Sonnet agent per file group. Each agent receives:

- Full source file content (read code FIRST)
- Documentation file content
- Filtered claims from `claims.json`
- Compilability findings (to avoid re-checking)
- `same-pr-checklist.json` entries for the file group, when `--same-pr` ran

Agent prompt:

```text
You are verifying documentation accuracy. Code is the source of truth.

SOURCE FILES (read these first):
[full content of mapped source files]

DOCUMENTATION FILE:
[full content of the documentation file]

CLAIMS TO VERIFY:
[filtered claims from claims.json]

For each claim:
1. Find the relevant code in the source files
2. Determine if the documentation claim accurately describes the code behavior
3. If inaccurate: severity, description, evidence (with line numbers), suggested fix
4. If accurate: mark as PASS

Additionally check for:
- Public API members in source absent from documentation
- Behavioral nuances the documentation omits or misrepresents
- Default values that differ between docs and code
```

Launch agents in parallel (one per file group).

### Phase 5: Cross-Document Consistency (Agent)

From `claims.json`, filter to `quantitative` and `behavioral` claims. Group by topic. For groups with conflicting values across files, dispatch a Sonnet agent with benchmark data to determine the correct value.

### Phase 6: Structure and Quality (Agent)

Duplication, cohesion, and coupling findings belong to `code-qualities-assessment`; apply its `references/executable-nl-artifacts.md` and do not restate the model here. Validate documentation structure (indexes, navigation, completeness). Apply comment quality framework (accuracy, completeness, long-term value, misleading elements, improvements) to a 20% sample of source comments.

### Reconciliation (Interactive)

Present proposed fixes for user approval before modifying any file. Categories:

- Documentation prose fixes
- Code example corrections
- Consistency resolution (single source of truth)
- Structural updates (indexes, navigation)

---

## Issue Taxonomy

| Class | Description | Detection Phase |
|-------|-------------|-----------------|
| 1: Spec vs Behavior | Docs say X, code does Y | Phase 4 |
| 2: Non-Compilable Code | Code examples reference nonexistent symbols | Phase 3 |
| 3: Cross-Doc Inconsistency | Same fact, different values across files | Phase 5 |
| 4: Domain Violations | Technology convention violations (OTel, Prometheus) | Phase 4 + Plugins |
| 5: API Surface Gaps | Public API exists but is undocumented | Phase 3 + Phase 4 |

## Severity Levels

| Level | Definition |
|-------|------------|
| Critical | Code will not compile, or behavior is silently wrong |
| High | Materially misleading but no immediate failure |
| Medium | Inconsistent or confusing but correct in at least one location |
| Low | Cosmetic, improvement opportunity, or minor omission |

---

## Exit Codes

Canonical source bundled with this skill:

```text
scripts/doc_accuracy.py
```

```text
Exit Codes:
    0: No findings at or above severity threshold
    1: Error or inconclusive run, including no source symbols for Phase 3
    2: Configuration error, including an invalid --diff-base
    3: External dependency failure, including unavailable or failed Git
    10: Findings at or above severity threshold
```

---

## Anti-Patterns

| Avoid | Why | Instead |
|-------|-----|---------|
| Trusting documentation as peer of code | Docs and code are not equal; code is truth | Always read implementation before checking docs |
| Using Haiku for behavioral verification | 15.8% recall vs 100% with Sonnet | Use Sonnet agents for Phase 4 |
| One agent per dimension | Loses cross-cutting context | One agent per file group |
| Skipping Phase 1 for Phase 4 | Agents need symbol index for precise verification | Always run Phases 1-2 first |
| Running all phases on unchanged files | Wastes time and tokens | Use `--diff-base` for incremental checks |

---

## Verification

After running:

- [ ] All JSON artifacts created in output directory
- [ ] Every finding has file path, line number, severity, and evidence
- [ ] Code examples verified against actual method signatures
- [ ] Behavioral claims verified by reading implementation source
- [ ] Cross-document conflicts identified with all locations listed
- [ ] Exit code reflects severity threshold
- [ ] Phase 3 reports `DID_NOT_RUN` when no source symbols exist

---

## Related Skills

| Skill | Relationship |
|-------|-------------|
| `incoherence` | **Replaced**: Detection logic superseded by Phases 3-5 |
| `doc-coverage` | **Replaced**: Symbol extraction logic preserved in Phase 1 |
| `doc-sync` | **Replaced**: Structural audit absorbed into Phase 6 |
| `analyze` | Complementary: broader codebase analysis |
| `style-enforcement` | Complementary: code style checks |
