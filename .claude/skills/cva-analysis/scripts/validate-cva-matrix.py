#!/usr/bin/env python3
"""
CVA Matrix Validation Script

Checks CVA matrix completeness and suggests patterns based on structure.

Exit Codes:
    0: Valid matrix, patterns suggested
    10: Validation failure (missing rows/columns, empty cells)
    1: Error (file not found, invalid format)

Usage:
    python3 validate-cva-matrix.py cva-matrix.md
    python3 validate-cva-matrix.py cva-matrix.md --verbose
"""

import argparse
import sys
from dataclasses import dataclass
from enum import Enum


class ValidationResult(Enum):
    VALID = 0
    VALIDATION_FAILURE = 10
    ERROR = 1


@dataclass
class CVAMatrix:
    """Represents a CVA matrix extracted from Markdown."""
    rows: list[str]  # Commonalities
    columns: list[str]  # Variabilities
    cells: list[list[str]]  # Matrix content

    def row_count(self) -> int:
        return len(self.rows)

    def column_count(self) -> int:
        return len(self.columns)

    def has_empty_cells(self) -> bool:
        for row in self.cells:
            for cell in row:
                if not cell or cell.strip() in ['', '-', 'TBD', 'TODO']:
                    return True
        return False

    def calculate_row_variability(self) -> float:
        """Calculate how much rows vary (0.0 = no variability, 1.0 = all different)."""
        if not self.cells:
            return 0.0

        total_cells = sum(len(row) for row in self.cells)
        unique_cells = 0

        for row in self.cells:
            unique_values = len(set(row))
            if unique_values > 1:
                unique_cells += unique_values

        return unique_cells / total_cells if total_cells > 0 else 0.0

    def calculate_column_variability(self) -> float:
        """Calculate how much columns vary (0.0 = no variability, 1.0 = all different)."""
        if not self.cells or not self.cells[0]:
            return 0.0

        num_cols = len(self.cells[0])
        num_rows = len(self.cells)
        total_cells = num_rows * num_cols
        unique_cells = 0

        for col_idx in range(num_cols):
            column_values = [self.cells[row_idx][col_idx] for row_idx in range(num_rows)]
            unique_values = len(set(column_values))
            if unique_values > 1:
                unique_cells += unique_values

        return unique_cells / total_cells if total_cells > 0 else 0.0


def parse_markdown_table(content: str) -> CVAMatrix | None:
    """
    Extract CVA matrix from Markdown table.

    Expected format:
    | Commonality | Var1 | Var2 | Var3 |
    |-------------|------|------|------|
    | Common1     | A1   | B1   | C1   |
    | Common2     | A2   | B2   | C2   |
    """
    lines = content.split('\n')

    # Find first table
    table_lines = []
    in_table = False

    for line in lines:
        if line.strip().startswith('|'):
            in_table = True
            table_lines.append(line.strip())
        elif in_table and not line.strip().startswith('|'):
            break

    if len(table_lines) < 3:  # Header + separator + at least one data row
        return None

    # Parse header (columns)
    header_cells = [cell.strip() for cell in table_lines[0].split('|')[1:-1]]
    if not header_cells:
        return None

    # First column is "Commonality" label, rest are variabilities
    columns = header_cells[1:]  # Skip first column header

    # Skip separator line (table_lines[1])

    # Parse data rows
    rows = []
    cells = []

    for line in table_lines[2:]:
        row_cells = [cell.strip() for cell in line.split('|')[1:-1]]
        if row_cells:
            rows.append(row_cells[0])  # First cell is commonality name
            cells.append(row_cells[1:])  # Rest are data cells

    return CVAMatrix(rows=rows, columns=columns, cells=cells)


def validate_matrix(matrix: CVAMatrix) -> tuple[bool, list[str]]:
    """
    Validate CVA matrix structure and completeness.

    Returns:
        (is_valid, issues)
    """
    issues = []

    # Check minimum dimensions (2x2 for pattern discovery)
    if matrix.row_count() < 2:
        issues.append(f"Matrix has only {matrix.row_count()} row(s). Need ≥2 commonalities for pattern discovery.")

    if matrix.column_count() < 2:
        issues.append(f"Matrix has only {matrix.column_count()} column(s). Need ≥2 variabilities for pattern discovery.")

    # Check for empty cells
    if matrix.has_empty_cells():
        issues.append("Matrix has empty cells. All cells must be filled with concrete implementations.")

    # Check for dimension mismatch
    for idx, row in enumerate(matrix.cells):
        if len(row) != matrix.column_count():
            issues.append(f"Row {idx + 1} has {len(row)} cells, expected {matrix.column_count()}.")

    return len(issues) == 0, issues


def suggest_patterns(matrix: CVAMatrix) -> list[str]:
    """
    Suggest design patterns based on matrix structure.

    Heuristics:
    - High row variability → Strategy pattern
    - High column variability → Abstract Factory pattern
    - Both high → Combination patterns
    - Both low → Consider not abstracting (YAGNI)
    """
    suggestions = []

    row_var = matrix.calculate_row_variability()
    col_var = matrix.calculate_column_variability()

    # Thresholds
    HIGH_VAR = 0.6
    MEDIUM_VAR = 0.3

    if row_var < MEDIUM_VAR and col_var < MEDIUM_VAR:
        suggestions.append("⚠️  LOW VARIABILITY: Matrix shows minimal variation.")
        suggestions.append("   Consider NOT abstracting (YAGNI). Document rationale in ADR.")
        suggestions.append(f"   Row variability: {row_var:.2f}, Column variability: {col_var:.2f}")

    if row_var >= HIGH_VAR and col_var < MEDIUM_VAR:
        suggestions.append("✓ PRIMARY PATTERN: Strategy Pattern")
        suggestions.append("  Rationale: High row variability (operations vary across use cases)")
        suggestions.append(f"  Row variability: {row_var:.2f} (high)")
        suggestions.append("  Each row (commonality) can be a strategy with multiple implementations.")

    if col_var >= HIGH_VAR and row_var < MEDIUM_VAR:
        suggestions.append("✓ PRIMARY PATTERN: Abstract Factory Pattern")
        suggestions.append("  Rationale: High column variability (coherent product families)")
        suggestions.append(f"  Column variability: {col_var:.2f} (high)")
        suggestions.append("  Each column represents a family of related implementations.")

    if row_var >= HIGH_VAR and col_var >= HIGH_VAR:
        suggestions.append("✓ COMBINATION PATTERNS: Strategy + Abstract Factory")
        suggestions.append("  Rationale: High variability in BOTH dimensions (multidimensional)")
        suggestions.append(f"  Row variability: {row_var:.2f} (high), Column variability: {col_var:.2f} (high)")
        suggestions.append("  Start with dominant axis, note multidimensional case in Extension Points.")

    if row_var >= MEDIUM_VAR and row_var < HIGH_VAR:
        suggestions.append("⚠️  MEDIUM ROW VARIABILITY: Consider Strategy pattern")
        suggestions.append(f"  Row variability: {row_var:.2f} (medium)")
        suggestions.append("  Evaluate if abstraction overhead is justified.")

    if col_var >= MEDIUM_VAR and col_var < HIGH_VAR:
        suggestions.append("⚠️  MEDIUM COLUMN VARIABILITY: Consider Abstract Factory pattern")
        suggestions.append(f"  Column variability: {col_var:.2f} (medium)")
        suggestions.append("  Evaluate if family cohesion justifies factory pattern.")

    return suggestions


def main():
    parser = argparse.ArgumentParser(
        description='Validate CVA matrix completeness and suggest patterns'
    )
    parser.add_argument('matrix_file', help='Path to CVA matrix markdown file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    # Validate input path to prevent path traversal (CWE-22)
    import os
    try:
        allowed_base = os.path.abspath(".")
        matrix_file_path = os.path.abspath(args.matrix_file)
        if not matrix_file_path.startswith(allowed_base):
            raise ValueError(
                f"Path traversal attempt detected in matrix_file: "
                f"{args.matrix_file}"
            )
    except ValueError as e:
        print(f"❌ ERROR: {e}", file=sys.stderr)
        return ValidationResult.ERROR.value

    # Read file
    try:
        with open(matrix_file_path, encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"❌ ERROR: File not found: {matrix_file_path}", file=sys.stderr)
        return ValidationResult.ERROR.value
    except Exception as e:
        print(f"❌ ERROR: Failed to read file: {e}", file=sys.stderr)
        return ValidationResult.ERROR.value

    # Parse matrix
    matrix = parse_markdown_table(content)
    if matrix is None:
        print("❌ ERROR: Failed to parse CVA matrix from file", file=sys.stderr)
        print("Expected Markdown table format:", file=sys.stderr)
        print("| Commonality | Var1 | Var2 |", file=sys.stderr)
        print("|-------------|------|------|", file=sys.stderr)
        print("| Common1     | A1   | B1   |", file=sys.stderr)
        return ValidationResult.ERROR.value

    if args.verbose:
        print("\n📊 CVA Matrix Dimensions:")
        print(f"   Rows (commonalities): {matrix.row_count()}")
        print(f"   Columns (variabilities): {matrix.column_count()}")
        print(f"   Total cells: {matrix.row_count() * matrix.column_count()}")

    # Validate matrix
    is_valid, issues = validate_matrix(matrix)

    if not is_valid:
        print("\n❌ VALIDATION FAILED", file=sys.stderr)
        print("\nIssues found:", file=sys.stderr)
        for issue in issues:
            print(f"  • {issue}", file=sys.stderr)
        return ValidationResult.VALIDATION_FAILURE.value

    # Suggest patterns
    print("\n✓ VALIDATION PASSED")
    print(f"\nMatrix: {matrix.row_count()} commonalities × {matrix.column_count()} variabilities")

    patterns = suggest_patterns(matrix)
    if patterns:
        print("\n📐 PATTERN RECOMMENDATIONS:\n")
        for pattern in patterns:
            print(pattern)

    print("\n✓ Next Steps:")
    print("  1. Review pattern recommendations with team")
    print("  2. Route to decision-critic: /decision-critic \"Validate [pattern] per CVA\"")
    print("  3. Create ADR with architect agent")
    print("  4. Document reassessment triggers")

    return ValidationResult.VALID.value


if __name__ == '__main__':
    sys.exit(main())
