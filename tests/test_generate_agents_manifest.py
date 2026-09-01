"""End-to-end tests proving an ADR-080 manifest KEEP_PIN entry reaches
generated output through the real generate_agents() entry point.

Split out of test_generate_agents.py (taste-lint file-size ratchet) once
the direct-call regression test needed the same manifest-plus-artifact
fixture as the already-present wiring test: three near-identical ~35-line
blocks (this file's two tests, plus
test_relative_templates_path_resolves_manifest_pins in
test_generate_agents_main.py) is the Rule of Three trigger for extracting
_write_keep_pin_manifest, and the extraction itself pushed
test_generate_agents.py over the ratchet, so the manifest-pin tests moved
here with it.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

# Add build directory to path for imports
_BUILD_DIR = Path(__file__).resolve().parent.parent / "build"
sys.path.insert(0, str(_BUILD_DIR))

from generate_agents import generate_agents  # noqa: E402

from tests.test_generate_agents import _create_test_structure  # noqa: E402


def _write_keep_pin_manifest(
    repo_root: Path,
    *,
    unit: str = "templates/agents/test-agent.shared.md",
    agent: str = "test-agent",
) -> None:
    """Write a KEEP_PIN manifest entry plus its committed sweep artifact.

    Shared by every end-to-end wiring test that proves a manifest pin
    reaches generated output through the real generate_agents()/main()
    entry point. ADR-080 rule 2 requires a *committed* sweep artifact whose
    CONTENT shows a qualifying result (resolve_manifest_model parses and
    cross-checks it; see _sweep_report_satisfies_rule2 in
    build/model_pin_manifest.py), not merely a file that exists, so this
    writes both the manifest entry and a real qualifying report for it.
    """
    manifest_dir = repo_root / ".agents" / "governance"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    # date uses the UTC date, matching resolve_manifest_model's own default
    # (datetime.now(timezone.utc).date()): a host ahead of UTC would
    # otherwise sometimes see the local date read as "tomorrow" in UTC
    # terms, failing this test via the age < 0 guard for reasons unrelated
    # to what it checks.
    utc_today = datetime.now(timezone.utc).date()
    (manifest_dir / "model-pin-evidence.json").write_text(
        "{"
        '"schema_version": "1", "pins": [{'
        f'"unit": "{unit}", '
        '"model": "claude-opus-4-6", '
        '"decision": "KEEP_PIN", '
        '"fixtures_sha": "abc123", '
        '"artifact": "evals/test-agent-spike/sweep.json", '
        '"default_model": "claude-sonnet-4-6", '
        f'"date": "{utc_today.isoformat()}"'
        "}]}",
        encoding="utf-8",
    )
    artifact_path = repo_root / "evals" / "test-agent-spike" / "sweep.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps({
            "schemaVersion": "1",
            "agent": agent,
            "decision": "KEEP_PIN",
            "winner": "claude-opus-4-6",
            "fixtures_sha": "abc123",
            "default_model": "claude-sonnet-4-6",
            "models": [
                {"model_id": "claude-opus-4-6"},
                {"model_id": "claude-sonnet-4-6"},
            ],
            "n_shared_fixtures": 8,
            "recall_delta": 0.05,
            "ci95": [0.01, 0.09],
        }),
        encoding="utf-8",
    )


class TestManifestWiring:
    """Tests for ADR-080 manifest KEEP_PIN resolution through generate_agents()."""

    def test_manifest_keep_pin_reaches_generated_output(self, tmp_path: Path) -> None:
        """End-to-end wiring proof (testing.md SHOULD 6): drives the real
        generate_agents() entry point, not just convert_frontmatter_for_platform
        directly, so a future change that stops passing manifest/source_unit
        through the call site fails this test even if the helper's own unit
        tests still pass."""
        repo_root, templates_path, output_root = _create_test_structure(
            tmp_path, with_model_tiers=True
        )
        _write_keep_pin_manifest(repo_root)

        exit_code = generate_agents(templates_path, output_root, repo_root)
        assert exit_code == 0

        output_file = output_root / "vs-code-agents" / "test-agent.agent.md"
        content = output_file.read_text(encoding="utf-8")
        assert "model: Claude Opus 4.6 (copilot)" in content

    def test_no_manifest_entry_for_unit_omits_model(self, tmp_path: Path) -> None:
        """Negative control for the same wiring: an empty manifest (today's
        real .agents/governance/model-pin-evidence.json state) must not
        change generation output at all."""
        repo_root, templates_path, output_root = _create_test_structure(tmp_path)
        manifest_dir = repo_root / ".agents" / "governance"
        manifest_dir.mkdir(parents=True)
        (manifest_dir / "model-pin-evidence.json").write_text(
            '{"schema_version": "1", "pins": []}', encoding="utf-8"
        )

        exit_code = generate_agents(templates_path, output_root, repo_root)
        assert exit_code == 0

        output_file = output_root / "vs-code-agents" / "test-agent.agent.md"
        content = output_file.read_text(encoding="utf-8")
        assert "model:" not in content

    def test_direct_call_resolves_relative_paths_and_manifest_pins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """generate_agents() itself, not just main(), must resolve relative
        arguments: a direct call bypasses main()'s own resolution, and
        checking a resolved COPY without reassigning
        templates_path/output_root/repo_root would pass the containment
        guard and then hang on the symlink-ancestor walk anyway -- or, for
        templates_path specifically, silently drop every manifest pin:
        shared_file.relative_to(repo_root) raises ValueError (caught,
        source_unit=None) once repo_root is absolute but shared_file (built
        from a still-relative templates_path) is not. A bare exit_code==0
        assertion cannot tell "generated correctly" apart from "generated
        with every pin silently dropped", so this also proves a KEEP_PIN
        entry actually reaches the output file, the same wiring
        test_manifest_keep_pin_reaches_generated_output proves for the
        already-absolute-paths case above."""
        repo_root, _templates, output_root = _create_test_structure(
            tmp_path, with_model_tiers=True
        )
        _write_keep_pin_manifest(repo_root)
        monkeypatch.chdir(repo_root)
        exit_code = generate_agents(Path("templates"), Path("src"), Path.cwd())
        assert exit_code == 0

        output_file = output_root / "vs-code-agents" / "test-agent.agent.md"
        content = output_file.read_text(encoding="utf-8")
        assert "model: Claude Opus 4.6 (copilot)" in content
