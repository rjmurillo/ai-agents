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
    """Create a minimal valid canonical file under tmp/.claude/skills/review/references/."""
    canonical_dir = tmp_path / ".claude" / "skills" / "review" / "references"
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
    text = (
        "---\nname: analyst\nrole: analyst\nversion: 1.0.0\n"
        "description: y\n---\n\n# body\n"
    )
    out = gen.transform(text, "analyst")
    assert out.startswith("<!-- GENERATED -- DO NOT EDIT -->\n")
    assert "<!-- Source: .claude/skills/review/references/analyst.md -->\n" in out
    assert (
        "<!-- Run: python3 build/scripts/generate_pr_quality_prompts.py -->\n"
        in out
    )


def test_transform_emits_context_mode_header_line() -> None:
    """Issue #1981: every generated prompt MUST carry the CONTEXT_MODE header
    line so the reviewer model sees the context-mode contract. The literal
    `${CONTEXT_MODE}` placeholder stays literal in the generated artifact. The
    ai-review action prepends the resolved CONTEXT_MODE header separately at
    runtime.
    """
    text = (
        "---\nname: x\nrole: x\nversion: 1.0.0\ndescription: y\n---\n\n# body\n"
    )
    out = gen.transform(text, "x")
    assert "<!-- CONTEXT_MODE: ${CONTEXT_MODE} (full|summary|partial); " in out
    assert "PASS forbidden when not full" in out


def test_transform_context_mode_header_is_literal_not_format_expanded() -> None:
    """The `${CONTEXT_MODE}` placeholder must survive str.format intact.

    `_CI_HEADER_TEMPLATE` is consumed via `.format(role=...)`; a single-brace
    `{CONTEXT_MODE}` would raise KeyError or be expanded. Pin that the doubled
    braces render to a literal `${CONTEXT_MODE}` token.
    """
    text = (
        "---\nname: x\nrole: x\nversion: 1.0.0\ndescription: y\n---\n\n# body\n"
    )
    out = gen.transform(text, "x")
    assert "${CONTEXT_MODE}" in out
    # The pre-format escape form must NOT appear (would mean a bug).
    assert "${{CONTEXT_MODE}}" not in out


def test_transform_context_mode_header_is_idempotent() -> None:
    """The header line carries no time/env token, so two runs are identical."""
    text = (
        "---\nname: x\nrole: x\nversion: 1.0.0\ndescription: y\n---\n\n# body\n"
    )
    assert gen.transform(text, "x") == gen.transform(text, "x")


def test_transform_header_has_no_timestamp_or_sha() -> None:
    text = (
        "---\nname: x\nrole: x\nversion: 1.0.0\ndescription: y\n---\n\n# body\n"
    )
    out1 = gen.transform(text, "qa")
    out2 = gen.transform(text, "qa")
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


def test_transform_residual_frontmatter_block_emitted() -> None:
    """When stripping required keys leaves residual non-required keys, the
    transform emits a `---\\n<residual>\\n---` block. PR #1965 critic
    Finding 14: this branch was unreachable in production canonical files.
    """
    text = dedent(
        """\
        ---
        name: foo
        role: foo
        version: 1.0.0
        description: x
        custom: keep_me
        another: also_keep
        ---

        body content
        """
    )
    out = gen.transform(text, "foo")
    # Residual frontmatter block survives.
    assert "custom: keep_me" in out
    assert "another: also_keep" in out
    # And it's wrapped in --- delimiters.
    assert "---\n" in out
    # Stripped keys are gone.
    assert "name: foo" not in out
    assert "role: foo" not in out


def test_transform_rejects_missing_frontmatter() -> None:
    # PR #1965 cluster X1 (loQ): canonical files MUST have frontmatter.
    # Skipping validation when frontmatter is absent let malformed files
    # produce CI prompts with no provenance metadata.
    with pytest.raises(gen.GeneratePromptsError, match="no frontmatter"):
        gen.transform("# Just a body\n", "x")


def test_transform_rejects_missing_required_keys() -> None:
    # Frontmatter present but missing one of name/role/version/description.
    text = "---\nname: x\nrole: x\n---\n\nbody\n"
    with pytest.raises(gen.GeneratePromptsError, match="missing required frontmatter"):
        gen.transform(text, "x")


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


def test_regenerate_rejects_symlinks_in_canonical_dir(tmp_path: Path) -> None:
    """CWE-22 hardening: a symlink in the canonical dir is a config error.

    A malicious symlink could redirect read_text outside the repo. The
    generator must refuse to process them rather than silently following
    the link.
    """
    canonical = tmp_path / "canonical"
    canonical.mkdir()
    real_target = tmp_path / "outside.md"
    real_target.write_text(
        "---\nname: x\nrole: x\nversion: 1.0.0\ndescription: y\n---\nbody\n",
        encoding="utf-8",
    )
    link = canonical / "evil.md"
    link.symlink_to(real_target)
    code, log = gen.regenerate(canonical, tmp_path / "out", dry_run=False)
    assert code == 2
    assert any("config_error" in line for line in log)
    assert any("symlink" in line.lower() for line in log), (
        "drift output should mention symlink rejection"
    )


def test_regenerate_symlinked_dest_no_status_written_log(
    stub_canonical: Path, tmp_path: Path
) -> None:
    """Symlinked output dest -> config_error AND no status=written follow-up.

    PR #1965 cursor 6hZB / devin 6hua: the GeneratePromptsError handler in
    the write path was missing a `continue`, so a role hitting the symlink
    rejection logged BOTH `status=config_error` and `status=written`. The
    log lied: no file was written because _atomic_write raised before
    os.replace. Pin the contract: never log status=written for a role that
    failed with config_error.
    """
    generated = tmp_path / "out"
    generated.mkdir()
    # Plant a symlink at the destination of the first stubbed role.
    role = sorted(p.stem for p in stub_canonical.iterdir())[0]
    dest = generated / f"pr-quality-gate-{role}.md"
    real = tmp_path / "elsewhere.md"
    real.write_text("decoy\n", encoding="utf-8")
    dest.symlink_to(real)

    code, log = gen.regenerate(stub_canonical, generated, dry_run=False)

    assert code == 2
    role_lines = [line for line in log if line.startswith(f"role={role} ")]
    assert any("status=config_error" in line for line in role_lines), (
        f"expected role={role} status=config_error, got {role_lines}"
    )
    assert not any("status=written" in line for line in role_lines), (
        f"role={role} must NOT log status=written after config_error; "
        f"got {role_lines}"
    )


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
    canonical = tmp_path / ".claude" / "skills" / "review" / "references"
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
    canonical = tmp_path / ".claude" / "skills" / "review" / "references"
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


# ---------------------------------------------------------------------------
# CI wrapper (run_drift_check_ci.py)
# ---------------------------------------------------------------------------

import importlib.util  # noqa: E402

_CI_WRAPPER = REPO_ROOT / "build" / "scripts" / "run_drift_check_ci.py"


def _load_wrapper():
    spec = importlib.util.spec_from_file_location(
        "run_drift_check_ci", _CI_WRAPPER
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_ci_wrapper_exists() -> None:
    assert _CI_WRAPPER.is_file()


def test_ci_wrapper_returns_two_when_generator_missing(
    tmp_path: Path,
) -> None:
    wrapper = _load_wrapper()
    assert wrapper.run(tmp_path / "does-not-exist.py") == 2


def test_ci_wrapper_format_summary_clean() -> None:
    wrapper = _load_wrapper()
    summary = wrapper._format_summary(0, "")
    assert "No drift detected" in summary


def test_ci_wrapper_format_summary_drift_includes_diff() -> None:
    wrapper = _load_wrapper()
    summary = wrapper._format_summary(1, "--- old\n+++ new\n+changed line\n")
    assert "Drift detected" in summary
    assert "+changed line" in summary
    assert "```diff" in summary


def test_ci_wrapper_format_summary_config_error() -> None:
    wrapper = _load_wrapper()
    summary = wrapper._format_summary(2, "config error message")
    assert "config error" in summary
    assert "code 2" in summary


def test_ci_wrapper_writes_step_summary_when_env_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    wrapper = _load_wrapper()
    wrapper._write_step_summary("## Test\n\nbody\n")
    assert summary_file.read_text(encoding="utf-8") == "## Test\n\nbody\n"


def test_ci_wrapper_step_summary_noop_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    wrapper = _load_wrapper()
    # Must not raise; just no-op.
    wrapper._write_step_summary("## ignored\n")


def test_ci_wrapper_propagates_config_error_exit_two(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Wrapper must return exit code 2 distinctly when generator returns 2.

    PR #1965 cluster D: collapsing config error (2) to drift (1) makes it
    impossible for CI to distinguish a fixable drift from a broken setup.
    """
    wrapper = _load_wrapper()
    # Stub generator path: a python script that exits 2.
    fake_gen = tmp_path / "fake_generator.py"
    fake_gen.write_text("import sys; print('config error stub'); sys.exit(2)\n")
    code = wrapper.run(fake_gen)
    assert code == 2


def test_ci_wrapper_returns_one_on_drift_exit(
    tmp_path: Path,
) -> None:
    """Wrapper returns 1 (and only 1) when generator reports drift."""
    wrapper = _load_wrapper()
    fake_gen = tmp_path / "fake_generator.py"
    fake_gen.write_text("import sys; print('drift stub'); sys.exit(1)\n")
    assert wrapper.run(fake_gen) == 1


def test_ci_wrapper_handles_subprocess_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wrapper maps subprocess.TimeoutExpired to exit 2 with annotation.

    PR #1965 round-6: previously a hung generator bypassed the ADR-035
    exit contract and emitted no step summary.
    """
    wrapper = _load_wrapper()
    fake_gen = tmp_path / "fake_generator.py"
    fake_gen.write_text("# does not matter; subprocess.run is mocked\n")

    def _boom(*args, **kwargs):
        raise __import__("subprocess").TimeoutExpired(cmd="python3", timeout=60)

    monkeypatch.setattr(wrapper.subprocess, "run", _boom)
    assert wrapper.run(fake_gen) == 2


def test_ci_wrapper_handles_oserror_from_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OSError from subprocess.run maps to exit 2 (env error)."""
    wrapper = _load_wrapper()
    fake_gen = tmp_path / "fake_generator.py"
    fake_gen.write_text("# does not matter; subprocess.run is mocked\n")

    def _boom(*args, **kwargs):
        raise OSError("simulated subprocess failure")

    monkeypatch.setattr(wrapper.subprocess, "run", _boom)
    assert wrapper.run(fake_gen) == 2


def test_dry_run_compares_against_head_not_working_tree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Drift check must compare against HEAD-committed content (REQ-008-03).

    PR #1965 cluster C: a developer who regenerates prompts but forgets to
    stage/commit will have a clean working tree. The hook would pass while
    pushing stale committed content. The fix reads dest from `git show
    HEAD:path`, not from the filesystem.

    This test verifies the read-from-HEAD path by stubbing the helper and
    asserting it is consulted before the filesystem fallback.
    """
    canonical = tmp_path / ".claude" / "skills" / "review" / "references"
    canonical.mkdir(parents=True)
    (canonical / "x.md").write_text(
        "---\nname: x\nrole: x\nversion: 1.0.0\ndescription: y\n---\nbody\n",
        encoding="utf-8",
    )
    generated = tmp_path / ".github" / "prompts"
    generated.mkdir(parents=True)
    # Working tree has matching content (would pass if hook used working tree).
    expected = gen.transform(
        (canonical / "x.md").read_text(encoding="utf-8"), "x"
    )
    (generated / "pr-quality-gate-x.md").write_text(expected, encoding="utf-8")

    # But HEAD has stale content. Stub _read_committed_dest to return stale.
    monkeypatch.setattr(gen, "_read_committed_dest", lambda dest: "stale\n")

    code, log = gen.regenerate(canonical, generated, dry_run=True)
    assert code == 1, (
        "drift check must consult HEAD via _read_committed_dest, not "
        "working tree; working tree matches but HEAD does not"
    )
    assert any("status=drift" in line for line in log)


def test_regenerate_per_file_oserror_returns_one(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """OSError during read/write must surface as exit 1 (logic), not crash.

    PR #1965 round-6: previously regenerate() let exceptions bubble,
    bypassing the ADR-035 exit contract.
    """
    canonical = tmp_path / ".claude" / "skills" / "review" / "references"
    canonical.mkdir(parents=True)
    (canonical / "x.md").write_text(
        "---\nname: x\nrole: x\nversion: 1.0.0\ndescription: y\n---\nbody\n",
        encoding="utf-8",
    )
    generated = tmp_path / "out"

    # Force read to raise OSError.
    original_read = Path.read_text

    def _bad_read(self, *args, **kwargs):
        if self.name == "x.md":
            raise OSError("simulated read failure")
        return original_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _bad_read)
    code, log = gen.regenerate(canonical, generated, dry_run=False)
    assert code == 1
    assert any("io_error" in line for line in log)


def test_regenerate_malformed_frontmatter_returns_two(
    tmp_path: Path,
) -> None:
    """A canonical with no frontmatter must surface as exit 2 (config error).

    Confirms transform()'s GeneratePromptsError is caught in regenerate()
    and converted to exit 2, not allowed to crash.
    """
    canonical = tmp_path / ".claude" / "skills" / "review" / "references"
    canonical.mkdir(parents=True)
    (canonical / "x.md").write_text("# no frontmatter\n", encoding="utf-8")
    generated = tmp_path / "out"
    code, log = gen.regenerate(canonical, generated, dry_run=False)
    assert code == 2
    assert any("config_error" in line for line in log)


def test_dry_run_falls_back_to_working_tree_when_git_unavailable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When git/HEAD is unavailable, fall back to working tree comparison.

    Keeps pytest tmp_path fixtures functional outside a git repo.
    """
    canonical = tmp_path / ".claude" / "skills" / "review" / "references"
    canonical.mkdir(parents=True)
    (canonical / "x.md").write_text(
        "---\nname: x\nrole: x\nversion: 1.0.0\ndescription: y\n---\nbody\n",
        encoding="utf-8",
    )
    generated = tmp_path / "out"
    generated.mkdir()

    monkeypatch.setattr(gen, "_read_committed_dest", lambda dest: None)

    expected = gen.transform(
        (canonical / "x.md").read_text(encoding="utf-8"), "x"
    )
    (generated / "pr-quality-gate-x.md").write_text(expected, encoding="utf-8")

    code, log = gen.regenerate(canonical, generated, dry_run=True)
    assert code == 0, "fallback to working tree should pass when content matches"
