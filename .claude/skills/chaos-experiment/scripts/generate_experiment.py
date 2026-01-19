#!/usr/bin/env python3
"""
Generate a chaos experiment document from the template.

Usage:
    python generate_experiment.py --name "API Gateway Resilience"
    python generate_experiment.py --name "DB Failover" --system "Payment Service" --owner "Jane"
    python generate_experiment.py --help
"""

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Result:
    """Structured result for automation."""

    success: bool
    message: str
    data: Optional[dict] = None
    errors: Optional[list] = None


def generate_experiment_id(name: str) -> str:
    """Generate a unique experiment ID from the name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    date_str = datetime.now().strftime("%Y%m%d")
    return f"chaos-{date_str}-{slug[:30]}"


def load_template() -> str:
    """Load the experiment template."""
    script_dir = Path(__file__).parent.parent
    template_path = script_dir / "templates" / "experiment-template.md"

    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    return template_path.read_text(encoding="utf-8")


def generate_document(
    name: str,
    system: str = "TBD",
    owner: str = "TBD",
    region: str = "TBD",
    target_date: Optional[str] = None,
) -> str:
    """Generate experiment document from template."""
    template = load_template()

    # Calculate dates
    now = datetime.now()
    date_created = now.strftime("%Y-%m-%d")
    if target_date is None:
        target_date = "TBD"

    # Generate ID
    experiment_id = generate_experiment_id(name)

    # Replace placeholders with provided values
    replacements = {
        "{{EXPERIMENT_NAME}}": name,
        "{{EXPERIMENT_ID}}": experiment_id,
        "{{DATE_CREATED}}": date_created,
        "{{TARGET_DATE}}": target_date,
        "{{OWNER}}": owner,
        "{{SYSTEM_NAME}}": system,
        "{{REGION}}": region,
    }

    document = template
    for placeholder, value in replacements.items():
        document = document.replace(placeholder, value)

    return document


def save_document(content: str, output_dir: Path, name: str) -> Path:
    """Save the generated document."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate filename
    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    filename = f"{date_str}-{slug[:50]}.md"
    output_path = output_dir / filename

    output_path.write_text(content, encoding="utf-8")
    return output_path


def main() -> Result:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate a chaos experiment document",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python generate_experiment.py --name "API Gateway Resilience"
    python generate_experiment.py --name "DB Failover" --system "Payment Service"
    python generate_experiment.py --name "Cache Partition" --output .agents/chaos/
        """,
    )

    parser.add_argument(
        "--name",
        required=True,
        help="Name of the chaos experiment",
    )
    parser.add_argument(
        "--system",
        default="TBD",
        help="System under test (default: TBD)",
    )
    parser.add_argument(
        "--owner",
        default="TBD",
        help="Experiment owner (default: TBD)",
    )
    parser.add_argument(
        "--region",
        default="TBD",
        help="Target region/zone (default: TBD)",
    )
    parser.add_argument(
        "--target-date",
        default=None,
        help="Target execution date (default: TBD)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".agents/chaos"),
        help="Output directory (default: .agents/chaos/)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print document without saving",
    )

    args = parser.parse_args()

    try:
        # Generate the document
        content = generate_document(
            name=args.name,
            system=args.system,
            owner=args.owner,
            region=args.region,
            target_date=args.target_date,
        )

        if args.dry_run:
            print(content)
            return Result(
                success=True,
                message="Document generated (dry run)",
                data={"content_length": len(content)},
            )

        # Save the document
        output_path = save_document(content, args.output, args.name)

        result = Result(
            success=True,
            message=f"Experiment document created: {output_path}",
            data={
                "path": str(output_path),
                "name": args.name,
                "system": args.system,
            },
        )

        if args.json:
            import json

            print(
                json.dumps(
                    {
                        "success": result.success,
                        "message": result.message,
                        "data": result.data,
                    }
                )
            )
        else:
            print(f"Created: {output_path}")

        return result

    except FileNotFoundError as e:
        result = Result(
            success=False,
            message=str(e),
            errors=[str(e)],
        )
        if args.json:
            import json

            print(
                json.dumps(
                    {
                        "success": result.success,
                        "message": result.message,
                        "errors": result.errors,
                    }
                )
            )
        else:
            print(f"Error: {e}", file=sys.stderr)
        return result

    except Exception as e:
        result = Result(
            success=False,
            message=f"Unexpected error: {e}",
            errors=[str(e)],
        )
        if args.json:
            import json

            print(
                json.dumps(
                    {
                        "success": result.success,
                        "message": result.message,
                        "errors": result.errors,
                    }
                )
            )
        else:
            print(f"Error: {e}", file=sys.stderr)
        return result


if __name__ == "__main__":
    result = main()
    sys.exit(0 if result.success else 1)
