#!/usr/bin/env bash
# Forge Adaptive Nightly Tests — Linux/macOS wrapper
#
# Schedule via cron:
#   0 3 * * * /path/to/Forge/scripts/nightly.sh
#
# All arguments forwarded to nightly_smart.py:
#   ./nightly.sh --full-sweep
#   ./nightly.sh --dry-run
#   ./nightly.sh --max-duration 30

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

if [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
elif [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON=".venv/Scripts/python.exe"
else
    echo "ERROR: No .venv found. Run install.py first."
    exit 1
fi

$PYTHON scripts/nightly_smart.py "$@"
