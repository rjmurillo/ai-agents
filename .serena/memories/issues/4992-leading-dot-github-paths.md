# Issue 4992 leading-dot GitHub paths

GitHub URL path validation in github-url-intercept should allow leading-dot path segments such as `.claude/settings.json` and `.github/workflows/ci.yml`. The path regex alone is not enough to reject traversal, because valid dotfile paths start with `.`.

Use this pattern:

- allow leading dots in `SAFE_PATH_RE`
- reject decoded `.` and `..` path segments explicitly
- reject encoded traversal forms like `%2e%2e` and `.%2e`
- keep blob and tree routing tests for positive dotfile paths and negative traversal cases

Validated by direct CLI probes and targeted tests in the copied skill tree and Copilot mirror.
