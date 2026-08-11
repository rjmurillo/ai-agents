"""Tests for the ai-review context builder split."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT_PATH = _REPO_ROOT / "scripts/ci/build_ai_review_context.py"
_OUTPUTS_MODULE_PATH = _REPO_ROOT / "scripts/ai_review_outputs.py"


def test_ci_entrypoint_no_longer_needs_file_size_ignore():
    """Issue #4597: the entrypoint must not carry a file-size escape hatch."""

    source = _SCRIPT_PATH.read_text(encoding="utf-8")

    assert "taste-lint: ignore file-size" not in source


def test_ci_entrypoint_stays_below_taste_file_size_cap():
    """Issue #4597: editing this script should not require a split first."""

    source = _SCRIPT_PATH.read_text(encoding="utf-8")

    assert len(source.splitlines()) <= 800


def test_output_helpers_are_extracted_from_ci_entrypoint():
    """Issue #4597: output writing is a cohesive seam outside scripts/ci."""

    entrypoint_source = _SCRIPT_PATH.read_text(encoding="utf-8")
    outputs_source = _OUTPUTS_MODULE_PATH.read_text(encoding="utf-8")

    assert 'import_module("ai_review_outputs")' in entrypoint_source
    assert "def write_outputs(" not in entrypoint_source
    assert "def append_multiline_output(" in outputs_source



def _import_outputs():
    """Import the outputs module fresh, with no prior entrypoint pollution."""
    import importlib.util
    import sys

    mod_name = "ai_review_outputs"
    # Remove cached versions
    sys.modules.pop(mod_name, None)
    sys.modules.pop("build_ai_review_context", None)

    spec = importlib.util.spec_from_file_location(mod_name, _OUTPUTS_MODULE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def _import_entrypoint():
    """Import the entrypoint module."""
    import importlib.util
    import sys

    mod_name = "build_ai_review_context"
    sys.modules.pop(mod_name, None)

    spec = importlib.util.spec_from_file_location(mod_name, _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_outputs_raises_exact_output_config_error(monkeypatch):
    """write_outputs must raise OutputConfigError, not a mutable alias type."""
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    outputs = _import_outputs()

    class FakeContext:
        text = "test"
        mode = "test"
        infrastructure_failure = False

    with __import__("pytest").raises(outputs.OutputConfigError) as exc_info:
        outputs.write_outputs(FakeContext())
    assert type(exc_info.value) is outputs.OutputConfigError


def test_entrypoint_import_does_not_change_outputs_exception_type(monkeypatch):
    """Importing the entrypoint must not mutate the outputs module exception."""
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    outputs = _import_outputs()
    original_type = outputs.OutputConfigError

    # Now import entrypoint (which previously mutated outputs)
    _import_entrypoint()

    class FakeContext:
        text = "test"
        mode = "test"
        infrastructure_failure = False

    with __import__("pytest").raises(original_type) as exc_info:
        outputs.write_outputs(FakeContext())
    # Must be EXACTLY OutputConfigError, not a substituted type
    assert type(exc_info.value) is original_type


def test_main_maps_config_error_to_exit_2(monkeypatch):
    """ConfigError from context building must produce exit code 2."""
    monkeypatch.setenv("CONTEXT_TYPE", "nonexistent-type")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")

    entrypoint = _import_entrypoint()
    result = entrypoint.main()
    assert result == 2


def test_main_maps_output_config_error_to_exit_2(monkeypatch, tmp_path):
    """OutputConfigError from write_outputs must produce exit code 2."""
    monkeypatch.setenv("CONTEXT_TYPE", "issue")
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    monkeypatch.setenv("ISSUE_NUMBER", "1")
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)

    # Stub gh to return valid issue data
    import subprocess
    original_run = subprocess.run

    def fake_run(cmd, **kwargs):
        if isinstance(cmd, list) and "gh" in cmd[0]:
            import json
            return subprocess.CompletedProcess(
                cmd, 0,
                stdout=json.dumps({"number": 1, "title": "t", "body": "b"}),
                stderr="",
            )
        return original_run(cmd, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)

    entrypoint = _import_entrypoint()
    result = entrypoint.main()
    # OutputConfigError from missing GITHUB_OUTPUT -> exit 2
    assert result == 2


def test_outputs_module_has_no_mutable_exception_alias():
    """No module-level attribute can serve as a mutable exception type alias.

    Mutation guard: reintroducing ``EXCEPTION_TYPE = OutputConfigError``
    (or any name) would be caught by this test.
    """
    outputs = _import_outputs()
    for name in dir(outputs):
        obj = getattr(outputs, name)
        if (
            isinstance(obj, type)
            and issubclass(obj, Exception)
            and obj is not outputs.OutputConfigError
            and name.isupper()
        ):
            __import__("pytest").fail(
                f"Mutable exception alias found: {name} = {obj.__name__}"
            )
        # Check for type[Exception] attributes (the original pattern)
        if name != "OutputConfigError" and obj is outputs.OutputConfigError:
            if name not in ("__class__",):
                __import__("pytest").fail(
                    f"Aliased OutputConfigError found as {name}"
                )


# --- Tests for gh_retry_helpers extraction (issue #4597) ---

_GH_RETRY_MODULE_PATH = _REPO_ROOT / "scripts/gh_retry_helpers.py"


def test_gh_retry_helpers_stays_below_taste_file_size_cap():
    """Issue #4597: extracted module must not itself exceed the 500-line cap."""
    source = _GH_RETRY_MODULE_PATH.read_text(encoding="utf-8")
    assert len(source.splitlines()) <= 500


def test_gh_retry_helpers_are_extracted_from_ci_entrypoint():
    """Issue #4597: GH retry/invoke helpers live in a separate module."""
    entrypoint_source = _SCRIPT_PATH.read_text(encoding="utf-8")
    gh_retry_source = _GH_RETRY_MODULE_PATH.read_text(encoding="utf-8")

    # The entrypoint imports from the module rather than defining inline
    assert "from gh_retry_helpers import" in entrypoint_source
    assert "def run_gh(" not in entrypoint_source
    assert "def _invoke_gh_once(" not in entrypoint_source
    assert "def _retry_delay(" not in entrypoint_source

    # The extracted module defines these functions
    assert "def run_gh(" in gh_retry_source
    assert "def _invoke_gh_once(" in gh_retry_source
    assert "def _retry_delay(" in gh_retry_source


def test_ci_entrypoint_under_500_lines():
    """Issue #4597: the entrypoint must stay at or below the 500-line taste-lint cap."""
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert len(source.splitlines()) <= 500
