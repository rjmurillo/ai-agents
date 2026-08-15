"""Host-local date regressions for retrospective entry points."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime
from hashlib import sha1
from pathlib import Path
from types import ModuleType

_SCRIPTS = Path(__file__).resolve().parents[3] / ".claude" / "skills" / "retrospective" / "scripts"


def _load_script(name: str) -> ModuleType:
    path = _SCRIPTS / f"{name}.py"
    module_name = f"test_retrospective_{name}_{sha1(str(path).encode()).hexdigest()[:12]}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_EXTRACT_EVIDENCE = _load_script("extract_evidence")
_RUN_RETROSPECTIVE = _load_script("run_retrospective")


def _write_session(sessions: Path, name: str, work: str) -> Path:
    sessions.mkdir(parents=True, exist_ok=True)
    path = sessions / name
    path.write_text(json.dumps({"workLog": [work]}), encoding="utf-8")
    return path


def test_session_selector_default_uses_host_local_date(tmp_path, monkeypatch):
    sessions = tmp_path / ".agents" / "sessions"
    selected = _write_session(sessions, "2026-06-04-session-1-host-ahead.json", "ahead")
    _write_session(sessions, "2026-06-03-session-1-utc.json", "utc")
    monkeypatch.setattr(_EXTRACT_EVIDENCE, "host_session_date", lambda: "2026-06-04")

    assert _EXTRACT_EVIDENCE.find_recent_session_log(sessions) == selected


def test_session_selector_finds_pre_migration_utc_tomorrow_log(
    tmp_path, monkeypatch
):
    sessions = tmp_path / ".agents" / "sessions"
    selected = _write_session(sessions, "2026-06-04-session-1-utc.json", "utc work")
    _write_session(sessions, "2026-06-02-session-1-stale.json", "stale work")
    monkeypatch.setattr(_EXTRACT_EVIDENCE, "host_session_date", lambda: "2026-06-03")

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 6, 4, 1, 30, tzinfo=UTC)

    monkeypatch.setattr(_EXTRACT_EVIDENCE, "datetime", _FrozenDateTime)

    assert _EXTRACT_EVIDENCE.find_recent_session_log(sessions) == selected


def test_extract_evidence_cli_default_uses_host_local_date(tmp_path, capsys, monkeypatch):
    sessions = tmp_path / ".agents" / "sessions"
    selected = _write_session(sessions, "2026-06-04-session-1-local.json", "host-local work")
    monkeypatch.setattr(_EXTRACT_EVIDENCE, "host_session_date", lambda: "2026-06-04")

    rc = _EXTRACT_EVIDENCE.main(["--project-dir", str(tmp_path)])
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["scope"] == "2026-06-04"
    assert payload["session_log_path"] == str(selected)
    assert payload["work_items"] == ["host-local work"]


def test_run_retrospective_default_uses_host_local_date(tmp_path, monkeypatch):
    sessions = tmp_path / ".agents" / "sessions"
    _write_session(sessions, "2026-06-03-session-1-local.json", "host-local work")
    monkeypatch.setattr(_RUN_RETROSPECTIVE, "host_session_date", lambda: "2026-06-03")

    rc = _RUN_RETROSPECTIVE.main(["--project-dir", str(tmp_path)])

    assert rc == 0
    artifact = tmp_path / ".agents" / "retrospective" / "2026-06-03-2026-06-03.md"
    assert artifact.is_file()
    assert "host-local work" in artifact.read_text(encoding="utf-8")
