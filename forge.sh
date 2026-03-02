#!/usr/bin/env bash
# Forge — Local AI Coding Assistant launcher (Linux/Mac)
# Run: chmod +x forge.sh && ./forge.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  ============================================="
echo "   FORGE — Local AI Coding Assistant"
echo "   No tokens. No compaction. No bullshit."
echo "  ============================================="
echo ""

# Use embedded venv Python
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ ! -f "$VENV_PYTHON" ]; then
    echo "  [ERROR] Venv not found. Run install.py first:"
    echo "    python3 install.py"
    exit 1
fi

PYVER=$("$VENV_PYTHON" --version 2>&1)
echo "  [OK] $PYVER (embedded venv)"

# Enable KV cache quantization and flash attention for Ollama
export OLLAMA_FLASH_ATTENTION=1
export OLLAMA_KV_CACHE_TYPE=q8_0
export OLLAMA_MAX_LOADED_MODELS=2

# Check / start Ollama
if curl -s http://localhost:11434/api/tags &>/dev/null; then
    echo "  [OK] Ollama running"
else
    echo "  [..] Starting Ollama with KV cache quantization (Q8)..."
    ollama serve &>/dev/null &
    OLLAMA_PID=$!
    TRIES=0
    while ! curl -s http://localhost:11434/api/tags &>/dev/null; do
        sleep 1
        TRIES=$((TRIES + 1))
        if [ $TRIES -ge 15 ]; then
            echo "  [ERROR] Ollama failed to start after 15 seconds."
            echo "  Install: curl -fsSL https://ollama.com/install.sh | sh"
            exit 1
        fi
    done
    echo "  [OK] Ollama started (flash_attention=ON, kv_cache=Q8, PID $OLLAMA_PID)"
fi

echo ""
echo "  Starting Forge..."
echo "  ============================================="
echo ""

"$VENV_PYTHON" -m forge "$@"
