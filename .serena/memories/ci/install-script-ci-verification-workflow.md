> **DEPRECATED (2026-01-17)**: This memory is historical. The PowerShell installation scripts
> and verify-install-script.yml workflow have been replaced by [skill-installer](https://github.com/rjmurillo/skill-installer).

- Added .github/workflows/verify-install-script.yml with matrix (ubuntu/macos/windows × Claude/Copilot/VSCode × Global/Repo) to run install.ps1 and verify output via scripts/tests/Verify-InstallOutput.ps1.
- Workflow uses dorny/paths-filter to skip when install-related files unchanged and sets APPDATA on non-Windows runners for VS Code path resolution.
- Verification helper script checks destination directories, agent files, prompt files, commands, instructions, skills, and repo .agents directories using Install-Common functions and Config.psd1.