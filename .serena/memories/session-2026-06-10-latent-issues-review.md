# 2026-06-10 Repo Latent-Issues Review (session 2381)

Full-repo latent-issue sweep (4 parallel agents: refs, hooks, workflows, doc drift + CI log analysis). Outcomes:

## Issues filed
- Reopened #2348: main RED. Renovate #2516 bumped claude-code-action to v1.0.142 in post-pr-retrospective.yml:243; tests/workflows/test_post_pr_retrospective.py:26 hardcodes old SHA. Root cause: SHA duplicated in test; every Renovate action bump re-breaks main. Durable fix: derive expected pin from workflow.
- #2519: pr-maintenance.yml:139 calls missing Resolve-PRConflicts.ps1 (replaced by resolve_pr_conflicts.py in ADR-042 migration); conflict auto-resolution dead.
- #2520: workflow injection surfaces (branch names into run: blocks in pr-maintenance.yml), over-broad workflow-level write perms, dead pull_request_target trigger types in rjmurillo-bot.yml.
- #2521: invoke_security_commit_gate.py emits top-level {"decision":"deny"} + exit 0; harness contract is "block" + exit 2 (cf. invoke_branch_protection_guard.py). Gate likely never blocks. HIGH.
- #2522: PR Maintenance scheduled run exits 3 when reaction POSTs 404 (invoke_pr_comment_processing.py:75-126); cosmetic failures fail the run.
- #2523: hooks hardening sweep (npx no timeout in invoke_markdown_auto_lint.py; Stop hook invoke_session_validator.py exits 2 vs documented 0; unbounded session-log read_text; msvcrt 1-byte lock; parents[2] layout assumption in invoke_adr_change_detection.py).
- #2524: compress_markdown_content.py sys.exit(4) at import when tiktoken missing -> pytest collection INTERNALERROR.
- #2525: README counts drift (69 vs 74 skills; 23 vs 20 agents; internal 23-vs-24 contradiction); docs/skill-reference.md still lists deprecated incoherence skill as active.
- #2526: 8 broken governance-doc refs (ADR-010 filename, skillcreator->SkillForge rename, malformed relative path in SECURITY-REVIEW-PROTOCOL.md:267, etc.).
- #2527: AGENTS.md "Python 3.14" vs pyproject requires-python ">=3.10" contradiction; no 3.10 CI leg.

## Noticed, unfiled
- Harden-runner flagged docs/retros/INDEX.md overwritten by python3.14 during CI pytest run: a test (or auto-retro path under test) writes into the source tree. Test-isolation smell, responsible test unidentified.
- Stop-hook auto-retro skeleton embedded a stale work-item summary from a different session (invoke_auto_retrospective.py work-item source may read cross-session state).

## Method notes
- Excluded as tracked: #2050/#2510 vendor portability (PR #2515 open), #2388 envelope shape.
- Local ruff/pytest in remote container not authoritative (no Python 3.14.5; uv tool versions mismatch pinned config); use CI logs (gh job logs) as evidence instead.
