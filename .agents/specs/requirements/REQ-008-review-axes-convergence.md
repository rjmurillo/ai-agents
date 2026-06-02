---
type: requirement
id: REQ-008
title: review-axes-convergence
status: draft
priority: high
category: tooling
epic: "1933"
related:
  - DESIGN-008
  - TASK-008
issues:
  - 1934
  - 1935
retrospective: .agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md
author: Richard Murillo
created: 2026-05-09
updated: 2026-05-10
---

# REQ-008: review-axes-convergence

## Context

Two review prompt families drift independently. CI runs 6 axes from `.github/prompts/pr-quality-gate-{role}.md`. `/review` runs 5 inline axes in `.claude/commands/review.md`. PR `feat/skill-eval-triage` saw `/review` PASS while `/pr-quality:all` BLOCKED, producing two recursive fix-loops, 5 extra commits, and 4 Round-2 regressions. Root cause documented in `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`. This requirement set establishes a single canonical source for all review axes and enforces parity between local and CI evaluation.

CVA summary: 11 canonical axes share role identity, PR diff evaluation, structured findings schema, and verdict token handling. Variabilities are evaluation focus, invocation mechanism (Stage-1 prompt, Stage-2 prompt, or Skill()), and CI counterpart presence. Abstraction decision: no new abstraction layer. `ai_review_common.py:merge_verdicts` captures verdict-token commonality; the Stage-1, Stage-2, and chained-skill split is encoded as explicit type discriminator in `/review` prose.

---

## REQ-008-01: Canonical Axis Files

### Requirement Statement

WHEN a maintainer commits `.claude/skills/review/references/{role}.md` for any canonical role (spec-compliance, analyst, architect, qa, security, devops, roadmap, reliability, observability, agent-safety, decision-rigor)
THE SYSTEM SHALL preserve YAML frontmatter fields `name`, `role`, `version`, `description` AND body sections `Grounding Rules`, `Analysis Focus Areas`, `Output Schema`
SO THAT canonical axis files are self-contained and serve as the single source of truth for both local `/review` and generated CI prompts.

### Acceptance Criteria

- [ ] Eleven files exist under `.claude/skills/review/references/`: `spec-compliance.md`, `analyst.md`, `architect.md`, `qa.md`, `security.md`, `devops.md`, `roadmap.md`, `reliability.md`, `observability.md`, `agent-safety.md`, and `decision-rigor.md`.
- [ ] Each file contains YAML frontmatter with keys: `name`, `role`, `version`, `description`.
- [ ] Each file contains body sections titled exactly: `Grounding Rules`, `Analysis Focus Areas`, `Output Schema`.
- [ ] `Output Schema` specifies fields: `severity`, `category`, `location`, `recommendation`, `verdict`.
- [ ] `verdict` tokens authored by non-spec canonical axes in Output Schema: `PASS`, `WARN`, `CRITICAL_FAIL`. The `spec-compliance` axis MAY author `UNKNOWN` as the parseable token for INCONCLUSIVE when no spec is linked. For all other axes, `UNKNOWN` is reserved for `/review`'s parser when an axis output is unparseable. Parser-recognized token vocabulary (consumed by `extract_verdict` and `merge_verdicts`): `PASS`, `WARN`, `CRITICAL_FAIL`, `REJECTED`, `FAIL`, `NEEDS_REVIEW`, `UNKNOWN`. Amended PR #1965 (cluster F) per critic Finding 3: original AC conflated authored vs parsed token sets.
- [ ] Schema-validation fixture at `tests/` asserts exact section-title strings (literal match, not substring): `"## Grounding Rules"`, `"## Analysis Focus Areas"`, `"## Output Schema"` must be present as level-2 headings in each canonical file. A maintainer renaming any section title fails CI.
- [ ] Body content (Grounding Rules + Analysis Focus Areas sections) seeded from the corresponding `.github/prompts/pr-quality-gate-{role}.md` at time of creation. CI source files have no frontmatter and no Output Schema; these are added during seed, not copied verbatim. A migration-validation script (`scripts/validation/validate_seed_parity.py`) computes SHA-256 of the seeded body (excluding frontmatter and Output Schema) and compares against SHA-256 of the source CI prompt body; the script exits 1 if any mismatch. This script runs as part of TASK-008-01 and its output is attached to the PR.
- [ ] No file under `.github/prompts/pr-quality-gate-{role}.md` is hand-edited after this feature ships; all edits flow through canonical.
- [ ] **Amended issue #1905 (Stage-1 spec-compliance axis)**: the canonical set includes a seventh quality-gate role, `spec-compliance`, plus the four later-added review axes (`reliability`, `observability`, `agent-safety`, `decision-rigor`). The live canonical directory is `.claude/skills/review/references/` (the repo moved here from the spec-original `.claude/review-axes/`; `tests/lib/test_axis_schema.py` and `tests/lib/conftest.py` enforce the live path and the full role set). `spec-compliance` is the Stage-1 gating axis: input is the PR diff plus linked REQ/DESIGN/TASK docs (or PR-body acceptance criteria); it emits `PASS`, `WARN`, `CRITICAL_FAIL`, or `UNKNOWN` (the parseable token for INCONCLUSIVE when no spec is linked). It reads spec docs that a CI context may lack, so it emits `UNKNOWN` when spec docs are unavailable and lets the caller decide how to gate that verdict. In `/review`, `UNKNOWN` is Stage-1 local-gating. It does not introduce a new verdict token: `INCONCLUSIVE` reuses `UNKNOWN` so `extract_verdict`/`merge_verdicts` (REQ-008-05) are untouched.
- [ ] **Short-circuit AC (issue #1905)**: WHEN `/review` runs, `spec-compliance` runs first. WHEN its verdict is `CRITICAL_FAIL` or `UNKNOWN` (INCONCLUSIVE), the 10 Stage-2 canonical axes and 3 chained skills SHALL be marked `SKIPPED`, the final verdict SHALL be the Stage-1 verdict, and only the Stage-1 findings SHALL be emitted. WHEN its verdict is `PASS` or `WARN`, the 10 Stage-2 canonical axes and 3 chained skills run and merge with the Stage-1 verdict. Authorized by repo-owner batch decision on issue #1905 (2026-05-31), which supersedes the issue's original AC1 (INCONCLUSIVE-proceeds) with INCONCLUSIVE-gates.

### Rationale

A single authoritative file eliminates the drift vector that caused PR `feat/skill-eval-triage` to diverge between local and CI review. The SoR pattern (data-intensive-applications rule) requires one owner per concept.

### Dependencies

None. This is the root artifact.

---

## REQ-008-02: Idempotent Generator

### Requirement Statement

WHEN `python3 build/scripts/generate_pr_quality_prompts.py` runs
THE SYSTEM SHALL read each `.claude/skills/review/references/{role}.md` canonical file, write `.github/prompts/pr-quality-gate-{role}.md` atomically (tmp file + fsync + rename), emit structured stdout (`key=value`), and exit with ADR-035 codes (0=ok, 1=logic, 2=config)
SO THAT generation is idempotent (zero diff on re-run against an already-up-to-date tree) and partial crashes leave no corrupt output.

### Acceptance Criteria

- [ ] Transform algorithm is fully declarative: (a) strip YAML frontmatter keys `name`, `role`, `version`, `description` from canonical file before output; (b) prepend a static 3-line CI header consisting of the lines `<!-- GENERATED -- DO NOT EDIT -->`, `<!-- Source: .claude/skills/review/references/{role}.md -->`, `<!-- Run: python3 build/scripts/generate_pr_quality_prompts.py -->` followed by a blank line; (c) emit canonical body unchanged. No timestamps, no SHAs, no environment-dependent tokens in output. Any time-varying token in the header breaks idempotency and is prohibited. Header uses hyphens, not em-dashes, per `.claude/rules/universal.md` MUST NOT 5.
- [ ] Running the generator twice in sequence produces zero git diff on `.github/prompts/`.
- [ ] Generator writes to a `.tmp` file, calls `fsync`, then renames atomically; no partial output survives a crash mid-write.
- [ ] Generator emits `key=value` lines to stdout for each processed role (e.g., `role=analyst status=ok`).
- [ ] Generator exits 0 on full success, 1 on content/logic error, 2 on config/missing-canonical error.
- [ ] Generator opens all output files in LF-only mode (`open(..., "w", newline="\n")`) to prevent platform-dependent line-ending divergence. A test round-trips a CRLF-terminated canonical file through the generator and asserts the output has LF-only line endings.
- [ ] Filename validation: canonical filenames must match regex `^[a-z][a-z0-9_-]*\.md$`; non-matching files cause a config-error exit (2). This catches typos at write time rather than silently skipping, matching the strictness of the canonical-source contract. Spec amended PR #1965 (cluster H): the original "skipped with a logged warning" was YAGNI carry-over from a different generator with a different threat model.
- [ ] NO-REGEN sentinel support is NOT required for this generator: every canonical file is intended to be regenerated on every run. The `generate_commands.py` precedent the original spec cited handles a different use case (commands map to authored skills that may have manual edits). Spec amended PR #1965 (cluster H).
- [ ] Generator contains no `eval`, `exec`, `shell=True`, or subprocess calls; pure Python string operations only.

### Rationale

Atomic writes prevent corrupt CI prompts if the generator is interrupted. Idempotency allows the generator to run in pre-push hooks without spurious diffs. Exit codes follow ADR-035 so CI can distinguish content errors from config errors.

### Dependencies

- REQ-008-01 (canonical files must exist before generator can run).

---

## REQ-008-03: Drift Detection Enforcement

### Requirement Statement

WHEN canonical `.claude/skills/review/references/{role}.md` and generated `.github/prompts/pr-quality-gate-{role}.md` diverge at `git push`
THE SYSTEM SHALL block the push via `.githooks/pre-push` emitting a unified diff and exit code 1
SO THAT divergence is caught at the author's terminal before CI is invoked.

WHEN divergence reaches PR merge without being caught by pre-push
THE SYSTEM SHALL block merge via a drift-check job in `ai-pr-quality-gate.yml` emitting GitHub Actions error annotations
SO THAT no divergent prompt ever ships to production as a backstop.

### Acceptance Criteria

- [ ] `.githooks/pre-push` contains a drift-detection step that runs after other checks.
- [ ] Pre-push drift step computes expected generated content by running the generator in dry-run mode (or equivalent) and diffs against the HEAD-committed content of `.github/prompts/` (not working tree content). Rationale: the author may have run the generator but not staged the output; the hook must catch committed divergence, not unstaged divergence.
- [ ] On divergence, pre-push outputs a unified diff to stderr and exits 1.
- [ ] Pre-push hook is bypassable (standard `--no-verify`); CI drift-check job is not bypassable.
- [ ] `ai-pr-quality-gate.yml` contains a `drift-check` job that runs the generator and fails with error annotations if diff is non-empty.
- [ ] CI drift-check job summary includes the full unified diff.
- [ ] Drift check does not execute prompt content; it compares file bytes only (no eval, no prompt injection surface).

### Rationale

Pre-push hook gives immediate feedback (seconds) at the author's terminal. CI job is the backstop for `--no-verify` bypasses. Defense in depth per release-it.md stability patterns.

### Dependencies

- REQ-008-01, REQ-008-02.

---

## REQ-008-04: /review Command Rewrite

### Requirement Statement

WHEN `/review` runs
THE SYSTEM SHALL load `spec-compliance` from `.claude/skills/review/references/` as the Stage-1 gate, load the remaining 10 canonical axis files from that directory as Stage-2 axes, chain `Skill(skill="code-qualities-assessment")`, `Skill(skill="golden-principles")`, and `Skill(skill="taste-lints")`, merge the collected verdicts via `merge_verdicts` from `.claude/lib/ai_review_common/`, and output a findings table with per-axis verdict and a final merged verdict with emoji
SO THAT `/review` local output matches what CI will surface, eliminating push-and-wait round-trips.

### Acceptance Criteria

- [ ] `/review` loads axis definitions from `.claude/skills/review/references/` not from inline prose.
- [ ] `spec-compliance` runs as the Stage-1 gate, then 10 Stage-2 canonical axes run: analyst, architect, qa, security, devops, roadmap, reliability, observability, agent-safety, decision-rigor.
- [ ] 3 skill axes chained: `code-qualities-assessment`, `golden-principles`, `taste-lints`.
- [ ] Total verdicts collected when Stage 2 runs: 14 (1 Stage-1 gate + 10 Stage-2 axes + 3 chained skills).
- [ ] Verdicts merged via `merge_verdicts` from `.claude/lib/ai_review_common/`.
- [ ] Merge rules: any `CRITICAL_FAIL`, `REJECTED`, or `FAIL` token yields `CRITICAL_FAIL`; any `WARN` yields `WARN`; all `PASS` yields `PASS`.
- [ ] Output includes a findings table with columns: axis, verdict (with emoji from `get_verdict_emoji`), summary.
- [ ] Final merged verdict displayed with emoji and human-readable label.
- [ ] If a skill invocation crashes or returns no verdict, that axis is marked `UNKNOWN` and `/review` continues (no abort); the `UNKNOWN` is surfaced in the findings table.

### Rationale

Converging `/review` onto the same canonical axis files as CI eliminates the drift that caused the PR `feat/skill-eval-triage` incident. `UNKNOWN` handling prevents a single skill failure from hiding all other findings.

### Dependencies

- REQ-008-01, REQ-008-05.

---

## REQ-008-05: Verdict Merge Module

### Requirement Statement

WHEN `merge_verdicts(verdicts: Sequence[str]) -> str` is called with any combination of verdict tokens (input domain: `PASS`, `WARN`, `CRITICAL_FAIL`, `REJECTED`, `FAIL`, `NEEDS_REVIEW`, `NON_COMPLIANT`, `COMPLIANT`, `PARTIAL`, `UNKNOWN`, plus any unrecognized string treated as UNKNOWN per below)
THE SYSTEM SHALL apply these rules in priority order: (1) if any token is in FAIL_VERDICTS (`CRITICAL_FAIL`, `REJECTED`, `FAIL`, `NEEDS_REVIEW`, `NON_COMPLIANT`) → return `CRITICAL_FAIL`; (2) if any token is `WARN` or `PARTIAL` → return `WARN`; (3) if any token is `UNKNOWN` OR unrecognized (and none triggered steps 1 or 2) → return `UNKNOWN`; (4) all remaining (`PASS`, `COMPLIANT`) → return `PASS`; (5) if sequence is empty → return `UNKNOWN`. Amended PR #1965 per critic Finding 10: original AC enumerated only PASS/WARN/CRITICAL_FAIL/UNKNOWN; CI action.yml accepts the broader vocabulary (Issue #470 added NEEDS_REVIEW; spec-validation flow uses COMPLIANT/NON_COMPLIANT/PARTIAL).
SO THAT callers receive a single deterministic merged verdict without implementing merge logic themselves. Rationale for UNKNOWN rule: when the severity chain produces PASS but some axes did not evaluate, the caller cannot claim PASS; UNKNOWN forces explicit attention. When the chain produces WARN or CRITICAL_FAIL, UNKNOWN adds no information and does not override.

WHEN `get_verdict_emoji(verdict: str) -> str` is called
THE SYSTEM SHALL return a consistent emoji for each known verdict token and a fallback for unknown tokens
SO THAT output is human-readable without callers duplicating emoji mappings.

WHEN `extract_verdict(text: str) -> str` is called with multi-line skill output
THE SYSTEM SHALL scan for the pattern `(?mi)^\s*(?:Final\s+)?[Vv]erdict:\s*(PASS|WARN|CRITICAL_FAIL|REJECTED|FAIL|UNKNOWN)\b` and return the matched token, or `UNKNOWN` if no match
SO THAT `/review` callers do not implement bespoke verdict-extraction regex and skill output with embedded verdict labels is parsed correctly.

### Acceptance Criteria

- [ ] Module exists at `.claude/lib/ai_review_common/` (Python package; synced from `scripts/ai_review_common/` via `scripts/sync_plugin_lib.py`). The package re-exports `merge_verdicts`, `get_verdict_emoji`, and `extract_verdict` from `verdict.py` and `issue_triage.py` submodules.
- [ ] `merge_verdicts` handles tokens: `PASS`, `WARN`, `CRITICAL_FAIL`, `REJECTED`, `FAIL`, `UNKNOWN`.
- [ ] `merge_verdicts([])` returns `UNKNOWN`.
- [ ] `merge_verdicts(["UNKNOWN"])` returns `UNKNOWN`.
- [ ] `merge_verdicts(["PASS"])` returns `PASS`.
- [ ] `merge_verdicts(["PASS", "WARN"])` returns `WARN`.
- [ ] `merge_verdicts(["PASS", "UNKNOWN"])` returns `UNKNOWN` (PASS not confirmed when axes unevaluated).
- [ ] `merge_verdicts(["WARN", "UNKNOWN"])` returns `WARN` (WARN is a real finding; UNKNOWN adds no information).
- [ ] `merge_verdicts(["PASS", "WARN", "CRITICAL_FAIL"])` returns `CRITICAL_FAIL`.
- [ ] `merge_verdicts(["PASS", "FAIL"])` returns `CRITICAL_FAIL`.
- [ ] `merge_verdicts(["PASS", "REJECTED"])` returns `CRITICAL_FAIL`.
- [ ] `merge_verdicts(["UNKNOWN", "WARN"])` returns `WARN`.
- [ ] `merge_verdicts(["CRITICAL_FAIL", "UNKNOWN"])` returns `CRITICAL_FAIL`.
- [ ] `merge_verdicts(["UNKNOWN", "UNKNOWN"])` returns `UNKNOWN`.
- [ ] `extract_verdict("Final verdict: WARN due to X")` returns `WARN`.
- [ ] `extract_verdict("no verdict here")` returns `UNKNOWN`.
- [ ] `extract_verdict("VERDICT: CRITICAL_FAIL")` returns `CRITICAL_FAIL`.
- [ ] `get_verdict_emoji("PASS")` returns a non-empty string.
- [ ] `get_verdict_emoji("WARN")` returns a non-empty string distinct from PASS.
- [ ] `get_verdict_emoji("CRITICAL_FAIL")` returns a non-empty string distinct from PASS and WARN.
- [ ] `get_verdict_emoji` with an unknown token returns a non-empty fallback string.
- [ ] Module exports REQ-008-introduced functions: `merge_verdicts` (extended for UNKNOWN + CI-token vocabulary), `get_verdict_emoji` (pre-existing), `extract_verdict` (new). The package also re-exports the pre-existing AI-review utility functions (`get_verdict`, `get_labels`, `get_milestone`, `format_verdict_alert`, etc.) that ship with the canonical `scripts/ai_review_common/` module via sync_plugin_lib.py; these are NOT introduced by #1934 and remain part of the existing API surface. Amended PR #1965 per critic Finding 12: original AC text "no other public names" conflicted with the synced canonical-package API contract.
- [ ] Module contains no `eval`, `exec`, or subprocess calls.
- [ ] 100% line and branch coverage in `tests/test_ai_review.py`.

### Rationale

Centralizing merge logic in one module prevents callers from each implementing subtly different merge rules, which was the root cause of divergence. 100% coverage enforces the module as a stable contract.

### Dependencies

None. This module has no internal dependencies.

---

## REQ-008-06: Vendored Install Compatibility

### Requirement Statement

WHEN `/review` runs in a vendored install that contains only `.claude/{agents,commands,hooks,lib,rules,settings.json,skills}` and `CLAUDE.md` (no `.agents/`, no `.github/`)
THE SYSTEM SHALL complete successfully and produce a valid findings table with merged verdict
SO THAT project-toolkit plugin consumers and downstream installers receive the same review capability without needing the full repository structure.

### Acceptance Criteria

- [ ] A `tests/integration/test_vendored_install.py` test copies only `.claude/{agents,commands,hooks,lib,rules,settings.json,skills}` plus `CLAUDE.md` to a `tmp_path` directory and asserts: (a) `import ai_review_common` succeeds from the copied `.claude/lib/`; (b) `merge_verdicts(["PASS"])` executes correctly from the copy; (c) all `.claude/skills/review/references/{role}.md` files are present and pass schema validation (frontmatter keys, body sections). This test does NOT invoke the Claude Code harness or require a live model; it tests the Python surface and file structure only.
- [ ] No runtime dependency in `/review` prose, `.claude/lib/ai_review_common/`, or any canonical axis on `.agents/`, `.github/`, `scripts/`, or `tests/` paths. Verified by AST-based scan in `tests/integration/test_vendored_install.py::test_no_runtime_dependency_on_agents_or_scripts_in_lib` (no `ImportFrom`/`Import` targeting `agents`/`scripts` namespaces; no `Call` argument string starting with those prefixes). Documentation prose that mentions these paths in advisory form (e.g. "check `.agents/architecture/` when present") is allowed because vendored installs without those paths skip rather than fail. Amended PR #1965 per critic Finding 1: the original literal-grep AC was contradicted by the seeded CI prose; AST runtime check is the right contract.
- [ ] A schema-validation fixture in `tests/` asserts each canonical file has all four frontmatter keys and all three body sections.

### Rationale

US3 (vendored installer) requires `/review` to work without the full repository. Hardcoded references to `.agents/` or `.github/` would break downstream plugin consumers.

### Dependencies

- REQ-008-01, REQ-008-04, REQ-008-05.

---

## REQ-008-07: Test Coverage

### Requirement Statement

WHEN `pytest` runs on `tests/build_scripts/test_generate_pr_quality_prompts.py`, `tests/test_ai_review.py`, and `tests/hooks/test_drift_check.py`
THE SYSTEM SHALL exercise idempotency, partial-write recovery, schema validation, all verdict token combinations including `UNKNOWN`, `get_verdict_emoji`, and drift hook positive and negative paths
SO THAT regressions in generation, merge logic, and drift detection are caught before merge.

### Acceptance Criteria

- [ ] `tests/test_ai_review.py` achieves >=99% line and branch coverage on `scripts/ai_review_common/verdict.py` (the canonical source synced to `.claude/lib/ai_review_common/`). Verified: `pytest tests/test_ai_review.py --cov=scripts.ai_review_common.verdict --cov-branch` reports 99% (1 line + 1 branch in pre-existing `get_labels_from_ai_output` defensive code path). The functions added by #1934 (`merge_verdicts` UNKNOWN handling, `extract_verdict`) are 100% covered by the truth-table tests. The full pytest suite runs under `.github/workflows/pytest.yml` with `pytest --cov`. A dedicated coverage gate IS pinned in `.github/workflows/pytest.yml`: the new step "Pin ai_review_common.verdict coverage at 98% (REQ-008-07)" runs `pytest tests/test_ai_review.py --cov=scripts.ai_review_common.verdict --cov-branch --cov-fail-under=98` and fails the build on any drop below 98%. Actual coverage is 98.62% (1 unreachable defensive branch in pre-existing `get_labels_from_ai_output:251`). Reaching 100% requires excluding or covering that branch and is tracked by follow-up issue #1970. The 98% floor prevents silent drops while accepting the pre-existing unreachable. Amended PR #1965 per critic Finding 8.
- [ ] `tests/build_scripts/test_generate_pr_quality_prompts.py` includes: (a) idempotency test (run twice, assert zero diff), (b) partial-write recovery test (simulate crash after tmp write, assert no corrupt output), (c) schema validation test (invalid filename, missing frontmatter key).
- [ ] `tests/hooks/test_drift_check.py` includes: (a) positive test (canonical matches generated, no output, exit 0), (b) negative test (canonical differs, unified diff emitted, exit 1).
- [ ] All tests pass with `pytest` 8+ and Python 3.14.
- [ ] No test uses `Skip` or `pytest.mark.skip` without a linked issue.
- [ ] No test modifies baseline fixtures to force a pass.

### Rationale

Test coverage is the enforcement mechanism for all other requirements. Without it, regressions in `merge_verdicts` or the generator reintroduce the drift that caused the original incident.

### Dependencies

- REQ-008-02, REQ-008-03, REQ-008-05.

---

## REQ-008-08: Stale Reference Cleanup

### Requirement Statement

WHEN `.claude/commands/pr-quality/all.md` cites verdict-merge logic
THE SYSTEM SHALL cite `.claude/lib/ai_review_common/` (Python module) and NOT `AIReviewCommon.psm1` (removed in commit `3f3326f9`)
SO THAT the canonical-source-mirror rule is satisfied and no reader is directed to a non-existent file.

WHEN GitHub issue #1934 or epic #1933 body contains the text "7 axes" or cites `.claude/lib/AIReviewCommon` without the `.py` extension
THE SYSTEM SHALL update those issue bodies via `gh issue edit` to reflect: the canonical review axis set, `ai_review_common.py` module, and chained-skills extras approach
SO THAT the issue tracker matches the implemented design.

### Acceptance Criteria

- [ ] `.claude/commands/pr-quality/all.md` contains the string `ai_review_common.py` and does not contain the string `AIReviewCommon.psm1`.
- [ ] `.claude/commands/pr-quality/all.md` does not contain the string `AIReviewCommon` without the `.py` suffix.
- [ ] GitHub issue #1934 body does not contain the string "7 axes" after update.
- [ ] GitHub issue #1934 body references `ai_review_common/verdict.py` explicitly.
- [ ] GitHub epic #1933 body does not contain the string "7 axes" after update.
- [ ] GitHub epic #1933 body references the chained-skills approach layered on the canonical review axis set.
- [ ] **NOTE (one-shot manual gate)**: these AC items are state-of-GitHub-issues claims, not file-tracked. They are verified once at PR merge time (via `gh issue view --json body` against the strings above) and not continuously. If issue body drift recurs post-merge, a follow-up issue must instrument the check (file at PR merge if not already present). Amended PR #1965 per critic Finding 4: original AC text was unfalsifiable post-merge; this addendum makes the verification window explicit.

### Rationale

The canonical-source-mirror rule (`.claude/rules/canonical-source-mirror.md`) requires that any citation of a module be accurate. A citation to a deleted file misleads reviewers and future maintainers. The PR `feat/skill-eval-triage` incident was partially caused by stale orchestrator prose.

### Dependencies

- REQ-008-05 (module must exist before it can be cited correctly).

---

## Kill Criteria (REQ-008-09)

The convergence experiment is falsifiable. Roll back to the dual-source
arrangement (separate inline /review prose + .github/prompts/) if any of
the following fire within 30 days post-merge:

- **K1**: drift hook produces 3+ false positives (axis edits the maintainer
  intended that the hook blocked incorrectly). Indicates the canonical
  contract is too strict for normal evolution.
- **K2**: generator-induced regressions in CI prompts (3+ instances of the
  generator producing CI prompts that fail the gate when canonical was
  meant to be a no-op refinement). Indicates the transform is unsafe.
- **K3**: vendored install breakage (1+ downstream installer reports
  /review fails to run after a project-toolkit plugin update tied to
  this PR). Hard fail; rollback immediately.
- **K4**: drift between local /review verdict and CI verdict on the same
  commit, observed 3+ times in 30 days. Indicates convergence claim is
  false; either /review or CI is silently diverging.

If any K1-K4 fires, file a follow-up issue, revert the relevant commits
on a hotfix branch, and re-evaluate the convergence design.

Rationale: per `.agents/retrospective/2026-05-05-pr-1887-iteration-paradox.md`
the original problem was unmonitored drift. A convergence design without
falsifiable kill criteria is itself unmonitored. Discovered by /review
roadmap axis (#1934).
