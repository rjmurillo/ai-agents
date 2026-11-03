"""Error paths for relocation collection and trigger recheck (issue #6506).

Covers the launch-failure branch of ``collect_tests`` and the trigger
``OSError`` that ``validation_record.py`` reports as a config error (exit 2).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parents[2] / ".claude" / "skills" / "validation-authority" / "scripts"
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_SCRIPTS))
import relocation_collector as collector_mod
import trigger_recheck
from relocation_cli_fixtures import PROJECT_ROOT
from validation_record_fixtures import make_record, make_relocation_target, mod


@pytest.mark.parametrize(
    "error",
    [subprocess.TimeoutExpired(["pytest"], 300), OSError("cannot start python")],
)
def test_collect_tests_launch_failure_is_a_collection_error(
    monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    def boom(*args: Any, **kwargs: Any) -> Any:
        raise error

    monkeypatch.setattr(collector_mod.subprocess, "run", boom)
    with pytest.raises(collector_mod.CollectionError, match="pytest collection could not run"):
        collector_mod.collect_tests(["tests/validation/test_x.py"], PROJECT_ROOT)


def _unreadable_trigger() -> SimpleNamespace:
    def decide(paths: Any, effects: Any, root: Any) -> Any:
        raise OSError("build_all.py: Permission denied")

    return SimpleNamespace(decide=decide)


def test_trigger_oserror_raises_a_recheck_error_not_a_defect() -> None:
    with pytest.raises(trigger_recheck.TriggerRecheckError, match="could not read its inputs"):
        trigger_recheck.recomputed_trigger_defects(
            {"decision": "skip", "effects": []}, ["tests/a.py"], PROJECT_ROOT, _unreadable_trigger()
        )


def test_trigger_value_error_stays_a_defect() -> None:
    def decide(paths: Any, effects: Any, root: Any) -> Any:
        raise ValueError("unknown effect: bogus")

    defects = trigger_recheck.recomputed_trigger_defects(
        {"decision": "skip", "effects": []},
        ["tests/a.py"],
        PROJECT_ROOT,
        SimpleNamespace(decide=decide),
    )
    assert defects == [
        "trigger recomputed from the changed paths was refused: unknown effect: bogus"
    ]


def test_cli_exits_2_when_the_trigger_cannot_read_its_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    record = tmp_path / "record.json"
    record.write_text(json.dumps(make_record(make_relocation_target())))
    monkeypatch.setattr(mod, "load_trigger", lambda path: _unreadable_trigger())

    code = mod.main(["--record", str(record), "--changed-path", "tests/a.py"])

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert "trigger could not read its inputs" in captured.err


def test_collect_tests_ignores_warning_text_that_holds_a_double_colon(tmp_path: Path) -> None:
    """A module warning at import with "::" in its text yields only the real id."""
    module = tmp_path / "tests" / "v" / "test_w.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "import warnings\n"
        'warnings.warn("mod::level", DeprecationWarning)\n'
        "\n\n"
        "def test_a():\n"
        "    assert True\n"
    )

    ids = collector_mod.collect_tests(["tests/v/test_w.py"], tmp_path)

    assert len(ids) == 1
    assert ids[0].endswith("test_w.py::test_a")
