# Deploying TRC Tally

## Portable, no-internet build (PyInstaller)

The app downloads nothing at runtime — config files are created locally on first
run and all assets (templates, static, `tally.svg`, `ColorSchemes.json`) are
bundled into the executable.

Build a single self-contained binary:

```bash
pip install -r requirements.txt pyinstaller
pyinstaller --clean -y TRC_Tally_Cloud_Client.spec
# -> dist/TRC_Tally_Cloud_Client  (or .exe on Windows)
```

The result needs no Python and no pip on the target machine. On first launch it
writes a `config.json` next to itself (edit everything from the web UI after).

### macOS, Linux and Windows together

PyInstaller **cannot cross-compile** — each binary must be built on its own OS.
Two ways to get all three:

- **GitHub Actions (recommended).** `.github/workflows/build.yml` builds on
  macOS, Linux and Windows runners. Run it manually (Actions → "Build
  executables" → Run), or push a `v*` tag (e.g. `git tag v1.0 && git push --tags`)
  to also attach the binaries to a GitHub Release. Download them from the run's
  Artifacts.
- **Locally on each machine.** Run the `pyinstaller` command above on a Mac, a
  Linux box, and a Windows PC respectively. (A VM works fine for the one you
  don't have.)

### Building on a machine with no internet

On a connected machine, pre-download the wheels, copy them over, then install
offline:

```bash
pip download -r requirements.txt pyinstaller -d wheels/      # connected machine
pip install --no-index --find-links wheels -r requirements.txt pyinstaller   # offline machine
pyinstaller TRC_Tally_Cloud_Client.spec
```

## Running on the vMix machine (recommended)

vMix's HTTP API runs locally, so the simplest, most reliable setup is to run TRC
Tally **on the same Windows PC as vMix**:

1. In vMix: Settings → Web Controller → enable it (API on port `8088`).
2. In TRC Tally, add a machine with URL `http://127.0.0.1:8088` — no network hop,
   nothing to break between boxes.
3. Open `http://localhost:8070` (or `http://<pc-ip>:8070` from another device).

Allow inbound TCP **8070** in Windows Firewall if operators connect from other
machines, and make sure the MQTT broker (`config.json` → `mqtt`) is reachable.

## Running as a Windows service

Use [NSSM](https://nssm.cc/) (simplest, auto-restart on crash, starts at boot).
A helper script is provided:

```powershell
# from an elevated PowerShell, with nssm.exe on PATH
.\windows\install-service.ps1 -ExePath "C:\TRCTally\TRC_Tally_Cloud_Client.exe"
```

Or manually:

```powershell
nssm install TRCTally "C:\TRCTally\TRC_Tally_Cloud_Client.exe"
nssm set TRCTally AppDirectory "C:\TRCTally"
nssm set TRCTally Start SERVICE_AUTO_START
nssm start TRCTally
```

`AppDirectory` matters — `config.json` is read/written there. To update config
later, edit via the web UI (the service keeps running) or stop the service,
edit, and start it again.

Alternatives: Windows Task Scheduler ("At system startup", run whether logged in
or not) or a `pywin32` service wrapper — NSSM is recommended for its built-in
crash-restart.
