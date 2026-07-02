# 2026-07-02 Safety Audit: Findings Index and Patterns

## Summary

Full six-pass read-only audit of the repo (report: `.agents/audits/2026-07-02-safety-audit.md`). Counts after cross-model reconciliation: Critical 0, High 13, Medium 37, Low 22. Issues #2806 through #2816 track remediation, grouped by defect shape.

## Dominant pattern worth remembering

Fail-open error handling on the safety and CI surface: guards, validators, and workflows where an infrastructure error is indistinguishable from a passing check. Canonical instances:

- `push_guard_base.py:388-395` allows pushes silently on malformed stdin without the fail-open EVENT its own docstring promises (#2806).
- `check_infrastructure_failures.py:69` and `load_review_results.py:61` turn unreadable infra-failure flags into passing quality-gate verdicts (#2809).
- `audit-hook-bypass.yml:52`, `pytest.yml:221` (bandit), `memory-validation.yml:92-95` convert scanner crashes into green CI (#2808).

## Verified-clean surfaces (do not re-audit soon)

Zero CWE-78, zero committed secrets, zero unpinned Actions, zero template-to-generated drift, zero instruction-tree drift (30 rules x 3 trees), `github_core` timeouts all present except `worktree_identity.py:38`.

## Premise corrections

`src/claude/*.md` is hand-maintained, NOT generated; only `src/vs-code-agents/` and `src/copilot-cli/agents/` come from `templates/agents/*.shared.md`. Skills/agents/hooks dispatch by string name: reference-sweep orphan evidence is weak by construction (#2815).

## Repo prior art for common fixes

- Atomic writes: temp+`os.replace` in `skill_pattern_loader.py:282`, flock in `invoke_plan_state_sync.py:211`, advisory lock in `metrics_writer.py`.
- Subprocess timeouts: `scripts/github_core/api.py` sets `timeout=` on every call; use `GH_TIMEOUT_SECONDS` pattern from `set_issue_labels.py`.
