#!/usr/bin/env sh
#
# Print the version. One implementation, so a packaging script cannot label a
# build with a number the application inside it does not report.
#
#   $ sh installer/version.sh
#   0.2.0
#
# Read by sed rather than by importing the package: this runs on a machine
# where MultyCapture may not be installed, and inside CI before the freeze.
# _version.py holds the string and nothing else, so the match cannot be
# broken by unrelated edits to the package.
#
set -eu

HERE="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$HERE/../src/multycapture/_version.py"

VERSION="$(sed -n 's/^VERSION = "\([^"]*\)"$/\1/p' "$SOURCE")"

if [ -z "$VERSION" ]; then
  echo "error: no VERSION assignment found in $SOURCE" >&2
  exit 1
fi

printf '%s\n' "$VERSION"
