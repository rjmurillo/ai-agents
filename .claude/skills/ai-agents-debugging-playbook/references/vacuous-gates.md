<!-- vendor-portability: contributor-facing knowledge pack for the rjmurillo/ai-agents repo itself; intentionally references upstream paths because its audience is repo contributors, not plugin consumers (issue #2050). Declared paths: build/scripts/build_all.py, build/scripts/validate_install_parity.py, scripts/ci/drift_run_detection.py -->

# Gates that pass in ways that read as success

Phase 3 step 3 of the playbook: prove a check can still fail. These four gates print OK for reasons that do not cover your change. Anchors verified 2026-10-31 at 42e409325.

- `validate_install_parity.py` is a co-change check, not a content comparison. It skips RULE groups entirely (`build/scripts/validate_install_parity.py`, branch `if kind == "RULE"`) and exempts diffs that touch only hand-maintained `SHARED_AGENT` copies (branch `if kind == "SHARED_AGENT"`).
- `validate_install_parity.py` and `run_plugin_version_bump_ci.py` both diff a base ref. An uncommitted control is invisible. Commit the control first.
- `detect_agent_drift.py` compares only the entries named in `SECTIONS_TO_COMPARE`, at an 80 percent similarity threshold (`Default: 80`). Content under an unlisted heading is never compared. Replacing all 22 agent names in the orchestrator's capability matrix in one install copy still reports "OK (100.0% similar)" and exits 0.
- `scripts/ci/drift_run_detection.py` captures the `detect_agent_drift.py` exit code as `drift_detected` and discards it.

Use `build/scripts/build_all.py --check` to learn whether a template edit reached every copy.
