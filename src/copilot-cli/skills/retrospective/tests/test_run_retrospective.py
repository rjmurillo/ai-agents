"""Tests for run_retrospective.py.

Covers a populated-session artifact (positive), the below-threshold learning
exit code (negative), the degraded-source skeleton (edge), and an integration
test that runs the orchestrator end to end and asserts the output matches the
canonical Learning Extraction Template headings.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path

UTC = timezone.utc  # noqa: UP017 - Python 3.10 compatibility

_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
_SCRIPT = _SCRIPT_DIR / "run_retrospective.py"
_TEMPLATE = Path(__file__).resolve().parent.parent / "references" / "learning-template.md"
_MODULE_NAME = f"retrospective_run_retrospective_{sha1(str(_SCRIPT).encode()).hexdigest()[:12]}"

_spec = importlib.util.spec_from_file_location(_MODULE_NAME, _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_MODULE_NAME] = _mod
_spec.loader.exec_module(_mod)

render_artifact = _mod.render_artifact
gather_evidence = _mod.gather_evidence
main = _mod.main
_resolve_output_path = _mod._resolve_output_path


# Canonical section headings the artifact MUST carry, lifted from
# references/learning-template.md. The integration test checks each appears.
_REQUIRED_HEADINGS = (
    "## Session Info",
    "## Phase 0: Data Gathering",
    "## Phase 1: Insights Generated",
    "## Phase 2: Diagnosis",
    "### Successes (Tag: helpful)",
    "### Failures (Tag: harmful)",
    "### Near Misses",
    "## Phase 3: Decisions",
    "## Phase 4: Extracted Learnings",
    "## Skillbook Updates",
    "## Deduplication Check",
)


_REQUIRED_TEMPLATE_LINES = (
    "- **Statement**: [Atomic - max 15 words]",
    "| [Strategy] | [Outcome] | [1-10] | [%] |",
    '"skill_id": "{domain}-{description}"',
)


def _write_session(tmp_path: Path, payload: dict) -> Path:
    sessions = tmp_path / ("." + "agents") / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    path = sessions / "2026-06-03-session-1-demo.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _today() -> str:
    return datetime.now(tz=UTC).strftime("%Y-%m-%d")


def _artifact_relpath(*parts: str) -> str:
    return str(Path("." + "agents", *parts))


# --- Positive: a populated session produces a scored artifact ---------------


def test_render_artifact_includes_scored_learning(tmp_path):
    # Arrange
    _write_session(tmp_path, {"workLog": ["Fixed the parser bug"]})
    evidence = gather_evidence(tmp_path, "demo")
    good = "Redis cache with 5-min TTL reduced API calls by 73% for user profiles"

    # Act
    artifact, any_below = render_artifact("demo", "2026-06-03", evidence, [good])

    # Assert
    assert any_below is False
    assert "Atomicity Score**: 100% (Excellent)" in artifact
    assert good in artifact
    assert "Fixed the parser bug" in artifact


def test_artifact_has_all_canonical_headings(tmp_path):
    # Arrange
    _write_session(tmp_path, {"workLog": ["did work"]})
    evidence = gather_evidence(tmp_path, "headings")

    # Act
    artifact, _ = render_artifact("headings", "2026-06-03", evidence, [])

    # Assert: every required heading and load-bearing placeholder is present.
    for heading in _REQUIRED_HEADINGS:
        assert heading in artifact, f"missing heading: {heading}"
    for line in _REQUIRED_TEMPLATE_LINES:
        assert line in artifact, f"missing template line: {line}"


# --- Negative: a below-threshold learning flips the exit signal -------------


def test_below_threshold_learning_sets_any_below(tmp_path):
    # Arrange
    _write_session(tmp_path, {"workLog": ["did work"]})
    evidence = gather_evidence(tmp_path, "weak")

    # Act
    artifact, any_below = render_artifact(
        "weak", "2026-06-03", evidence, ["The thing was generally good"]
    )

    # Assert
    assert any_below is True
    assert "Rejected" in artifact or "Needs Work" in artifact


def test_cli_returns_one_when_a_learning_is_weak(tmp_path):
    # Arrange
    _write_session(tmp_path, {"workLog": ["did work"]})

    # Act
    rc = main([
        "--project-dir", str(tmp_path),
        "--scope", "weak",
        "--learning", "The thing was generally good",
    ])

    # Assert
    assert rc == 1


# --- Edge: degraded sources still produce a usable skeleton -----------------


def test_render_artifact_marks_missing_sources(tmp_path):
    # Arrange: no session log, no git repo.
    (tmp_path / ("." + "agents") / "sessions").mkdir(parents=True)
    evidence = gather_evidence(tmp_path, "degraded")

    # Act
    artifact, _ = render_artifact("degraded", "2026-06-03", evidence, [])

    # Assert: degraded markers present, no invented data, outcome is Partial.
    assert "Evidence Notes (degraded sources)" in artifact
    assert "No session log found" in artifact
    assert "**Outcome**: Partial" in artifact
    # No fabricated work items leak in.
    assert "_No session work items available._" in artifact


# --- Integration: end-to-end run writes a template-conformant artifact ------


def test_integration_run_writes_conformant_artifact(tmp_path):
    # Arrange: a project dir with a populated session log.
    _write_session(tmp_path, {"workLog": [{"step": 1, "action": "Shipped X", "outcome": "ok"}]})

    # Act
    rc = main([
        "--project-dir", str(tmp_path),
        "--scope", "integration",
        "--learning", "Pin git Actions to a SHA to block tag-hijack supply attacks",
    ])

    # Assert: exit zero, file written at the canonical path, headings present.
    assert rc == 0
    written = tmp_path / ("." + "agents") / "retrospective" / f"{_today()}-integration.md"
    assert written.is_file()
    content = written.read_text(encoding="utf-8")
    for heading in _REQUIRED_HEADINGS:
        assert heading in content, f"integration artifact missing heading: {heading}"
    assert content.startswith("# Retrospective: integration")
    assert "Step 1: Shipped X -> ok" in content


def test_scope_date_controls_artifact_date_and_prefix(tmp_path):
    # Arrange
    _write_session(tmp_path, {"workLog": ["scoped work"]})

    # Act
    rc = main(["--project-dir", str(tmp_path), "--scope", "2026-06-03"])

    # Assert
    assert rc == 0
    written = tmp_path / ("." + "agents") / "retrospective" / "2026-06-03-2026-06-03.md"
    assert written.is_file()
    content = written.read_text(encoding="utf-8")
    assert "- **Date**: 2026-06-03" in content


def test_fill_mode_overwrites_skeleton(tmp_path):
    # Arrange: an existing auto-retro skeleton the Stop hook would have produced.
    retro_dir = tmp_path / ("." + "agents") / "retrospective"
    retro_dir.mkdir(parents=True)
    skeleton = retro_dir / "2026-06-03-auto-retro.md"
    skeleton.write_text("# Retrospective: 2026-06-03\n\n> UNFILLED SKELETON\n", encoding="utf-8")
    (tmp_path / ("." + "agents") / "sessions").mkdir(parents=True)

    # Act
    rc = main([
        "--project-dir", str(tmp_path),
        "--scope", "2026-06-03",
        "--fill", str(skeleton),
    ])

    # Assert: filled content replaces the skeleton per SKILL.md.
    assert rc == 0
    assert skeleton.is_file()
    content = skeleton.read_text(encoding="utf-8")
    assert "UNFILLED SKELETON" not in content
    assert "## Phase 0: Data Gathering" in content
    assert not (retro_dir / "2026-06-03-retro-filled.md").exists()


def test_fill_mode_resolves_relative_path_from_project_dir(tmp_path):
    # Arrange: a relative path to an existing skeleton under the project.
    retro_dir = tmp_path / ("." + "agents") / "retrospective"
    retro_dir.mkdir(parents=True)
    skeleton = retro_dir / "2026-06-03-auto-retro.md"
    skeleton.write_text("# Retrospective: 2026-06-03\n\n> UNFILLED SKELETON\n", encoding="utf-8")
    (tmp_path / ("." + "agents") / "sessions").mkdir(parents=True)

    # Act
    rc = main([
        "--project-dir", str(tmp_path),
        "--scope", "2026-06-03",
        "--fill", _artifact_relpath("retrospective", "2026-06-03-auto-retro.md"),
    ])

    # Assert
    assert rc == 0
    assert skeleton.is_file()
    assert "## Phase 0: Data Gathering" in skeleton.read_text(encoding="utf-8")


def test_fill_mode_resolves_basename_from_retrospective_dir(tmp_path):
    # Arrange: a basename should target the retrospective artifact directory.
    retro_dir = tmp_path / ("." + "agents") / "retrospective"
    retro_dir.mkdir(parents=True)
    skeleton = retro_dir / "2026-06-03-auto-retro.md"
    skeleton.write_text("# Retrospective: 2026-06-03\n\n> UNFILLED SKELETON\n", encoding="utf-8")
    (tmp_path / ("." + "agents") / "sessions").mkdir(parents=True)

    # Act
    rc = main([
        "--project-dir", str(tmp_path),
        "--scope", "2026-06-03",
        "--fill", "2026-06-03-auto-retro.md",
    ])

    # Assert
    assert rc == 0
    assert "## Phase 0: Data Gathering" in skeleton.read_text(encoding="utf-8")


def test_fill_mode_rejects_filled_retrospective(tmp_path):
    # Arrange: a filled artifact has no unfilled marker and must not be overwritten.
    retro_dir = tmp_path / ("." + "agents") / "retrospective"
    retro_dir.mkdir(parents=True)
    filled = retro_dir / "2026-06-03-auto-retro.md"
    original = "# Retrospective: 2026-06-03\n\n## Phase 0: Data Gathering\nManual notes\n"
    filled.write_text(original, encoding="utf-8")
    (tmp_path / ("." + "agents") / "sessions").mkdir(parents=True)

    # Act
    rc = main([
        "--project-dir", str(tmp_path),
        "--scope", "2026-06-03",
        "--fill", _artifact_relpath("retrospective", "2026-06-03-auto-retro.md"),
    ])

    # Assert
    assert rc == 2
    assert filled.read_text(encoding="utf-8") == original


def test_fill_mode_rejects_missing_skeleton(tmp_path):
    # Arrange
    _write_session(tmp_path, {"workLog": ["work"]})

    # Act
    rc = main([
        "--project-dir", str(tmp_path),
        "--scope", "2026-06-03",
        "--fill", _artifact_relpath("retrospective", "missing-auto-retro.md"),
    ])

    # Assert
    assert rc == 2
    assert not (tmp_path / ("." + "agents") / "retrospective" / "missing-auto-retro.md").exists()


def test_integration_subprocess_writes_file(tmp_path):
    # Arrange
    _write_session(tmp_path, {"workLog": ["sub work"]})

    # Act: exercise the real process boundary.
    result = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--project-dir",
            str(tmp_path),
            "--scope",
            "sub",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Assert
    assert result.returncode == 0
    out_path = Path(result.stdout.strip())
    assert out_path.is_file()
    assert out_path.name == f"{_today()}-sub.md"


# --- Error paths: ADR-035 exit codes ----------------------------------------


def test_cli_returns_two_for_bad_project_dir(tmp_path):
    # Arrange: a path that is not a directory.
    not_a_dir = tmp_path / "missing"

    # Act
    rc = main(["--project-dir", str(not_a_dir)])

    # Assert
    assert rc == 2


def test_cli_returns_three_when_gather_fails(tmp_path, monkeypatch):
    # Arrange: force the evidence gather to raise so the boundary handler runs.
    (tmp_path / ("." + "agents") / "sessions").mkdir(parents=True)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("gather exploded")

    monkeypatch.setattr(_mod, "gather_evidence", _boom)

    # Act
    rc = main(["--project-dir", str(tmp_path), "--scope", "boom"])

    # Assert
    assert rc == 3


def test_cli_returns_three_when_write_fails(tmp_path, monkeypatch):
    # Arrange: a real session, but writing the artifact raises OSError.
    _write_session(tmp_path, {"workLog": ["work"]})

    real_write = Path.write_text

    def _fail_write(self, *args, **kwargs):
        if self.suffix == ".md":
            raise OSError("disk full")
        return real_write(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _fail_write)

    # Act
    rc = main(["--project-dir", str(tmp_path), "--scope", "nowrite"])

    # Assert
    assert rc == 3


def test_cli_output_override_writes_to_explicit_path(tmp_path):
    # Arrange
    _write_session(tmp_path, {"workLog": ["work"]})
    target = tmp_path / "custom" / "my-retro.md"

    # Act
    rc = main([
        "--project-dir", str(tmp_path),
        "--scope", "custom",
        "--output", str(target),
    ])

    # Assert
    assert rc == 0
    assert target.is_file()


def test_cli_allows_artifact_root_override_outside_project(tmp_path, monkeypatch):
    # Arrange: packaged consumers can redirect generated artifacts outside cwd.
    artifact_root = tmp_path.parent / "artifact-root"
    monkeypatch.setenv("AI_AGENTS_ARTIFACT_ROOT", str(artifact_root))

    # Act
    rc = main(["--project-dir", str(tmp_path), "--scope", "2026-06-03"])

    # Assert
    assert rc == 0
    written = artifact_root / "retrospective" / "2026-06-03-2026-06-03.md"
    assert written.is_file()


def test_blank_artifact_root_override_behaves_unset(tmp_path, monkeypatch):
    # Arrange
    monkeypatch.setenv("AI_AGENTS_ARTIFACT_ROOT", "   ")

    # Act
    rc = main(["--project-dir", str(tmp_path), "--scope", "2026-06-03"])

    # Assert
    assert rc == 0
    assert (tmp_path / ("." + "agents") / "retrospective" / "2026-06-03-2026-06-03.md").is_file()


def test_fill_mode_artifact_root_accepts_project_style_relative_path(tmp_path, monkeypatch):
    # Arrange
    artifact_root = tmp_path.parent / f"artifact-root-fill-{_MODULE_NAME}"
    monkeypatch.setenv("AI_AGENTS_ARTIFACT_ROOT", str(artifact_root))
    retro_dir = artifact_root / "retrospective"
    retro_dir.mkdir(parents=True)
    skeleton = retro_dir / "2026-06-03-auto-retro.md"
    skeleton.write_text("# Retrospective\n\n> UNFILLED SKELETON\n", encoding="utf-8")

    # Act
    rc = main([
        "--project-dir", str(tmp_path),
        "--scope", "2026-06-03",
        "--fill", _artifact_relpath("retrospective", "2026-06-03-auto-retro.md"),
    ])

    # Assert
    assert rc == 0
    assert "UNFILLED SKELETON" not in skeleton.read_text(encoding="utf-8")


def test_cli_rejects_output_override_outside_project(tmp_path):
    # Arrange
    _write_session(tmp_path, {"workLog": ["work"]})
    target = tmp_path.parent / "outside-retro.md"

    # Act
    rc = main([
        "--project-dir", str(tmp_path),
        "--scope", "escape",
        "--output", str(target),
    ])

    # Assert
    assert rc == 2
    assert not target.exists()


def test_cli_rejects_relative_output_traversal(tmp_path):
    # Arrange
    _write_session(tmp_path, {"workLog": ["work"]})
    target = tmp_path.parent / "escape.md"

    # Act
    rc = main([
        "--project-dir", str(tmp_path),
        "--scope", "escape",
        "--output", "../escape.md",
    ])

    # Assert
    assert rc == 2
    assert not target.exists()


def test_cli_rejects_fill_path_outside_project(tmp_path):
    # Arrange
    _write_session(tmp_path, {"workLog": ["work"]})
    outside = tmp_path.parent / "2026-06-03-auto-retro.md"
    outside.write_text("# Retrospective\n", encoding="utf-8")

    # Act
    rc = main([
        "--project-dir", str(tmp_path),
        "--scope", "escape",
        "--fill", str(outside),
    ])

    # Assert
    assert rc == 2
    assert outside.read_text(encoding="utf-8") == "# Retrospective\n"


def test_cli_rejects_fill_path_inside_project_but_outside_retrospective(tmp_path):
    # Arrange
    _write_session(tmp_path, {"workLog": ["work"]})
    target = tmp_path / "README.md"
    target.write_text("# Existing project file\n", encoding="utf-8")

    # Act
    rc = main([
        "--project-dir", str(tmp_path),
        "--scope", "escape",
        "--fill", "README.md",
    ])

    # Assert
    assert rc == 2
    assert target.read_text(encoding="utf-8") == "# Existing project file\n"


def test_resolve_fill_rejects_escape_before_existence_probe(tmp_path, monkeypatch):
    # Arrange
    outside = tmp_path.parent / "2026-06-03-auto-retro.md"

    def _fail_is_file(self):
        if self == outside:
            raise AssertionError("outside path was probed")
        return False

    monkeypatch.setattr(Path, "is_file", _fail_is_file)

    # Act / Assert
    try:
        _resolve_output_path(
            tmp_path / ("." + "agents") / "retrospective",
            "2026-06-03",
            "2026-06-03",
            str(outside),
            tmp_path,
        )
    except ValueError as exc:
        assert "escapes allowed root" in str(exc)
    else:
        raise AssertionError("expected escaped fill path to be rejected")


def test_resolve_output_path_for_new_artifact(tmp_path):
    # Arrange / Act
    path = _resolve_output_path(tmp_path, r"my scope/with\slash:colon", "2026-06-03", None)

    # Assert: filename separators and Windows-invalid colon are normalized.
    assert path.name == "2026-06-03-my-scope-with-slash-colon.md"


def test_resolve_output_path_for_fill_keeps_auto_retro_path(tmp_path):
    # Arrange
    skeleton = tmp_path / "2026-06-03-auto-retro.md"
    skeleton.write_text("# Retrospective\n\n> UNFILLED SKELETON\n", encoding="utf-8")

    # Act
    path = _resolve_output_path(tmp_path, "2026-06-03", "2026-06-03", str(skeleton))

    # Assert
    assert path.name == "2026-06-03-auto-retro.md"


# --- Guard: the canonical template still has the headings we mirror ---------


def test_canonical_template_still_defines_required_headings():
    # Arrange: read the reference the artifact mirrors.
    template = _TEMPLATE.read_text(encoding="utf-8")

    # Assert: every heading we assert in the artifact is defined in the
    # canonical template, so the mirror claim stays honest (canonical-source-
    # mirror rule). The "## Session Info" through "## Deduplication Check"
    # headings appear inside the fenced template block.
    for heading in _REQUIRED_HEADINGS:
        assert heading in template, f"template no longer defines: {heading}"
