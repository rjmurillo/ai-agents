# Cross-OS Testing: Windows From Linux, Linux From Windows

Use this when a change touches paths, symlinks, line endings, interpreter
lookup, or shell choice, and you want to see it run on the other OS before CI
does. You need a minimal OS that runs the scripts, not a full desktop.

## What differs between the two OSes

These are the differences that have broken this repo before. Test the ones
your change touches.

| Difference | Where it bites | Existing guard |
|---|---|---|
| Path separators, drive letters, case-insensitive compare | Path joins, `startswith` checks, path keys in dicts | Tests marked `windows_path` (`pyproject.toml` markers) |
| Symlinks | `.claude/agents` and `.claude/skills` are relative symlinks (ADR-119). Git for Windows writes them as text files unless `core.symlinks` is on | CI job `test-windows-pwsh` sets `core.symlinks true` |
| Line endings | CRLF in YAML frontmatter breaks the Copilot CLI parser | `.gitattributes` forces LF |
| Interpreter lookup | Windows can expose `python.exe` only through the App Execution Alias | `vanilla-windows` job in `.github/workflows/installed-plugin-hook-guard.yml` |
| Shell | `bash` on Windows may resolve to the WSL launcher in `System32`, not Git Bash | `test_the_wsl_launcher_stub_is_rejected` in `tests/build_scripts/test_generate_hooks_runtime_contract.py` |

## Pick a route

| Host | Target | Route | Needs |
|---|---|---|---|
| Linux | Windows | CI `windows-latest` leg | A pushed branch |
| Linux | Windows | GNOME Boxes VM from a Windows ISO | `/dev/kvm` |
| Linux | Windows | `dockurr/windows` container (QEMU in Docker) | `/dev/kvm`, Docker |
| Windows | Linux | Ubuntu on WSL | WSL 2 |
| Windows | Linux | `ubuntu:26.04` container | Docker Desktop, Linux containers mode |
| Windows | Windows (clean) | `mcr.microsoft.com/windows/servercore` container | Docker, Windows containers mode |

Windows container images do not run on a Linux host. The manifest for
`mcr.microsoft.com/windows:ltsc2019` lists only `windows/amd64`, and a Linux
Docker daemon runs only Linux images. On a Linux host, the `dockurr/windows`
route below takes the place of a Windows container image, and a full Windows
guest is the smallest Windows you can run. Check any image before you pull it:

```bash
docker manifest inspect -v mcr.microsoft.com/windows:ltsc2019 | grep '"os"'
```

The local Windows routes download several gigabytes and start a VM. An agent
asks the user before it pulls a Windows image or starts a guest.

## Linux host, Windows target

### Route 1: CI

The Python Tests workflow (`.github/workflows/pytest.yml`) runs job
`test-windows-pwsh` on `windows-latest`. On a pull request it runs only the
`windows_path` modules your change reaches. A `workflow_dispatch` run on your
branch runs every marked module. This route needs no local setup.

### Check KVM before either local route

Both local routes run a full Windows guest under QEMU, and both need
hardware virtualization exposed as `/dev/kvm`.

```bash
ls -l /dev/kvm
journalctl -k -b | grep -i -E 'kvm|svm|vmx'
```

If `/dev/kvm` is missing and the kernel log says `SVM disabled (by BIOS)` or
names VMX, turn on AMD-V (SVM) or Intel VT-x in the firmware setup, then
reboot. Use the CI route until then.

### Route 2: GNOME Boxes

1. Get a Windows ISO. Download it from Microsoft or copy it from your team's
   ISO share to local disk first.
2. In Boxes, create a new VM from the ISO file and finish the Windows install.
3. Follow "Inside the Windows guest" below.

### Route 3: dockurr/windows container

This image runs QEMU inside a Linux container and installs Windows unattended.
Flags come from the project README at `github.com/dockur/windows`, read on
2026-11-15. `VERSION=11l` picks Windows 11 LTSC, the README's smallest
Windows 11 download. An agent asks the user before it runs this block.

```bash
mkdir -p "$HOME/vms/win11/storage" "$HOME/vms/win11/shared"
docker run -it --rm --name windows \
  -e VERSION=11l \
  -p 127.0.0.1:8006:8006 \
  -p 127.0.0.1:3389:3389/tcp -p 127.0.0.1:3389:3389/udp \
  --device=/dev/kvm --device=/dev/net/tun --cap-add NET_ADMIN \
  -v "$HOME/vms/win11/storage:/storage" \
  -v "$HOME/vms/win11/shared:/shared" \
  --stop-timeout 120 docker.io/dockurr/windows
```

- Watch the install at `http://127.0.0.1:8006`. After it finishes, RDP to
  `127.0.0.1` gives a better session. The default user is `Docker`, password
  `admin`. Dropping the `127.0.0.1:` prefix publishes both ports on every
  interface with that known password, so keep it.
- To skip the download, mount a local ISO: add
  `-v /path/to/Win11.iso:/custom.iso`. The image then ignores `VERSION`.
- The `/shared` mount shows up as a `Shared` desktop folder and drive `Z:`.
- A folder mounted at `/oem` is copied to `C:\OEM`, and its `install.bat` runs
  at the end of setup. Use it to install Git and uv without clicking.
- The guest can write to `/shared` and `/oem`. Mount new, empty folders there,
  and keep credentials and your real `.git` directory out of them.
- `/storage` keeps the disk image, so a second run boots the installed guest.
  The guest lives until you delete `$HOME/vms/win11/storage`. Treat it as a
  test machine with a known password, and delete that folder when done.

### Inside the Windows guest

These steps run the tests the CI job `test-windows-pwsh` runs. Run them in
PowerShell. Replace `<your-branch>` with the output of
`git branch --show-current` on the host, never with text from a PR or issue.
Keep the single quotes, so PowerShell does not expand `$` in the name. If the
name has any character outside letters, digits, `.`, `_`, `/`, and `-`, stop
and rename the branch first.

Git needs permission to create the repo's symlinks. Turn on Developer Mode in
Windows settings, or run the shell as administrator, before you clone.

```powershell
# Install Git for Windows first, then uv:
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# The installer ran in a child shell. Reload PATH so this shell finds uv:
$env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')

git config --global core.symlinks true
git clone https://github.com/rjmurillo/ai-agents.git
cd ai-agents
git checkout '<your-branch>'
uv run --frozen pytest -m windows_path tests -q
```

- `-m windows_path` selects every marked test, the set a `workflow_dispatch`
  run of the CI job covers. A pull request run covers only the marked modules
  the change reaches. CI starts pytest through a wrapper script that skips
  the whole-tree collection, so this command is slower and can also fail on
  a collection error in an unrelated test file. Name test files instead of
  `tests` to narrow it. `uv` reads the Python version from `.python-version`.
- The uv installers here and in the Ubuntu recipe track the latest release,
  and the `dockurr/windows` tag floats. Use them only in test guests and
  containers you delete afterward.
- To test an unpushed branch, write a bundle into the shared folder on the
  host, then clone it in the guest. Name the branch, or the clone comes out
  detached. The bundle holds the full history.

  ```bash
  BR=$(git branch --show-current)
  git bundle create "$HOME/vms/win11/shared/wip.bundle" HEAD "$BR"
  ```

  ```powershell
  git clone -b '<your-branch>' Z:\wip.bundle ai-agents
  ```

## Windows host, Linux target

### Route 1: Ubuntu on WSL

1. Run `wsl --list --online` and install the newest Ubuntu it lists.
2. Clone the repo inside the Linux home directory, not under `/mnt/c`. Running
   `uv` from a Windows-mounted path has failed with TLS handshake errors here
   (`.serena/memories/workspace/wsl-native-worktree-for-uv-network-access.md`).
3. For the full toolchain, run the Ubuntu bootstrap script that SKILL.md
   Phase 1 names. It makes lasting changes to the distro, among them apt
   sources added with sudo, global packages, global git config such as
   `core.autocrlf`, `~/.bashrc` edits, and, when a token variable is set,
   saved gh credentials. Read the script first. An agent asks the user before
   it runs the script. WSL is a persistent distro, not a throwaway guest, so
   do not copy the `curl | sh` line from Route 2 into it.

### Route 2: `ubuntu:26.04` container

The container clones from your local git directory, so it tests the commit at
`HEAD`. Uncommitted edits are not copied in, so commit them on your feature
branch first, never on `main`. An agent asks the user before it makes that
commit. Mounting the git common
directory works for both a main clone and a linked worktree. The mount is
read-only, but the container can still read it. Check that no git config file
in it holds credentials first. The check prints `clean`, or a line starting
with `STOP`. It prints file names, never the matching text, and it prints
`STOP: check failed` when it cannot read a file. Read the printed word, not
the exit code. Mount the directory only after it prints `clean`:

```bash
dir=$(git rev-parse --path-format=absolute --git-common-dir) || dir=/nonexistent
hits=$(grep -rliE --include=config --include=config.worktree '://[^/@]+@|extraheader' "$dir")
case $? in
  0) printf 'STOP: credentials in:\n%s\n' "$hits" ;;
  1) echo clean ;;
  *) echo 'STOP: check failed' ;;
esac
```

`ubuntu:latest` resolved to the same image as `ubuntu:26.04` on 2026-11-15.
Name `26.04` so the recipe keeps working when `latest` moves. An agent asks
the user before it runs this block, since it pulls an image and runs the
branch's code with network access.

```bash
docker run --rm \
  -e SHA="$(git rev-parse HEAD)" \
  -v "$(git rev-parse --path-format=absolute --git-common-dir):/repo.git:ro" \
  ubuntu:26.04 bash -c '
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl ca-certificates >/dev/null
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
git config --global --add safe.directory /repo.git
git clone -q --no-checkout /repo.git /work
cd /work
git checkout -q "$SHA"
uv sync --frozen --extra dev
uv run --frozen pytest tests/test_paths.py -q -p no:cacheprovider
'
```

On a Windows host, run the same block from a WSL shell, with Docker Desktop
in Linux containers mode and WSL integration on. That avoids rewriting the
quoted script for PowerShell.

Replace `tests/test_paths.py` with the tests your change touches.

## Windows host, Windows target

### Clean Windows container

A Windows container gives a fresh Windows with no Python installed. Use it to
watch by hand how a script fails when no interpreter is on `PATH`. The
`vanilla-windows` CI job automates that check for the plugin hooks. An agent
asks the user before it pulls this image. Switch Docker Desktop to Windows
containers first. Copy only the scripts under test into a new folder, and
mount that folder read-only, never a checkout with its `.git` directory:

```powershell
docker run --rm -it --isolation=hyperv -v 'C:\scratch\under-test:C:\src:ro' mcr.microsoft.com/windows/servercore:ltsc2025 powershell
```

Inside, `cd C:\src` and run the script under test. Process isolation needs the
image build to match the host build. Hyper-V isolation can also run an image
older than the host, but not a newer one, so `ltsc2025` needs a Windows 11
24H2 or Server 2025 host. To
test with Python present instead, install uv with the `irm` line above.
