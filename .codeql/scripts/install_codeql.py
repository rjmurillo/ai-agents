#!/usr/bin/env python3
"""Download and install the CodeQL CLI for static analysis.

Downloads the appropriate CodeQL CLI bundle for the current platform
(Windows, Linux, or macOS) and architecture, extracts it to the
specified installation path, and optionally adds it to PATH.

Exit codes follow ADR-035:
    0 - Success
    1 - Logic error (invalid parameters, installation check failed)
    2 - Configuration error (unsupported platform)
    3 - External dependency error (download failed, extraction failed)
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download and install the CodeQL CLI.",
    )
    parser.add_argument(
        "--version", default=os.environ.get("CODEQL_VERSION", "v2.23.9"),
        help="CodeQL CLI version to install.",
    )
    parser.add_argument(
        "--install-path", default=os.environ.get("CODEQL_INSTALL_PATH", ".codeql/cli"),
        help="Directory where CodeQL CLI will be installed.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite an existing CodeQL installation.",
    )
    parser.add_argument(
        "--add-to-path", action="store_true",
        help="Add the CodeQL CLI to the PATH environment variable.",
    )
    parser.add_argument(
        "--ci", action="store_true",
        help="CI mode with non-interactive behavior.",
    )
    return parser


def get_download_url(version: str) -> str:
    system = platform.system().lower()
    if system == "windows":
        plat = "win64"
    elif system == "linux":
        plat = "linux64"
    elif system == "darwin":
        plat = "osx64"
    else:
        print(f"Unsupported platform: {system}", file=sys.stderr)
        sys.exit(2)

    base_url = "https://github.com/github/codeql-action/releases/download"
    return f"{base_url}/codeql-bundle-{version}/codeql-bundle-{plat}.tar.gz"


def check_codeql_installed(install_path: str) -> bool:
    exe_name = "codeql.exe" if platform.system().lower() == "windows" else "codeql"
    codeql_path = Path(install_path) / exe_name
    if not codeql_path.exists():
        return False
    try:
        result = subprocess.run(
            [str(codeql_path), "version"],
            capture_output=True, text=True, timeout=30, check=False,
        )
        if result.returncode != 0:
            print(
                f"CodeQL verification failed (exit code {result.returncode}): "
                f"{result.stderr.strip()}",
                file=sys.stderr,
            )
        return result.returncode == 0
    except OSError as exc:
        print(
            f"CodeQL binary at {codeql_path} is not executable: {exc}",
            file=sys.stderr,
        )
        return False
    except subprocess.TimeoutExpired:
        print(
            f"CodeQL version check timed out after 30s for {codeql_path}",
            file=sys.stderr,
        )
        return False


def install_codeql_cli(url: str, destination: str, ci: bool) -> None:
    temp_dir = tempfile.mkdtemp(prefix="codeql-install-")
    try:
        archive_path = os.path.join(temp_dir, "codeql-bundle.tar.gz")

        if not ci:
            print(f"Downloading CodeQL CLI from {url}...", file=sys.stderr)

        try:
            urllib.request.urlretrieve(url, archive_path)
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Failed to download CodeQL CLI (network error): {exc.reason}"
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f"Failed to download CodeQL CLI (filesystem error): {exc}"
            ) from exc

        if not ci:
            print("Download complete. Extracting...", file=sys.stderr)

        extract_dir = os.path.join(temp_dir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)

        result = subprocess.run(
            ["tar", "-xzf", archive_path, "-C", extract_dir],
            capture_output=True, text=True, timeout=300, check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"tar extraction failed with exit code {result.returncode}: {result.stderr}"
            )

        codeql_dir = os.path.join(extract_dir, "codeql")
        if not os.path.isdir(codeql_dir):
            raise RuntimeError(
                "Extraction succeeded but expected 'codeql' directory not found."
            )

        parent_dir = os.path.dirname(destination)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        if os.path.exists(destination):
            shutil.rmtree(destination)

        shutil.move(codeql_dir, destination)

        if not ci:
            print(
                f"CodeQL CLI installed successfully to {destination}",
                file=sys.stderr,
            )
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def add_to_path(install_path: str, ci: bool) -> None:
    absolute_path = str(Path(install_path).resolve())

    current_path = os.environ.get("PATH", "")
    separator = ";" if platform.system().lower() == "windows" else ":"
    path_entries = current_path.split(separator)

    if absolute_path in path_entries:
        return

    os.environ["PATH"] = f"{absolute_path}{separator}{current_path}"
    if not ci:
        print("Added CodeQL CLI to session PATH", file=sys.stderr)

    home = Path.home()
    shell = os.environ.get("SHELL", "")
    export_line = f'export PATH="{absolute_path}:$PATH"'

    profile_scripts: list[Path] = []
    if "bash" in shell:
        profile_scripts.append(home / ".bashrc")
    if "zsh" in shell:
        profile_scripts.append(home / ".zshrc")
    profile_scripts.append(home / ".profile")

    for profile in dict.fromkeys(profile_scripts):
        try:
            if profile.exists():
                content = profile.read_text(encoding="utf-8")
                if absolute_path not in content:
                    with open(profile, "a", encoding="utf-8") as f:
                        f.write(f"\n# Added by CodeQL installer\n{export_line}\n")
                    if not ci:
                        print(f"Added CodeQL CLI to {profile}", file=sys.stderr)
            else:
                profile.write_text(
                    f"# Added by CodeQL installer\n{export_line}\n",
                    encoding="utf-8",
                )
                if not ci:
                    print(f"Created {profile} with CodeQL CLI path", file=sys.stderr)
        except OSError as exc:
            print(
                f"WARNING: Failed to update {profile}: {exc}",
                file=sys.stderr,
            )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    install_path = args.install_path
    if not os.path.isabs(install_path):
        install_path = os.path.join(os.getcwd(), install_path)

    if check_codeql_installed(install_path):
        if args.force:
            if not args.ci:
                print(
                    "CodeQL CLI already installed. Reinstalling due to --force flag.",
                    file=sys.stderr,
                )
        else:
            if not args.ci:
                print(
                    f"CodeQL CLI is already installed at {install_path}",
                    file=sys.stderr,
                )
                print("Use --force to reinstall", file=sys.stderr)
            return 0

    try:
        download_url = get_download_url(args.version)
        install_codeql_cli(download_url, install_path, args.ci)
    except RuntimeError as exc:
        print(f"CodeQL CLI installation failed: {exc}", file=sys.stderr)
        error_msg = str(exc).lower()
        if any(kw in error_msg for kw in ("download", "extract", "tar", "not found")):
            return 3
        return 1

    if args.add_to_path:
        add_to_path(install_path, args.ci)

    if not check_codeql_installed(install_path):
        print(
            "Installation completed but CodeQL CLI verification failed.",
            file=sys.stderr,
        )
        return 1

    if not args.ci:
        print("\nCodeQL CLI installation complete!", file=sys.stderr)
        print(f"Location: {install_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
