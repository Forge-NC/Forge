"""Configuration loader — reads ~/.forge/config.yaml.

Creates a default config on first run. All hardcoded values
in the engine can be overridden here.
"""

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ── Default configuration ──
# These are the values used if config.yaml doesn't exist or is missing keys.

DEFAULTS = {
    # Safety
    "safety_level": 1,               # 0=unleashed, 1=smart_guard, 2=confirm_writes, 3=locked_down
    "sandbox_enabled": False,         # restrict file ops to sandbox_roots
    "sandbox_roots": [],              # list of allowed directories (empty = cwd only when sandbox is on)

    # Model
    "default_model": "qwen2.5-coder:14b",
    "small_model": "",                    # fast model for simple tasks (e.g. "qwen2.5-coder:7b")
    "router_enabled": False,              # enable multi-model routing
    "embedding_model": "nomic-embed-text",
    "ollama_url": "http://localhost:11434",

    # Context
    "context_safety_margin": 0.85,    # use 85% of calculated context
    "swap_threshold_pct": 85,         # auto-swap at this % usage
    "swap_summary_target_tokens": 500,# target swap summary size

    # Agent loop
    "max_agent_iterations": 15,       # max tool-call loops per turn
    "shell_timeout": 30,              # default shell command timeout (seconds)
    "shell_max_output": 10000,        # truncate shell output at this many chars

    # Plan mode
    "plan_mode": "off",               # off, manual, auto, always
    "plan_auto_threshold": 3,         # complexity score above which auto-plan triggers
    "plan_verify_mode": "off",        # off, report, repair, strict
    "plan_verify_tests": True,        # run tests after each step
    "plan_verify_lint": False,        # run linter after each step
    "plan_verify_timeout": 30,        # max seconds for test suite

    # Tool deduplication
    "dedup_enabled": True,            # suppress near-duplicate tool calls
    "dedup_threshold": 0.92,          # similarity threshold (0.0-1.0)
    "dedup_window": 5,                # recent calls to compare against per tool

    # File cache
    "cache_enabled": True,

    # Voice
    "voice_model": "tiny",            # faster-whisper model size
    "voice_language": "en",           # whisper language code (en, es, fr, de, ja, zh, etc.)
    "voice_vox_threshold": 0.02,      # RMS threshold for VOX mode
    "voice_silence_timeout": 1.5,     # seconds of silence to end VOX
    "tts_engine": "edge",             # "edge" (cloud neural voices) or "local" (offline pyttsx3)

    # UI
    "theme": "midnight",              # UI color theme (see /theme for options)
    "effects_enabled": True,          # Animated visual effects (theme-dependent)
    "ansi_effects_enabled": False,    # Animated spinners/gradients in console terminal
    "terminal_mode": "console",       # console or gui (default launch from dashboard)
    "gui_terminal_effects": True,     # Visual effects in GUI terminal window
    "persona": "professional",        # professional, casual, mentor, hacker
    "show_hardware_on_start": True,
    "show_billing_on_start": True,
    "show_cache_on_start": True,

    # Continuity Grade
    "continuity_enabled": True,
    "continuity_threshold": 60,              # mild recovery below this
    "continuity_aggressive_threshold": 40,   # aggressive recovery below this

    # Billing
    "starting_balance": 50.0,

    # Enterprise
    "enterprise_mode": False,          # flips safety defaults for governance

    # Event bus
    "event_log_enabled": False,           # write every event to ~/.forge/events/session_{id}.jsonl

    # Behavioral fingerprinting (Phase 2)
    "behavioral_fingerprint": True,       # run 30-probe suite at session start (background)

    # Proof of Inference (Phase 3)
    "challenge_url": "https://forge-nc.dev/challenge_server.php",

    # AI Assurance (Phase 4)
    "assurance_url": "https://forge-nc.dev/assurance_verify.php",
    "auto_assurance": False,          # run /assure automatically on session.end
    "assurance_self_rate": False,     # ask model to rate own confidence + explain failures

    # Telemetry (opt-in, disabled by default)
    "telemetry_enabled": False,           # send redacted session data on exit
    "telemetry_url": "",                  # custom endpoint (leave blank for default)
    "telemetry_redact": True,             # strip prompts/responses (metadata only)
    "telemetry_token": "",                # per-user auth token (leave blank for legacy shared key)
    "telemetry_label": "",                # optional machine nickname, e.g. "DirtStar-RTX5070"

    # Bug Reporter (auto-files GitHub Issues on crashes/ghost errors)
    "bug_reporter_enabled": False,             # master switch (owner-only by default)
    "bug_reporter_max_session": 3,             # max issues filed per session
    "bug_reporter_max_daily": 10,              # max issues filed per day
    "bug_reporter_cooldown_hours": 24,         # per-fingerprint cooldown
    "bug_reporter_ghost_detection": True,      # detect silent failures
    "bug_reporter_labels": "bug,auto-reported",# GitHub issue labels

    # Security Hardening (all gated by safety_level — L0=off, scales up to L3)
    "output_scanning": True,              # scan LLM output for secrets/threats
    "rag_scanning": True,                 # scan RAG retrievals before injection
    "data_retention_days": 30,            # auto-prune forensics/exports older than N days (0=disabled)
    "rate_limiting": True,                # circuit breaker for runaway tool calls
    "rate_limit_per_minute": 30,          # max tool calls per sliding minute window

    # Threat Intelligence
    "threat_signatures_enabled": True,    # load external signature database
    "threat_signatures_url": "https://forge-nc.dev/signatures.json",  # URL for signature updates
    "threat_auto_update": True,           # auto-check for signature updates on startup

    # Adaptive Model Intelligence
    "ami_enabled": True,                  # self-healing model orchestration
    "ami_max_retries": 3,                 # max recovery attempts per turn
    "ami_quality_threshold": 0.7,         # below this score triggers retry
    "ami_auto_probe": True,               # auto-detect model capabilities on first use
    "ami_constrained_fallback": True,     # use JSON schema to force tool-call format

    # Adaptive Nightly Testing
    "nightly_manifest_url": "",                 # custom manifest endpoint (blank = default)
    "nightly_max_duration_m": 60,               # max nightly run time in minutes
    "nightly_auto_close": False,                # auto-close heavy processes before nightly
    "nightly_auto_close_list": [],              # process names to auto-close
    "nightly_resource_ram_threshold_mb": 500,   # flag processes using more RAM than this
    "nightly_resource_vram_threshold_mb": 200,  # flag processes using more VRAM than this
    "nightly_force_kill": False,                # allow force-kill after graceful timeout
    "nightly_show_cortex": False,               # show Neural Cortex overlay during tests
    "nightly_cortex_position": "top_right",     # overlay corner position
    "nightly_cortex_size": 180,                 # brain render size in pixels
    "nightly_auto_bisect": False,               # auto git-bisect on new failures
    "nightly_auto_ceiling": False,              # auto binary-search for max stable turns
    "adaptive_expand_limits": False,            # if false, server can only reduce scope
    "nightly_schedule_time": "03:00",           # time for scheduled nightly runs (HH:MM)
    "nightly_rebuild_signatures": True,         # rebuild + push threat signatures each night (origin machine)

    # Shipwright (AI release management)
    "shipwright_llm_classify": False,           # use LLM for ambiguous commit classification
    "push_on_ship": False,                      # push branch + tag to origin after /ship go

    # AutoForge (smart auto-commit)
    "auto_commit": False,                       # auto-commit file edits each turn
    "push_on_commit": False,                    # push to origin after each auto-commit

    # License / BPoS (Behavioral Proof of Stake)
    "license_tier": "community",                # community, pro, power

    # Plugins
    "disabled_plugins": [],                     # list of plugin class names to skip on load

    # Multi-backend LLM provider
    "backend_provider": "ollama",               # ollama, openai, anthropic
    "openai_api_key": "",                       # or set OPENAI_API_KEY env var
    "anthropic_api_key": "",                    # or set ANTHROPIC_API_KEY env var
    "openai_base_url": "",                      # custom OpenAI-compatible endpoint
}

# Path to the config file
CONFIG_PATH = Path.home() / ".forge" / "config.yaml"

# Template written on first run
_CONFIG_TEMPLATE = """\
# ╔═══════════════════════════════════════════════════════════════╗
# ║  Forge Configuration                                         ║
# ║  Edit this file to customize Forge's behavior.               ║
# ║  Changes take effect on next startup (or use /config reload). ║
# ╚═══════════════════════════════════════════════════════════════╝

# ── Safety ──
# 0 = unleashed   — everything runs, no checks, full trust
# 1 = smart_guard  — shell blocklist catches dangerous commands (DEFAULT)
# 2 = confirm_writes — file writes need brief confirmation (auto-accepts in 3s)
# 3 = locked_down  — every tool call requires approval
safety_level: 1

# Sandbox: restrict file operations to specific directories
# When enabled with no roots listed, defaults to the working directory
sandbox_enabled: false
sandbox_roots: []
#  - C:/Users/you/projects
#  - D:/repos

# ── Model ──
default_model: "qwen2.5-coder:14b"
small_model: ""                        # fast model for simple tasks (e.g. "qwen2.5-coder:7b")
router_enabled: false                  # enable multi-model routing (needs small_model set)
embedding_model: "nomic-embed-text"
ollama_url: "http://localhost:11434"

# ── Context Window ──
context_safety_margin: 0.85    # use this fraction of calculated max context
swap_threshold_pct: 85         # auto-swap context at this % usage
swap_summary_target_tokens: 500

# ── Agent Loop ──
max_agent_iterations: 15       # max tool-call rounds per turn
shell_timeout: 30              # seconds before shell commands time out
shell_max_output: 10000        # truncate shell output at this many chars

# ── Plan Mode ──
# off = disabled, manual = /plan triggers, auto = complex prompts, always = every prompt
plan_mode: "off"
plan_auto_threshold: 3         # complexity score for auto-plan (higher = less frequent)

# ── Tool Deduplication ──
dedup_enabled: true            # suppress near-duplicate tool calls within a turn
dedup_threshold: 0.92          # similarity ratio (0.0-1.0), higher = stricter
dedup_window: 5                # recent calls to compare per tool

# ── File Cache ──
cache_enabled: true

# ── Voice ──
voice_model: "tiny"            # faster-whisper model: tiny, base, small, medium
voice_vox_threshold: 0.02      # RMS threshold for voice-activated mode
voice_silence_timeout: 1.5     # seconds of silence to stop recording

# ── UI ──
theme: "midnight"                     # color theme (midnight, obsidian, dracula, nord, etc.)
effects_enabled: true                 # animated visual effects (theme-dependent)
ansi_effects_enabled: false           # animated spinners/gradients in console terminal
terminal_mode: "console"              # console or gui (default launch from dashboard)
gui_terminal_effects: true            # visual effects in GUI terminal window
persona: "professional"        # professional, casual, mentor, hacker
show_hardware_on_start: true
show_billing_on_start: true
show_cache_on_start: true

# ── Continuity Grade ──
continuity_enabled: true          # measure context quality across swaps
continuity_threshold: 60           # mild recovery below this score
continuity_aggressive_threshold: 40 # aggressive recovery below this score

# ── Billing ──
starting_balance: 50.0

# ── Enterprise ──
# When true: strict plan verification, forensics always on, safety >= 2
enterprise_mode: false

# ── Bug Reporter ──
# Auto-files GitHub Issues when Forge crashes or detects silent failures.
# Requires `gh` CLI authenticated. Owner/developer tool — disabled by default.
# bug_reporter_enabled: false
# bug_reporter_max_session: 3       # max issues per session
# bug_reporter_max_daily: 10        # max issues per day
# bug_reporter_cooldown_hours: 24   # same-bug cooldown
# bug_reporter_ghost_detection: true # detect silent failures (embed, tool, context)
# bug_reporter_labels: "bug,auto-reported"

# ── Security Hardening ──
# All features are gated by safety_level: L0 (unleashed) = off, scales up to L3.
# output_scanning: true          # scan LLM output for secrets/threats
# rag_scanning: true             # scan RAG retrievals before context injection
# data_retention_days: 30        # auto-prune old forensics/exports (0 = keep forever)
# rate_limiting: true            # circuit breaker for runaway tool call loops
# rate_limit_per_minute: 30      # max tool calls per sliding 60s window

# ── Threat Intelligence ──
# Upgradeable threat signature database (like antivirus definitions).
# threat_signatures_enabled: true     # load external signature database
# threat_signatures_url: ""           # URL for signature updates (empty = bundled only)
# threat_auto_update: true            # auto-check for updates (interval scales with safety level)

# ── Adaptive Model Intelligence ──
# Self-healing model orchestration: detects failures, forces compliance, auto-recovers.
# ami_enabled: true                   # enable AMI quality checks and recovery
# ami_max_retries: 3                  # max recovery attempts per turn
# ami_quality_threshold: 0.7          # below this score triggers retry
# ami_auto_probe: true                # auto-detect model capabilities on first use
# ami_constrained_fallback: true      # use JSON schema to force tool-call format

# ── Telemetry (opt-in) ──
# When enabled, sends a redacted audit summary to the Forge team on session exit.
# No user prompts or AI responses are included unless you set telemetry_redact to false.
# telemetry_enabled: false
# telemetry_url: ""
# telemetry_redact: true

# ── AutoForge (smart auto-commit) ──
# Automatically stages and commits file edits at each turn boundary.
# Operates on whatever git repo the current working directory belongs to.
# auto_commit: false          # enable auto-commit
# push_on_commit: false       # push to origin after each auto-commit
#                             # requires git credentials for the remote

# ── Shipwright (AI release management) ──
# Classifies commits, bumps semantic version, tags and optionally pushes releases.
# shipwright_llm_classify: false   # use AI to classify ambiguous commit messages
# push_on_ship: false              # push branch + tag to origin after /ship go
#                                  # requires git credentials for the remote
"""


def _strip_comment(line: str) -> str:
    """Strip # comments from a YAML line, but not inside quoted strings."""
    in_quote = None
    for i, ch in enumerate(line):
        if ch in ('"', "'") and in_quote is None:
            in_quote = ch
        elif ch == in_quote:
            in_quote = None
        elif ch == '#' and in_quote is None:
            return line[:i].rstrip()
    return line.rstrip()


def _parse_yaml_simple(text: str) -> dict:
    """Minimal YAML parser — handles flat key: value pairs and simple lists.

    We avoid requiring PyYAML as a dependency. This handles the subset
    of YAML that our config uses: scalars, simple lists, and comments.
    """
    result = {}
    current_key = None
    current_list = None

    for raw_line in text.splitlines():
        # Strip comments — but not inside quoted strings
        line = _strip_comment(raw_line)
        if not line.strip():
            if current_key and current_list is not None:
                # End of list on blank line
                result[current_key] = current_list
                current_key = None
                current_list = None
            continue

        # List item: "  - value"
        if line.strip().startswith("- ") and current_key:
            val = line.strip()[2:].strip()
            # Strip one layer of quotes
            if (val.startswith('"') and val.endswith('"')) or \
               (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            if current_list is None:
                current_list = []
            current_list.append(val)
            continue

        # Close any open list
        if current_key and current_list is not None:
            result[current_key] = current_list
            current_key = None
            current_list = None

        # Key: value pair
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()

            if not val:
                # Could be start of a list — only becomes [] if items follow
                current_key = key
                current_list = None
                continue

            # Parse value — strip one layer of quotes
            if (val.startswith('"') and val.endswith('"')) or \
               (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            if val.lower() == "true":
                result[key] = True
            elif val.lower() == "false":
                result[key] = False
            elif val == "[]":
                result[key] = []
            else:
                try:
                    if "." in val:
                        result[key] = float(val)
                    else:
                        result[key] = int(val)
                except ValueError:
                    result[key] = val

    # Close any trailing list
    if current_key and current_list is not None:
        result[current_key] = current_list
    elif current_key and current_list is None:
        # Bare key with no list items — treat as empty string
        result[current_key] = ""

    return result


def _format_yaml_value(key: str, val) -> str:
    """Format a single key-value pair as YAML."""
    if isinstance(val, bool):
        return f"{key}: {'true' if val else 'false'}"
    elif isinstance(val, list):
        if not val:
            return f"{key}: []"
        else:
            lines = [f"{key}:"]
            for item in val:
                if ':' in str(item) or '#' in str(item):
                    lines.append(f'  - "{item}"')
                else:
                    lines.append(f"  - {item}")
            return "\n".join(lines)
    elif isinstance(val, str):
        return f'{key}: "{val}"'
    else:
        return f"{key}: {val}"


def _find_inline_comment(line: str) -> int:
    """Find the position of an inline # comment, respecting quoted strings.

    Returns the index of the '#' or -1 if no inline comment exists.
    """
    in_quote = None
    # Skip the key: value portion — find the value start first
    colon_pos = line.find(":")
    if colon_pos < 0:
        return -1
    for i in range(colon_pos + 1, len(line)):
        ch = line[i]
        if ch in ('"', "'") and in_quote is None:
            in_quote = ch
        elif ch == in_quote:
            in_quote = None
        elif ch == '#' and in_quote is None:
            return i
    return -1


def _merge_yaml(existing_text: str, data: dict) -> str:
    """Merge updated values into existing YAML text, preserving comments."""
    lines = existing_text.splitlines()
    updated_keys = set()
    result = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        stripped = _strip_comment(raw)
        # Check if this line is a key: value pair (not a list item, not blank)
        if stripped.strip() and not stripped.strip().startswith("-") and ":" in stripped:
            key, _, _ = stripped.partition(":")
            key = key.strip()
            if key in data:
                updated_keys.add(key)
                val = data[key]
                # Preserve inline comment if present
                inline_comment = ""
                raw_stripped = raw.rstrip()
                comment_idx = _find_inline_comment(raw_stripped)
                if comment_idx >= 0:
                    inline_comment = "  " + raw_stripped[comment_idx:]
                formatted = _format_yaml_value(key, val)
                if isinstance(val, list) and val:
                    result.append(formatted)
                    # Skip old list items
                    i += 1
                    while i < len(lines):
                        s = lines[i].strip()
                        if s.startswith("- ") or s.startswith("#- "):
                            i += 1
                        else:
                            break
                    continue
                else:
                    result.append(formatted + inline_comment)
            else:
                result.append(raw)
        else:
            result.append(raw)
        i += 1

    # Append any new keys that weren't in the original file
    new_keys = set(data.keys()) - updated_keys
    if new_keys:
        result.append("")
        for key in new_keys:
            result.append(_format_yaml_value(key, data[key]))

    return "\n".join(result) + "\n"


def _dump_yaml_simple(data: dict) -> str:
    """Dump dict to simple YAML string."""
    lines = []
    for key, val in data.items():
        if isinstance(val, bool):
            lines.append(f"{key}: {'true' if val else 'false'}")
        elif isinstance(val, list):
            if not val:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in val:
                    lines.append(f"  - {item}")
        elif isinstance(val, str):
            lines.append(f'{key}: "{val}"')
        else:
            lines.append(f"{key}: {val}")
    return "\n".join(lines) + "\n"


_VALIDATORS = {
    "safety_level": lambda v: isinstance(v, int) and 0 <= v <= 3,
    "sandbox_enabled": lambda v: isinstance(v, bool),
    "sandbox_roots": lambda v: isinstance(v, list),
    "context_safety_margin": lambda v: isinstance(v, (int, float)) and 0 < v <= 1.0,
    "swap_threshold_pct": lambda v: isinstance(v, int) and 10 <= v <= 100,
    "swap_summary_target_tokens": lambda v: isinstance(v, int) and v > 0,
    "max_agent_iterations": lambda v: isinstance(v, int) and 1 <= v <= 100,
    "shell_timeout": lambda v: isinstance(v, int) and v > 0,
    "shell_max_output": lambda v: isinstance(v, int) and v > 0,
    "plan_mode": lambda v: v in ("off", "manual", "auto", "always"),
    "plan_verify_mode": lambda v: v in ("off", "report", "repair", "strict"),
    "plan_verify_tests": lambda v: isinstance(v, bool),
    "plan_verify_lint": lambda v: isinstance(v, bool),
    "plan_verify_timeout": lambda v: isinstance(v, int) and v > 0,
    "plan_auto_threshold": lambda v: isinstance(v, int) and v > 0,
    "dedup_enabled": lambda v: isinstance(v, bool),
    "dedup_threshold": lambda v: isinstance(v, (int, float)) and 0 <= v <= 1.0,
    "dedup_window": lambda v: isinstance(v, int) and v > 0,
    "cache_enabled": lambda v: isinstance(v, bool),
    "continuity_enabled": lambda v: isinstance(v, bool),
    "continuity_threshold": lambda v: isinstance(v, int) and 0 <= v <= 100,
    "continuity_aggressive_threshold": lambda v: isinstance(v, int) and 0 <= v <= 100,
    "starting_balance": lambda v: isinstance(v, (int, float)) and v >= 0,
    "effects_enabled": lambda v: isinstance(v, bool),
    "router_enabled": lambda v: isinstance(v, bool),
    "enterprise_mode": lambda v: isinstance(v, bool),
    "event_log_enabled": lambda v: isinstance(v, bool),
    "behavioral_fingerprint": lambda v: isinstance(v, bool),
    "challenge_url": lambda v: isinstance(v, str),
    "assurance_url": lambda v: isinstance(v, str),
    "auto_assurance": lambda v: isinstance(v, bool),
    "assurance_self_rate": lambda v: isinstance(v, bool),
    "telemetry_enabled": lambda v: isinstance(v, bool),
    "telemetry_url": lambda v: isinstance(v, str),
    "telemetry_redact": lambda v: isinstance(v, bool),
    "bug_reporter_enabled": lambda v: isinstance(v, bool),
    "bug_reporter_max_session": lambda v: isinstance(v, int) and 1 <= v <= 50,
    "bug_reporter_max_daily": lambda v: isinstance(v, int) and 1 <= v <= 100,
    "bug_reporter_cooldown_hours": lambda v: isinstance(v, (int, float)) and v >= 0,
    "bug_reporter_ghost_detection": lambda v: isinstance(v, bool),
    "bug_reporter_labels": lambda v: isinstance(v, str),
    "output_scanning": lambda v: isinstance(v, bool),
    "rag_scanning": lambda v: isinstance(v, bool),
    "data_retention_days": lambda v: isinstance(v, int) and v >= 0,
    "rate_limiting": lambda v: isinstance(v, bool),
    "rate_limit_per_minute": lambda v: isinstance(v, int) and 5 <= v <= 200,
    "threat_signatures_enabled": lambda v: isinstance(v, bool),
    "threat_signatures_url": lambda v: isinstance(v, str),
    "threat_auto_update": lambda v: isinstance(v, bool),
    "ami_enabled": lambda v: isinstance(v, bool),
    "ami_max_retries": lambda v: isinstance(v, int) and 0 <= v <= 10,
    "ami_quality_threshold": lambda v: isinstance(v, (int, float)) and 0.0 <= v <= 1.0,
    "ami_auto_probe": lambda v: isinstance(v, bool),
    "ami_constrained_fallback": lambda v: isinstance(v, bool),
    "tts_engine": lambda v: isinstance(v, str) and v in ("edge", "local"),
    "voice_language": lambda v: isinstance(v, str) and len(v) >= 2,
    "voice_model": lambda v: isinstance(v, str) and v in ("tiny", "base", "small", "medium", "large"),
    "voice_vox_threshold": lambda v: isinstance(v, (int, float)) and 0 < v < 1.0,
    "voice_silence_timeout": lambda v: isinstance(v, (int, float)) and v > 0,
    "default_model": lambda v: isinstance(v, str) and len(v) > 0,
    "small_model": lambda v: isinstance(v, str),
    "embedding_model": lambda v: isinstance(v, str) and len(v) > 0,
    "ollama_url": lambda v: isinstance(v, str) and v.startswith("http"),
    "theme": lambda v: isinstance(v, str),
    "persona": lambda v: isinstance(v, str) and v in ("professional", "casual", "mentor", "hacker"),
    "terminal_mode": lambda v: isinstance(v, str) and v in ("console", "gui"),
    "ansi_effects_enabled": lambda v: isinstance(v, bool),
    "gui_terminal_effects": lambda v: isinstance(v, bool),
    "show_hardware_on_start": lambda v: isinstance(v, bool),
    "show_billing_on_start": lambda v: isinstance(v, bool),
    "show_cache_on_start": lambda v: isinstance(v, bool),
    "telemetry_token": lambda v: isinstance(v, str),
    "telemetry_label": lambda v: isinstance(v, str),
    "nightly_manifest_url": lambda v: isinstance(v, str),
    "nightly_max_duration_m": lambda v: isinstance(v, int) and v > 0,
    "nightly_auto_close": lambda v: isinstance(v, bool),
    "nightly_auto_close_list": lambda v: isinstance(v, list),
    "nightly_resource_ram_threshold_mb": lambda v: isinstance(v, int) and v > 0,
    "nightly_resource_vram_threshold_mb": lambda v: isinstance(v, int) and v > 0,
    "nightly_force_kill": lambda v: isinstance(v, bool),
    "nightly_show_cortex": lambda v: isinstance(v, bool),
    "nightly_cortex_position": lambda v: isinstance(v, str) and v in ("top_right", "top_left", "bottom_right", "bottom_left"),
    "nightly_cortex_size": lambda v: isinstance(v, int) and 50 <= v <= 500,
    "nightly_auto_bisect": lambda v: isinstance(v, bool),
    "nightly_auto_ceiling": lambda v: isinstance(v, bool),
    "adaptive_expand_limits": lambda v: isinstance(v, bool),
    "nightly_schedule_time": lambda v: isinstance(v, str) and len(v) == 5,
    "shipwright_llm_classify": lambda v: isinstance(v, bool),
    "push_on_ship": lambda v: isinstance(v, bool),
    "nightly_rebuild_signatures": lambda v: isinstance(v, bool),
    "auto_commit": lambda v: isinstance(v, bool),
    "push_on_commit": lambda v: isinstance(v, bool),
    "license_tier": lambda v: isinstance(v, str) and v in ("community", "pro", "power", "origin"),
    "backend_provider": lambda v: isinstance(v, str) and v in ("ollama", "openai", "anthropic"),
    "openai_api_key": lambda v: isinstance(v, str),
    "anthropic_api_key": lambda v: isinstance(v, str),
    "openai_base_url": lambda v: isinstance(v, str),
    "disabled_plugins": lambda v: isinstance(v, list) and all(isinstance(s, str) for s in v),
}


class ForgeConfig:
    """Forge configuration backed by ~/.forge/config.yaml."""

    def __init__(self, config_dir: Path = None):
        self._config_dir = config_dir or (Path.home() / ".forge")
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._path = self._config_dir / "config.yaml"
        self._data: dict = dict(DEFAULTS)
        self._load()

    def _load(self):
        """Load config from disk, creating default if missing."""
        if not self._path.exists():
            self._write_default()

        try:
            text = self._path.read_text(encoding="utf-8")
            parsed = _parse_yaml_simple(text)
            # Merge with defaults (config file values override defaults)
            for key, val in parsed.items():
                if key in DEFAULTS:
                    validator = _VALIDATORS.get(key)
                    if validator and not validator(val):
                        log.warning("Invalid value for %s: %r — using default %r",
                                    key, val, DEFAULTS[key])
                    else:
                        self._data[key] = val
                else:
                    log.warning("Unknown config key: %s", key)
        except Exception as e:
            log.warning("Failed to load config: %s — using defaults", e)
            # Back up the corrupted file so it isn't lost
            try:
                backup = self._path.with_suffix(".yaml.bak")
                shutil.copy2(str(self._path), str(backup))
                log.warning("Corrupted config backed up to %s", backup)
            except Exception:
                pass

    def _write_default(self):
        """Write the default config template."""
        try:
            self._path.write_text(_CONFIG_TEMPLATE, encoding="utf-8")
            log.info("Created default config at %s", self._path)
        except Exception as e:
            log.warning("Failed to write default config: %s", e)

    def reload(self):
        """Reload config from disk."""
        self._data = dict(DEFAULTS)
        self._load()

    def get(self, key: str, default: Any = None) -> Any:
        """Get a config value."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any):
        """Set a config value (in memory only — use save() to persist)."""
        if key not in DEFAULTS:
            log.warning("Setting unknown config key: %s", key)
        validator = _VALIDATORS.get(key)
        if validator and not validator(value):
            log.warning("Invalid value for %s: %r", key, value)
            return
        self._data[key] = value

    def save(self):
        """Persist current config to disk, merging into existing file to
        preserve comments and formatting where possible.

        Uses atomic write (temp file + os.replace) to prevent corruption
        if the process is killed mid-write.
        """
        try:
            if self._path.exists():
                existing = self._path.read_text(encoding="utf-8")
                content = _merge_yaml(existing, self._data)
            else:
                content = _dump_yaml_simple(self._data)
            # Atomic write
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._path.parent), suffix=".yaml.tmp")
            try:
                os.write(fd, content.encode("utf-8"))
                os.close(fd)
                fd = -1
                os.replace(tmp_path, str(self._path))
            except BaseException:
                if fd >= 0:
                    os.close(fd)
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            log.warning("Failed to save config: %s", e)

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: str) -> bool:
        return key in self._data

    @property
    def path(self) -> Path:
        return self._path


def load_config() -> ForgeConfig:
    """Convenience alias — returns a ForgeConfig instance."""
    return ForgeConfig()
