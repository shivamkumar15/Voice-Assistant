#!/usr/bin/env bash
# Launch Ninja with the project virtualenv, so voice dependencies resolve
# even when the shell has not run `source .venv/bin/activate`.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
    echo "No .venv found. Create it first:" >&2
    echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

exec .venv/bin/python ninja.py "$@"
