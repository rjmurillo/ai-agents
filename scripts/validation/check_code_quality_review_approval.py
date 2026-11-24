"""Check a maintainer's approval of one exact ai-agents assessment.

Exit 0 prints a candidate inventory or a verified WARN.
Exit 1 leaves the ordinary gate in force. Exit 2 means invalid input.
Exit 3 means Git, the assessor, or the approval lookup failed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

INTEGRATION_REF = "refs/remotes/origin/main"
ASSESSOR_PATH = "src/claude/skills/code-qualities-assessment/scripts/assess.py"
CONFIG_PATH = ".qualityrc.json"
API_ROOT = "https://api.github.com/repos/rjmurillo/ai-agents/issues"
MAINTAINER = "rjmurillo"
_MAX_COMMENT_BYTES = 1 << 20
_READ_COMMENT = """
import sys
from urllib.request import Request, urlopen

request = Request(sys.argv[1], headers={
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
})
with urlopen(request, timeout=10) as response:
    sys.stdout.buffer.write(response.read(int(sys.argv[2])))
"""


class UnapprovedError(Exception):
    """The review has no applicable approval."""


def _git_env() -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    checkout = Path.cwd().resolve()
    tool_path = os.pathsep.join(
        entry
        for entry in os.get_exec_path(env)
        if Path(entry).is_absolute() and not Path(entry).resolve().is_relative_to(checkout)
    )
    return {
        **env,
        "PATH": tool_path,
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }


def _git(*args: str, cwd: Path | None = None) -> bytes:
    env = _git_env()
    git = shutil.which("git", path=env["PATH"])
    if git is None:
        raise FileNotFoundError("Git is missing from the trusted PATH")
    return subprocess.run(
        [git, *args], cwd=cwd, env=env, capture_output=True, check=True, timeout=60
    ).stdout


def _revision(ref: str) -> str:
    return _git("rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}").strip().decode()


def _blob(revision: str, path: str) -> bytes:
    return _git("cat-file", "blob", f"{revision}:{path}")


def _regressions(report: dict[str, Any]) -> list[dict[str, object]]:
    if report["gate_mode"] != "regression" or not report["files"]:
        raise ValueError("expected a nonempty regression report")
    for file in report["files"]:
        gate = file["threshold_gate"]
        if gate is not None and gate["failed"] is not False:
            raise UnapprovedError("the assessor reported an absolute threshold failure")

    rows: dict[tuple[str, str], dict[str, object]] = {}
    for comparison in report["comparisons"]:
        if comparison["evidence_loss"]:
            raise UnapprovedError("the assessor reported lost evidence")
        # Rows the trusted assessor admitted (issue #7525) still sit in the raw
        # report but need no owner decision, so they stay out of the inventory.
        admitted = comparison.get("rule_admissions") or {}
        for quality in comparison["regressions"]:
            if quality in admitted:
                continue
            matches = [delta for delta in comparison["deltas"] if delta["quality"] == quality]
            path = comparison["file_path"]
            key = path, quality
            if key in rows or len(matches) != 1 or matches[0]["status"] != "compared":
                raise ValueError(f"ambiguous regression for {path} ({quality})")
            rows[key] = {
                "path": path,
                "quality": quality,
                "base": matches[0]["base"],
                "head": matches[0]["head"],
            }
    if not rows:
        raise ValueError("exit 10 has no comparable regressions")
    return [rows[key] for key in sorted(rows)]


def _require_blob(path: Path, oid: bytes, object_format: str) -> None:
    data = path.read_bytes()
    digest = hashlib.new(object_format, usedforsecurity=False)
    digest.update(f"blob {len(data)}\0".encode())
    digest.update(data)
    if digest.hexdigest().encode() != oid:
        raise UnapprovedError(f"checkout differs from the committed blob: {path.name}")


def _validate_snapshot(snapshot: Path, integration: str, head: str) -> None:
    flags = ("--raw", "--no-abbrev", "--no-renames", "--ignore-submodules=none", "-z")
    raw = _git("diff", *flags, f"{integration}...{head}", cwd=snapshot)
    object_format = _git("rev-parse", "--show-object-format", cwd=snapshot).strip().decode()
    pairs = iter(raw.split(b"\0")[:-1])
    regular = {b"000000", b"100644", b"100755"}
    for header, name in zip(pairs, pairs, strict=True):
        old_mode, new_mode, _, head_oid, _ = header[1:].split()
        path = snapshot / os.fsdecode(name)
        if old_mode not in regular or new_mode not in regular:
            raise UnapprovedError(f"cannot verify nonregular diff entry {path.name}")
        if new_mode == b"000000":
            continue
        if not path.is_file() or not path.resolve().is_relative_to(snapshot):
            raise UnapprovedError(f"checkout omitted a changed file: {path.name}")
        _require_blob(path, head_oid, object_format)
        if path.suffix.lower() == ".go":
            for directory in path.resolve().parents:
                module = directory / "go.mod"
                if module.is_file():
                    if not (
                        directory.is_relative_to(snapshot)
                        and module.resolve().is_relative_to(snapshot)
                    ):
                        raise UnapprovedError(f"Go module context escapes snapshot: {path.name}")
                    relative = module.relative_to(snapshot).as_posix()
                    module_oid = _git("rev-parse", "--verify", f"{head}:{relative}", cwd=snapshot)
                    _require_blob(module, module_oid.strip(), object_format)
                    break


def _assess(integration: str, head: str) -> subprocess.CompletedProcess[bytes]:
    for path in (ASSESSOR_PATH, CONFIG_PATH):
        if _blob(integration, path) != _blob(head, path):
            raise UnapprovedError(f"the review changes trusted assessment input {path}")

    with tempfile.TemporaryDirectory(prefix="quality-review-") as tmp:
        snapshot = (Path(tmp) / "snapshot").resolve()
        _git("clone", "--quiet", "--shared", "--no-checkout", "--template=", ".", str(snapshot))
        _git("-c", "core.autocrlf=false", "checkout", "--quiet", "--detach", head, cwd=snapshot)
        _validate_snapshot(snapshot, integration, head)
        scanner = Path(tmp) / "assess.py"
        config = Path(tmp) / "qualityrc.json"
        scanner.write_bytes(_blob(integration, ASSESSOR_PATH))
        config.write_bytes(_blob(integration, CONFIG_PATH))
        command = [sys.executable, "-I", str(scanner), "--target", ".", "--changed-only"]
        command += ["--base", integration, "--config", str(config), "--format", "json"]
        return subprocess.run(
            command, cwd=snapshot, env=_git_env(), capture_output=True, timeout=300, check=False
        )


def _assert_revisions(integration: str, head: str) -> None:
    if _revision("HEAD") != head or _revision(INTEGRATION_REF) != integration:
        raise UnapprovedError("HEAD or the integration branch differs from the pinned review")


def _inventory(
    integration: str, head: str, assessment: subprocess.CompletedProcess[bytes]
) -> dict[str, object]:
    if assessment.returncode in (0, 11):
        raise UnapprovedError(f"approval does not apply to assessor exit {assessment.returncode}")
    if assessment.returncode != 10:
        raise RuntimeError(f"assessor exit {assessment.returncode}")
    return {
        "base_sha": integration,
        "reviewed_sha": head,
        "regressions": _regressions(json.loads(assessment.stdout)),
    }


def _comment(comment_id: int) -> dict[str, Any]:
    # A child deadline covers the entire request, including a slow response body.
    url = f"{API_ROOT}/comments/{comment_id}"
    command = [sys.executable, "-I", "-c", _READ_COMMENT, url, str(_MAX_COMMENT_BYTES + 1)]
    result_bytes = subprocess.run(command, capture_output=True, timeout=15, check=True).stdout
    if len(result_bytes) > _MAX_COMMENT_BYTES:
        raise ValueError("GitHub issue comment exceeds the response limit")
    result = json.loads(result_bytes)
    if not isinstance(result, dict):
        raise ValueError("expected a GitHub issue comment")
    return result


def _verify_comment(issue: int, comment_id: int, digest: str) -> None:
    comment = _comment(comment_id)
    checks = (
        (comment["id"] == comment_id and comment["issue_url"] == f"{API_ROOT}/{issue}", "locator"),
        (
            comment["user"]["login"] == MAINTAINER and comment["author_association"] == "OWNER",
            "owner",
        ),
        (comment["updated_at"] == comment["created_at"], "edited comment"),
        (comment["body"].strip() == f"Code-quality review approval SHA256: {digest}", "digest"),
    )
    for passes, reason in checks:
        if not passes:
            raise UnapprovedError(f"no matching approval from the repository owner: {reason}")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="pinned origin/main commit SHA")
    parser.add_argument("--head", required=True, help="pinned candidate commit SHA")
    parser.add_argument("--assessment", required=True, type=Path, help="raw assessment JSON path")
    parser.add_argument("--issue", type=int)
    parser.add_argument("--comment", type=int, help="GitHub comment ID of the owner approval")
    args = parser.parse_args(argv)
    issue: int | None = args.issue
    comment_id: int | None = args.comment
    if (issue is None) != (comment_id is None):
        parser.error("--issue and --comment must be supplied together")
    if (issue is not None and issue < 1) or (comment_id is not None and comment_id < 1):
        parser.error("--issue and --comment require positive IDs")
    return args


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    issue: int | None = args.issue
    comment_id: int | None = args.comment
    result: dict[str, object] = {"base_sha": args.base, "reviewed_sha": args.head}
    if issue is not None:
        result.update(issue=issue, comment=comment_id)
    status = 0
    try:
        if os.name != "posix":
            raise RuntimeError("approval verification requires a trusted POSIX environment")
        if _git("rev-parse", "--show-prefix").strip():
            raise UnapprovedError("run from the repository root")
        _assert_revisions(args.base, args.head)
        assessment = _assess(args.base, args.head)
        result.update(
            raw_exit=assessment.returncode,
            assessment_sha256=hashlib.sha256(assessment.stdout).hexdigest(),
            stderr_sha256=hashlib.sha256(assessment.stderr).hexdigest(),
        )
        stderr_path = args.assessment.with_suffix(f"{args.assessment.suffix}.stderr")
        stderr_path.write_bytes(assessment.stderr)
        args.assessment.write_bytes(assessment.stdout)
        inventory = _inventory(args.base, args.head, assessment)
        digest = hashlib.sha256(
            json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        if issue is not None and comment_id is not None:
            _verify_comment(issue, comment_id, digest)
        _assert_revisions(args.base, args.head)
        result.update(inventory, approval_sha256=digest)
        if issue is not None and comment_id is not None:
            result["verdict"] = "WARN"
    except UnapprovedError as exc:
        print(exc, file=sys.stderr)
        status = 1
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        print(f"Invalid review evidence: {exc}", file=sys.stderr)
        status = 2
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"")[-512:].decode(errors="replace").strip()
        print(
            f"Could not verify review approval: {exc}. Diagnostic: {ascii(detail)}", file=sys.stderr
        )
        status = 3
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"Could not verify review approval: {exc}", file=sys.stderr)
        status = 3
    print(json.dumps(result, indent=2))
    return status


if __name__ == "__main__":
    sys.exit(main())
