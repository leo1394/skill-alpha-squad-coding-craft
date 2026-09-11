#!/bin/sh

set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)

if command -v python3 >/dev/null 2>&1; then
    python_command=python3
elif command -v python >/dev/null 2>&1; then
    python_command=python
else
    printf '%s\n' 'Error: Python 3 is required to install this plugin.' >&2
    exit 1
fi

exec "$python_command" "$script_dir/scripts/install_codex.py" "$@"
