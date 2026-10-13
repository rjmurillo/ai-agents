# Export Specification

## 1. Behavior

An export request returns a CSV file with a header row.
Requests above 10000 rows return error EXPORT_TOO_LARGE with HTTP status 413.
Only members of the Admin role may export. Other roles receive HTTP status 403.

## 2. Idempotency

Repeating an export request with the same request id returns the original file.
Two writers updating the same export record: the later write wins by version number.
