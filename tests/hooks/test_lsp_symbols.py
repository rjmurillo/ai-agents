"""Tests for scripts/hook_utilities/lsp_symbols.py (ADR-062 symbol detection).

Faithful-port verification of the kit ``isCodeSymbol`` regex set (camelCase,
PascalCase, dotted, snake>=9), the allowlist, the dropped-Tailwind kebab branch,
the grep-family / git-grep predicates, zero-width stripping, and pattern
extraction from bash grep commands. Covers positive, negative, and edge cases.
"""

from __future__ import annotations

import pytest

from scripts.hook_utilities.lsp_symbols import (
    extract_pattern_and_target,
    is_code_symbol,
    is_git_grep,
    is_grep_search,
    strip_zero_width,
)

# ---------------------------------------------------------------------------
# is_code_symbol: positive shapes
# ---------------------------------------------------------------------------


class TestIsCodeSymbolPositive:
    @pytest.mark.parametrize(
        "symbol",
        [
            "getUserData",
            "fetchAll",
            "handleClick",
            "isReady",  # camel, 7 chars, has upper
        ],
    )
    def test_camel_case(self, symbol):
        assert is_code_symbol(symbol) is True

    @pytest.mark.parametrize(
        "symbol",
        [
            "UserService",
            "AbstractFactory",
            "Foo1Bar",
        ],
    )
    def test_pascal_case(self, symbol):
        assert is_code_symbol(symbol) is True

    @pytest.mark.parametrize(
        "symbol",
        [
            "user.name",
            "obj.prop",
            "App.run",
        ],
    )
    def test_dotted_symbol(self, symbol):
        assert is_code_symbol(symbol) is True

    def test_snake_case_func_at_min_length(self):
        # snake needs >=2 underscores AND length >= 9
        assert is_code_symbol("get_user_data") is True
        assert len("aa_bb_ccc") == 9
        assert is_code_symbol("aa_bb_ccc") is True


# ---------------------------------------------------------------------------
# is_code_symbol: negative shapes / allowlist
# ---------------------------------------------------------------------------


class TestIsCodeSymbolNegative:
    def test_non_string(self):
        assert is_code_symbol(None) is False
        assert is_code_symbol(123) is False
        assert is_code_symbol(["x"]) is False

    def test_too_short(self):
        assert is_code_symbol("abc") is False
        assert is_code_symbol("") is False

    def test_whitespace(self):
        assert is_code_symbol("get user") is False

    def test_metacharacters(self):
        assert is_code_symbol("foo(bar") is False
        assert is_code_symbol("a$bcd") is False
        assert is_code_symbol("a*bcd") is False

    @pytest.mark.parametrize(
        "symbol",
        [
            "TODOnow",
            "FIXMElater",
            "console.log",
            "import foo",  # has space anyway, but allowlist also
            "from x",
            "http://x",
            "1234abc",
            ".hidden",
        ],
    )
    def test_allowlist(self, symbol):
        assert is_code_symbol(symbol) is False

    def test_screaming_snake_constant(self):
        # /^[A-Z_]{3,}$/ allowlist
        assert is_code_symbol("MAX_VALUE") is False
        assert is_code_symbol("ABCDEF") is False

    def test_short_lowercase_word(self):
        # /^[a-z]{1,8}$/ allowlist (up to 8 lowercase)
        assert is_code_symbol("function") is False  # 8 chars all lowercase
        assert is_code_symbol("abcd") is False

    def test_quote_prefixed(self):
        assert is_code_symbol("'hello") is False
        assert is_code_symbol('"World') is False

    def test_use_client_server(self):
        # The /^use (client|server)/ allowlist matches the space form, which the
        # whitespace guard already rejects; both paths return False.
        assert is_code_symbol("use client") is False
        assert is_code_symbol("use server") is False

    def test_kebab_case_dropped_branch(self):
        # Tailwind/component allowlist dropped: kebab is never a symbol here.
        assert is_code_symbol("my-component") is False
        assert is_code_symbol("user-modal") is False
        assert is_code_symbol("actions-helper") is False
        assert is_code_symbol("text-center") is False

    def test_lowercase_long_no_upper_not_camel(self):
        # 9+ lowercase letters, no underscore, no upper -> not camel/snake
        assert is_code_symbol("definitely") is False

    def test_snake_too_short(self):
        assert is_code_symbol("a_b_c") is False  # length 5 < 9
        assert is_code_symbol("one_two") is False  # only 1 underscore


# ---------------------------------------------------------------------------
# strip_zero_width
# ---------------------------------------------------------------------------


class TestStripZeroWidth:
    def test_strips_zwsp(self):
        assert strip_zero_width("foo​bar") == "foobar"

    def test_strips_bom(self):
        assert strip_zero_width("﻿hello") == "hello"

    def test_strips_soft_hyphen(self):
        assert strip_zero_width("a­b") == "ab"

    def test_empty(self):
        assert strip_zero_width("") == ""

    def test_no_zero_width(self):
        assert strip_zero_width("clean") == "clean"


# ---------------------------------------------------------------------------
# is_grep_search / is_git_grep
# ---------------------------------------------------------------------------


class TestGrepPredicates:
    @pytest.mark.parametrize(
        "cmd",
        [
            "grep -r Foo src/",
            "rg Foo",
            "egrep pattern file",
            "fgrep literal file",
            "ag Foo",
            "ack Foo",
            "GREP -i foo",  # case-insensitive
        ],
    )
    def test_is_grep_search_true(self, cmd):
        assert is_grep_search(cmd) is True

    @pytest.mark.parametrize(
        "cmd",
        [
            "ls -la",
            "cat file.txt",
            "find . -name x",
            "",
        ],
    )
    def test_is_grep_search_false(self, cmd):
        assert is_grep_search(cmd) is False

    def test_is_grep_search_none(self):
        assert is_grep_search(None) is False

    def test_zero_width_evasion_in_binary_name_no_boundary(self):
        # grep​Foo -> grepFoo after strip: no word boundary, not a grep
        assert is_grep_search("grep​Foo") is False

    def test_zero_width_then_space_still_grep(self):
        # grep​ Foo -> grep Foo after strip: boundary preserved
        assert is_grep_search("grep​ Foo") is True

    def test_is_git_grep_true(self):
        assert is_git_grep("git grep Foo") is True
        assert is_git_grep("cd x && git  grep Bar") is True

    def test_is_git_grep_false(self):
        assert is_git_grep("grep Foo") is False
        assert is_git_grep("") is False
        assert is_git_grep(None) is False


# ---------------------------------------------------------------------------
# extract_pattern_and_target
# ---------------------------------------------------------------------------


class TestExtractPatternAndTarget:
    def test_empty_command(self):
        assert extract_pattern_and_target("") == ([], "")

    def test_none_command(self):
        assert extract_pattern_and_target(None) == ([], "")

    def test_double_quoted_pattern(self):
        parts, cmd = extract_pattern_and_target('grep "getUserData" src/')
        assert parts == ["getUserData"]
        assert cmd == 'grep "getUserData" src/'

    def test_single_quoted_pattern(self):
        parts, _ = extract_pattern_and_target("grep 'UserService' lib/")
        assert parts == ["UserService"]

    def test_alternation_split_on_pipe(self):
        parts, _ = extract_pattern_and_target('rg "getUserData|UserService"')
        assert parts == ["getUserData", "UserService"]

    def test_dotted_split(self):
        # split on '.' so each side evaluated independently (kit behavior)
        parts, _ = extract_pattern_and_target('grep "mcp.Tool"')
        assert parts == ["mcp", "Tool"]

    def test_metacharacters_stripped(self):
        parts, _ = extract_pattern_and_target('grep "get.*Data"')
        # split on '.', strip metachars: "get", "" (from *), "Data" -> drop empties
        assert "Data" in parts
        assert "" not in parts

    def test_bare_pascal_pattern_faithful_to_kit(self):
        # Faithful to the kit's fragile bare-pattern regex: on an unquoted
        # multi-arg command the capture lands on the trailing path token
        # ("src"), not the symbol. Verified against the kit JS regex. The
        # downstream is_code_symbol filter rejects "src" (lowercase, len 3),
        # so the guard does not block; the symbol filter is the real gate.
        parts, _ = extract_pattern_and_target("grep -r UserService src/")
        assert parts == ["src"]
        assert is_code_symbol("src") is False

    def test_bare_pascal_pattern_single_arg(self):
        # When the PascalCase symbol is the only/last token, it is captured.
        parts, _ = extract_pattern_and_target("grep -r UserService")
        assert parts == ["UserService"]
        assert is_code_symbol("UserService") is True

    def test_no_pattern_match(self):
        parts, cmd = extract_pattern_and_target("ls -la")
        assert parts == []
        assert cmd == "ls -la"

    def test_zero_width_stripped_from_command(self):
        parts, cmd = extract_pattern_and_target('grep "Foo​Bar"')
        assert "​" not in cmd
        assert parts == ["FooBar"]

    def test_escaped_double_quotes_unescaped(self):
        # \" sequences are unescaped before matching the quoted form
        parts, _ = extract_pattern_and_target('grep \\"getUserData\\"')
        assert parts == ["getUserData"]
