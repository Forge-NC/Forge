# Forge

Local AI coding assistant powered by Ollama. Runs entirely on your machine — no cloud, no telemetry, no API keys. Manages its own context window with automatic swap/summarize, tracks security threats, records forensic audit logs, and keeps a billing ledger for token usage.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally
- 8GB+ VRAM recommended (works with less, slower)
- Windows 10/11 or Linux

## Quick Start

```bash
git clone <repo-url> Forge
cd Forge
python install.py          # Creates venv, installs deps, creates shortcut
.venv/Scripts/forge        # Launch (Windows)
# or: .venv/bin/forge      # Launch (Linux)
```

On first run, Forge creates `~/.forge/`, detects Ollama, and offers to pull the default model (`qwen2.5-coder:14b`).

## Launch Modes

| Command | Description |
|---------|-------------|
| `forge` | Console terminal (default) |
| `forge --fnc` | Neural Cortex GUI dashboard |
| `forge --gui-terminal` | GUI terminal with visual effects |

## Features

- **Context Continuity** — Automatic context swap with summarization. Continuity grade (A-F) tracks quality across swaps.
- **Crucible Security** — 4-layer content scanner: prompt injection, zero-width Unicode, base64 payloads, behavioral tripwires. Threat log with forensic detail.
- **Forensic Audit** — Every tool call, threat event, and session metric recorded. Export governance-grade zip bundles with `/export`.
- **Billing Ledger** — Token-level accounting with per-turn tracking, balance management, and session cost reports.
- **Plugin System** — Drop Python files in `~/.forge/plugins/`. Auto-disable after 5 consecutive errors.
- **Plan Mode** — Multi-step task planning with optional test/lint verification after each step.
- **Multi-Model Router** — Route simple tasks to a small model, complex ones to the primary model.
- **Voice Input** — Push-to-talk and VOX modes via faster-whisper (optional `forge[voice]` install).
- **12 Themes** — midnight, obsidian, dracula, solarized_dark, nord, monokai, cyberpunk, matrix, amber, phosphor, arctic, sunset.

## Commands

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/model` | Switch model |
| `/context` | Show context window state |
| `/pin` / `/unpin` / `/drop` | Manage pinned context entries |
| `/save` / `/load` | Save/load sessions |
| `/billing` | Token usage and costs |
| `/safety` | View/set safety level (0-3) |
| `/crucible` | Threat scanner status |
| `/forensics` | Session forensics |
| `/export` | Export audit zip bundle |
| `/continuity` | Context continuity grade |
| `/plan` | Plan mode controls |
| `/theme` | Switch color theme |
| `/voice` | Voice input controls |
| `/plugins` | Plugin manager |
| `/config` | View/edit configuration |
| `/dashboard` | Open HUD overlay |
| `/stats` | Session statistics |

45 commands total — run `/help` for the full list.

## Configuration

Edit `~/.forge/config.yaml` or use `/config` in-session. Key settings:

```yaml
default_model: "qwen2.5-coder:14b"
safety_level: 1                    # 0=unleashed, 1=smart_guard, 2=confirm_writes, 3=locked_down
swap_threshold_pct: 85             # Auto-swap context at this % usage
continuity_enabled: true           # Context quality tracking
theme: "midnight"                  # UI color theme
```

## Running Tests

```bash
# All tests (unit + integration stub mode)
pytest tests/ -v --timeout=300

# Integration stress tests with real Ollama
pytest tests/integration/ -v --live --timeout=600

# Stress runner with presets
python scripts/run_live_stress.py --live --smoke -n 5
python scripts/run_live_stress.py --live --full -n 1

# View stress test dashboard
python scripts/view_stress_results.py
```

### Stress Test Results

20/20 live iterations passing against `qwen2.5-coder:14b` on RTX 5070 Ti:
- 360 test runs, 0 failures
- 100% success rate
- 13 scenarios, 8 invariants, 63 integration tests
- Use `/export` to include trendline data in audit bundles

## Project Structure

```
forge/
  engine.py          # Core engine (ForgeEngine)
  context.py         # Context window management
  continuity.py      # Continuity grade scoring
  crucible.py        # Security threat scanner
  forensics.py       # Session forensics
  audit.py           # Audit export (zip bundles)
  billing.py         # Token billing ledger
  config.py          # Configuration loader
  safety.py          # Tiered safety guard
  commands.py        # Slash command dispatch
  plugins/           # Plugin system
  ui/                # Terminal, dashboard, themes
  models/            # Ollama backend
tests/
  integration/       # 13-scenario stress harness
scripts/
  run_live_stress.py # Stress test runner
  view_stress_results.py  # HTML dashboard generator
```

## License

Proprietary. All rights reserved. See [LICENSE](LICENSE) for details.
