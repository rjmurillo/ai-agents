"""The artifact flow gate refuses what skillforge's shipped `fm.artifacts.shape` refuses.

PyYAML reads `null`, `~`, and an unquoted `yes` as typed values, where the
stdlib parser that ships to consumers keeps them as text. Without the shared
rule, a template could pass this gate and still fail the consumer's lint.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.validation.artifact_flow_fixtures import _corpus, _run, _write_skill

_SHAPE = "skillforge rule fm.artifacts.shape refuses this template"


def _with_metadata(root: Path, block: str) -> None:
    path = _write_skill(root, "extra-skill", invoker="harness")
    text = path.read_text(encoding="utf-8").replace("metadata:\n", "metadata:\n" + block, 1)
    path.write_text(text, encoding="utf-8")


@pytest.mark.parametrize(
    ("block", "problem"),
    [
        ("  outputs:\n    scratch-note: null\n", "outputs.scratch-note must be empty"),
        ("  outputs:\n    scratch-note: ~\n", "outputs.scratch-note must be empty"),
        (
            "  inputs:\n    scratch-note:\n      source: user\n      required: yes\n",
            "inputs.scratch-note.required must be true or false",
        ),
    ],
)
def test_values_pyyaml_types_but_the_shipped_lint_rejects_exit_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], block: str, problem: str
) -> None:
    root = _corpus(tmp_path)
    _with_metadata(root, block)

    code, _, err = _run(root, capsys)

    assert code == 1, err
    assert _SHAPE in err
    assert problem in err


def test_an_entry_with_nothing_after_the_colon_still_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _corpus(tmp_path)
    _with_metadata(root, "  outputs:\n    scratch-note:\n")

    code, _, err = _run(root, capsys)

    assert code == 0, err
