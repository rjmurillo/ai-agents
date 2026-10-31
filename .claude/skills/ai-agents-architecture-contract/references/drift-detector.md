# Agent Drift Detector: What It Measures

Detail behind Phase 1 of `ai-agents-architecture-contract`.

<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths because its audience is repo contributors, not plugin consumers (issue #2050). Declared paths: build/scripts/detect_agent_drift.py -->

`build/scripts/detect_agent_drift.py` measures something else again, and NOT against templates: it scores `src/claude` against `src/vs-code-agents`, and `.claude/agents` against `.github/agents`, over an 18-section allowlist. It is a similarity floor (default 80), not an equality check, and it is a weekly audit rather than a merge gate: `.github/workflows/drift-detection.yml` triggers only on `schedule` (Mondays 09:00 UTC) and `workflow_dispatch`, and opens an issue on drift. The PR-time workflow `agent-drift-detection.yml` runs `generate_agents.py --validate` instead and never invokes this detector. Template bodies are never a comparison input, and for four agents the allowlist matches nothing so the score is hardcoded to 100.0 and the check cannot fail. See `.claude/rules/claude-agents.md` for the measured trip point and what its green does and does not prove.
