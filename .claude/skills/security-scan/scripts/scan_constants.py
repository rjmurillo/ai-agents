"""Exit-code constants for the security scanner (ADR-035 compliant).

Single source of truth shared by ``scan_vulnerabilities.py`` (the entry point)
and ``scan_format.py`` (console formatter). Extracted so the formatter can reference
``EXIT_VULNERABILITIES`` without importing the main module, which would create an
import cycle. The values are unchanged from the original inline definitions.

Exit codes:
    0  - No vulnerabilities found
    1  - Scan error (file not found, invalid arguments)
    10 - Vulnerabilities detected
"""

EXIT_SUCCESS = 0
EXIT_ERROR = 1
EXIT_VULNERABILITIES = 10
