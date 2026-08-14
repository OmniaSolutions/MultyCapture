#!/usr/bin/env bash
#
# Decide what version a CI build carries, and refuse to build a release whose
# tag disagrees with the application.
#
# A tag is a claim about what is inside the artefact. Nothing enforced that
# claim: the number reached the .deb and the .iss from the command line while
# the application kept stamping session.json from multycapture.__version__, so
# a release could — and did — ship labelled as something it was not. Tagging
# without bumping is a one-line mistake made weeks after the code was written,
# which is exactly the kind CI should catch.
#
# On a tag  : the tag must equal __version__, or this fails.
# Otherwise : __version__, so a branch build is labelled honestly.
#             (GITHUB_REF_NAME is the *branch* off a tag, so the old
#             "${GITHUB_REF_NAME#v}" produced installers versioned "main".)
#
set -euo pipefail

MODULE="$(sh installer/version.sh)"

if [ "${GITHUB_REF_TYPE:-branch}" = "tag" ]; then
  TAG="${GITHUB_REF_NAME#v}"
  if [ "$TAG" != "$MODULE" ]; then
    echo "::error::tag v${TAG} does not match VERSION ${MODULE}." \
         "Bump src/multycapture/_version.py and re-tag." >&2
    exit 1
  fi
  VERSION="$TAG"
else
  VERSION="$MODULE"
fi

echo "building version ${VERSION}"
echo "version=${VERSION}" >> "${GITHUB_OUTPUT:-/dev/stdout}"
