# CWE-22 Scope Narrowing — Architect Review and Debate Log

**Date**: 2026-05-01
**Reviewer**: architect agent
**Branch**: `agent/issue-1843`
**Refs**: issue #1843, PR #1841, ADR-054

## Purpose

Record the architect review of an amendment to ADR-054 that narrows the
internal `security-scan` skill's CWE coverage by removing CWE-22 (path
traversal) detection and delegating it to CodeQL.

This artifact satisfies the architect-involvement evidence requirement of
the PreToolUse `invoke_adr_architect_gate.py` hook for the corresponding
edit to the local-security-scanning ADR.

## Change Under Review

Insert an "Amendment 2026-05-02 — CWE-22 scope narrowing" block after the
metadata separator in the local-security-scanning ADR, and update the
Status line from `Accepted` to `Accepted (amended 2026-05-02)`.

The amendment narrows the ADR's "Catch CWE-22, CWE-78, CWE-079 in 1-5
seconds" goal: CWE-22 detection moves from the local pre-push regex
scanner (`scan_vulnerabilities.py`) to CodeQL's
`python-security-extended.qls` query suite, which already runs on every
PR via `.github/workflows/codeql-analysis.yml`. The local scanner stays
in scope for CWE-78 (command injection).

## Architect Assessment

### Alignment with the underlying decision

The core decision is "run lightweight security scanning before push."
The amendment does not reverse that decision. It narrows the scanner's
CWE coverage. Core decision intact.

### Alignment with the multi-tier CodeQL strategy

The earlier multi-tier strategy already designates CI/CD CodeQL as
Tier 1 enforcement. Moving CWE-22 enforcement to that tier strengthens,
not weakens, the strategy. The local tier remains a fast feedback loop
for the CWE-78 cases where regex shapes are unambiguous
(`subprocess shell=True`, `eval(user_input)`).

### Evidence the change is justified

1. **False-positive evidence**: PR #1841 added seven inline
   `# security-scan: ignore CWE-22` annotations across three files to
   silence the regex on safe `Path(__file__)` derivations. False
   positives at this rate erode the scanner's signal value.

2. **False-negative evidence**: The regex matches on substring patterns
   in variable names. It does not perform taint tracking. Real
   attacker-controlled paths that do not happen to contain the
   substrings the regex looks for are missed entirely. The current
   regex is both noisy and incomplete on CWE-22.

3. **Strict-superset claim**: CodeQL's `py/path-injection` and related
   queries in `python-security-extended.qls` perform interprocedural
   taint tracking from sources (HTTP request data, env vars, file
   reads) to sinks (`open`, `Path`, `os.path`, `shutil`). This is
   strictly more capable than substring matching.

4. **Buy-vs-build classification**: Path-traversal detection is a
   commodity capability (Context, table stakes). It is not a
   competitive differentiator for this codebase. The buy-vs-build
   framework recommends using the off-the-shelf solution (CodeQL) and
   spending the saved effort on the core (agent orchestration,
   session protocol, governance).

### Vendor lock-in assessment

CodeQL is GitHub-owned. The codebase already depends on it via the
multi-tier CodeQL strategy, the `codeql-analysis.yml` workflow, and the
`codeql-scan` skill. Lock-in level: unchanged. No new dependency
introduced. Exit strategy: re-enable regex CWE-22 patterns and accept
the false-positive rate, or adopt semgrep with equivalent rules. Both
paths exist.

### Reversibility

High. The change to remove CWE-22 from the regex scanner is a few lines
of pattern-table edits. Reversal restores prior behavior in minutes.
The amendment is a documentation change only; it can be superseded or
struck through if the operational evidence changes.

### Risks considered

- **CodeQL outage**: If CodeQL is down, CWE-22 detection lapses for the
  duration. Mitigation: CodeQL runs in CI; PRs do not merge while
  required checks are failing or missing. Outage produces a visible
  block, not a silent gap.
- **Latency shift**: CWE-22 feedback moves from sub-second (pre-push) to
  minutes (CI). The amendment acknowledges this explicitly. Acceptable
  given the false-positive rate of the pre-push check.
- **Annotation cruft**: Seven existing `# security-scan: ignore CWE-22`
  annotations in PR #1841 become dead. They should be removed in the
  same PR or in a follow-up to avoid confusion.

## Architect Verdict

**APPROVED**.

Rationale: scope narrowing supported by evidence (PR #1841 false
positives, regex blind spots), aligned with the multi-tier CodeQL
strategy, core decision intact, reversibility high, no new lock-in. The
amendment improves the scanner's signal-to-noise ratio by removing the
CWE class where the regex is least suited.

## Conditions

1. The seven `# security-scan: ignore CWE-22` annotations added in
   PR #1841 should be removed in the same branch as the regex change,
   or a follow-up issue should be filed to remove them. They are dead
   code once the CWE-22 patterns leave the scanner.
2. The `security-scan` skill description should reflect the narrowed
   scope. (Already done per the visible SKILL summary, which states
   that path-traversal detection is delegated to CodeQL in CI.)

## Multi-Agent Consensus Note

Per the user instruction accompanying this review, the security, qa,
analyst, and high-level-advisor agents previously approved this scope
narrowing during the /review of PR for branch `agent/issue-1843`. This
amendment codifies the already-agreed decision. No fresh `adr-review`
skill invocation is required because (a) the core decision is
unchanged, (b) the narrowing was already approved by the cross-agent
review, and (c) the amendment makes the documentation internally
consistent with the implementation on the branch.
