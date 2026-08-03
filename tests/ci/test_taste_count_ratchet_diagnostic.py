"""Tests for the taste ratchet's regression diagnostic (issue #3902).

``list_violations`` read ``report["findings"]`` and ``item["path"]`` while
``taste_lints.py`` emits ``report["violations"]`` with an ``item["file"]`` key,
and has never emitted either name the lister looked for. The lister therefore
returned an empty list on every input, so a tripped ratchet printed the new
count and named none of the violations behind it. The function shipped with no
test coverage at all, which is how the mismatch survived.

These tests pin both key names against the emitter's real shape. The fake below
is deliberately narrower than ``_fake_scan`` in ``test_taste_count_ratchet``:
``list_violations`` touches only the file listing and the linter, never the
baseline probes, so modelling those legs here would assert nothing.
"""

from __future__ import annotations

import json
import subprocess

from scripts.ci import taste_count_ratchet as ratchet


def _report(items: list[object], *, key: str = "violations") -> str:
    return json.dumps(
        {
            "files_scanned": 1,
            "files_by_category": {"authored": 1},
            "error_count": len(items),
            "warning_count": 0,
            key: items,
        }
    )


def _error_item(**overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "rule": "file-size",
        "severity": "error",
        "category": "authored",
        "file": "docs/big.md",
        "line": 1990,
        "message": "File exceeds 500 lines (1990 lines)",
    }
    item.update(overrides)
    return item


def _fake(stdout: str, *, returncode: int = 10, tracked: tuple[str, ...] = ("pkg/mod.py",)):
    """Stand in for the two subprocess legs ``list_violations`` actually uses."""

    def _run(cmd, **kwargs):
        if cmd[0] == "git":
            listing = "\0".join(tracked) + ("\0" if tracked else "")
            return subprocess.CompletedProcess(cmd, 0, stdout=listing, stderr="")
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr="")

    return _run


def test_an_error_severity_violation_is_rendered(tmp_path, monkeypatch):
    """Positive: file, rule, and message reach the contributor."""
    monkeypatch.setattr(subprocess, "run", _fake(_report([_error_item()])))
    assert ratchet.list_violations(tmp_path) == [
        "docs/big.md: [file-size] File exceeds 500 lines (1990 lines)"
    ]


def test_the_stale_findings_key_is_none_not_empty(tmp_path, monkeypatch, capsys):
    """Negative: a report keyed "findings" must not render, and must not read clean.

    ``taste_lints.py`` has never emitted that key. If this ever returns a line,
    the lister has regressed onto the name that caused the empty diagnostic.

    The contract changed here (adversarial review of #4284): this used to
    return ``[]``, which the caller prints exactly like a clean tree. A report
    carrying no ``violations`` list did not come from a healthy emitter, so it
    is a scan failure and now says so.
    """
    monkeypatch.setattr(subprocess, "run", _fake(_report([_error_item()], key="findings")))
    assert ratchet.list_violations(tmp_path) is None
    assert "carried no violations list" in capsys.readouterr().err


def test_the_stale_path_key_is_a_named_failure(tmp_path, monkeypatch, capsys):
    """Negative: an item keyed "path" proves we read "file" instead.

    Contract changed by the review of #4284: this used to render
    ``"?: [file-size] ..."``, a line that looks like real diagnostic output and
    names no file, so a contributor went looking for a violation the renderer
    had already lost. A missing ``file`` is a broken emitter, not a violation.
    """
    item = _error_item()
    item.pop("file")
    item["path"] = "docs/big.md"
    monkeypatch.setattr(subprocess, "run", _fake(_report([item])))
    assert ratchet.list_violations(tmp_path) is None
    assert "no string file" in capsys.readouterr().err


def test_warning_severity_is_not_listed(tmp_path, monkeypatch):
    """Negative: the ratchet counts errors, so the diagnostic lists only errors."""
    monkeypatch.setattr(subprocess, "run", _fake(_report([_error_item(severity="warning")])))
    assert ratchet.list_violations(tmp_path) == []


def test_a_non_mapping_entry_is_a_named_failure(tmp_path, monkeypatch, capsys):
    """Edge: one malformed entry condemns the batch, and says which shape it was.

    Contract changed by the review of #4284: skipping it silently discarded a
    violation while the surviving entries made the list look complete. A
    partial list read as the whole truth is the failure this diagnostic exists
    to remove, so an unreadable entry is a scan failure like any other.
    """
    monkeypatch.setattr(subprocess, "run", _fake(_report(["not-a-dict", _error_item()])))
    assert ratchet.list_violations(tmp_path) is None
    assert "was not a JSON object" in capsys.readouterr().err


def test_absent_rule_and_message_are_a_named_failure(tmp_path, monkeypatch, capsys):
    """Edge: a sparse entry names its cause rather than rendering placeholders.

    Contract changed by the review of #4284: ``"a.md: [?] "`` named a file, no
    rule, and no message, which is a line a contributor cannot act on and
    cannot distinguish from a real one.
    """
    monkeypatch.setattr(subprocess, "run", _fake(_report([{"severity": "error", "file": "a.md"}])))
    assert ratchet.list_violations(tmp_path) is None
    assert "no string rule" in capsys.readouterr().err


def test_unparseable_output_names_the_cause(tmp_path, monkeypatch, capsys):
    """Edge: a broken linter must not read as a clean tree, and must say why.

    ``run`` prints the list under ``if violations:``, so a lister that returns
    None prints exactly as much as a clean tree: nothing (review of #4284).
    """
    monkeypatch.setattr(subprocess, "run", _fake("{not json"))
    assert ratchet.list_violations(tmp_path) is None
    assert "linter output was not JSON" in capsys.readouterr().err


def test_an_unexpected_exit_code_names_the_cause(tmp_path, monkeypatch, capsys):
    """Edge: only the clean and violations exit codes carry a usable report."""
    monkeypatch.setattr(subprocess, "run", _fake(_report([_error_item()]), returncode=1))
    assert ratchet.list_violations(tmp_path) is None
    assert "linter exit 1" in capsys.readouterr().err


def test_a_linter_that_cannot_launch_names_the_cause(tmp_path, monkeypatch, capsys):
    """Edge: the launch failure leg was the third silent one."""

    def _run(cmd, **kwargs):
        if cmd[0] == "git":
            return subprocess.CompletedProcess(cmd, 0, stdout="pkg/mod.py\0", stderr="")
        raise FileNotFoundError("python")

    monkeypatch.setattr(subprocess, "run", _run)
    assert ratchet.list_violations(tmp_path) is None
    assert "diagnostic unavailable" in capsys.readouterr().err


def test_an_empty_tracked_tree_lists_nothing(tmp_path, monkeypatch):
    """Edge: no tracked files means no violations, distinct from a scan failure."""
    monkeypatch.setattr(subprocess, "run", _fake(_report([_error_item()]), tracked=()))
    assert ratchet.list_violations(tmp_path) == []


# Ordering under the 40-line cap (adversarial review of issue #3902).
#
# Fixing the key names made the lister emit lines, but the ratchet caps the
# printed list at 40 and this repository carries 601 tracked violations. On
# #3902's own PR the single added violation sat at index 596, so the correct
# lister still printed 40 unrelated historical entries and hid the one line the
# contributor needed. Ordering branch-touched files first is what makes the
# diagnostic actionable; these tests pin that ordering and the wiring that
# feeds it.


def _batching_fake(reports: list[str], tracked: tuple[str, ...]):
    """Return a distinct report per linter batch, in call order.

    The single-report fake above cannot see a lister that returns only the
    first batch. The real tree needs 19 batches, so that gap is load bearing.
    """
    remaining = list(reports)

    def _run(cmd, **kwargs):
        if cmd[0] == "git":
            listing = "\0".join(tracked) + ("\0" if tracked else "")
            return subprocess.CompletedProcess(cmd, 0, stdout=listing, stderr="")
        return subprocess.CompletedProcess(cmd, 10, stdout=remaining.pop(0), stderr="")

    return _run


def test_a_touched_file_is_listed_before_untouched_ones(tmp_path, monkeypatch):
    """Positive: the branch's own violation leads, whatever its scan position."""
    items = [_error_item(file=f"old/f{index}.py") for index in range(50)]
    items.append(_error_item(file="mine.py", message="File exceeds 500 lines (900 lines)"))
    monkeypatch.setattr(subprocess, "run", _fake(_report(items)))

    lines = ratchet.list_violations(tmp_path, frozenset({"mine.py"}))

    assert lines[0].startswith("mine.py: "), "the touched file must not be buried"
    assert len(lines) == 51, "prioritising must reorder, never drop"
    assert lines[1] == "old/f0.py: [file-size] File exceeds 500 lines (1990 lines)"


def test_an_untouched_tree_keeps_scan_order(tmp_path, monkeypatch):
    """Negative: an empty priority set must not reshuffle anything."""
    items = [_error_item(file=f"old/f{index}.py") for index in range(3)]
    monkeypatch.setattr(subprocess, "run", _fake(_report(items)))

    lines = ratchet.list_violations(tmp_path, frozenset())

    assert [line.split(":", 1)[0] for line in lines] == ["old/f0.py", "old/f1.py", "old/f2.py"]


def test_a_priority_path_that_is_clean_changes_nothing(tmp_path, monkeypatch):
    """Edge: naming a file with no violations is not an error."""
    items = [_error_item(file="old/f0.py")]
    monkeypatch.setattr(subprocess, "run", _fake(_report(items)))

    assert ratchet.list_violations(tmp_path, frozenset({"untouched.py"})) == [
        "old/f0.py: [file-size] File exceeds 500 lines (1990 lines)"
    ]


def test_every_batch_contributes_violations(tmp_path, monkeypatch):
    """Edge: a lister that returned only the first batch would pass the rest."""
    big = "x" * 20000
    monkeypatch.setattr(
        subprocess,
        "run",
        _batching_fake(
            [
                _report([_error_item(file="first.py")]),
                _report([_error_item(file="second.py")]),
            ],
            tracked=(f"{big}/a.py", f"{big}/b.py"),
        ),
    )

    lines = ratchet.list_violations(tmp_path, frozenset())

    assert [line.split(":", 1)[0] for line in lines] == ["first.py", "second.py"]


# The report shape is not assumed (adversarial review of #4284).
#
# ``report.get("violations", [])`` gave a malformed report the same answer as a
# clean one, and gave several shapes no answer at all: a null or numeric
# ``violations`` raised TypeError and a report that was not a mapping raised
# AttributeError, straight out of the pre-push hook.
#
# Canonical shape, from ``format_json`` in
# ``.claude/skills/taste-lints/scripts/taste_lints.py``:
#
#     data = {"files_scanned": ..., "files_by_category": ..., "error_count": ...,
#             "warning_count": ..., "violations": [ ... for v in ... ]}
#
# and ``Violation`` in the same file declares ``rule: str``, ``severity: str``,
# ``file: str``, ``line: int``, ``message: str``, ``remediation: str``,
# ``category: str``. So the top level is always an object, ``violations`` is
# always a list, and every entry is an object carrying four strings. Anything
# else is a failed scan and is now read as one: None, with the cause on stderr.


def _named_none(payload: str, tmp_path, monkeypatch, capsys) -> str:
    """Assert ``payload`` is read as a scan failure, and hand back what it said."""
    monkeypatch.setattr(subprocess, "run", _fake(payload))
    assert ratchet.list_violations(tmp_path) is None
    err = capsys.readouterr().err
    assert "diagnostic unavailable" in err
    return err


def test_a_report_without_a_violations_list_is_not_a_clean_read(tmp_path, monkeypatch, capsys):
    """Negative: a positive error_count with no violation list is a failure.

    This is the shape the ratchet is likeliest to meet in the field. The count
    says the tree is dirty, so a diagnostic printing nothing is a
    contradiction, not a clean tree.
    """
    payload = json.dumps({"files_scanned": 1, "error_count": 3, "warning_count": 0})
    assert "carried no violations list" in _named_none(payload, tmp_path, monkeypatch, capsys)


def test_a_non_list_violations_value_is_not_a_clean_read(tmp_path, monkeypatch, capsys):
    """Edge: every non-list value, including the two that used to raise.

    ``None`` and ``5`` crashed the hook with TypeError; ``"oops"`` iterated as
    characters and rendered nothing; a mapping iterated as its keys and did the
    same.
    """
    for value in (None, 5, "oops", {"a": 1}, True):
        payload = json.dumps({"error_count": 3, "violations": value})
        assert "carried no violations list" in _named_none(payload, tmp_path, monkeypatch, capsys)


def test_a_non_mapping_report_is_not_a_clean_read(tmp_path, monkeypatch, capsys):
    """Edge: a report that parsed as JSON but is not an object.

    Each of these raised AttributeError on ``report.get``. The lister must fail
    soft, so a shape it cannot read is a named None, never a traceback.
    """
    for payload in ("null", "7", '"hello"', "[]", '[{"severity": "error"}]'):
        assert "not a JSON object" in _named_none(payload, tmp_path, monkeypatch, capsys)


# Every entry is validated, not just the list around it (pass-2 review of #4284).
#
# A well-formed list can still carry a malformed entry, and the renderer used
# ``finding.get(name, "?")`` on three of the four fields it reads. That turned a
# broken emitter into output that looks like a working diagnostic.


def test_a_non_string_field_is_a_named_failure(tmp_path, monkeypatch, capsys):
    """Edge: each required field, and each wrong type, named individually.

    ``format_json`` copies ``Violation``'s four string fields straight across,
    so a non-string is a broken emitter. Covering every field and several types
    keeps the guard from being written for the one shape a report happened to
    show.
    """
    for name in ("severity", "file", "rule", "message"):
        for value in (None, 7, ["a"], {"a": 1}, True):
            item = _error_item(**{name: value})
            payload = _report([item])
            err = _named_none(payload, tmp_path, monkeypatch, capsys)
            assert f"no string {name}" in err, (name, value)


def test_a_missing_field_is_a_named_failure(tmp_path, monkeypatch, capsys):
    """Edge: absent is checked like wrong-typed, for every required field."""
    for name in ("severity", "file", "rule", "message"):
        item = _error_item()
        item.pop(name)
        err = _named_none(_report([item]), tmp_path, monkeypatch, capsys)
        assert f"no string {name}" in err, name


def test_a_malformed_warning_entry_is_still_a_failure(tmp_path, monkeypatch, capsys):
    """Edge: the check runs before the severity filter, so warnings count too.

    A guard that only validated entries it was about to render would pass a
    report the emitter could not have produced, and the error entries in that
    same report are exactly as untrustworthy.
    """
    item = _error_item(severity="warning")
    item.pop("message")
    assert "no string message" in _named_none(_report([item]), tmp_path, monkeypatch, capsys)


def test_a_malformed_entry_beside_a_good_one_still_fails(tmp_path, monkeypatch, capsys):
    """Edge: a partial list must not be returned as if it were whole.

    Rendering the good entry and dropping the bad one gives the caller a list
    that looks complete and is not, which is the silent shape this work exists
    to remove.
    """
    payload = _report([_error_item(), _error_item(rule=None)])
    assert "no string rule" in _named_none(payload, tmp_path, monkeypatch, capsys)


def test_a_well_formed_empty_report_is_still_a_clean_read(tmp_path, monkeypatch, capsys):
    """Inverse: the new guards must not fire on a genuinely clean scan.

    An empty ``violations`` list is what a clean tree emits. If this ever
    returns None the ratchet loses its diagnostic on every clean run, and a
    note on stderr would print on every one of them.
    """
    monkeypatch.setattr(subprocess, "run", _fake(_report([]), returncode=0))
    assert ratchet.list_violations(tmp_path) == []
    assert capsys.readouterr().err == ""


def test_the_canonical_entry_shape_is_silent(tmp_path, monkeypatch, capsys):
    """Inverse: an entry carrying every key format_json emits must render.

    The guard is written against that emitter's real output, so the full
    canonical item, ``remediation`` and ``line`` and ``category`` included, is
    the case that must never trip it.
    """
    item = _error_item(remediation="Split the file", category="authored")
    monkeypatch.setattr(subprocess, "run", _fake(_report([item])))
    assert ratchet.list_violations(tmp_path) == [
        "docs/big.md: [file-size] File exceeds 500 lines (1990 lines)"
    ]
    assert capsys.readouterr().err == ""


def test_an_empty_message_is_not_a_malformed_entry(tmp_path, monkeypatch, capsys):
    """Inverse: empty is a string. Truthiness here would reject a real entry.

    ``Violation.message`` is typed ``str`` with no non-empty guarantee, so a
    rule that emits one would lose the whole diagnostic to a falsy check.
    """
    monkeypatch.setattr(subprocess, "run", _fake(_report([_error_item(message="")])))
    assert ratchet.list_violations(tmp_path) == ["docs/big.md: [file-size] "]
    assert capsys.readouterr().err == ""
