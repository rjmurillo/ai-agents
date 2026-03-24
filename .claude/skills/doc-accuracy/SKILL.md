---
name: doc-accuracy
version: 1.0.0
model: claude-sonnet-4-5
description: >-
  Multi-phase documentation verification treating code as source of truth.
  Consolidates incoherence, doc-coverage, doc-sync, and comment-analyzer into
  a single workflow. Use when auditing documentation accuracy, verifying code
  examples compile, checking behavioral claims, or running pre-release doc audits.
license: MIT
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

```
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

## Invocation

```bash
# Full deterministic scan (Phases 1-3)
python3 scripts/doc_accuracy.py --target /path/to/repo

# Compilability only
python3 scripts/doc_accuracy.py --target /path/to/repo --phases 3

# Incremental (changed files only)
python3 scripts/doc_accuracy.py --target /path/to/repo --diff-base main

# JSON output to specific directory
python3 scripts/doc_accuracy.py --target /path/to/repo --output-dir .doc-accuracy

# Set severity threshold for exit code
python3 scripts/doc_accuracy.py --target /path/to/repo --severity-threshold critical

# Markdown report output
python3 scripts/doc_accuracy.py --target /path/to/repo --format markdown

# Text summary to stdout
python3 scripts/doc_accuracy.py --target /path/to/repo --format summary
```

---

## Output Artifacts

| File | Description |
|------|-------------|
| `assessment.json` | Phase 1: doc/source inventory with symbol index |
| `claims.json` | Phase 2: verifiable claims extracted from docs |
| `compilability-findings.json` | Phase 3: symbol resolution findings |
| `gate-result.json` | Gate verdict with severity counts |
| `report.md` | Markdown summary (when `--format markdown`) |

---

## Process

### Phases 1-3: Deterministic (Script)

Run `doc_accuracy.py` to produce JSON artifacts. No LLM calls.

1. **Phase 1 (Assessment)**: Enumerate documentation and source files. Extract public symbols via regex. Build doc-to-source mapping.
2. **Phase 2 (Claim Extraction)**: Parse markdown files. Extract verifiable claims with file path, line number, claim type, and referenced symbols.
3. **Phase 3 (Compilability)**: Verify type names, method names, parameter names in code examples exist in the codebase via symbol index lookup.

### Phase 4: Behavioral Verification (Agent)

Dispatch one Sonnet agent per file group. Each agent receives:

- Full source file content (read code FIRST)
- Documentation file content
- Filtered claims from `claims.json`
- Compilability findings (to avoid re-checking)

Agent prompt:

```
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

Validate documentation structure (indexes, navigation, completeness). Apply comment quality framework (accuracy, completeness, long-term value, misleading elements, improvements) to a 20% sample of source comments.

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

| Code | Meaning |
|------|---------|
| 0 | No findings at or above severity threshold |
| 1 | Error (file not found, parse error) |
| 10 | Findings at or above severity threshold |

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

---

## Related Skills

| Skill | Relationship |
|-------|-------------|
| `incoherence` | **Replaced**: Detection logic superseded by Phases 3-5 |
| `doc-coverage` | **Replaced**: Symbol extraction logic preserved in Phase 1 |
| `doc-sync` | **Replaced**: Structural audit absorbed into Phase 6 |
| `analyze` | Complementary: broader codebase analysis |
| `style-enforcement` | Complementary: code style checks |
