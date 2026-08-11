#!/usr/bin/env bash
#
# Build a MultyCapture .deb from the PyInstaller one-folder bundle.
#
# Prerequisites (on a Debian/Ubuntu machine):
#   - dpkg-deb (package: dpkg-dev)
#   - dist/MultyCapture/ produced by:  pyinstaller --noconfirm packaging/multycapture.spec
#
# Usage:
#   VERSION=0.1.0 ARCH=amd64 bash installer/debian/build_deb.sh
#
set -euo pipefail

VERSION="${VERSION:-0.1.0}"
ARCH="${ARCH:-amd64}"
MAINTAINER="${MAINTAINER:-MultyCapture <noreply@example.com>}"

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
DIST="$ROOT/dist/MultyCapture"
PKG="$HERE/pkgroot"
OUT="$HERE/out"

if [ ! -d "$DIST" ]; then
  echo "error: $DIST not found. Run PyInstaller first:" >&2
  echo "  pyinstaller --noconfirm packaging/multycapture.spec" >&2
  exit 1
fi

echo ">> Laying out package tree"
rm -rf "$PKG"
install -d "$PKG/opt/multycapture"
install -d "$PKG/usr/bin"
install -d "$PKG/usr/share/applications"
install -d "$PKG/usr/share/icons/hicolor/256x256/apps"
install -d "$PKG/DEBIAN"

# Application bundle
cp -a "$DIST/." "$PKG/opt/multycapture/"

# Launcher on PATH
cat > "$PKG/usr/bin/multycapture" <<'EOF'
#!/bin/sh
exec /opt/multycapture/MultyCapture "$@"
EOF
chmod 0755 "$PKG/usr/bin/multycapture"

# Desktop entry + icon
install -m 0644 "$HERE/multycapture.desktop" "$PKG/usr/share/applications/multycapture.desktop"
install -m 0644 "$ROOT/packaging/assets/multycapture.png" \
  "$PKG/usr/share/icons/hicolor/256x256/apps/multycapture.png"

# Control metadata
INSTALLED_KB="$(du -sk "$PKG/opt" | cut -f1)"
cat > "$PKG/DEBIAN/control" <<EOF
Package: multycapture
Version: ${VERSION}
Section: utils
Priority: optional
Architecture: ${ARCH}
Maintainer: ${MAINTAINER}
Installed-Size: ${INSTALLED_KB}
Depends: libxcb1, libxcb-cursor0, libxkbcommon-x11-0, libegl1, libglib2.0-0, libfontconfig1, libdbus-1-3
Description: Fast-track screencasts into step-by-step documentation
 MultyCapture records every mouse click and keystroke, each with a screenshot and
 the active window's context, then condenses that stream into numbered steps and
 exports a Word (.docx) document.
 .
 Requires an X11 session (Wayland is detected and refused).
EOF

# Post-install: refresh desktop & icon caches (best-effort)
cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
  gtk-update-icon-cache -q /usr/share/icons/hicolor || true
fi
exit 0
EOF
chmod 0755 "$PKG/DEBIAN/postinst"

echo ">> Building .deb"
mkdir -p "$OUT"
DEB="$OUT/multycapture_${VERSION}_${ARCH}.deb"
# xz, not the modern dpkg-deb default (zstd): dpkg only learned to read
# zstd members in 1.21.18, so a zstd .deb built on ubuntu-latest cannot be
# installed on Debian 11/12 or Ubuntu 20.04. xz is understood everywhere.
dpkg-deb --root-owner-group -Zxz --build "$PKG" "$DEB"

echo ">> Done: $DEB"
dpkg-deb --info "$DEB" | sed 's/^/   /'
