"""Shared builders for the surface parity tests (issue #5637)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "build" / "scripts"))

import check_surface_parity as csp  # noqa: E402
import surface_manifest as sm  # noqa: E402


def put(root: Path, rel: str, text: str = "x\n") -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_manifest(root: Path, surfaces: list[dict[str, Any]], roots: list[str]) -> None:
    doc = {"schemaVersion": "1.0", "roots": roots, "surfaces": surfaces}
    put(root, sm.MANIFEST_REL, yaml.safe_dump(doc, sort_keys=False))


def surface(**fields: Any) -> dict[str, Any]:
    fields.setdefault("id", fields["path"].replace("/", "-").strip("."))
    return fields


def generated(path: str, authority: str, generator: str) -> dict[str, Any]:
    return surface(
        path=path, relation="generated", authority=authority, generator=generator, owner="gate"
    )


def independent(path: str, **extra: Any) -> dict[str, Any]:
    return surface(path=path, relation="independent", reason="authored in place", **extra)


def make_repo(tmp_path: Path) -> Path:
    """A git repo with one generator, one authority, and one generated copy."""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    put(root, "pyproject.toml", "[project]\n")
    put(root, "build/gen.py", "# generator\n")
    put(root, "templates/agents/a.md", "body\n")
    put(root, "src/out/a.md", "body\n")
    put(root, "src/notes/readme.md", "authored\n")
    write_manifest(
        root,
        [
            generated("src/out", "templates/agents", "build/gen.py"),
            independent("src/notes"),
        ],
        ["src"],
    )
    return root


def findings(root: Path, prefixes: tuple[str, ...] = ()) -> list[sm.Finding]:
    manifest = sm.load_manifest(root)
    assert manifest is not None
    return csp.run_checks(root, manifest, owned_prefixes=prefixes)


def kinds(found: list[sm.Finding]) -> list[str]:
    return sorted(f.kind for f in found)
