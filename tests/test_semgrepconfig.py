"""The semgrep project config and the two in-repo rule-exclusion call sites (issue #4725).

Hermetic: no network, no semgrep.dev, no SEMGREP_APP_TOKEN. The only semgrep
code exercised is the config loader that ships in the pinned wheel, and the two
argv builders, both of which are pure functions over their inputs once the
executable resolution and the subprocess are stubbed.

Two things are pinned here, and they are different in kind.

The FILE is a record, not a control. `.semgrepconfig.yml` is read and uploaded
by `semgrep ci`, but its schema cannot express a rule exclusion, so it can never
turn the cloud check green. The tests below pin that ceiling so a later reader
does not mistake the file for a rule-control surface and add a key that breaks
the scan.

The ARGV is a control, and it was broken. `--exclude-rule` matches an id
exactly. `scripts/security/run_semgrep.py` passed the family prefix
`python.lang.compatibility.python36` and suppressed nothing while its comment
claimed otherwise. The argv tests below bond both call sites to the same four
full ids so the two cannot drift again.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / ".semgrepconfig.yml"

_VALIDATION_DIR = REPO_ROOT / "scripts" / "validation"
if str(_VALIDATION_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATION_DIR))

# The four ids every in-repo exclusion must carry, in full. A family prefix
# such as "python.lang.compatibility.python36" matches nothing.
EXPECTED_RULE_IDS = frozenset(
    {
        "python.lang.compatibility.python36.python36-compatibility-Popen1",
        "python.lang.compatibility.python36.python36-compatibility-Popen2",
        "python.lang.compatibility.python37.python37-compatibility-Popen1",
        "python.lang.compatibility.python37.python37-compatibility-Popen2",
    }
)


def _exclude_rule_values(argv: list[str]) -> set[str]:
    """Collect every value following an ``--exclude-rule`` flag in ``argv``."""
    return {argv[i + 1] for i, token in enumerate(argv) if token == "--exclude-rule"}


# --- the file is read by the loader the Platform path uses -------------------


def test_the_config_parses_with_the_pinned_semgrep_loader() -> None:
    """Valid YAML is not the bar. The bar is that ProjectConfig accepts it,
    because that is the loader `semgrep ci` runs before uploading the file."""
    project_config = pytest.importorskip("semgrep.app.project_config")

    config = project_config.ProjectConfig.load_from_file(CONFIG_PATH)

    assert config.version == "v1"
    assert isinstance(config.tags, list)
    assert config.tags, "the tag is the only thing this file can actually carry"


def test_the_wire_payload_carries_version_and_tags_only() -> None:
    """Pins the ceiling: this is everything the repository can ever send the
    Platform, so the file cannot become a rule-control surface by accident."""
    project_config = pytest.importorskip("semgrep.app.project_config")

    config = project_config.ProjectConfig.load_from_file(CONFIG_PATH)

    assert set(config.to_CiConfigFromRepo().to_json()) == {"version", "tags"}


def test_an_unknown_key_is_fatal_rather_than_ignored(tmp_path: Path) -> None:
    """Negative control for the two tests above, which would otherwise pass on
    an empty file. An exclusion key does not degrade to a no-op: it fails the
    whole scan, which is why the record lives in comments instead."""
    project_config = pytest.importorskip("semgrep.app.project_config")
    from semgrep.error import SemgrepError

    stray = tmp_path / ".semgrepconfig.yml"
    stray.write_text(
        "version: v1\nexclude_rules:\n  - python.lang.compatibility.python36\n",
        encoding="utf-8",
    )

    with pytest.raises(SemgrepError) as excinfo:
        project_config.ProjectConfig.load_from_file(stray)

    assert excinfo.value.code == 5


def test_the_config_declares_no_key_beyond_the_supported_schema() -> None:
    loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))

    assert set(loaded) <= {"version", "tags"}


def test_the_config_records_every_rule_id_the_platform_exception_must_cover() -> None:
    """The file cannot exclude the rules, so its whole value is naming them."""
    text = CONFIG_PATH.read_text(encoding="utf-8")

    missing = sorted(rule_id for rule_id in EXPECTED_RULE_IDS if rule_id not in text)

    assert not missing, f"rule ids absent from the record: {missing}"


# --- the argv exclusions, which are a real control ---------------------------


def test_the_pre_push_hook_excludes_the_four_ids_in_full() -> None:
    import git_hook_policy

    excluded = _exclude_rule_values(git_hook_policy._semgrep_command("auto", []))

    assert excluded == EXPECTED_RULE_IDS


def test_the_security_scanner_excludes_the_four_ids_in_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The regression this branch fixes. This call site passed the family prefix
    and suppressed nothing while its comment said it did."""
    from scripts.security import run_semgrep

    captured: dict[str, list[str]] = {}

    def _fake_run(cmd: list[str], **_kwargs: object) -> object:
        captured["cmd"] = list(cmd)
        raise AssertionError("stop after argv capture")

    # The constructor resolves the repo root through a Git subprocess. Stub that
    # lookup first so the test reads no live Git state and passes outside a
    # worktree; then stub the executable resolution and the scan subprocess.
    monkeypatch.setattr(run_semgrep, "get_repo_root", lambda: REPO_ROOT)
    monkeypatch.setattr(run_semgrep, "_resolve_semgrep_executable", lambda _root: "semgrep")
    monkeypatch.setattr(run_semgrep.subprocess, "run", _fake_run)
    scanner = run_semgrep.SemgrepScanner()

    with pytest.raises(AssertionError, match="stop after argv capture"):
        scanner._run_semgrep([Path("scripts/validation/run_workflow_local_test.py")])

    assert _exclude_rule_values(captured["cmd"]) == EXPECTED_RULE_IDS


def test_neither_call_site_passes_a_bare_family_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A prefix is the specific defect, so assert its absence directly rather
    than relying on the equality checks above to imply it."""
    import git_hook_policy

    from scripts.security import run_semgrep

    captured: dict[str, list[str]] = {}

    def _fake_run(cmd: list[str], **_kwargs: object) -> object:
        captured["cmd"] = list(cmd)
        raise AssertionError("stop")

    monkeypatch.setattr(run_semgrep, "get_repo_root", lambda: REPO_ROOT)
    monkeypatch.setattr(run_semgrep, "_resolve_semgrep_executable", lambda _root: "semgrep")
    monkeypatch.setattr(run_semgrep.subprocess, "run", _fake_run)
    scanner = run_semgrep.SemgrepScanner()
    with pytest.raises(AssertionError):
        scanner._run_semgrep([Path("x.py")])

    every_exclusion = _exclude_rule_values(captured["cmd"]) | _exclude_rule_values(
        git_hook_policy._semgrep_command("auto", [])
    )

    prefixes = sorted(
        value
        for value in every_exclusion
        if value.startswith("python.lang.compatibility.") and value not in EXPECTED_RULE_IDS
    )

    assert not prefixes, f"family prefixes suppress nothing: {prefixes}"


# --- what deliberately does not exist ----------------------------------------


@pytest.mark.parametrize("name", [".semgrepignore", ".semgrep.yml", ".semgrep.yaml", ".semgrep"])
def test_no_blanket_exclusion_surface_is_introduced(name: str) -> None:
    """A root `.semgrepignore` would silence every rule on whichever file it
    lists, and it REPLACES semgrep's built-in default ignore list rather than
    extending it, so it would newly pull tests/ and build/ into scan scope.
    `.semgrep.yml` and `.semgrep/` make a bare `semgrep scan` abort since 1.38.0.
    """
    assert not (REPO_ROOT / name).exists()
