#!/bin/sh
# Set up the DrivnX workspace on macOS or Linux:
#   curl -fsSL https://raw.githubusercontent.com/trisonlab/drivnx-cli/main/get.sh | sh
# Creates ~/DrivnX (or $DRIVNX_HOME), clones drivnx-cli into it and runs `drivnx install`.
set -eu

ws="${DRIVNX_HOME:-$HOME/DrivnX}"
command -v git >/dev/null 2>&1 || { echo "Install git first: https://git-scm.com/downloads" >&2; exit 1; }
py="$(command -v python3 || true)"
if [ -z "$py" ] || ! "$py" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  echo "Install Python 3.10 or newer first: https://www.python.org/downloads/" >&2
  exit 1
fi

mkdir -p "$ws"
if [ -d "$ws/drivnx-cli/.git" ]; then
  git -C "$ws/drivnx-cli" pull --ff-only --quiet
else
  git clone --quiet https://github.com/trisonlab/drivnx-cli.git "$ws/drivnx-cli"
fi

# Piped into sh, stdin is this script: give `drivnx install` the terminal so it can ask questions.
if [ -t 1 ] && (exec </dev/tty) 2>/dev/null; then
  exec "$py" "$ws/drivnx-cli/drivnx" install "$@" </dev/tty
else
  exec "$py" "$ws/drivnx-cli/drivnx" install "$@"
fi
