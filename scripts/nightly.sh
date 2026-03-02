#!/usr/bin/env bash
# Forge Nightly Stress Tests
#
# Runs --full (1 iteration) and --soak (1 iteration) against real Ollama.
# Schedule via Task Scheduler (Windows) or cron (Linux).
#
# Windows Task Scheduler setup:
#   Program: C:\Users\theup\Desktop\Forge\.venv\Scripts\python.exe
#   Arguments: scripts/nightly.sh  (or use the .bat wrapper below)
#   Start in: C:\Users\theup\Desktop\Forge
#   Trigger: Daily at 3:00 AM
#
# Or use the companion nightly.bat for Windows Task Scheduler.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Detect venv python
if [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON=".venv/Scripts/python.exe"
elif [ -f ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
else
    echo "ERROR: No .venv found. Run install.py first."
    exit 1
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="$HOME/.forge/nightly_logs"
mkdir -p "$LOG_DIR"

echo "============================================"
echo "  Forge Nightly Stress Test — $TIMESTAMP"
echo "============================================"

# Phase 1: Full suite (5 live scenarios, ~35 min)
echo ""
echo "[1/2] Running --live --full (1 iteration)..."
$PYTHON scripts/run_live_stress.py --live --full -n 1 \
    2>&1 | tee "$LOG_DIR/nightly_full_${TIMESTAMP}.log"
FULL_EXIT=$?

# Phase 2: Soak test (endurance + context storm, ~15 min)
echo ""
echo "[2/2] Running --live --soak (1 iteration)..."
$PYTHON scripts/run_live_stress.py --live --soak -n 1 \
    2>&1 | tee "$LOG_DIR/nightly_soak_${TIMESTAMP}.log"
SOAK_EXIT=$?

# Summary
echo ""
echo "============================================"
echo "  Nightly Complete — $TIMESTAMP"
echo "  Full:  $([ $FULL_EXIT -eq 0 ] && echo 'PASS' || echo 'FAIL')"
echo "  Soak:  $([ $SOAK_EXIT -eq 0 ] && echo 'PASS' || echo 'FAIL')"
echo "  Logs:  $LOG_DIR"
echo "============================================"

# Regenerate dashboard
$PYTHON scripts/view_stress_results.py --no-open 2>/dev/null || true

# Exit with failure if either failed
[ $FULL_EXIT -eq 0 ] && [ $SOAK_EXIT -eq 0 ]
