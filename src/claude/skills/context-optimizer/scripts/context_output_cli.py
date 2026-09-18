"""Command-line interface for the context output extractor."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from types import ModuleType

from context_output_report import print_manifest_report


def _report_error(prefix: str, error: Exception, exit_code: int) -> int:
    """Print one CLI error and return its process exit code."""
    print(f"{prefix}: {error}", file=sys.stderr)
    return exit_code


def _build_parser(core: ModuleType) -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Extract markdown sections and generate a pipe-delimited index",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=core.__doc__,
    )
    parser.add_argument("-i", "--input", type=Path, help="Input markdown file path")
    parser.add_argument("-d", "--detail-dir", type=Path, help="Directory for extracted detail files")
    parser.add_argument("-r", "--detail-ref", help="Relative path for index references")
    parser.add_argument("-o", "--output", type=Path, help="Output index file path, default: stdout as JSON")
    parser.add_argument("--manifest", type=Path, help="Explicit JSON manifest for complete check-only validation")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--check", action="store_true", help="Check generated files without writing them")
    parser.add_argument("--staged", action="store_true", help="Read manifest inputs and outputs from the Git index")
    return parser


def _check_manifest_cli(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    core: ModuleType,
) -> int:
    """Validate the manifest and return its CLI exit code."""
    if not args.check:
        parser.error("--manifest requires --check")
    if any((args.input, args.detail_dir, args.detail_ref, args.output)):
        parser.error("--manifest cannot be combined with single-file options")
    try:
        report = core.check_manifest(args.manifest, staged=args.staged)
    except PermissionError as error:
        return _report_error("Error", error, 3)
    except RuntimeError as error:
        return _report_error("Error checking manifest", error, 3)
    except (OSError, ValueError) as error:
        return _report_error("Error reading manifest", error, 2)
    print_manifest_report(report)
    return 0 if not report.issues else 1


def _read_input(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    core: ModuleType,
) -> tuple[str, str]:
    """Validate single-file arguments and read the source document."""
    if args.input is None or args.detail_dir is None:
        parser.error("--input and --detail-dir are required without --manifest")
    if args.check and args.output is None:
        parser.error("--check requires --output")
    if not args.input.exists():
        print(f"Error: Input file not found: {args.input}", file=sys.stderr)
        raise SystemExit(1)

    try:
        resolved_input = core.validate_path_within_repo(args.input)
        content = resolved_input.read_text(encoding="utf-8")
    except PermissionError as error:
        print(f"Error: {error}", file=sys.stderr)
        raise SystemExit(3) from error
    except OSError as error:
        print(f"Error reading input file: {error}", file=sys.stderr)
        raise SystemExit(1) from error
    return content, args.detail_ref or str(args.detail_dir)


def _run_single_check(
    args: argparse.Namespace,
    content: str,
    detail_ref: str,
    core: ModuleType,
) -> int:
    """Check one generated index and its detail files."""
    try:
        issues = core.check_generated_files(content, args.detail_dir, args.output, detail_ref)
    except (PermissionError, OSError) as error:
        prefix = "Error" if isinstance(error, PermissionError) else "Error checking generated files"
        return _report_error(prefix, error, 3)

    detail_count = len(core._detail_file_contents(core.parse_sections(content)))
    print(f"Checked 1 index and {detail_count} detail files.", file=sys.stderr)
    if issues:
        print("Context output drift detected:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
    return 1 if issues else 0


def _run_generation(
    args: argparse.Namespace,
    content: str,
    detail_ref: str,
    core: ModuleType,
) -> int:
    """Generate output and return its CLI exit code."""
    try:
        result = core.extract_and_index(content, args.detail_dir, detail_ref)
    except RuntimeError as error:
        return _report_error("Error", error, 4)
    except (PermissionError, OSError) as error:
        prefix = "Error" if isinstance(error, PermissionError) else "Error extracting sections"
        return _report_error(prefix, error, 3)

    if args.output:
        try:
            resolved_output = core.validate_path_within_repo(args.output)
            resolved_output.write_text(result.index_content, encoding="utf-8")
            if args.verbose:
                print(
                    f"Index written to: {args.output}\n"
                    f"Metrics: {result.metrics.original_tokens} -> "
                    f"{result.metrics.index_tokens} tokens "
                    f"({result.metrics.reduction_percent}% reduction)",
                    file=sys.stderr,
                )
        except (PermissionError, OSError) as error:
            prefix = "Error" if isinstance(error, PermissionError) else "Error writing output file"
            return _report_error(prefix, error, 3)
    else:
        print(json.dumps(asdict(result), indent=2))
    return 0


def main(core: ModuleType) -> None:
    """Run the extractor command line using its core module."""
    parser = _build_parser(core)
    args = parser.parse_args()
    if args.staged and not args.manifest:
        parser.error("--staged requires --manifest")
    if args.manifest:
        sys.exit(_check_manifest_cli(args, parser, core))

    content, detail_ref = _read_input(args, parser, core)
    if args.verbose:
        print(f"Extracting sections from: {args.input}", file=sys.stderr)
    if args.check:
        sys.exit(_run_single_check(args, content, detail_ref, core))
    sys.exit(_run_generation(args, content, detail_ref, core))
