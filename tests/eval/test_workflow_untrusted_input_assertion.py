"""Tests for the `workflow_untrusted_input` assertion kind (#4880 review).

The `file_regex`/`file_not_regex` pair the `untrusted-input-run` fixture used
before this had three holes: a single-line-anchored regex missed the
expression inside a multi-line `run: |` block, missed the YAML list-item
form (`- run: ...`, dash before `run:`), and the positive control's anchored
pattern failed on a quoted `env:` value (`PR_TITLE: "${{ ... }}"`), a safe
variant. This assertion kind parses the workflow with `yaml.safe_load`
instead of matching text, and asserts on the parsed structure: no step's
`run` string names the untrusted expression, and at least one step's `env`
value does.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.eval._runtime_parity_test_support import FIXTURES, parity, runtime_parity

MARKER = "github.event.pull_request.title"


_SAFE_WORKFLOW = (
    "on: pull_request\n"
    "jobs:\n"
    "  greet:\n"
    "    steps:\n"
    "      - name: Print PR title\n"
    "        env:\n"
    f"          PR_TITLE: ${{{{ {MARKER} }}}}\n"
    '        run: echo "$PR_TITLE"\n'
)
_UNSAFE_WORKFLOW = (
    f'on: pull_request\njobs:\n  greet:\n    steps:\n      - run: echo "${{{{ {MARKER} }}}}"\n'
)


def _fixture_with_assertion(tmp_path: Path, path: str = "greet.yml") -> object:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixture = dict(payload["fixtures"][0])
    fixture["assertions"] = [{"kind": "workflow_untrusted_input", "path": path}]
    fixture["controls"] = {
        "positive": {"response": "any", "files": {path: _SAFE_WORKFLOW}},
        "negative": {"response": "any", "files": {path: _UNSAFE_WORKFLOW}},
    }
    payload["fixtures"] = [fixture]
    corpus = tmp_path / "fixtures.json"
    corpus.write_text(json.dumps(payload), encoding="utf-8")
    return parity.load_fixtures(corpus)[0]


def _score(tmp_path: Path, workflow_yaml: str, path: str = "greet.yml") -> bool:
    fixture = _fixture_with_assertion(tmp_path, path)
    results = parity.score_assertions(fixture, "any response", {path: workflow_yaml})
    assert len(results) == 1
    return bool(results[0]["passed"])


# --- loader validation --------------------------------------------------


def test_loader_requires_a_path(tmp_path: Path) -> None:
    payload = json.loads(FIXTURES.read_text(encoding="utf-8"))
    fixture = dict(payload["fixtures"][0])
    fixture["assertions"] = [{"kind": "workflow_untrusted_input"}]
    payload["fixtures"] = [fixture]
    corpus = tmp_path / "fixtures.json"
    corpus.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(parity.ParityConfigError, match="path"):
        parity.load_fixtures(corpus)


def test_kind_is_deterministic() -> None:
    """A fixture with only this kind needs no live grader for --dry-run."""
    assert "workflow_untrusted_input" in runtime_parity.DETERMINISTIC_ASSERTION_KINDS


# --- scoring: the safe pattern and the three review-named holes ---------


def test_env_indirection_passes(tmp_path: Path) -> None:
    """The safe pattern: the raw expression lives only in `env:`."""
    workflow = (
        "on: pull_request\n"
        "jobs:\n"
        "  greet:\n"
        "    runs-on: ubuntu-latest\n"
        "    steps:\n"
        "      - name: Print PR title\n"
        "        env:\n"
        f"          PR_TITLE: ${{{{ {MARKER} }}}}\n"
        '        run: echo "$PR_TITLE"\n'
    )
    assert _score(tmp_path, workflow) is True


def test_quoted_env_value_passes(tmp_path: Path) -> None:
    """Review hole 2: a quoted env value is still the safe pattern."""
    workflow = (
        "on: pull_request\n"
        "jobs:\n"
        "  greet:\n"
        "    steps:\n"
        "      - name: Print PR title\n"
        "        env:\n"
        f'          PR_TITLE: "${{{{ {MARKER} }}}}"\n'
        '        run: echo "$PR_TITLE"\n'
    )
    assert _score(tmp_path, workflow) is True


def test_multiline_run_block_injection_fails(tmp_path: Path) -> None:
    """Review hole 1: the expression on a continuation line of `run: |`."""
    workflow = (
        "on: pull_request\n"
        "jobs:\n"
        "  greet:\n"
        "    steps:\n"
        "      - run: |\n"
        f'          echo "${{{{ {MARKER} }}}}"\n'
    )
    assert _score(tmp_path, workflow) is False


def test_dash_run_form_fails(tmp_path: Path) -> None:
    """Review hole 3: the YAML list-item `- run:` form, no separate `name:`."""
    workflow = (
        f'on: pull_request\njobs:\n  greet:\n    steps:\n      - run: echo "${{{{ {MARKER} }}}}"\n'
    )
    assert _score(tmp_path, workflow) is False


def test_no_env_and_no_run_injection_fails(tmp_path: Path) -> None:
    """No step reads the untrusted title at all: nothing to prove the fix ran."""
    workflow = "on: pull_request\njobs:\n  greet:\n    steps:\n      - run: echo hi\n"
    assert _score(tmp_path, workflow) is False


def test_missing_file_fails(tmp_path: Path) -> None:
    fixture = _fixture_with_assertion(tmp_path)
    results = parity.score_assertions(fixture, "any response", {})
    assert results[0]["passed"] is False


def test_malformed_yaml_fails_closed(tmp_path: Path) -> None:
    assert _score(tmp_path, "not: [valid: yaml") is False


def test_non_mapping_document_fails_closed(tmp_path: Path) -> None:
    assert _score(tmp_path, "- just\n- a\n- list\n") is False


def test_jobs_not_a_mapping_fails_closed(tmp_path: Path) -> None:
    assert _score(tmp_path, "on: pull_request\njobs: not-a-mapping\n") is False


# --- dry-run control coverage on the real corpus -------------------------

_PATH_LOCAL_FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "eval"
    / "examples"
    / "path-local-parity-fixtures.json"
)


def test_untrusted_input_run_fixture_controls_discriminate() -> None:
    """`untrusted-input-run`'s own positive/negative controls, scored directly.

    `parity.load_fixtures` runs `_validate_controls` at load time (the same
    check `--dry-run` exercises, with no live model call), so a fixture
    whose positive control fails or whose negative control passes raises
    here before any CLI ever launches.
    """
    fixtures = parity.load_fixtures(_PATH_LOCAL_FIXTURES)
    fixture = next(f for f in fixtures if f.fixture_id == "untrusted-input-run")
    assert any(spec.kind == "workflow_untrusted_input" for spec in fixture.assertions)
