"""Tests for build/scripts/generate_pr_quality_prompts.py.

Coverage targets per REQ-008-07:
- (a) idempotency: running twice produces zero diff
- (b) partial-write recovery: failure mid-write leaves no corrupt output
- (c) schema/filename validation: invalid filename, missing canonical dir
- (d) transform: frontmatter strip, header prepend, body unchanged
- (e) dry-run: clean exit 0, drift exit 1 with diff
- (f) exit codes per ADR-035

Refs #1934.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from textwrap import dedent

import pytest

# Make build/scripts importable.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import generate_pr_quality_prompts as gen  # noqa: E402


@pytest.fixture
def stub_canonical(tmp_path: Path) -> Path:
    """Create a minimal valid canonical file under tmp/.claude/review-axes/."""
    canonical_dir = tmp_path / ".claude" / "review-axes"
    canonical_dir.mkdir(parents=True)
    file = canonical_dir / "example.md"
    file.write_text(
        dedent(
            """\
            ---
            name: example
            role: example
            version: 1.0.0
            description: A test axis
            ---

            # Example Axis

            ## Grounding Rules

            Test rule.

            ## Analysis Focus Areas

            Test area.

            ## Output Schema

            verdict: PASS|WARN|CRITICAL_FAIL|UNKNOWN
            severity: HIGH|LOW
            category: test
            location: file:line
            recommendation: do thing
            """
        ),
        encoding="utf-8",
        newline="\n",
    )
    return canonical_dir


# ---------------------------------------------------------------------------
# transform()
# ---------------------------------------------------------------------------


def test_transform_strips_required_frontmatter_keys() -> None:
    text = dedent(
        """\
        ---
        name: foo
        role: foo
        version: 1.0.0
        description: x
        ---

        # Body
        """
    )
    out = gen.transform(text, "foo")
    assert "name: foo" not in out
    assert "role: foo" not in out
    assert "version: 1.0.0" not in out
    assert "description: x" not in out
    assert "# Body" in out


def test_transform_prepends_static_ci_header() -> None:
    out = gen.transform("# body\n", "analyst")
    assert out.startswith("<!-- GENERATED -- DO NOT EDIT -->\n")
    assert "<!-- Source: .claude/review-axes/analyst.md -->\n" in out
    assert (
        "<!-- Run: python3 build/scripts/generate_pr_quality_prompts.py -->\n"
        in out
    )


def test_transform_header_has_no_timestamp_or_sha() -> None:
    out1 = gen.transform("# body\n", "qa")
    out2 = gen.transform("# body\n", "qa")
    assert out1 == out2  # idempotent: same input -> same output every time


def test_transform_preserves_body_verbatim() -> None:
    body = "# Title\n\nLine 1.\nLine 2.\n```python\ncode\n```\n"
    text = f"---\nname: x\nrole: x\nversion: 1.0.0\ndescription: x\n---\n\n{body}"
    out = gen.transform(text, "x")
    assert body in out


def test_transform_preserves_unstripped_frontmatter_keys() -> None:
    text = dedent(
        """\
        ---
        name: foo
        role: foo
        version: 1.0.0
        description: x
        custom: keep_me
        ---

        body
        """
    )
    out = gen.transform(text, "foo")
    assert "custom: keep_me" in out


def test_transform_handles_no_frontmatter() -> None:
    out = gen.transform("# Just a body\n", "x")
    assert "# Just a body" in out
    assert out.startswith("<!-- GENERATED")


# ---------------------------------------------------------------------------
# regenerate() - happy paths
# ---------------------------------------------------------------------------


def test_regenerate_writes_files_atomically(stub_canonical: Path) -> None:
    generated = stub_canonical.parent.parent.parent / "out"
    code, log = gen.regenerate(stub_canonical, generated, dry_run=False)
    assert code == 0
    assert (generated / "pr-quality-gate-example.md").exists()
    assert any("status=written" in line for line in log)


def test_regenerate_is_idempotent(stub_canonical: Path) -> None:
    generated = stub_canonical.parent.parent.parent / "out"
    gen.regenerate(stub_canonical, generated, dry_run=False)
    out_path = generated / "pr-quality-gate-example.md"
    first = out_path.read_text(encoding="utf-8")
    gen.regenerate(stub_canonical, generated, dry_run=False)
    second = out_path.read_text(encoding="utf-8")
    assert first == second  # zero diff on re-run


def test_regenerate_dry_run_clean_returns_zero(stub_canonical: Path) -> None:
    generated = stub_canonical.parent.parent.parent / "out"
    gen.regenerate(stub_canonical, generated, dry_run=False)
    code, log = gen.regenerate(stub_canonical, generated, dry_run=True)
    assert code == 0
    assert any("status=ok" in line for line in log)


def test_regenerate_dry_run_drift_returns_one(stub_canonical: Path) -> None:
    generated = stub_canonical.parent.parent.parent / "out"
    generated.mkdir(parents=True, exist_ok=True)
    # Write stale content to trigger drift.
    (generated / "pr-quality-gate-example.md").write_text(
        "stale content\n", encoding="utf-8"
    )
    code, log = gen.regenerate(stub_canonical, generated, dry_run=True)
    assert code == 1
    assert any("status=drift" in line for line in log)


# ---------------------------------------------------------------------------
# regenerate() - error paths (exit codes per ADR-035)
# ---------------------------------------------------------------------------


def test_regenerate_missing_canonical_dir_returns_two(tmp_path: Path) -> None:
    code, log = gen.regenerate(
        tmp_path / "does-not-exist", tmp_path / "out", dry_run=False
    )
    assert code == 2
    assert any("config_error" in line for line in log)


def test_regenerate_empty_canonical_dir_returns_two(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    code, log = gen.regenerate(canonical, tmp_path / "out", dry_run=False)
    assert code == 2
    assert any("config_error" in line for line in log)


def test_regenerate_invalid_filename_returns_two(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    (canonical / "BadName.md").write_text("# x\n", encoding="utf-8")
    code, _ = gen.regenerate(canonical, tmp_path / "out", dry_run=False)
    assert code == 2


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_atomic_write_creates_file(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    gen._atomic_write(target, "hello\n")
    assert target.read_text(encoding="utf-8") == "hello\n"


def test_atomic_write_uses_lf_only(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    gen._atomic_write(target, "line1\nline2\n")
    raw = target.read_bytes()
    assert b"\r\n" not in raw  # LF only, no CRLF


def test_atomic_write_replaces_existing(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    target.write_text("old\n", encoding="utf-8")
    gen._atomic_write(target, "new\n")
    assert target.read_text(encoding="utf-8") == "new\n"


def test_atomic_write_preserves_prior_on_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If write crashes mid-way, the original file is untouched.

    Simulated by patching os.replace to raise after the tmp file is written.
    """
    target = tmp_path / "out.md"
    target.write_text("original\n", encoding="utf-8")

    def boom(*_args, **_kwargs) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr(gen.os, "replace", boom)
    with pytest.raises(OSError):
        gen._atomic_write(target, "new\n")
    assert target.read_text(encoding="utf-8") == "original\n"


# ---------------------------------------------------------------------------
# Filename validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "analyst.md",
        "ai-architect.md",
        "qa_v2.md",
        "a.md",
    ],
)
def test_validate_filename_accepts_valid(name: str) -> None:
    gen._validate_filename(name)  # no raise


@pytest.mark.parametrize(
    "name",
    [
        "Analyst.md",  # uppercase
        ".md",  # no stem
        "1.md",  # leading digit
        "axis.txt",  # wrong extension
        "axis.md.bak",  # extra suffix
        "no_extension",  # no extension
    ],
)
def test_validate_filename_rejects_invalid(name: str) -> None:
    with pytest.raises(gen.GeneratePromptsError):
        gen._validate_filename(name)


# ---------------------------------------------------------------------------
# main() exit code wiring
# ---------------------------------------------------------------------------


def test_main_dry_run_clean_exit_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end: main() returns 0 on a clean dry-run."""
    canonical = tmp_path / ".claude" / "review-axes"
    canonical.mkdir(parents=True)
    (canonical / "x.md").write_text(
        "---\nname: x\nrole: x\nversion: 1.0.0\ndescription: y\n---\nbody\n",
        encoding="utf-8",
    )
    generated = tmp_path / "out"
    monkeypatch.setattr(gen, "CANONICAL_DIR", canonical)
    monkeypatch.setattr(gen, "GENERATED_DIR", generated)
    # First write so dry-run is clean.
    assert gen.main([]) == 0
    assert gen.main(["--dry-run"]) == 0


def test_main_dry_run_drift_exit_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    canonical = tmp_path / ".claude" / "review-axes"
    canonical.mkdir(parents=True)
    (canonical / "x.md").write_text(
        "---\nname: x\nrole: x\nversion: 1.0.0\ndescription: y\n---\nbody\n",
        encoding="utf-8",
    )
    generated = tmp_path / "out"
    generated.mkdir()
    (generated / "pr-quality-gate-x.md").write_text(
        "stale\n", encoding="utf-8"
    )
    monkeypatch.setattr(gen, "CANONICAL_DIR", canonical)
    monkeypatch.setattr(gen, "GENERATED_DIR", generated)
    assert gen.main(["--dry-run"]) == 1
