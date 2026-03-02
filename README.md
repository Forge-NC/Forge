# Forge

Local AI coding assistant powered by [Ollama](https://ollama.com). Runs entirely on your machine -- no cloud APIs, no API keys, no data leaves your box unless you opt in. Manages its own context window with automatic swap and summarization, scans every interaction through a 4-layer security system, records forensic audit logs, tracks token-level billing, and wraps it all in a Neural Cortex GUI with 12 visual themes.

42,000+ lines of Python across 136 files. 593 tests passing.

## Architecture

```
                          +------------------+
                          |   ForgeEngine    |  Core orchestrator
                          +--------+---------+
                                   |
         +------------+------------+------------+------------+
         |            |            |            |            |
   ContextWindow  OllamaBackend  ToolRegistry  Crucible  BillingMeter
   (swap/sum)     (LLM calls)   (6 tool sets) (4 layers) (token $)
         |                         |
   ContinuityMon          +-------+-------+-------+-------+
   (A-F grade)             |       |       |       |       |
                        files    git   treesitter  web   digest
                                                          (AST)

   ModelRouter ── routes simple tasks to small model, complex to primary
   PlanVerifier ── multi-step task execution with test/lint gates
   SessionForensics ── every tool call recorded, exportable as zip
   EpisodicMemory ── long-term recall with embeddings
   CodebaseIndex ── fast file pattern matching and retrieval
   PluginSystem ── drop .py files in ~/.forge/plugins/
   VoiceInput ── push-to-talk and VOX via faster-whisper
```

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) running locally
- 8 GB+ VRAM recommended (works with less, slower)
- Windows 10/11 or Linux
- [GitHub CLI](https://cli.github.com) (optional, for `/update` and `/admin` commands)

## Quick Start

```bash
git clone https://github.com/ups0n/Forge.git
cd Forge
python install.py          # Creates venv, installs deps, creates desktop shortcut
.venv/Scripts/forge        # Launch (Windows)
# or: .venv/bin/forge      # Launch (Linux)
```

On first run Forge creates `~/.forge/`, detects your Ollama instance, and offers to pull the default model (`qwen2.5-coder:14b`).

## Launch Modes

| Command | Description |
|---------|-------------|
| `forge` | Console terminal (default) |
| `forge --fnc` | Neural Cortex -- full GUI dashboard with brain animation, performance cards, HUD menu |
| `forge --gui-terminal` | GUI terminal with visual effects (scanlines, glow, matrix rain) |

## Core Subsystems

### Context Window Management
Forge tracks every token entering the context window. When usage hits the configurable threshold (default 85%), it automatically swaps older entries out, summarizing them to preserve continuity. Pinned entries survive swaps. The **Continuity Grade** (A through F) scores swap quality across 6 signals and triggers auto-recovery when quality drops.

### Crucible Security Scanner
Every user message, AI response, and file read passes through 4 detection layers:
1. **Static patterns** -- prompt injection signatures, shell metacharacters, LOLBins
2. **Zero-width Unicode** -- invisible characters that can alter code behavior
3. **Base64 / encoded payloads** -- nested encoding detection
4. **Behavioral tripwires** -- monitors timing, call frequency, and honeypot canary integrity

Threats are logged with forensic detail and severity levels. The scanner runs in under 50ms per check.

### Forensic Audit System
Every tool call, threat event, context swap, and session metric is recorded in structured JSONL. Export governance-grade zip bundles with `/export` -- each bundle includes a manifest with SHA-256 hashes for chain-of-custody verification. Supports redaction mode for sensitive environments.

### Billing Ledger
Token-level accounting with per-turn tracking. Set a starting balance, monitor burn rate, compare costs against cloud providers with `/compare`. The ledger persists across sessions and includes detailed breakdowns by model, tool call, and swap overhead.

### Plan Mode
Multi-step task planning with optional verification after each step. PlanVerifier can run tests, linters, or custom checks between plan steps. Modes: `off`, `manual`, `auto` (triggers on complex tasks), `always`.

### Multi-Model Router
Routes simple tasks (greetings, short questions) to a smaller, faster model and complex tasks (code generation, analysis) to the primary model. Configurable threshold. Saves tokens without sacrificing quality where it matters.

### Plugin System
Drop Python files in `~/.forge/plugins/`. Plugins hook into: `on_command`, `on_user_input`, `on_tool_call`, `on_response`, `on_error`, and more. Auto-disables after 5 consecutive errors to prevent cascading failures.

### Voice Input
Push-to-talk (hold backtick) and VOX (voice-activated) modes via faster-whisper. Optional install: `pip install forge[voice]`.

### 12 Visual Themes
midnight, obsidian, dracula, solarized_dark, nord, monokai, cyberpunk, matrix, amber, phosphor, arctic, sunset. Hot-swap with `/theme <name>` or from Settings.

## Adaptive Nightly Testing

Fleet-wide automated testing with server-side intelligence.

- **Smart scheduler** (`scripts/nightly_smart.py`) -- GPU-aware time budgeting, automatic scenario selection via server manifest, resource guarding (auto-close heavy processes), cortex overlay for live progress
- **13 integration scenarios** -- endurance, model swap, context storm, plugin chaos, crash recovery, malicious repo, oscillation, repair loop, embedding loss, network chaos, tool corruption, verification theater, policy drift
- **8 invariants** checked after every scenario -- context consistency, billing integrity, forensics integrity, state files, continuity state, crucible state, workspace/sandbox, tool-call validity
- **Auto-bisect** -- when a scenario starts failing, automatically binary-searches recent commits to find the regression
- **Cross-platform scheduling** -- Settings > Nightly > Install Schedule (Windows Task Scheduler or Linux cron)

### Server Analytics

PHP backend processes telemetry uploads into fleet-wide analytics:
- **Per-machine profiles** with hardware fingerprints, scenario history, pass rates
- **Adaptive manifest** -- server learns which scenarios are flaky on which hardware and adjusts test assignments
- **HTML dashboard** at the analytics endpoint with fleet health charts, scenario breakdowns, machine timelines
- **SLA alerting** via Discord, Slack, or email when fleet pass rate drops below threshold

## Commands

49 commands organized by category. Run `/help` in-session for the full list.

| Category | Commands |
|----------|----------|
| **Session** | `/save`, `/load`, `/clear`, `/reset`, `/quit` |
| **Context** | `/context`, `/pin`, `/unpin`, `/drop` |
| **Models** | `/model`, `/models`, `/router` |
| **Development** | `/tools`, `/cd`, `/scan`, `/digest`, `/index`, `/search`, `/tasks`, `/plan` |
| **Memory** | `/memory`, `/journal`, `/recall` |
| **Billing** | `/billing`, `/compare`, `/topup` |
| **Safety** | `/safety`, `/crucible`, `/forensics`, `/provenance` |
| **Continuity** | `/continuity`, `/dedup` |
| **Audit** | `/export`, `/benchmark`, `/stats` |
| **UI** | `/theme`, `/dashboard`, `/docs`, `/voice`, `/plugins`, `/synapse` |
| **Config** | `/config`, `/hardware`, `/cache` |
| **Updates** | `/update`, `/update --yes` |
| **Admin** | `/admin`, `/admin invite <user>`, `/admin remove <user>`, `/admin pending`, `/admin token <label>` |

## Configuration

Edit `~/.forge/config.yaml` or use `/config` in-session.

```yaml
# Model
default_model: "qwen2.5-coder:14b"
small_model: "qwen2.5-coder:3b"
router_enabled: true

# Safety (0=unleashed, 1=smart_guard, 2=confirm_writes, 3=locked_down)
safety_level: 1
sandbox_enabled: true

# Context
swap_threshold_pct: 85
continuity_enabled: true

# UI
theme: "midnight"
effects_enabled: true

# Telemetry (opt-in)
telemetry_enabled: false
telemetry_token: ""
telemetry_label: ""

# Nightly testing
nightly_schedule_time: "03:00"
nightly_max_duration_m: 120
nightly_auto_bisect: true
```

80+ configuration keys total. See `/config` for the full list with descriptions.

## Updating Forge

```bash
# From the terminal:
/update              # Check what's available
/update --yes        # Pull and apply

# Or from the Neural Cortex GUI:
# HUD Menu > Check for Updates
```

Updates use `git pull --ff-only` (safe, no merge conflicts). If `pyproject.toml` changed, dependencies are automatically reinstalled. Core file changes prompt a restart.

## Admin

Manage GitHub collaborators and telemetry tokens from within Forge.

```bash
/admin                     # List collaborators
/admin invite <username>   # Send GitHub repo invitation
/admin remove <username>   # Remove collaborator
/admin pending             # Show pending invitations
/admin token <label>       # Generate + register a telemetry token
```

Or use the GUI: **HUD Menu > Admin Panel** for a visual interface with invite, remove, token generation, and repo info.

Requires [GitHub CLI](https://cli.github.com) authenticated with `repo` scope.

## Development and Testing

```bash
# Unit tests (530 tests)
pytest tests/ -v --timeout=300

# Integration stress tests -- stub mode (63 tests, no Ollama needed)
pytest tests/integration/ -v --timeout=600

# Integration stress tests -- live mode (requires running Ollama)
pytest tests/integration/ -v --live --timeout=600

# Stress runner with presets
python scripts/run_live_stress.py --stub --smoke -n 5     # Quick: ~40s
python scripts/run_live_stress.py --live --smoke -n 5     # Real: ~5min
python scripts/run_live_stress.py --live --full -n 1      # Deep: ~35min

# View stress test dashboard
python scripts/view_stress_results.py

# Local test history
python scripts/my_dashboard.py
```

## Project Structure

```
forge/
  __init__.py              # Package version
  __main__.py              # CLI entry point (--fnc, --gui-terminal, --model, --dir)
  engine.py                # ForgeEngine -- core orchestrator (3,287 lines)
  context.py               # Context window with swap/summarize/pin
  commands.py              # 49 slash commands
  config.py                # YAML config loader with validation
  safety.py                # 4-tier safety guard with sandbox
  crucible.py              # 4-layer security scanner (1,183 lines)
  forensics.py             # Session forensics and audit logging
  audit.py                 # Zip bundle exporter with SHA-256 manifest
  billing.py               # Token-level cost accounting
  continuity.py            # Context swap quality grading (A-F)
  plan_verifier.py         # Plan step verification (test/lint gates)
  planner.py               # Multi-step task planning
  router.py                # Multi-model routing (simple/complex)
  memory.py                # Episodic memory with embeddings
  index.py                 # Codebase indexing and search
  digest.py                # Tree-sitter AST analysis (1,475 lines)
  stats.py                 # Session metrics collector
  reliability.py           # Cross-session reliability scoring
  dedup.py                 # Content deduplication
  file_cache.py            # LRU file read cache
  tokenizer.py             # Token counting (tiktoken)
  persona.py               # Persona profiles (professional/casual/mentor/hacker)
  hardware.py              # GPU/CPU/RAM detection, VRAM-aware sizing
  resource_guard.py        # Process resource monitor and throttling
  scheduler.py             # Cross-platform nightly schedule (schtasks/cron)
  machine_id.py            # Stable machine fingerprinting
  telemetry.py             # Opt-in telemetry upload
  benchmark.py             # Reproducible benchmark suite

  audio/
    stt.py                 # Speech-to-text (faster-whisper)
    tts.py                 # Text-to-speech (edge-tts)
    sounds.py              # Sound effects library
    commands.py            # Voice command parsing

  models/
    ollama.py              # Ollama backend (streaming, tool calls)

  tools/
    registry.py            # Tool dispatch and ToolResult dataclass
    filesystem.py          # File operations (read, write, edit, search, glob)
    git_tools.py           # Git operations (status, diff, log, commit, branch)
    web_tools.py           # HTTP requests, HTML parsing
    treesitter_tools.py    # AST navigation for 8+ languages (1,653 lines)
    digest_tools.py        # Codebase analysis tools

  ui/
    dashboard.py           # Neural Cortex GUI (3,384 lines)
    terminal.py            # Console terminal I/O with ANSI
    gui_terminal.py        # GUI terminal with visual effects
    effects.py             # Animation engine (1,273 lines)
    themes.py              # 12 color themes with hot-swap
    settings_dialog.py     # 8-tab settings (Safety thru Telemetry)
    admin_panel.py         # GitHub collaborator + token management
    model_manager.py       # VRAM-aware model browser (1,271 lines)
    test_runner.py         # Visual test suite runner
    docs_window.py         # In-app documentation viewer
    cortex_overlay.py      # Transparent HUD overlay
    charts.py              # PIL chart engine (line, bar, donut, sparkline)

  plugins/
    __init__.py            # Plugin loader with auto-disable
    base.py                # ForgePlugin base class
    examples/
      auto_lint.py         # Example: auto-lint on file changes

scripts/
  nightly_smart.py         # Adaptive nightly test runner (976 lines)
  bisect_failure.py        # Auto-bisect failing scenarios
  run_live_stress.py       # Stress test runner with presets
  view_stress_results.py   # HTML+Chart.js dashboard
  my_dashboard.py          # Offline local test history

server/
  auth.php                 # Token authentication (SHA-256 + legacy key)
  manifest.php             # Adaptive test manifest (per-machine)
  telemetry_receiver.php   # Result ingestion + zip upload
  analyzer.php             # Fleet-wide analytics processor
  analytics.php            # HTML dashboard with charts
  alert.php                # SLA alerting (Discord/Slack/email)
  token_admin.php          # Admin token management API

tests/
  22 unit test files        # 530 tests covering all subsystems
  integration/
    13 scenario tests       # 63 integration tests
    harness.py             # Stress test framework
    ollama_stub.py         # Fake Ollama for deterministic testing
    state_verifier.py      # 8-invariant checker
```

## License

Proprietary. All rights reserved. See [LICENSE](LICENSE) for details.
