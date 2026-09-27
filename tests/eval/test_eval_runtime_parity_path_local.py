"""Tests for the `path_local` and `cwd` fixture fields (SPEC-4880 T7, REQ-9).

Covers the evaluator's own capability, not the three shipped fixtures in
`scripts/eval/examples/path-local-parity-fixtures.json` (T8, covered by the
`--dry-run` control check in `scripts/eval/README.md` and CI). Sections:
loading and validation, install location, ref resolution, cwd handling, and
the Copilot listing preflight's expected set.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest import mock

import pytest

from tests.eval._runtime_parity_test_support import (
    FIXTURES,
    FixedResponseRunner,
    corpus_with_instructions,
    parity,
    runtime_harness,
    runtime_parity,
)

REPO_ROOT = runtime_parity.REPO_ROOT


def _corpus(tmp_path: Path, overrides: dict[str, object]) -> Path:
    """Build a one-fixture corpus from the stock "resume-phase-3" fixture.

    Unlike `corpus_with_instructions`, `overrides` is written verbatim, so a
    negative test can inject a malformed `path_local` or `cwd` value that the
    loader itself must reject.
    """
    source = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixture = dict(source["fixtures"][0])
    fixture.update(overrides)
    path = tmp_path / "fixtures.json"
    path.write_text(json.dumps({"schema_version": 1, "fixtures": [fixture]}), encoding="utf-8")
    return path


# --- Loading and validation (REQ-9) -----------------------------------------


def test_path_local_and_cwd_default_when_omitted(tmp_path: Path) -> None:
    """REQ-9: a fixture with neither field loads with the pre-#4880 shape."""
    path = _corpus(tmp_path, {})

    fixture = runtime_parity.load_fixtures(path)[0]

    assert fixture.path_local == ()
    assert fixture.cwd == "."


def test_path_local_parses_repository_relative_paths(tmp_path: Path) -> None:
    """REQ-9: `path_local` accepts a list of repo-relative file paths."""
    path = _corpus(
        tmp_path,
        {"path_local": ["AGENTS.md", ".github/AGENTS.md"], "cwd": ".github/workflows"},
    )

    fixture = runtime_parity.load_fixtures(path)[0]

    assert fixture.path_local == ("AGENTS.md", ".github/AGENTS.md")
    assert fixture.cwd == ".github/workflows"


def test_path_local_rejects_non_string_items(tmp_path: Path) -> None:
    path = _corpus(tmp_path, {"path_local": ["AGENTS.md", 7]})

    with pytest.raises(runtime_parity.ParityConfigError, match="must be an array of strings"):
        runtime_parity.load_fixtures(path)


def test_path_local_rejects_a_non_list_value(tmp_path: Path) -> None:
    path = _corpus(tmp_path, {"path_local": "AGENTS.md"})

    with pytest.raises(runtime_parity.ParityConfigError, match="must be an array of strings"):
        runtime_parity.load_fixtures(path)


def test_path_local_rejects_duplicate_paths(tmp_path: Path) -> None:
    """Unlike `instructions`, a duplicate is exact-string, not basename."""
    path = _corpus(tmp_path, {"path_local": ["AGENTS.md", "AGENTS.md"]})

    with pytest.raises(runtime_parity.ParityConfigError, match="duplicate paths"):
        runtime_parity.load_fixtures(path)


def test_path_local_allows_two_files_sharing_a_basename(tmp_path: Path) -> None:
    """Unlike `instructions`, "AGENTS.md" and ".github/AGENTS.md" do not collide."""
    path = _corpus(tmp_path, {"path_local": ["AGENTS.md", ".github/AGENTS.md"]})

    fixture = runtime_parity.load_fixtures(path)[0]

    assert fixture.path_local == ("AGENTS.md", ".github/AGENTS.md")


def test_path_local_rejects_a_path_escaping_the_repository_root(tmp_path: Path) -> None:
    path = _corpus(tmp_path, {"path_local": ["../outside.md"]})

    with pytest.raises(runtime_parity.ParityConfigError, match="escapes the repository root"):
        runtime_parity.load_fixtures(path)


def test_cwd_rejects_an_absolute_path(tmp_path: Path) -> None:
    path = _corpus(tmp_path, {"cwd": "/etc"})

    with pytest.raises(
        runtime_parity.ParityConfigError, match="must stay inside the fixture workspace"
    ):
        runtime_parity.load_fixtures(path)


def test_cwd_rejects_a_parent_traversal(tmp_path: Path) -> None:
    path = _corpus(tmp_path, {"cwd": "../escape"})

    with pytest.raises(
        runtime_parity.ParityConfigError, match="must stay inside the fixture workspace"
    ):
        runtime_parity.load_fixtures(path)


def test_cwd_rejects_a_non_string_value(tmp_path: Path) -> None:
    path = _corpus(tmp_path, {"cwd": 7})

    with pytest.raises(runtime_parity.ParityConfigError, match="non-empty string"):
        runtime_parity.load_fixtures(path)


# --- Install location (REQ-9) ------------------------------------------------


def _installed(fixture: runtime_parity.Fixture, ref: str | None = None) -> dict[str, bytes]:
    return runtime_parity.resolve_instructions(fixture.path_local, ref)


def test_prepare_workspace_installs_path_local_for_claude(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(
        tmp_path, default_instructions=False, path_local=["AGENTS.md"]
    )
    fixture = runtime_parity.load_fixtures(corpus)[0]
    workspace = tmp_path / "ws-claude"

    runtime_harness.prepare_workspace(fixture, "claude", workspace, path_local=_installed(fixture))

    installed = workspace / "AGENTS.md"
    assert installed.read_bytes() == (REPO_ROOT / "AGENTS.md").read_bytes()


def test_prepare_workspace_installs_path_local_for_copilot(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(
        tmp_path, default_instructions=False, path_local=[".github/AGENTS.md"]
    )
    fixture = runtime_parity.load_fixtures(corpus)[0]
    workspace = tmp_path / "ws-copilot"

    runtime_harness.prepare_workspace(fixture, "copilot", workspace, path_local=_installed(fixture))

    installed = workspace / ".github" / "AGENTS.md"
    assert installed.read_bytes() == (REPO_ROOT / ".github" / "AGENTS.md").read_bytes()


def test_prepare_workspace_copilot_still_writes_the_sentinel_without_path_local(
    tmp_path: Path,
) -> None:
    """No `instructions` and no `path_local`: the existing leak canary still writes."""
    corpus = corpus_with_instructions(tmp_path, default_instructions=False)
    fixture = runtime_parity.load_fixtures(corpus)[0]
    workspace = tmp_path / "ws-sentinel"

    runtime_harness.prepare_workspace(fixture, "copilot", workspace)

    sentinel = workspace / ".github" / "copilot-instructions.md"
    assert runtime_harness.SENTINEL in sentinel.read_text(encoding="utf-8")


def test_prepare_workspace_copilot_skips_the_sentinel_with_path_local(
    tmp_path: Path,
) -> None:
    """A `path_local` fixture opts out of the sentinel, same as `instructions`."""
    corpus = corpus_with_instructions(
        tmp_path, default_instructions=False, path_local=["AGENTS.md"]
    )
    fixture = runtime_parity.load_fixtures(corpus)[0]
    workspace = tmp_path / "ws-no-sentinel"

    runtime_harness.prepare_workspace(fixture, "copilot", workspace, path_local=_installed(fixture))

    sentinel = workspace / ".github" / "copilot-instructions.md"
    assert not sentinel.exists()


def test_prepare_workspace_creates_the_declared_cwd_when_no_setup_files_touch_it(
    tmp_path: Path,
) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False, cwd=".github/workflows")
    fixture = runtime_parity.load_fixtures(corpus)[0]
    workspace = tmp_path / "ws-cwd"

    runtime_harness.prepare_workspace(fixture, "claude", workspace)

    assert (workspace / ".github" / "workflows").is_dir()


def test_prepare_workspace_defaults_cwd_to_the_workspace_root(tmp_path: Path) -> None:
    corpus = corpus_with_instructions(tmp_path, default_instructions=False)
    fixture = runtime_parity.load_fixtures(corpus)[0]
    workspace = tmp_path / "ws-default-cwd"

    runtime_harness.prepare_workspace(fixture, "claude", workspace)

    assert runtime_harness.resolve_cwd(workspace, fixture.cwd) == workspace.resolve()


# --- Ref resolution (REQ-9) ---------------------------------------------------


def test_path_local_resolves_from_the_working_tree() -> None:
    resolved = runtime_parity.resolve_instructions(["AGENTS.md"], None)

    assert resolved["AGENTS.md"] == (REPO_ROOT / "AGENTS.md").read_bytes()


def test_path_local_resolves_from_a_git_ref() -> None:
    resolved = runtime_parity.resolve_instructions(["AGENTS.md"], "HEAD")

    assert resolved["AGENTS.md"] == (REPO_ROOT / "AGENTS.md").read_bytes()


def test_path_local_missing_at_a_good_ref_is_a_config_error() -> None:
    with pytest.raises(runtime_parity.ParityConfigError, match="could not resolve"):
        runtime_parity.resolve_instructions(["does/not/exist/at/head.md"], "HEAD")


def test_resolve_ablation_resolves_path_local_once_for_both_harnesses(
    tmp_path: Path,
) -> None:
    """`_resolve_ablation` (private, exercised via `run_evaluation` dry-run) records
    identical `path_local` bytes for both harnesses, since no projection applies.
    """
    corpus = corpus_with_instructions(
        tmp_path, default_instructions=False, path_local=["AGENTS.md"]
    )

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=True,
    )

    assert code == parity.EXIT_OK
    record = report["fixtures"][0]
    assert record["path_local"] == [
        {"path": "AGENTS.md", "sha256": record["path_local"][0]["sha256"]}
    ]


# --- cwd handling (REQ-9) -----------------------------------------------------


def test_resolve_cwd_resolves_relative_to_the_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    resolved = runtime_harness.resolve_cwd(workspace, ".github/workflows")

    assert resolved == (workspace / ".github" / "workflows").resolve()


def test_resolve_cwd_root_default_resolves_to_the_workspace_itself(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()

    assert runtime_harness.resolve_cwd(workspace, ".") == workspace.resolve()


def test_resolve_cwd_rejects_an_escape_defensively(tmp_path: Path) -> None:
    """The loader already rejects `..` (see above); `resolve_cwd` guards independently."""
    workspace = tmp_path / "ws"
    workspace.mkdir()

    with pytest.raises(runtime_parity.ParityConfigError, match="escapes workspace"):
        runtime_harness.resolve_cwd(workspace, "../escape")


# --- Copilot listing preflight expected set (REQ-9) --------------------------


def test_invoke_runtime_runs_the_preflight_for_a_path_local_only_fixture(
    tmp_path: Path,
) -> None:
    """`fixture.instructions` empty, `fixture.path_local` non-empty: preflight still runs."""
    corpus = corpus_with_instructions(
        tmp_path, default_instructions=False, path_local=["AGENTS.md"]
    )
    fixture = runtime_parity.load_fixtures(corpus)[0]
    runner = FixedResponseRunner("CONTINUE_PHASE_3")

    run, argv, failure, listing = parity._invoke_runtime(
        fixture,
        "copilot",
        "copilot",
        parity.DEFAULT_MODEL,
        tmp_path / "ws",
        runner,
        30,
        {},
        runtime_parity.resolve_instructions(fixture.path_local, None),
    )

    assert failure is None
    assert listing == [{"sourcePath": "AGENTS.md"}]
    assert run is not None


def test_invoke_runtime_preflight_uses_the_path_local_union_set(tmp_path: Path) -> None:
    """`_invoke_runtime` wires `path_local` into the preflight's expected set.

    A listing that omits the declared `AGENTS.md` source is a config error
    raised before the model call, which this fake runner would otherwise
    fail loudly on (`AssertionError`) if reached.
    """
    corpus = corpus_with_instructions(
        tmp_path, default_instructions=False, path_local=["AGENTS.md"]
    )
    fixture = runtime_parity.load_fixtures(corpus)[0]

    def runner(argv: list[object], **kwargs: object) -> subprocess.CompletedProcess[str]:
        args = [str(value) for value in argv]
        if args[1:4] == ["instruction", "list", "--json"]:
            return subprocess.CompletedProcess(args, 0, "[]", "")
        raise AssertionError("the model call must not run after a failed preflight")

    with pytest.raises(runtime_parity.ParityConfigError, match=r"missing=\['AGENTS\.md'\]"):
        parity._invoke_runtime(
            fixture,
            "copilot",
            "copilot",
            parity.DEFAULT_MODEL,
            tmp_path / "ws",
            runner,
            30,
            {},
            runtime_parity.resolve_instructions(fixture.path_local, None),
        )


def test_verify_listing_passes_when_it_matches_instructions_union_path_local(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    listing = [
        {"sourcePath": ".github/instructions/voice.instructions.md"},
        {"sourcePath": "AGENTS.md"},
    ]
    runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(listing), ""))
    fixture = runtime_parity.load_fixtures(FIXTURES)[0]

    result, failure = parity._verify_copilot_instruction_listing(
        fixture,
        "copilot",
        workspace,
        workspace,
        runner,
        30,
        {".github/instructions/voice.instructions.md": b"x"},
        {"AGENTS.md": b"y"},
    )

    assert failure is None
    assert result == listing


def test_verify_listing_fails_when_path_local_entry_is_extra(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    listing = [{"sourcePath": "AGENTS.md"}, {"sourcePath": "CLAUDE.md"}]
    runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, json.dumps(listing), ""))
    fixture = runtime_parity.load_fixtures(FIXTURES)[0]

    with pytest.raises(runtime_parity.ParityConfigError, match=r"extra=\['CLAUDE\.md'\]"):
        parity._verify_copilot_instruction_listing(
            fixture, "copilot", workspace, workspace, runner, 30, {}, {"AGENTS.md": b"y"}
        )


# --- End-to-end: the harness process launches from the declared cwd ---------


def test_run_evaluation_launches_the_model_call_from_the_declared_cwd(
    tmp_path: Path,
) -> None:
    """REQ-9: both CLI invocations run with `cwd` = `workspace / fixture.cwd`.

    A fixture's `setup_files` still write relative to the workspace ROOT
    (matching `file_equals`/`file_regex` assertion paths), so this asserts
    the subprocess `cwd` kwarg directly rather than a file location.
    """
    corpus = corpus_with_instructions(
        tmp_path,
        default_instructions=False,
        path_local=["AGENTS.md"],
        cwd=".github/workflows",
    )
    seen_cwd: dict[str, Path] = {}
    fake = FixedResponseRunner("CONTINUE_PHASE_3")

    def runner(argv: list[object], **kwargs: object) -> subprocess.CompletedProcess[str]:
        args = [str(value) for value in argv]
        executable = Path(args[0]).name.lower()
        if args[1:4] == ["instruction", "list", "--json"]:
            seen_cwd["listing"] = Path(str(kwargs["cwd"]))
            return subprocess.CompletedProcess(args, 0, "[]", "")
        if "--version" not in args:
            seen_cwd[executable] = Path(str(kwargs["cwd"]))
        return fake(argv, **kwargs)

    report, code = parity.run_evaluation(
        fixtures_path=corpus,
        model=parity.DEFAULT_MODEL,
        output=tmp_path / "run" / "report.json",
        claude_bin="claude",
        copilot_bin="copilot",
        timeout=30,
        dry_run=False,
        runner=runner,
        harnesses="claude",
    )

    assert code == parity.EXIT_OK
    workspace = tmp_path / "run" / "workspaces" / "resume-phase-3" / "claude"
    assert seen_cwd["claude"] == (workspace / ".github" / "workflows").resolve()
