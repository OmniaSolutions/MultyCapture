# Packaging MultyCapture

Two installers are produced from one PyInstaller freeze:

- **Windows** — an Inno Setup `Setup.exe`
- **Debian/Ubuntu** — a `.deb`

The app is frozen with PyInstaller so end users need **no Python** installed.

## Option A — GitHub Actions (recommended)

`.github/workflows/build-installers.yml` builds both on native runners.

- **Manual:** GitHub → *Actions* → *build-installers* → *Run workflow*. Installers
  are uploaded as workflow **artifacts**.
- **Release:** push a version tag and both installers are attached to a GitHub
  Release automatically:

  ```bash
  git tag v0.1.0
  git push origin v0.1.0
  ```

Nothing needs to be installed locally.

## Option B — build locally

### Windows (needs Inno Setup + Python 3.12)

```powershell
pip install -e ".[build]"
pyinstaller --noconfirm packaging\multycapture.spec
iscc /DMyAppVersion=0.1.0 installer\windows\multycapture.iss
```

Result: `installer\windows\Output\MultyCapture-Setup-0.1.0.exe`

### Debian/Ubuntu (needs dpkg-dev + Python 3.12, on an X11 machine)

```bash
sudo apt-get install -y dpkg-dev libxcb-cursor0
pip install -e ".[build]"
pyinstaller --noconfirm packaging/multycapture.spec
VERSION=0.1.0 ARCH=amd64 bash installer/debian/build_deb.sh
```

Result: `installer/debian/out/multycapture_0.1.0_amd64.deb`

Install / remove:

```bash
sudo apt install ./installer/debian/out/multycapture_0.1.0_amd64.deb
sudo apt remove multycapture
```

## What gets installed

| | Windows | Debian |
|--|---------|--------|
| App files | `C:\Program Files\MultyCapture\` | `/opt/multycapture/` |
| Launcher | Start Menu / optional desktop shortcut | `multycapture` on PATH + app menu entry |
| Autostart | optional (task in installer) | not by default |
| Icon | `packaging/assets/multycapture.ico` | `.../hicolor/256x256/apps/multycapture.png` |

Running the executable with no arguments opens the **tray app**; with arguments it
is the CLI (`MultyCapture record`, `MultyCapture doc`, `MultyCapture selftest`).

## Notes

- The frozen bundle verifies itself in CI via `MultyCapture selftest` (imports the
  full capture + GUI stack).
- Linux target requires an **X11** session; Wayland is detected and refused.
- The `.deb` declares the Qt/xcb runtime libraries under `Depends:`.
