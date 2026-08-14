#!/usr/bin/env bash
#
# Run the test suite -- or the whole installer build -- on a Windows VirtualBox
# guest, from this Linux host, against the working tree you are editing here.
#
# Why: parts of this project only exist on Windows. QSettings lives in the
# registry rather than a file, the Documents folder can be redirected into
# OneDrive, and POSIX permission bits are absent -- that last one is what broke
# CI in 9e00ae5. GitHub Actions covers all of it and remains the authority;
# this is the short loop, minutes instead of a CI round trip.
#
#   bash tools/win-vm/check.sh                        # the suite
#   bash tools/win-vm/check.sh tests/test_ai.py -q    # part of it
#   bash tools/win-vm/check.sh --build                # tests, freeze, installer
#
# Configure with environment variables, or tools/win-vm/vm.conf if you prefer
# a file (gitignored -- it is not committed and must not be):
#
#   VM             VirtualBox VM name           (default: SidelDevMachine)
#   VM_USER        Windows account              (default: uomnia)
#   VM_PASS_FILE   file holding its password    (default: ~/.mc-vm-pass, mode 0600)
#   SHARE          shared folder name           (default: workspace)
#   SHARE_HOST     what that share points at    (default: /media/OneTDisk/workspace)
#   VM_START       1 to start the VM if it is powered off (default: no)
#
# What this does NOT do: install anything in the guest, change the VM's saved
# configuration, or write outside %USERPROFILE%\mc-test and %USERPROFILE%\mc-venv
# in the guest. The one exception is --build, which copies the finished
# installer back into dist-win/ here.
#
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

# shellcheck source=/dev/null
[ -f "$HERE/vm.conf" ] && . "$HERE/vm.conf"

VM="${VM:-SidelDevMachine}"
VM_USER="${VM_USER:-uomnia}"
VM_PASS_FILE="${VM_PASS_FILE:-$HOME/.mc-vm-pass}"
SHARE="${SHARE:-workspace}"
SHARE_HOST="${SHARE_HOST:-/media/OneTDisk/workspace}"
VM_START="${VM_START:-0}"

die() { echo "error: $*" >&2; exit 1; }
say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

# --------------------------------------------------------------------------- #
# preflight -- each of these fails confusingly later if left to chance
# --------------------------------------------------------------------------- #
command -v VBoxManage >/dev/null || die "VBoxManage is not installed"
VBoxManage showvminfo "$VM" >/dev/null 2>&1 || die "no such VM: $VM"
[ -f "$VM_PASS_FILE" ] || die "no password file at $VM_PASS_FILE.
  Create it with:  umask 077; printf '%%s' 'THEPASSWORD' > $VM_PASS_FILE
  (VBoxManage guestcontrol has no passwordless mode.)"

# A password readable by every account on this machine is worth one line to
# catch. Not fatal -- it is the user's file and their call.
perms="$(stat -c %a "$VM_PASS_FILE")"
[ "$perms" = "600" ] || echo "warning: $VM_PASS_FILE is mode $perms; 600 would be better" >&2

# Where the repo sits inside the shared folder, so this keeps working if the
# checkout moves within it.
case "$REPO" in
  "$SHARE_HOST"/*) rel="${REPO#"$SHARE_HOST"/}" ;;
  *) die "this repo ($REPO) is not inside the shared folder $SHARE_HOST.
  The guest reaches the source through that share; set SHARE_HOST, or share
  the directory the repo actually lives in." ;;
esac

if ! VBoxManage list runningvms | grep -q "\"$VM\""; then
  if [ "$VM_START" = "1" ]; then
    say "starting $VM (headless)"
    VBoxManage startvm "$VM" --type headless >/dev/null
    say "waiting for a logged-in session (up to 5 minutes)"
    deadline=$(( $(date +%s) + 300 ))
    until VBoxManage guestproperty get "$VM" /VirtualBox/GuestInfo/OS/LoggedInUsers 2>/dev/null \
          | grep -qE 'Value: [1-9]'; do
      [ "$(date +%s)" -lt "$deadline" ] || die "the guest never reported a logged-in user.
  guestcontrol cannot type at the login screen, so the account has to log in by
  itself, and Guest Additions must be running."
      sleep 5
    done
  else
    die "$VM is not running. Start it, or re-run with VM_START=1.
  It is left alone by default because it is a machine you use for other work."
  fi
fi

# --------------------------------------------------------------------------- #
# hand off to the guest
# --------------------------------------------------------------------------- #
# UNC rather than the auto-mounted Y: on purpose. Drive mappings belong to an
# interactive logon session; guestcontrol opens a different one, where Y: does
# not necessarily exist but \\VBoxSvr\<share> always resolves.
#
# The path deliberately contains no spaces, so nothing here needs quoting that
# cmd would have to re-parse. That is the whole trick: every command that failed
# against this guest failed on quotes mangled between bash, VBoxManage and cmd.
# The quotes below are bash's own and are consumed by bash. All the real logic
# lives in guest-run.cmd, where no such escaping layer exists.
guest_script="\\\\VBoxSvr\\$SHARE\\$(echo "$rel" | tr '/' '\\')\\tools\\win-vm\\guest-run.cmd"

mode="test"
if [ "${1:-}" = "--build" ]; then
  mode="build"
  shift
fi

say "$VM: $mode"
echo "   guest script: $guest_script"

set +e
VBoxManage guestcontrol "$VM" run \
  --username "$VM_USER" --passwordfile "$VM_PASS_FILE" \
  --exe 'C:\Windows\System32\cmd.exe' --wait-stdout --wait-stderr \
  -- cmd.exe /c "$guest_script" "$mode" "$@"
status=$?
set -e

if [ "$status" = 0 ]; then
  say "OK on $VM"
else
  say "FAILED on $VM (exit $status)"
fi
exit "$status"
