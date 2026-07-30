"""Function citation verification: comment safety, multi-language, and hyphen support.

These tests cover the three failure modes fixed in issue #4012:
- Python false positive when 'def' appears only in a comment or string
- Non-Python languages failing because the verifier only matched 'def'
- Hyphenated PowerShell names rejected by _FUNCTION_PATTERN
"""

from __future__ import annotations

import pytest

from memory_enhancement.models import Citation, SourceType
from memory_enhancement.verification import _FUNCTION_PATTERN, verify_citation


class TestVerifyFunctionCitationCommentSafety:
    """Python function citations must not pass when def appears only in a comment or string."""

    @pytest.mark.unit
    def test_def_in_comment_not_found(self, tmp_path):
        """False positive: a def inside a comment must not satisfy the check."""
        (tmp_path / "module.py").write_text("# def ghost_func(): pass\nx = 1\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="module.py::ghost_func",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False

    @pytest.mark.unit
    def test_def_in_string_literal_not_found(self, tmp_path):
        """False positive: a def inside a string literal must not satisfy the check."""
        (tmp_path / "module.py").write_text('x = "def ghost_func(): pass"\n')
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="module.py::ghost_func",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False

    @pytest.mark.unit
    def test_async_def_in_comment_not_found(self, tmp_path):
        """False positive: async def inside a comment must not satisfy the check."""
        (tmp_path / "module.py").write_text("# async def ghost_async(): pass\nx = 1\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="module.py::ghost_async",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False

    @pytest.mark.unit
    def test_real_def_still_found(self, tmp_path):
        """Regression: a real def must still be found after the AST switch."""
        (tmp_path / "module.py").write_text("# def not_this(): pass\ndef real_func():\n    pass\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="module.py::real_func",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_async_def_found(self, tmp_path):
        """Async function definitions are found via AsyncFunctionDef AST node."""
        (tmp_path / "module.py").write_text("async def async_func():\n    pass\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="module.py::async_func",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_syntax_error_fallback_found(self, tmp_path):
        """Malformed Python falls back to regex; real def is still found."""
        (tmp_path / "module.py").write_text("def fallback_func():\n    pass\n!!SYNTAX ERROR\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="module.py::fallback_func",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True
        assert "fallback" in result.reason.lower()

    @pytest.mark.unit
    def test_syntax_error_fallback_not_found(self, tmp_path):
        """Malformed Python falls back to regex; missing func is not found."""
        (tmp_path / "module.py").write_text("def other_func():\n    pass\n!!SYNTAX ERROR\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="module.py::missing_func",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False
        assert "fallback" in result.reason.lower()

    @pytest.mark.unit
    def test_pyi_stub_uses_ast(self, tmp_path):
        """Stub files (.pyi) are handled via AST, not raw regex."""
        (tmp_path / "stub.pyi").write_text(
            "# def fake_func() -> None: ...\ndef real_stub() -> None: ...\n"
        )
        c_fake = Citation(
            source_type=SourceType.FUNCTION,
            target="stub.pyi::fake_func",
            context="",
        )
        c_real = Citation(
            source_type=SourceType.FUNCTION,
            target="stub.pyi::real_stub",
            context="",
        )
        assert verify_citation(c_fake, tmp_path).is_valid is False
        assert verify_citation(c_real, tmp_path).is_valid is True


class TestVerifyFunctionCitationMultiLanguage:
    """Function citations for TypeScript, JavaScript, C#, and PowerShell."""

    @pytest.mark.unit
    def test_typescript_function_keyword(self, tmp_path):
        """TypeScript: 'function handleAuth()' is found."""
        (tmp_path / "app.ts").write_text("function handleAuth(): void {}\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="app.ts::handleAuth",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_typescript_export_function(self, tmp_path):
        """TypeScript: 'export function foo()' is found."""
        (tmp_path / "app.ts").write_text("export function foo(): string { return ''; }\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="app.ts::foo",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_typescript_missing_function(self, tmp_path):
        """TypeScript: a function not defined in the file is not found."""
        (tmp_path / "app.ts").write_text("function otherFunc(): void {}\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="app.ts::missingFunc",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "content",
        [
            "// function ghost(): void {}\n",
            "/*\nfunction ghost(): void {}\n*/\n",
            'const example = "function ghost(): void {}";\n',
        ],
    )
    def test_typescript_non_code_function_not_found(self, tmp_path, content):
        """TypeScript comments and strings must not satisfy a citation."""
        (tmp_path / "app.ts").write_text(content)
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="app.ts::ghost",
            context="",
        )
        assert verify_citation(c, tmp_path).is_valid is False

    @pytest.mark.unit
    def test_unterminated_typescript_string_does_not_hang(self, tmp_path):
        """An unterminated TypeScript string masks its remaining content in linear time."""
        escaped_quotes = '\\"' * 100
        (tmp_path / "app.ts").write_text(
            f'const doc = "{escaped_quotes}\nfunction ghost(): void {{}}\n'
        )
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="app.ts::ghost",
            context="",
        )
        assert verify_citation(c, tmp_path).is_valid is False

    @pytest.mark.unit
    def test_unterminated_typescript_block_comment_does_not_hang(self, tmp_path):
        """An unterminated block comment masks its remaining content in linear time."""
        comment_openers = "/*\n" * 100
        (tmp_path / "app.ts").write_text(f"{comment_openers}function ghost(): void {{}}\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="app.ts::ghost",
            context="",
        )
        assert verify_citation(c, tmp_path).is_valid is False

    @pytest.mark.unit
    def test_javascript_function_found(self, tmp_path):
        """JavaScript: 'function processEvent()' is found."""
        (tmp_path / "handler.js").write_text("function processEvent(e) { return e; }\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="handler.js::processEvent",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_tsx_function_found(self, tmp_path):
        """TSX: 'function MyComponent()' is found."""
        (tmp_path / "ui.tsx").write_text("function MyComponent() { return null; }\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="ui.tsx::MyComponent",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_jsx_function_found(self, tmp_path):
        """JSX: 'export function App()' is found."""
        (tmp_path / "app.jsx").write_text("export function App() { return null; }\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="app.jsx::App",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_csharp_method_found(self, tmp_path):
        """C#: 'public void DoThing()' is found."""
        (tmp_path / "Service.cs").write_text("public void DoThing() {}\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="Service.cs::DoThing",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_csharp_missing_method(self, tmp_path):
        """C#: a method not declared in the file is not found."""
        (tmp_path / "Service.cs").write_text("public void OtherMethod() {}\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="Service.cs::DoThing",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "content",
        [
            "DoThing();\n",
            "return DoThing();\n",
            "// public void DoThing() {}\n",
            "/*\npublic void DoThing() {}\n*/\n",
            'var example = "public void DoThing() {}";\n',
        ],
    )
    def test_csharp_call_or_non_code_method_not_found(self, tmp_path, content):
        """C# calls, comments, and strings must not satisfy a citation."""
        (tmp_path / "Service.cs").write_text(content)
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="Service.cs::DoThing",
            context="",
        )
        assert verify_citation(c, tmp_path).is_valid is False

    @pytest.mark.unit
    def test_powershell_function_found(self, tmp_path):
        """PowerShell: 'function Invoke-Deploy' is found."""
        (tmp_path / "deploy.ps1").write_text("function Invoke-Deploy { param([string]$Env) }\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="deploy.ps1::Invoke-Deploy",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True

    @pytest.mark.unit
    def test_powershell_missing_function(self, tmp_path):
        """PowerShell: a function not defined in the file is not found."""
        (tmp_path / "deploy.ps1").write_text("function Other-Func { }\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="deploy.ps1::Invoke-Deploy",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False

    @pytest.mark.unit
    @pytest.mark.parametrize(
        "content",
        [
            "# function Invoke-Deploy { }\n",
            "<#\nfunction Invoke-Deploy { }\n#>\n",
            '$example = "function Invoke-Deploy { }"\n',
            '@"\nfunction Invoke-Deploy { }\n"@\n',
            "@'\nfunction Invoke-Deploy { }\n'@\n",
            '$doc = @"\nThe "deploy" command\nfunction Invoke-Deploy { }\n"@\n',
            "$doc = @'\nfunction Invoke-Deploy { }\n'@\n",
        ],
    )
    def test_powershell_non_code_function_not_found(self, tmp_path, content):
        """PowerShell comments and strings must not satisfy a citation."""
        (tmp_path / "deploy.ps1").write_text(content)
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="deploy.ps1::Invoke-Deploy",
            context="",
        )
        assert verify_citation(c, tmp_path).is_valid is False

    @pytest.mark.unit
    def test_unterminated_powershell_here_string_does_not_hang(self, tmp_path):
        """An unterminated here-string masks its remaining content in linear time."""
        decoys = "\n".join(
            f"function Decoy-{index} {{ Write-Output fake }}" for index in range(100)
        )
        (tmp_path / "deploy.ps1").write_text(f'$doc = @"\n{decoys}\nfunction Invoke-Deploy {{ }}\n')
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="deploy.ps1::Invoke-Deploy",
            context="",
        )
        assert verify_citation(c, tmp_path).is_valid is False

    @pytest.mark.unit
    def test_unterminated_powershell_string_does_not_hang(self, tmp_path):
        """An unterminated PowerShell string masks its remaining content in linear time."""
        escaped_quotes = '`"' * 100
        (tmp_path / "deploy.ps1").write_text(
            f'$doc = "{escaped_quotes}\nfunction Invoke-Deploy {{ }}\n'
        )
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="deploy.ps1::Invoke-Deploy",
            context="",
        )
        assert verify_citation(c, tmp_path).is_valid is False

    @pytest.mark.unit
    def test_unterminated_powershell_block_comment_does_not_hang(self, tmp_path):
        """An unterminated block comment masks its remaining content in linear time."""
        comment_openers = "<#\n" * 100
        (tmp_path / "deploy.ps1").write_text(f"{comment_openers}function Invoke-Deploy {{ }}\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="deploy.ps1::Invoke-Deploy",
            context="",
        )
        assert verify_citation(c, tmp_path).is_valid is False

    @pytest.mark.unit
    def test_powershell_function_match_is_case_insensitive(self, tmp_path):
        """PowerShell names use case-insensitive matching."""
        (tmp_path / "deploy.ps1").write_text("function Invoke-Deploy { }\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="deploy.ps1::invoke-deploy",
            context="",
        )
        assert verify_citation(c, tmp_path).is_valid is True

    @pytest.mark.unit
    def test_unsupported_extension_returns_unsupported(self, tmp_path):
        """An unsupported extension returns is_valid=False with an 'unsupported' reason."""
        (tmp_path / "code.rb").write_text("def my_method\nend\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="code.rb::my_method",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is False
        assert "unsupported" in result.reason.lower()

    @pytest.mark.unit
    def test_psm1_function_found(self, tmp_path):
        """PowerShell module (.psm1): 'function Get-Config' is found."""
        (tmp_path / "module.psm1").write_text("function Get-Config { return @{} }\n")
        c = Citation(
            source_type=SourceType.FUNCTION,
            target="module.psm1::Get-Config",
            context="",
        )
        result = verify_citation(c, tmp_path)
        assert result.is_valid is True


class TestFunctionPatternHyphenSupport:
    """_FUNCTION_PATTERN must accept hyphenated names (PowerShell Verb-Noun)."""

    @pytest.mark.unit
    def test_hyphenated_name_matches(self):
        """'util.ps1::Get-Thing' parses to path=util.ps1, func=Get-Thing."""
        m = _FUNCTION_PATTERN.match("util.ps1::Get-Thing")
        assert m is not None
        assert m.group("path") == "util.ps1"
        assert m.group("func") == "Get-Thing"

    @pytest.mark.unit
    def test_plain_name_still_matches(self):
        """Plain names (no hyphen) continue to match."""
        m = _FUNCTION_PATTERN.match("module.py::my_func")
        assert m is not None
        assert m.group("func") == "my_func"

    @pytest.mark.unit
    def test_name_starting_with_hyphen_rejected(self):
        """A name starting with a hyphen is invalid and must not match."""
        assert _FUNCTION_PATTERN.match("file.ps1::-Thing") is None

    @pytest.mark.unit
    def test_empty_func_name_rejected(self):
        """An empty function name after '::' is invalid and must not match."""
        assert _FUNCTION_PATTERN.match("file.ps1::") is None

    @pytest.mark.unit
    def test_multi_hyphen_name_matches(self):
        """Multi-segment names like 'Set-Item-Value' must match."""
        m = _FUNCTION_PATTERN.match("util.ps1::Set-Item-Value")
        assert m is not None
        assert m.group("func") == "Set-Item-Value"
