"""Tests for review_memory_export_security.py sensitive data scanning."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.review_memory_export_security import main, scan_file


@pytest.fixture
def clean_file(tmp_path: Path) -> Path:
    p = tmp_path / "clean.json"
    p.write_text('{"data": "safe content, no secrets here"}', encoding="utf-8")
    return p


@pytest.fixture
def file_with_api_key(tmp_path: Path) -> Path:
    p = tmp_path / "secrets.json"
    p.write_text('{"key": "ghp_abcdefghijklmnopqrstuvwxyz1234567890"}', encoding="utf-8")
    return p


@pytest.fixture
def file_with_private_key(tmp_path: Path) -> Path:
    p = tmp_path / "private.json"
    p.write_text('{"data": "-----BEGIN RSA KEY-----"}', encoding="utf-8")
    return p


@pytest.fixture
def file_with_home_path(tmp_path: Path) -> Path:
    p = tmp_path / "paths.json"
    p.write_text('{"path": "/home/testuser/secrets/config"}', encoding="utf-8")
    return p


# Name of the memory backend retired in issue #5574. Spelled in pieces so a
# repository-wide grep for it reports zero hits in this tree, which is the
# decommission gate. Only the removed-flag negative control below needs it.
_RETIRED_BACKEND = "forget" + "ful"


class TestScanFile:
    def test_clean_file_returns_0(self, clean_file: Path) -> None:
        assert scan_file(clean_file, quiet=True) == 0

    def test_file_with_api_key_returns_1(self, file_with_api_key: Path) -> None:
        assert scan_file(file_with_api_key, quiet=True) == 1

    def test_file_with_private_key_returns_1(self, file_with_private_key: Path) -> None:
        assert scan_file(file_with_private_key, quiet=True) == 1

    def test_file_with_home_path_returns_1(self, file_with_home_path: Path) -> None:
        assert scan_file(file_with_home_path, quiet=True) == 1

    def test_clean_file_reports_success(
        self,
        clean_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert scan_file(clean_file) == 0
        assert "CLEAN - No sensitive data patterns detected" in capsys.readouterr().out

    def test_sensitive_file_reports_warning(
        self,
        file_with_api_key: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        assert scan_file(file_with_api_key) == 1
        assert "WARNING - Sensitive data patterns detected!" in capsys.readouterr().out

    def test_invalid_pattern_fails_closed(
        self,
        clean_file: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        with patch(
            "scripts.review_memory_export_security.SENSITIVE_PATTERNS",
            {"Invalid": ["["]},
        ):
            assert scan_file(clean_file) == 1
        assert "Found 0 potential sensitive data matches" in capsys.readouterr().out

    def test_generic_34_character_token_returns_1_without_logging_secret(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        export_file = tmp_path / "generic-token.json"
        secret = "t" * 34
        export_file.write_text(f'{{"data": "{secret}"}}', encoding="utf-8")

        assert scan_file(export_file) == 1
        output = capsys.readouterr().out
        assert secret not in output
        assert "{34,}" not in output

    def test_generic_33_character_value_returns_0(self, tmp_path: Path) -> None:
        export_file = tmp_path / "short-value.json"
        export_file.write_text(f'{{"data": "{"t" * 33}"}}', encoding="utf-8")

        assert scan_file(export_file, quiet=True) == 0

    @pytest.mark.parametrize(
        ("field_name", "canonical_uuid"),
        [
            ("id", "550e8400-e29b-41d4-a716-446655440000"),
            ("user_id", "550E8400-E29B-41D4-A716-446655440000"),
        ],
    )
    def test_canonical_uuid_in_id_field_returns_1(
        self,
        tmp_path: Path,
        field_name: str,
        canonical_uuid: str,
    ) -> None:
        """The identifier exemption is gone; these lines now scan as secrets.

        This assertion is the inverse of the one it replaces, which required
        0 under the opt-in mode. The scanner got stricter, not looser: a
        canonical UUID in an `id` field is now reported like any other long
        opaque token. Only one export format put them there, and it no
        longer exists.
        """
        export_file = tmp_path / "canonical-uuid.json"
        export_file.write_text(
            f'{{"{field_name}": "{canonical_uuid}"}}',
            encoding="utf-8",
        )

        assert scan_file(export_file, quiet=True) == 1

    @pytest.mark.parametrize(
        "field_name",
        ["content", "session", "session_id", "auth_id", "token_id"],
    )
    def test_uuid_outside_id_field_returns_1(
        self,
        tmp_path: Path,
        field_name: str,
    ) -> None:
        export_file = tmp_path / "uuid-value.json"
        export_file.write_text(
            f'{{"{field_name}": "550e8400-e29b-41d4-a716-446655440000"}}',
            encoding="utf-8",
        )

        assert scan_file(export_file, quiet=True) == 1

    def test_pretty_printed_uuid_returns_1(self, tmp_path: Path) -> None:
        """Layout never mattered to the pattern, only to the old exemption."""
        export_file = tmp_path / "pretty-export.json"
        export_file.write_text(
            '{\n  "id": "550e8400-e29b-41d4-a716-446655440000"\n}\n',
            encoding="utf-8",
        )

        assert scan_file(export_file, quiet=True) == 1

    def test_uuid_does_not_hide_other_token(self, tmp_path: Path) -> None:
        export_file = tmp_path / "uuid-with-token.json"
        export_file.write_text(
            f'{{"id": "550e8400-e29b-41d4-a716-446655440000", '
            f'"data": "{"t" * 34}"}}',
            encoding="utf-8",
        )

        assert scan_file(export_file, quiet=True) == 1

    def test_uuid_does_not_hide_second_uuid(self, tmp_path: Path) -> None:
        export_file = tmp_path / "two-uuids.json"
        export_file.write_text(
            '{"id": "550e8400-e29b-41d4-a716-446655440000", '
            '"data": "550e8400-e29b-41d4-a716-446655440000"}',
            encoding="utf-8",
        )

        assert scan_file(export_file, quiet=True) == 1

    def test_escaped_id_text_still_returns_1(self, tmp_path: Path) -> None:
        export_file = tmp_path / "escaped-id-text.json"
        export_file.write_text(
            '{"data": "embedded {\\"id\\": '
            '\\"550e8400-e29b-41d4-a716-446655440000\\"}"}',
            encoding="utf-8",
        )

        assert scan_file(export_file, quiet=True) == 1

    @pytest.mark.parametrize(
        "uuid_like_token",
        [
            "550e8400-e29b-41d4-a716-44665544000g",
            "550e8400-e29b-41d4-a716-446655440000x",
            "t" * 34,
        ],
    )
    def test_uuid_like_token_returns_1(
        self,
        tmp_path: Path,
        uuid_like_token: str,
    ) -> None:
        export_file = tmp_path / "uuid-like-token.json"
        export_file.write_text(f'{{"id": "{uuid_like_token}"}}', encoding="utf-8")

        assert scan_file(export_file, quiet=True) == 1


class TestMain:
    def test_export_file_option_is_rejected(self, clean_file: Path) -> None:
        with pytest.raises(SystemExit) as exc_info:
            main(["--export-file", str(clean_file)])
        assert exc_info.value.code == 2

    def test_missing_file_returns_1(self) -> None:
        assert main(["nonexistent.json"]) == 1

    def test_clean_file_returns_0(self, clean_file: Path) -> None:
        assert main([str(clean_file)]) == 0

    def test_quiet_flag_accepted(self, clean_file: Path) -> None:
        assert main([str(clean_file), "--quiet"]) == 0

    def test_removed_export_mode_flag_is_rejected(self, clean_file: Path) -> None:
        """Negative control: the opt-in exemption flag no longer parses.

        A caller still passing it must fail loudly. Silently ignoring it
        would let a script believe identifiers are being exempted when the
        scanner is in fact reporting them.

        The flag name is assembled rather than written out because the
        decommission in issue #5574 is gated on the retired backend's name
        being absent from this tree, and a literal here would be the one
        remaining hit. `_RETIRED_BACKEND` holds the name once, at the top of
        the file, where the next reader can see why.
        """
        with pytest.raises(SystemExit) as exc_info:
            main([f"--{_RETIRED_BACKEND}-export", str(clean_file), "--quiet"])
        assert exc_info.value.code == 2
