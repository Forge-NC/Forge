"""Forge engine — orchestrates context, tools, LLM, caching, and billing.

The main loop:
  1. User types input
  2. Input + context -> LLM
  3. LLM responds with text and/or tool calls
  4. Tool calls execute; file reads check cache first
  5. If tool calls occurred, loop back to step 2
  6. Display response + context status + billing
"""

import os
import sys
import json
import time
import logging
import tempfile
import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from forge.context import ContextWindow, ContextFullError
from forge.models.ollama import OllamaBackend
from forge.tools.registry import ToolRegistry, ToolResult
from forge.tools import filesystem
from forge.file_cache import FileCache
from forge.billing import BillingMeter
from forge.memory import EpisodicMemory
from forge.index import CodebaseIndex
from forge.digest import CodebaseDigester
from forge.stats import StatsCollector
from forge.hardware import (
    get_hardware_summary, format_hardware_report, MODEL_SPECS,
    calculate_max_context, format_context_report,
)
from forge.ui.terminal import (
    RESET, DIM, BOLD, YELLOW, RED, CYAN, GREEN, MAGENTA, WHITE, GRAY,
)
from forge.ui.terminal_io import TerminalIO, ConsoleTerminalIO
from forge.persona import get_persona
from forge.config import ForgeConfig
from forge.safety import SafetyGuard, LEVEL_NAMES, NAME_TO_LEVEL
from forge.crucible import Crucible, ThreatLevel
from forge.forensics import SessionForensics
from forge.router import ModelRouter
from forge.tokenizer import count_tokens, tokenizer_status
from forge.commands import CommandHandler
from forge.planner import PlanMode, Plan, parse_plan
from forge.reliability import ReliabilityTracker
from forge.plan_verifier import PlanVerifier
from forge.dedup import ToolDedup
from forge.continuity import ContinuityMonitor

log = logging.getLogger(__name__)


# ── Checkpoint / Interrupt infrastructure ──

@dataclass
class TurnCheckpoint:
    """Snapshot of engine state at the start of a turn for rollback."""
    context_entry_count: int       # len(ctx._entries) at turn start
    context_total_tokens: int      # ctx._total_tokens at turn start
    file_backups: dict[str, Optional[str]] = field(default_factory=dict)
    files_created: list[str] = field(default_factory=list)
    timestamp: float = 0.0
    iteration: int = 0


class EscapeMonitor:
    """Background thread that detects Escape key presses during agent loop.

    Windows: polls msvcrt.kbhit() at ~50Hz.
    Linux: uses select() on stdin with tty.setcbreak().
    Only active between start() and stop() calls.
    """

    def __init__(self):
        self._interrupted = threading.Event()
        self._active = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def interrupted(self) -> bool:
        return self._interrupted.is_set()

    def start(self):
        """Start monitoring for Escape. Call before agent loop."""
        self._interrupted.clear()
        self._active.set()
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._poll_loop, daemon=True,
                name="ForgeEscapeMonitor")
            self._thread.start()

    def stop(self):
        """Stop monitoring. Call after agent loop / before input()."""
        self._active.clear()

    def reset(self):
        """Clear the interrupted flag for a new turn."""
        self._interrupted.clear()

    def _poll_loop(self):
        """Poll for Escape key at ~50Hz while active."""
        if sys.platform == "win32":
            self._poll_windows()
        else:
            self._poll_unix()

    def _poll_windows(self):
        try:
            import msvcrt
        except ImportError:
            return
        while True:
            if not self._active.wait(timeout=0.5):
                # Not active — sleep longer, check periodically
                continue
            while self._active.is_set():
                if msvcrt.kbhit():
                    ch = msvcrt.getch()
                    if ch == b'\x1b':  # Escape
                        self._interrupted.set()
                        self._active.clear()
                        return
                    # Not Escape — push it back so input() can read it.
                    # Without this, keystrokes typed while the model is
                    # thinking are silently eaten from the console buffer.
                    try:
                        msvcrt.ungetch(ch)
                    except (OSError, ValueError):
                        pass
                    # Sleep longer to avoid busy re-reading the same char
                    time.sleep(0.15)
                    continue
                time.sleep(0.02)  # ~50Hz

    def _poll_unix(self):
        try:
            import tty
            import termios
            import select
        except ImportError:
            return
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            while True:
                if not self._active.wait(timeout=0.5):
                    continue
                while self._active.is_set():
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.02)
                    if rlist:
                        ch = sys.stdin.read(1)
                        if ch == '\x1b':
                            self._interrupted.set()
                            self._active.clear()
                            return
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


SYSTEM_PROMPT = """You are a local AI coding assistant running on the user's machine.

You have tools for reading, writing, editing, and searching files, and running
shell commands. Use them to help the user with coding tasks.

## Core Rules
- Read files before editing them. Understand existing code before modifying it.
- Make minimal, surgical edits. Don't rewrite files unnecessarily.
- When using edit_file, the old_string must match exactly and be unique in the file.
- Prefer editing existing files over creating new ones.
- Be direct and concise. No filler. No preamble.
- If you're unsure about something, say so. Don't guess.

## Tool Usage — CRITICAL
- Call tools using the tool calling interface. NEVER write JSON tool calls in your
  text response. NEVER wrap tool calls in ```json``` code blocks. If you want to
  use a tool, CALL it — don't print it.
- After a tool returns an error, READ the error carefully. Do NOT retry the exact
  same call with the same arguments — that will fail again.
- If edit_file fails because old_string is not unique, include more surrounding
  lines to make it unique. If old_string was not found, read the file first to
  find the actual text.
- If a file is not found, use glob_files or list_directory to locate it.
  Do NOT guess file paths.
- NEVER read a file you just wrote or edited — you already know its contents.
- If a file read returns "[CACHED - unchanged]", the content is already in your
  context from a previous read. Do NOT read it again.
- If stuck after 2 failed attempts at the same operation, explain what's blocking
  you and ask the user for help instead of retrying.

## Planning
- For tasks involving 3+ files or complex logic, use the think tool to plan
  your approach before executing.
- State your plan once, then execute. Do NOT repeat the plan between steps.
- After completing each step, move to the next. Don't re-explain what you did.

## Codebase Analysis Protocol
When asked to analyze, audit, review, or understand a codebase:
1. FIRST: call scan_codebase to get the structural map. This gives you x-ray
   vision of every file, class, function, route, and table without reading
   a single file into context. This costs ~4-8K tokens regardless of project size.
2. Study the summary. Identify the most important files from symbol rankings.
3. Use digest_file on specific files to see their structure before reading.
   This costs ~50 tokens per file vs hundreds for a full read.
4. Use read_symbols to read ONLY specific functions or classes you need to
   inspect. This costs ~10-100 tokens per symbol — 10-15x cheaper than read_file.
5. Only use read_file when you need to EDIT a file or need full context.
6. Use write_notes to record architectural observations as you go. These
   persist across sessions and appear in future scan summaries.
NEVER skip step 1. NEVER fabricate analysis. NEVER invent directory structures.
The structural map gives you real data for every file — use it.

## Thoroughness
- When working with files: ACTUALLY READ THEM. Use the tools — don't guess or
  fabricate what files contain. If you haven't read it, you don't know what's
  in it — say so and go read it.
- Base all analysis on what you actually read, not on what a "typical" project
  might look like. The user wants YOUR reading of THEIR code, not a template.

## Efficiency
- Don't read files you've already read this session unless checking for external changes.
- Don't search for files you've already found.
- One read of a file is enough — use the content already in your context.

## Context Awareness
- You may see a "## Session Context (auto-generated)" block. This is a swap
  summary — your context was refreshed but session knowledge is preserved.
  Continue working seamlessly.
- You may see "[Semantic Recall]" blocks with relevant code snippets. Use them
  as context but read the full file if you need to make edits.
- You may see "[System: ...]" messages with guidance after errors. Follow them.
- Messages prefixed with "[voice]" come from the user speaking via microphone.
  You CAN hear them — your system has speech-to-text built in. Treat voice
  messages exactly like typed messages. Do NOT claim you can't hear or process audio.
- Messages like "[Voice interrupt: ...]" mean the user spoke while you were
  working. The answer was already given inline. Acknowledge it briefly and continue.

Platform: {platform}
Working directory: {cwd}
"""

# Best open-source coding models (MIT/Apache licensed, ranked by quality)
RECOMMENDED_MODELS = [
    ("qwen2.5-coder:32b", "Best quality, needs ~20GB VRAM (may use CPU offload)"),
    ("qwen2.5-coder:14b", "Great quality, fits 16GB VRAM comfortably"),
    ("qwen2.5-coder:7b", "Good quality, fast, fits any modern GPU"),
    ("deepseek-coder-v2:16b", "Strong alternative, good at refactoring"),
    ("codellama:13b", "Meta's coding model, solid baseline"),
]

WARN_PCT = 75
DANGER_PCT = 90


class ForgeEngine:
    """Main Forge engine."""

    def __init__(self, model: str = None, cwd: str = None,
                 terminal_io: TerminalIO = None):
        self.io: TerminalIO = terminal_io or ConsoleTerminalIO()
        self.cwd = cwd or os.getcwd()
        self._config_dir = Path.home() / ".forge"
        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._session_file = self._config_dir / "last_session.json"

        # Load configuration
        self.config = ForgeConfig(self._config_dir)

        # Set UI theme from config (before any UI module imports colors)
        from forge.ui.themes import set_theme
        set_theme(self.config.get("theme", "midnight"))

        # Initialize safety guard
        sandbox_roots = self.config.get("sandbox_roots", [])
        if not sandbox_roots and self.config.get("sandbox_enabled"):
            sandbox_roots = [self.cwd]
        self.safety = SafetyGuard(
            level=self.config.get("safety_level", 1),
            sandbox_enabled=self.config.get("sandbox_enabled", False),
            sandbox_roots=sandbox_roots,
        )

        # Initialize LLM backend
        self.llm = OllamaBackend(
            model=model or self.config.get("default_model", "qwen2.5-coder:14b"))

        # Initialize context window with accurate tokenizer
        self.ctx = ContextWindow(max_tokens=32768, tokenizer_fn=count_tokens)

        # File content cache — never re-read unchanged files
        self.cache = FileCache(
            persist_path=self._config_dir / "file_cache.json")

        # Codebase digest — structural analysis engine (zero LLM tokens)
        self._digester = CodebaseDigester(
            persist_dir=self._config_dir / "digest")

        # Sandbox billing
        self.billing = BillingMeter(
            persist_path=self._config_dir / "billing.json")

        # Crucible — content threat scanner
        self.crucible = Crucible(
            enabled=self.safety.level > 0,  # disabled in unleashed mode
        )

        # Session forensics — audit trail
        self.forensics = SessionForensics(
            persist_dir=self._config_dir / "forensics")

        # Multi-model router
        _small = self.config.get("small_model", "")
        self.router = ModelRouter(
            big_model=self.llm.model,
            small_model=_small,
            enabled=bool(_small) and self.config.get("router_enabled", False),
        )

        # Plan mode — structured planning before execution
        self.planner = PlanMode(
            mode=self.config.get("plan_mode", "off"),
            auto_threshold=self.config.get("plan_auto_threshold", 3),
        )

        # Plan step verifier — runs tests/lint after each plan step
        self.plan_verifier = PlanVerifier(
            mode=self.config.get("plan_verify_mode", "off"),
            run_tests=self.config.get("plan_verify_tests", True),
            run_lint=self.config.get("plan_verify_lint", False),
            max_test_time=self.config.get("plan_verify_timeout", 30),
            working_dir=os.getcwd(),
        )

        # Tool call deduplication
        self.dedup = ToolDedup(
            threshold=self.config.get("dedup_threshold", 0.92),
            window_size=self.config.get("dedup_window", 5),
            enabled=self.config.get("dedup_enabled", True),
        )

        # Initialize tools
        self.tools = ToolRegistry()
        self._register_tools()

        # Command handler (slash commands live in forge/commands.py)
        self._command_handler = CommandHandler(self)

        # Plugin system
        try:
            from forge.plugins import PluginManager
            self.plugin_manager = PluginManager(
                plugin_dir=self._config_dir / "plugins")
            self.plugin_manager.discover()
            self.plugin_manager.load_all(self)
            loaded = self.plugin_manager.get_loaded()
            if loaded:
                log.info("Loaded %d plugin(s)", len(loaded))
        except Exception as e:
            log.debug("Plugin system init: %s", e)
            from forge.plugins import PluginManager
            self.plugin_manager = PluginManager(
                plugin_dir=self._config_dir / "plugins")

        # Episodic memory — persistent journal across sessions
        self.memory = EpisodicMemory(
            persist_dir=self._config_dir / "journal")

        # Semantic index — initialized lazily in run() after model check
        self.index: Optional[CodebaseIndex] = None

        # Analytics
        self.stats = StatsCollector(persist_dir=self._config_dir)

        # Continuity Grade — measures context quality across swaps
        self.continuity = ContinuityMonitor(
            enabled=self.config.get("continuity_enabled", True),
            threshold=self.config.get("continuity_threshold", 60),
            aggressive_threshold=self.config.get(
                "continuity_aggressive_threshold", 40),
        )

        # Reliability tracking — cross-session stability metrics
        self.reliability = ReliabilityTracker(
            persist_path=self._config_dir / "reliability.json")

        # Enterprise mode — override safety defaults for governance
        if self.config.get("enterprise_mode", False):
            self._apply_enterprise_defaults()

        # Dashboard (GUI) — launched on demand
        self._dashboard = None

        # Voice input (optional)
        self._voice = None
        self._voice_queue = queue.Queue()
        self._voice_initiated = False  # True when current turn came from voice
        self._tts = None  # Text-to-speech for voice responses

        # State
        self._turn_count = 0
        self._total_generated = 0
        self._session_start = time.time()
        self._last_warning_pct = 0

        # Escape-key interrupt + checkpoint
        self._escape_monitor = EscapeMonitor()
        self._current_checkpoint: Optional[TurnCheckpoint] = None

        # Per-turn tracking (reset each turn)
        self._current_turn_tools: list[dict] = []
        self._current_turn_files: list[str] = []
        self._turn_prompt_tokens = 0
        self._turn_eval_count = 0
        self._turn_error_counts: dict[str, int] = {}  # tool error nudges

    def _apply_enterprise_defaults(self):
        """Override settings for enterprise/governance mode."""
        # PlanVerifier → strict (not off)
        if self.plan_verifier.mode == "off":
            self.plan_verifier.mode = "strict"
        # Forensics always enabled
        self.forensics._enabled = True
        # Safety minimum level 2
        if self.safety.level < 2:
            self.safety.level = 2
        # Crucible always enabled
        self.crucible.enabled = True
        log.info("Enterprise mode active — strict verification, "
                 "forensics on, safety >= 2")

    def _register_tools(self):
        """Register all tools, wrapping file ops with cache logic."""
        # We wrap read_file to intercept with cache
        self.tools.register(
            "read_file", self._cached_read_file,
            "Read a file and return its contents with line numbers. "
            "Returns a cache stub if the file hasn't changed since last read.",
            {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to read",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Start line (1-based). 0 = beginning.",
                        "default": 0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max lines to read. 0 = all.",
                        "default": 0,
                    },
                },
                "required": ["file_path"],
            },
        )

        # Wrap write_file and edit_file to invalidate cache
        self.tools.register(
            "write_file", self._cached_write_file,
            "Write content to a file (creates or overwrites).",
            {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to write to"},
                    "content": {"type": "string", "description": "Full file content"},
                },
                "required": ["file_path", "content"],
            },
        )

        self.tools.register(
            "edit_file", self._cached_edit_file,
            "Replace a specific string in a file. The old_string must be unique unless replace_all is True.",
            {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the file"},
                    "old_string": {"type": "string", "description": "Exact text to find"},
                    "new_string": {"type": "string", "description": "Replacement text"},
                    "replace_all": {"type": "boolean", "description": "Replace all occurrences", "default": False},
                },
                "required": ["file_path", "old_string", "new_string"],
            },
        )

        # Register remaining tools normally
        self.tools.register(
            "glob_files", filesystem.glob_files,
            "Find files matching a glob pattern (e.g. '**/*.py').",
            {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Glob pattern"},
                    "path": {"type": "string", "description": "Directory to search in", "default": "."},
                },
                "required": ["pattern"],
            },
        )

        self.tools.register(
            "grep_files", filesystem.grep_files,
            "Search file contents with regex. Returns matching lines with file paths and line numbers.",
            {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Regex pattern to search for"},
                    "path": {"type": "string", "description": "Directory to search in", "default": "."},
                    "glob_filter": {"type": "string", "description": "Filter files by glob (e.g. '*.py')", "default": ""},
                },
                "required": ["pattern"],
            },
        )

        self.tools.register(
            "list_directory", filesystem.list_directory,
            "List contents of a directory with file sizes.",
            {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path", "default": "."},
                },
            },
        )

        self.tools.register(
            "run_shell", self._guarded_run_shell,
            "Execute a shell command and return its output. Use for git, build tools, tests, etc.",
            {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
                    "cwd": {"type": "string", "description": "Working directory"},
                },
                "required": ["command"],
            },
        )

        self.tools.register(
            "think", self._think,
            "Use this to reason step-by-step about a problem before acting. "
            "Good for planning multi-file changes, debugging errors, or "
            "deciding next steps. Your thought is recorded but not shown "
            "to the user.",
            {
                "type": "object",
                "properties": {
                    "thought": {
                        "type": "string",
                        "description": "Your step-by-step reasoning or plan",
                    },
                },
                "required": ["thought"],
            },
        )

        # Register codebase digest tools (structural analysis)
        from forge.tools.digest_tools import register_all as register_digest_tools
        register_digest_tools(self.tools, self._digester)

        # Register git tools
        try:
            from forge.tools.git_tools import register_git_tools
            register_git_tools(self.tools, self.cwd)
        except Exception as e:
            log.debug("Git tools registration failed: %s", e)

        # Register web tools
        try:
            from forge.tools.web_tools import register_web_tools
            register_web_tools(self.tools)
        except Exception as e:
            log.debug("Web tools registration failed: %s", e)

        # Register tree-sitter code navigation tools
        try:
            from forge.tools.treesitter_tools import register_treesitter_tools
            register_treesitter_tools(self.tools, self.cwd)
        except Exception as e:
            log.debug("Tree-sitter tools registration failed: %s", e)

    def _think(self, thought: str) -> str:
        """Think tool — lets the model reason without visible output."""
        return f"[Thought recorded: {len(thought)} chars]"

    def _cached_read_file(self, file_path: str, offset: int = 0,
                          limit: int = 0) -> str:
        """Read file with cache check — skip unchanged files."""
        # Safety check
        allowed, reason = self.safety.check_file_read(file_path)
        if not allowed:
            return f"Error: {reason}"

        # Only cache full-file reads (no offset/limit)
        if offset == 0 and limit == 0:
            hit = self.cache.check(file_path)
            if hit:
                saved = hit["tokens_saved"]
                reads = hit["read_count"]
                lines = hit["line_count"]
                print(f"  {GREEN}[CACHE HIT]{RESET} {DIM}{file_path} "
                      f"unchanged ({lines} lines, {saved:,} tokens saved, "
                      f"read #{reads}){RESET}")
                return (f"[CACHED - unchanged since last read] "
                        f"{file_path} ({lines} lines). "
                        f"File content is already in your context from a "
                        f"previous read. Do not re-read.")

        result = filesystem.read_file(file_path, offset, limit)

        # Let plugins transform content after read
        if not result.startswith("Error") and hasattr(self, 'plugin_manager'):
            result = self.plugin_manager.dispatch_file_read(file_path, result)

        # Crucible: scan content for threats before feeding to AI
        if not result.startswith("Error") and self.crucible.enabled:
            # Extract raw content (skip the header line)
            raw_lines = result.split("\n", 1)
            raw_content = raw_lines[1] if len(raw_lines) > 1 else result
            threats = self.crucible.scan_content(file_path, raw_content)

            if threats:
                # Find the highest severity threat
                worst = max(threats, key=lambda t: t.level)

                # Set dashboard to threat mode
                self._write_dashboard_state("threat",
                                            {"file": file_path,
                                             "level": worst.level_name})

                # Record threat in forensics
                self.forensics.record("threat",
                                      f"Threat in {file_path}: {worst.description}",
                                      {"file": file_path, "level": worst.level_name,
                                       "description": worst.description,
                                       "category": worst.category},
                                      risk_level=worst.level)

                # Handle based on severity
                if worst.level >= ThreatLevel.WARNING:
                    choice = self.crucible.handle_threat_interactive(
                        worst, raw_content)

                    if choice == "skip":
                        self._write_dashboard_state("idle")
                        return (f"Error: File '{file_path}' skipped — "
                                f"Crucible detected a threat: "
                                f"{worst.description}")

                    if choice == "remove":
                        repaired = self.crucible.repair_file(
                            file_path, worst, raw_content)
                        if repaired is not None:
                            result = raw_lines[0] + "\n" + repaired
                            print(f"  {GREEN}[CRUCIBLE]{RESET} "
                                  f"{DIM}Threat removed, "
                                  f"continuing with clean content{RESET}")
                        self._write_dashboard_state("idle")

                    else:
                        # ignore — proceed with original content
                        self._write_dashboard_state("idle")

                else:
                    # SUSPICIOUS level — just warn, don't interrupt
                    print(f"  {YELLOW}[CRUCIBLE]{RESET} "
                          f"{DIM}Suspicious content in {file_path}: "
                          f"{worst.description}{RESET}")
                    self._write_dashboard_state("idle")

        # Store in cache (only full reads)
        if offset == 0 and limit == 0 and not result.startswith("Error"):
            token_count = max(1, len(result) // 4)
            self.cache.store(file_path, result, token_count)
            self.forensics.record("file_read", f"Read {file_path}",
                                  {"path": file_path, "tokens": token_count})

        return result

    def _cached_write_file(self, file_path: str, content: str) -> str:
        """Write file with overwrite warning and cache invalidation."""
        # Safety check
        allowed, reason = self.safety.check_file_write(file_path, "write")
        if not allowed:
            return f"Error: {reason}"

        p = Path(file_path).resolve()
        if p.exists() and p.is_file():
            try:
                old_size = p.stat().st_size
                new_size = len(content.encode("utf-8"))
                old_lines = p.read_text(
                    encoding="utf-8", errors="replace").count("\n") + 1
                new_lines = content.count("\n") + 1
                print(f"  {YELLOW}[OVERWRITE]{RESET} {DIM}{p.name}: "
                      f"{old_lines} lines ({old_size:,}B) -> "
                      f"{new_lines} lines ({new_size:,}B){RESET}")
            except Exception:
                print(f"  {YELLOW}[OVERWRITE]{RESET} {DIM}{p.name}{RESET}")
        self._backup_file_before_write(file_path)
        self.cache.invalidate(file_path)
        created = not p.exists()
        # Let plugins transform content before write
        if hasattr(self, 'plugin_manager'):
            content = self.plugin_manager.dispatch_file_write(file_path, content)
        result = filesystem.write_file(file_path, content)
        self.forensics.record("file_write", f"Write {file_path}",
                              {"path": file_path, "created": created})
        return result

    def _cached_edit_file(self, file_path: str, old_string: str,
                          new_string: str, replace_all: bool = False) -> str:
        """Edit file with before/after preview and cache invalidation."""
        # Safety check
        allowed, reason = self.safety.check_file_write(file_path, "edit")
        if not allowed:
            return f"Error: {reason}"

        old_preview = old_string[:80].replace("\n", "\\n")
        new_preview = new_string[:80].replace("\n", "\\n")
        print(f"  {DIM}  - {RED}{old_preview}{RESET}")
        print(f"  {DIM}  + {GREEN}{new_preview}{RESET}")
        # File integrity check — detect external modifications
        integrity = self.cache.check_integrity(file_path)
        if integrity:
            print(f"  {YELLOW}[INTEGRITY]{RESET} {DIM}{file_path} was modified "
                  f"externally since last read ({integrity['last_read_ago']}s ago). "
                  f"Re-read before editing.{RESET}")
            self.forensics.record("integrity_warning",
                                  f"File modified externally: {file_path}",
                                  {"path": file_path}, risk_level=1)

        self._backup_file_before_write(file_path)
        self.cache.invalidate(file_path)
        # Let plugins transform new_string before edit
        if hasattr(self, 'plugin_manager'):
            new_string = self.plugin_manager.dispatch_file_write(
                file_path, new_string)
        result = filesystem.edit_file(file_path, old_string, new_string,
                                      replace_all)
        self.forensics.record("file_edit", f"Edit {file_path}",
                              {"path": file_path})
        return result

    def _guarded_run_shell(self, command: str, timeout: int = 30,
                           cwd: str = None) -> str:
        """Run shell command through safety guard."""
        allowed, reason = self.safety.check_shell(command)
        if not allowed:
            self.forensics.record("shell_blocked",
                                  f"Blocked: {command[:100]}",
                                  {"command": command, "reason": reason},
                                  risk_level=2)
            return f"Error: Command blocked — {reason}"
        timeout = timeout or self.config.get("shell_timeout", 30)
        result = filesystem.run_shell(command, timeout, cwd)
        self.forensics.record("shell", f"Shell: {command[:80]}",
                              {"command": command})
        return result

    def _backup_file_before_write(self, file_path: str):
        """Backup file content into the current checkpoint before writing.

        Only backs up once per file per turn (first write wins — preserves
        the original pre-turn state). New files are recorded for deletion
        on rollback.
        """
        cp = self._current_checkpoint
        if cp is None:
            return

        try:
            resolved = str(Path(file_path).resolve())
        except Exception:
            resolved = file_path

        # Already backed up this file this turn
        if resolved in cp.file_backups:
            return

        try:
            p = Path(resolved)
            if p.exists():
                cp.file_backups[resolved] = p.read_text(encoding="utf-8")
            else:
                # File doesn't exist yet — mark for deletion on rollback
                cp.file_backups[resolved] = None
                cp.files_created.append(resolved)
        except Exception as e:
            log.debug("Checkpoint backup failed for %s: %s", file_path, e)

    def _check_for_updates_on_boot(self):
        """Check for updates on startup and prompt user."""
        import subprocess as _sp
        import re as _re
        forge_root = str(Path(__file__).resolve().parent.parent)
        flags = {}
        if os.name == "nt":
            flags["creationflags"] = _sp.CREATE_NO_WINDOW

        try:
            _sp.run(["git", "fetch", "origin"], cwd=forge_root,
                     capture_output=True, timeout=10, **flags)
            result = _sp.run(
                ["git", "rev-list", "--count", "HEAD..origin/master"],
                cwd=forge_root, capture_output=True, text=True,
                timeout=5, **flags)
            if result.returncode != 0:
                return
            count = int(result.stdout.strip())
            if count == 0:
                return

            # Get remote version
            ver_result = _sp.run(
                ["git", "show", "origin/master:pyproject.toml"],
                cwd=forge_root, capture_output=True, text=True,
                timeout=5, **flags)
            remote_ver = ""
            if ver_result.returncode == 0:
                m = _re.search(r'version\s*=\s*"([^"]+)"', ver_result.stdout)
                if m:
                    remote_ver = m.group(1)

            # Get changelog
            log_result = _sp.run(
                ["git", "log", "--oneline", "HEAD..origin/master"],
                cwd=forge_root, capture_output=True, text=True,
                timeout=5, **flags)
            changes = []
            if log_result.returncode == 0:
                for line in log_result.stdout.strip().split("\n")[:5]:
                    parts = line.strip().split(" ", 1)
                    if len(parts) > 1:
                        changes.append(parts[1])

            ver_str = f" v{remote_ver}" if remote_ver else ""
            print(f"\n{YELLOW}{BOLD}Update available:{RESET}"
                  f" {count} new commit{'s' if count != 1 else ''}"
                  f"{' -> ' + ver_str if ver_str else ''}")
            if changes:
                for ch in changes:
                    print(f"  {DIM}{ch}{RESET}")
                if count > 5:
                    print(f"  {DIM}... and {count - 5} more{RESET}")

            print(f"\n{CYAN}Update now? [y/N]{RESET} ", end="", flush=True)
            try:
                answer = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = ""

            if answer in ("y", "yes"):
                self.io.print_info("Pulling updates...")
                pull = _sp.run(
                    ["git", "pull", "--ff-only", "origin", "master"],
                    cwd=forge_root, capture_output=True, text=True,
                    timeout=30, **flags)
                if pull.returncode != 0:
                    self.io.print_error(f"Pull failed: {pull.stderr[:200]}")
                    return

                # Check if deps changed
                diff = _sp.run(
                    ["git", "diff", "--name-only", f"HEAD~{count}", "HEAD"],
                    cwd=forge_root, capture_output=True, text=True,
                    timeout=5, **flags)
                changed = diff.stdout.strip().split("\n") if diff.stdout.strip() else []
                if "pyproject.toml" in changed:
                    self.io.print_info("Dependencies changed, reinstalling...")
                    venv_py = Path(forge_root) / ".venv" / "Scripts" / "python.exe"
                    if not venv_py.exists():
                        venv_py = Path(forge_root) / ".venv" / "bin" / "python"
                    if venv_py.exists():
                        _sp.run(
                            [str(venv_py), "-m", "pip", "install", "-e",
                             forge_root, "--quiet"],
                            capture_output=True, timeout=120, **flags)

                print(f"\n  {GREEN}Updated to{ver_str}!{RESET}")
                print(f"  {YELLOW}Restart Forge to use the new code.{RESET}\n")
            else:
                print()  # clean newline after prompt

        except Exception:
            pass  # Silent — no git, no network, etc.

    def run(self):
        """Main interactive loop."""
        self.io.enable_ansi()
        self.io.print_banner()

        # Check for updates
        self._check_for_updates_on_boot()

        # Model setup — check availability, offer to download
        if not self._ensure_model():
            return

        # Show hardware profile
        if not hasattr(self, '_hw_summary'):
            print(f"{DIM}Scanning hardware...{RESET}")
            self._hw_summary = get_hardware_summary()
        hw = self._hw_summary
        if hw["gpu"]:
            gpu = hw["gpu"]
            self.io.print_info(f"GPU: {gpu['name']} ({hw['vram_gb']}GB VRAM, "
                       f"{hw['vram_free_gb']}GB free)")
        if hw["cpu"]:
            self.io.print_info(f"CPU: {hw['cpu']}")
        if hw["ram_gb"]:
            self.io.print_info(f"RAM: {hw['ram_gb']}GB")

        # Configure context window — VRAM-aware calculation
        vram_gb = hw.get("vram_gb", 0)
        if vram_gb > 0:
            ctx_info = calculate_max_context(vram_gb, self.llm.model)
            self._ctx_info = ctx_info

            optimal_ctx = ctx_info["recommended_context"]
            kv_mode = ctx_info["recommended_mode"]

            # Check if Ollama has KV quantization enabled
            kv_env = os.environ.get("OLLAMA_KV_CACHE_TYPE", "").lower()
            flash_env = os.environ.get("OLLAMA_FLASH_ATTENTION", "")
            kv_active = kv_env in ("q8_0", "q4_0")
            flash_active = flash_env == "1"

            if kv_mode != "fp16" and not kv_active:
                # KV quant recommended but not enabled — fall back to FP16 calc
                self.io.print_warning(
                    "KV cache quantization is not active on Ollama.")
                self.io.print_info(
                    "For maximum context, restart Ollama via the Forge launcher")
                self.io.print_info(
                    "or set: OLLAMA_FLASH_ATTENTION=1  "
                    "OLLAMA_KV_CACHE_TYPE=q8_0")
                # Use FP16 context size since that's what Ollama is actually doing
                optimal_ctx = ctx_info["modes"]["fp16"]["context"]
                kv_mode = "fp16"

            # Tell Ollama to use this context size
            self.llm.num_ctx = optimal_ctx

            # Reserve safety margin
            margin = self.config.get("context_safety_margin", 0.85)
            usable = int(optimal_ctx * margin)
            self.ctx.max_tokens = usable

            self.io.print_info(f"Model: {self.llm.model}")
            self.io.print_info(f"Context: {optimal_ctx:,} tokens "
                       f"(KV cache: {kv_mode.upper()}, "
                       f"usable: {usable:,})")
            if kv_active and kv_mode != "fp16":
                self.io.print_info(f"KV quantization active — "
                           f"{ctx_info['reason']}")
        else:
            # Fallback: use Ollama's reported context length
            ctx_length = self.llm.get_context_length()
            max_ctx = int(ctx_length * 0.8)
            self.ctx.max_tokens = max_ctx
            self.io.print_info(f"Model: {self.llm.model} "
                       f"(context: {ctx_length:,} tokens, "
                       f"usable: {max_ctx:,})")

        self.io.print_info(f"Working directory: {self.cwd}")

        # Show billing status
        bs = self.billing.status()
        self.io.print_info(f"Sandbox balance: ${bs['balance']:.2f} "
                   f"(lifetime: {bs['lifetime_tokens']:,} tokens "
                   f"across {bs['lifetime_sessions']} sessions)")

        # Show cache stats
        cs = self.cache.stats()
        if cs["cached_files"]:
            self.io.print_info(f"File cache: {cs['cached_files']} files cached, "
                       f"{cs['tokens_saved']:,} tokens saved lifetime "
                       f"({cs['hit_rate']:.0f}% hit rate)")

        # Initialize voice input (optional — silent if deps missing)
        self._init_voice()

        # Show safety level + Crucible status
        safety_colors = {0: RED, 1: GREEN, 2: YELLOW, 3: RED}
        sc = safety_colors.get(self.safety.level, WHITE)
        crucible_status = (f"{GREEN}ON{RESET}" if self.crucible.enabled
                           else f"{DIM}OFF{RESET}")
        tok_info = tokenizer_status()
        tok_tag = (f"{GREEN}{tok_info['tokenizer']}{RESET}" if tok_info["accurate"]
                   else f"{YELLOW}{tok_info['tokenizer']}{RESET}")
        self.io.print_info(f"Safety: {sc}{BOLD}{self.safety.level_name}{RESET}"
                   f" | Crucible: {crucible_status}"
                   f" | Tokenizer: {tok_tag}"
                   f"{DIM} (/safety, /crucible){RESET}")

        self.io.print_info("Type /help for commands. /docs or F1 for documentation.\n")

        # Initialize input history + tab completion
        self.io.init_readline(str(self._config_dir))
        self.io.setup_completer([
            "/help", "/quit", "/exit", "/context", "/drop", "/pin",
            "/unpin", "/clear", "/reset", "/save", "/load", "/model",
            "/models", "/tools", "/cd", "/billing", "/compare", "/topup",
            "/cache", "/scan", "/digest", "/memory", "/journal",
            "/recall", "/search", "/index", "/tasks", "/stats",
            "/dashboard", "/hardware", "/voice", "/safety", "/config",
            "/crucible", "/forensics", "/router", "/provenance",
            "/docs", "/plugins", "/plan", "/dedup", "/synapse",
        ])

        # Initialize semantic index (non-blocking)
        self._init_semantic_index()

        # Add system prompt with persona
        platform = "Windows" if os.name == "nt" else "Linux"
        persona = get_persona()
        persona_prefix = persona.system_prompt_prefix + "\n\n"
        sys_prompt = persona_prefix + SYSTEM_PROMPT.format(
            platform=platform, cwd=self.cwd)
        # Inject Crucible honeypot canary
        if self.crucible.enabled:
            sys_prompt += self.crucible.get_canary_prompt()
        self.ctx.add("system", sys_prompt, tag="system", pinned=True)

        # Inject prior session memory so the AI knows what happened before
        self._inject_session_recap()

        self.io.print_context_bar(self.ctx.status())

        while True:
            user_input = self._get_input()
            if not user_input:
                continue

            # Check voice plan mode file (set by dashboard voice command)
            self._check_voice_plan_mode()

            # Check if dashboard saved new config settings
            self._check_config_trigger()

            # Handle voice-initiated plan mode commands
            if self._voice_initiated:
                from forge.audio.commands import parse_voice_command
                vcmd, _vrest = parse_voice_command(
                    user_input, get_persona().name)
                if vcmd == "plan_mode":
                    self.planner.mode = "manual"
                    self.planner.arm()
                    self.io.print_info("Plan mode armed — next prompt will "
                               "generate a plan.")
                    continue
                elif vcmd == "plan_off":
                    self.planner.mode = "off"
                    self.planner.disarm()
                    self.io.print_info("Plan mode disabled.")
                    continue

            if user_input.startswith("/"):
                if self._handle_command(user_input):
                    continue

            try:
                self.ctx.add("user", user_input, tag="user_msg")
            except ContextFullError as e:
                self.io.print_error(str(e))
                continue

            # Inject semantic context before LLM call
            self._inject_semantic_context(user_input)

            # Route to appropriate model based on input complexity
            complexity_score = None
            if self.router.enabled:
                from forge.router import estimate_complexity
                est = estimate_complexity(
                    user_input,
                    context_entries=self.ctx.entry_count,
                    active_files=len(self._current_turn_files) if hasattr(self, '_current_turn_files') else 0,
                )
                complexity_score = est["score"]
                routed_model = self.router.route(
                    user_input,
                    context_entries=self.ctx.entry_count,
                    active_files=len(self._current_turn_files) if hasattr(self, '_current_turn_files') else 0,
                )
                if routed_model != self.llm.model:
                    log.debug("Router: %s -> %s", self.llm.model, routed_model)
                    self.llm.model = routed_model

            # Plan mode — generate plan before execution
            if self.planner.should_plan(user_input, complexity_score):
                plan_result = self._run_plan_mode(user_input)
                if plan_result == "rejected":
                    self._print_status_bar()
                    continue
                elif plan_result == "executed":
                    self._print_status_bar()
                    continue
                # else: plan_result is None, fall through to normal execution

            # Reset per-turn tracking
            self._current_turn_tools = []
            self._current_turn_files = []
            self._turn_prompt_tokens = 0
            self._turn_eval_count = 0
            self._turn_error_counts = {}
            self.dedup.soft_reset()  # preserve previous turn for cross-turn detection

            # Create checkpoint for interrupt/rollback
            self._current_checkpoint = TurnCheckpoint(
                context_entry_count=self.ctx.entry_count,
                context_total_tokens=self.ctx.total_tokens,
                timestamp=time.time(),
            )

            # Start escape monitoring during agent loop
            self._escape_monitor.reset()
            self._escape_monitor.start()

            redirect = self._agent_loop()

            # Stop escape monitoring before waiting for input
            self._escape_monitor.stop()
            self._current_checkpoint = None

            # Inject a brief turn summary so the model knows what it
            # already did (prevents cross-turn repetition of the same work)
            if self._current_turn_tools:
                tool_names = [t["name"] for t in self._current_turn_tools]
                # Deduplicate while preserving order
                seen = set()
                unique = []
                for n in tool_names:
                    if n not in seen:
                        seen.add(n)
                        unique.append(n)
                summary = (
                    f"[System: Previous turn used these tools: "
                    f"{', '.join(unique)} ({len(tool_names)} total calls). "
                    f"Do not repeat the same work — build on those results.]"
                )
                try:
                    self.ctx.add("system", summary, tag="turn_summary",
                                 partition="working")
                except ContextFullError as e:
                    log.warning("Context full, skipped injection: %s", e)

            # If agent loop returned a redirect, use it as next input
            if redirect:
                if redirect.lower() == "undo":
                    # Rollback already happened inside _handle_interrupt
                    self._print_status_bar()
                    continue
                # User typed new input after interrupt — inject resume context
                if self._current_checkpoint:
                    cp = self._current_checkpoint
                    modified = [Path(p).name
                                for p, c in cp.file_backups.items()
                                if c is not None]
                    created = [Path(p).name for p in cp.files_created]
                    parts = ["[System: Previous response was interrupted."]
                    if modified:
                        parts.append(
                            f"Files modified: {', '.join(modified)}.")
                    if created:
                        parts.append(
                            f"Files created: {', '.join(created)}.")
                    parts.append("User has redirected below.]")
                    try:
                        self.ctx.add("system", " ".join(parts),
                                     tag="resume_ctx",
                                     partition="working")
                    except ContextFullError as e:
                        log.warning("Context full, skipped injection: %s", e)

                try:
                    self.ctx.add("user", redirect, tag="user_msg")
                except ContextFullError as e:
                    self.io.print_error(str(e))
                    continue
                # Reset tracking for the redirect turn
                self._current_turn_tools = []
                self._current_turn_files = []
                self._turn_prompt_tokens = 0
                self._turn_eval_count = 0
                self._turn_error_counts = {}
                self._current_checkpoint = TurnCheckpoint(
                    context_entry_count=self.ctx.entry_count,
                    context_total_tokens=self.ctx.total_tokens,
                    timestamp=time.time(),
                )
                self._escape_monitor.reset()
                self._escape_monitor.start()
                redirect = self._agent_loop()
                self._escape_monitor.stop()
                self._current_checkpoint = None
                if redirect:
                    # Second interrupt — just stop, don't recurse
                    self._print_status_bar()
                    continue

            # Record turn to episodic memory
            last_response = self._get_last_assistant_response()
            self.memory.record_turn(
                user_message=user_input,
                assistant_response=last_response,
                tool_calls=self._current_turn_tools,
                files_touched=self._current_turn_files,
                tokens_used=self._turn_prompt_tokens + self._turn_eval_count,
            )

            # TTS: speak the response if this turn was voice-initiated
            if (self._voice_initiated and last_response
                    and self._tts and self._tts.enabled):
                self._tts.speak(last_response)

            # Continuity Grade — score context quality after each turn
            if self.continuity.enabled:
                self.continuity.advance_turn(self._turn_count)
                ts_cg = self.memory.get_task_state()
                if ts_cg and ts_cg.objective:
                    self.continuity.set_objective(ts_cg.objective)
                snap = self.continuity.score(self.ctx._entries, ts_cg)
                recovery = self.continuity.needs_recovery(snap)
                if recovery:
                    snap.recovery_triggered = True
                    self._continuity_recovery(recovery)

            # Auto context swap at 85% instead of just warning
            self._auto_context_swap()
            self._print_status_bar()

    def _ensure_model(self) -> bool:
        """Check Ollama is running and a model is available.
        Offers interactive download if no coding model found.
        Returns True if ready to go."""
        # Step 1: Check if Ollama is reachable at all
        available = []
        try:
            available = self.llm.list_models()
        except Exception:
            pass

        if not available:
            # Ollama not running or empty — check if it's just empty vs not running
            try:
                import requests
                r = requests.get("http://localhost:11434/api/tags", timeout=3)
                if r.status_code == 200:
                    # Ollama running but no models at all
                    self.io.print_info("Ollama is running but has no models installed.")
                    return self._offer_model_download()
            except Exception:
                pass

            self.io.print_error("Cannot connect to Ollama.")
            self.io.print_info("Start Ollama first, then run Forge again.")
            self.io.print_info("  Windows: Start 'Ollama' from Start Menu")
            self.io.print_info("  Linux:   ollama serve &")
            return False

        # Step 2: Check if our preferred model is available
        if self.llm.is_available():
            return True

        # Step 3: Look for any coding model already installed
        for name, _ in RECOMMENDED_MODELS:
            base = name.split(":")[0]
            for avail in available:
                if base in avail:
                    self.llm.model = avail
                    self.io.print_info(f"Using available coding model: {avail}")
                    return True

        # Step 4: No coding model found — offer to download one
        self.io.print_warning("No coding model found in Ollama.")
        self.io.print_info(f"Available models: {', '.join(available)}")
        print()
        return self._offer_model_download(fallback_model=available[0])

    def _offer_model_download(self, fallback_model: str = None) -> bool:
        """Interactively offer to download a recommended coding model.

        Profiles the user's hardware, recommends the best model that
        fits entirely on GPU, and offers alternatives.
        Returns True if a model is ready (downloaded or fallback).
        """
        # Profile hardware
        print(f"{DIM}Scanning hardware...{RESET}")
        hw = get_hardware_summary()
        self._hw_summary = hw  # Store for /hardware command

        print(f"\n{BOLD}{format_hardware_report(hw)}{RESET}")
        print()

        rec = hw.get("recommendation", {})
        rec_model = rec.get("model", RECOMMENDED_MODELS[1][0])
        rec_reason = rec.get("reason", "")
        alternatives = rec.get("alternatives", [])

        # Build the selection list: recommended first, then alternatives
        choices = [(rec_model, f"RECOMMENDED — {rec_reason}")]
        for alt in alternatives:
            choices.append((alt["model"], alt["desc"]))
        # Add remaining from RECOMMENDED_MODELS not already listed
        listed = {c[0] for c in choices}
        for name, desc in RECOMMENDED_MODELS:
            if name not in listed:
                choices.append((name, desc))

        print(f"{BOLD}Available coding models:{RESET}")
        print()
        for i, (name, desc) in enumerate(choices, 1):
            if i == 1:
                print(f"  {GREEN}{i}. {BOLD}{name}{RESET}")
                print(f"     {GREEN}{desc}{RESET}")
            else:
                print(f"  {CYAN}{i}.{RESET} {BOLD}{name}{RESET}")
                print(f"     {DIM}{desc}{RESET}")
        print()

        if fallback_model:
            print(f"  {DIM}0. Skip — use {fallback_model} instead{RESET}")
        else:
            print(f"  {DIM}0. Skip — exit Forge{RESET}")
        print()

        try:
            choice = input(
                f"{GREEN}Download which model? "
                f"[1={rec_model} (recommended), 0 to skip]: {RESET}"
            ).strip()
        except (EOFError, KeyboardInterrupt):
            choice = "0"

        if not choice or choice == "0":
            if fallback_model:
                self.llm.model = fallback_model
                self.io.print_info(f"Using: {fallback_model}")
                return True
            return False

        try:
            idx = int(choice) - 1
            if not (0 <= idx < len(choices)):
                raise ValueError()
        except ValueError:
            idx = 0  # Default to recommended
            self.io.print_info(f"Defaulting to recommended: {choices[0][0]}")

        model_name = choices[idx][0]
        print()
        print(f"{BOLD}Downloading {model_name}...{RESET}")
        print(f"{DIM}This may take several minutes depending on your connection.{RESET}")
        print()

        try:
            last_status = ""
            for progress in self.llm.pull_model(model_name):
                if progress != last_status:
                    print(f"\r  {CYAN}{progress:60}{RESET}", end="", flush=True)
                    last_status = progress
            print()
            print(f"\n{GREEN}{BOLD}Download complete!{RESET}")
            self.llm.model = model_name
            return True
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Download cancelled.{RESET}")
            if fallback_model:
                self.llm.model = fallback_model
                self.io.print_info(f"Using: {fallback_model}")
                return True
            return False
        except Exception as e:
            self.io.print_error(f"Download failed: {e}")
            if fallback_model:
                self.llm.model = fallback_model
                self.io.print_info(f"Falling back to: {fallback_model}")
                return True
            return False

    def _agent_loop(self) -> Optional[str]:
        """Run LLM -> tool calls -> LLM loop until no more tool calls.

        Returns None for normal completion, or a redirect string if the
        user pressed Escape and typed new input (or "undo" for rollback).

        Guards against infinite loops:
          1. Max 15 iterations per turn
          2. Strip tool-call JSON from text before saving to context
          3. Detect duplicate tool calls (same tool+args as prev iteration)
          4. Warn user if iteration limit reached

        Interrupt points:
          B: After each streaming chunk — breaks out of stream
          C: Before each tool call — skips remaining tools
          D: Normal exit — stops escape monitor
        """
        max_iterations = self.config.get("max_agent_iterations", 15)
        iteration = 0
        turn_cache_savings = 0
        total_prompt_tokens = 0
        total_eval_count = 0
        prev_tool_sigs: set[str] = set()  # detect duplicate calls
        prev_prev_sigs: set[str] = set()  # oscillation detection
        turn_file_reads: dict[str, int] = {}  # per-file read count
        turn_tool_counts: dict[str, int] = {}  # per-tool call count

        while iteration < max_iterations:
            iteration += 1
            if self._current_checkpoint:
                self._current_checkpoint.iteration = iteration
            messages = self.ctx.get_messages()
            tools = self.tools.get_ollama_tools()

            full_response = ""
            tool_calls = []
            eval_count = 0
            prompt_tokens = 0
            duration_ns = 0
            stream_interrupted = False

            # Signal dashboard: brain is thinking
            self._write_dashboard_state("thinking")
            if self._dashboard and self._dashboard._running:
                self._dashboard.set_state("thinking")

            print()
            for chunk in self.llm.chat(messages, tools=tools):
                # Point B: check escape or voice interrupt after each chunk
                if self._escape_monitor.interrupted:
                    stream_interrupted = True
                    break
                # Voice interrupt check (every chunk is fine —
                # queue.get_nowait is ~0 cost)
                voice_action = self._check_voice_interrupt()
                if voice_action == "stop":
                    stream_interrupted = True
                    break

                if chunk["type"] == "token":
                    self.io.print_streaming_token(chunk["content"])
                    full_response += chunk["content"]
                elif chunk["type"] == "tool_call":
                    tool_calls.append(chunk["tool_call"])
                elif chunk["type"] == "done":
                    eval_count = chunk.get("eval_count", 0)
                    prompt_tokens = chunk.get("prompt_eval_count", 0)
                    duration_ns = chunk.get("total_duration_ns", 0)
                elif chunk["type"] == "error":
                    self._write_dashboard_state("error",
                                                {"msg": chunk["content"]})
                    print()
                    self.io.print_error(chunk["content"])
                    # Record billing for tokens consumed before error
                    self._turn_count += 1
                    self._turn_prompt_tokens = total_prompt_tokens
                    self._turn_eval_count = total_eval_count
                    if total_prompt_tokens or total_eval_count:
                        self.billing.record_turn(
                            input_tokens=total_prompt_tokens,
                            output_tokens=total_eval_count,
                            cache_hit_tokens=turn_cache_savings,
                        )
                    self._write_dashboard_state("idle")
                    return None

            # Post-stream interrupt check
            if stream_interrupted or self._escape_monitor.interrupted:
                print()  # newline after partial stream
                return self._handle_interrupt(
                    self._current_checkpoint, full_response)

            # Accumulate billing across all iterations (bug fix)
            total_prompt_tokens += prompt_tokens
            total_eval_count += eval_count

            # Record performance sample for analytics
            if eval_count > 0 and duration_ns > 0:
                self.stats.record_llm_call(
                    prompt_tokens=prompt_tokens,
                    eval_tokens=eval_count,
                    duration_ns=duration_ns,
                    iteration=iteration,
                    model=self.llm.model,
                )
                self.stats.record_context_usage(self.ctx.usage_pct)

            if full_response:
                print()

            if eval_count:
                self.io.print_stats(eval_count, prompt_tokens, duration_ns)
                self._total_generated += eval_count

            evict_cb = self.memory.record_eviction

            # Fallback: if model output tool calls as text (not structured),
            # parse them from the response
            text_parsed = False
            if not tool_calls and full_response:
                tool_calls = self._parse_text_tool_calls(full_response)
                if tool_calls:
                    text_parsed = True
                    print(f"\n{DIM}(parsed {len(tool_calls)} tool "
                          f"call{'s' if len(tool_calls) > 1 else ''} "
                          f"from text output){RESET}")

            # Save assistant response to context — but if we parsed tool
            # calls from text, strip the JSON blocks out so the model
            # doesn't see its own tool call JSON and loop on it
            if full_response:
                ctx_response = full_response
                if text_parsed:
                    ctx_response = self._strip_tool_json(full_response)
                if ctx_response.strip():
                    try:
                        self.ctx.add("assistant", ctx_response, tag="response",
                                     eviction_callback=evict_cb)
                    except ContextFullError as e:
                        self.io.print_error(str(e))
                        return None

            if not tool_calls:
                # No tool calls = turn is done, brain goes idle
                self._write_dashboard_state("idle")
                if self._dashboard and self._dashboard._running:
                    self._dashboard.set_state("idle")
                self._turn_count += 1
                # Record accumulated billing for entire turn
                self._turn_prompt_tokens = total_prompt_tokens
                self._turn_eval_count = total_eval_count
                self.billing.record_turn(
                    input_tokens=total_prompt_tokens,
                    output_tokens=total_eval_count,
                    cache_hit_tokens=turn_cache_savings,
                )
                return None

            # Duplicate detection: if every tool call this iteration is
            # identical to the previous iteration, the model is looping
            current_sigs = set()
            for tc in tool_calls:
                fn_info = tc.get("function", {})
                sig = json.dumps(
                    {"n": fn_info.get("name"), "a": fn_info.get("arguments")},
                    sort_keys=True)
                current_sigs.add(sig)

            if current_sigs and current_sigs == prev_tool_sigs:
                self.io.print_warning(
                    "Detected duplicate tool calls — stopping loop "
                    "to prevent repeating the same work.")
                self._write_dashboard_state("idle")
                if self._dashboard and self._dashboard._running:
                    self._dashboard.set_state("idle")
                # Record billing for tokens consumed before loop exit
                self._turn_count += 1
                self._turn_prompt_tokens = total_prompt_tokens
                self._turn_eval_count = total_eval_count
                if total_prompt_tokens or total_eval_count:
                    self.billing.record_turn(
                        input_tokens=total_prompt_tokens,
                        output_tokens=total_eval_count,
                        cache_hit_tokens=turn_cache_savings,
                    )
                return None

            # Oscillation: A -> B -> A pattern
            if (current_sigs and current_sigs == prev_prev_sigs
                    and current_sigs != prev_tool_sigs):
                self.io.print_warning(
                    "Detected oscillating tool calls — stopping loop.")
                self._write_dashboard_state("idle")
                if self._dashboard and self._dashboard._running:
                    self._dashboard.set_state("idle")
                # Record billing for tokens consumed before loop exit
                self._turn_count += 1
                self._turn_prompt_tokens = total_prompt_tokens
                self._turn_eval_count = total_eval_count
                if total_prompt_tokens or total_eval_count:
                    self.billing.record_turn(
                        input_tokens=total_prompt_tokens,
                        output_tokens=total_eval_count,
                        cache_hit_tokens=turn_cache_savings,
                    )
                return None

            prev_prev_sigs = prev_tool_sigs
            prev_tool_sigs = current_sigs

            for tc in tool_calls:
                # Point C: check escape or voice before each tool call
                if self._escape_monitor.interrupted:
                    return self._handle_interrupt(
                        self._current_checkpoint, full_response)
                voice_action = self._check_voice_interrupt()
                if voice_action == "stop":
                    return self._handle_interrupt(
                        self._current_checkpoint, full_response)

                fn_info = tc.get("function", {})
                fn_name = fn_info.get("name", "unknown")
                fn_args = fn_info.get("arguments", {})

                if isinstance(fn_args, str):
                    try:
                        fn_args = json.loads(fn_args)
                    except json.JSONDecodeError:
                        fn_args = {}

                # Dedup: suppress near-duplicate tool calls
                if fn_name != "think":
                    dedup_result = self.dedup.check(fn_name, fn_args)
                    if dedup_result:
                        sim_pct = dedup_result["similarity"] * 100
                        cross = dedup_result.get("cross_turn", False)
                        if cross:
                            nudge = (
                                f"[System: {fn_name} suppressed — you "
                                f"already called this with near-identical "
                                f"args last turn ({sim_pct:.0f}% match). "
                                f"Use the results you already have.]")
                        else:
                            nudge = (
                                f"[System: Duplicate {fn_name} suppressed "
                                f"({sim_pct:.0f}% similar to a recent "
                                f"call). Move on to a different action.]")
                        print(f"  {YELLOW}{DIM}{nudge}{RESET}")
                        try:
                            self.ctx.add("tool", nudge,
                                         tag=f"dedup:{fn_name}",
                                         partition="working")
                        except ContextFullError as e:
                            log.warning("Context full, skipped injection: %s", e)
                        continue

                # Crucible: check tool call for behavioral anomalies + canary
                if self.crucible.enabled and fn_name != "think":
                    cmd_str = fn_args.get("command", "")
                    threat = self.crucible.check_tool_call(
                        fn_name, fn_args, cmd_str)
                    if threat:
                        self._write_dashboard_state("threat",
                                                    {"tool": fn_name})
                        choice = self.crucible.handle_threat_interactive(
                            threat, "")
                        self._write_dashboard_state("idle")
                        if choice == "skip":
                            result = (f"Error: Blocked by Crucible — "
                                      f"{threat.description}")
                            is_error = True
                            self.io.print_tool_error(result)
                            self.ctx.add(
                                "tool", result,
                                tag=f"result:{fn_name}",
                                partition="working")
                            continue
                        # ignore or other — proceed

                # Think tool gets subtle display
                if fn_name == "think":
                    thought = fn_args.get("thought", "")
                    preview = thought[:120].replace("\n", " ")
                    print(f"\n  {DIM}[thinking: {preview}...]{RESET}")
                    tool_result = self.tools.call(fn_name, fn_args)
                    result = tool_result.output
                    is_error = False
                else:
                    self.io.print_tool_call(fn_name, fn_args)
                    self._write_dashboard_state("tool_exec",
                                                {"tool": fn_name})
                    if self._dashboard and self._dashboard._running:
                        self._dashboard.set_state("tool_exec")
                    tool_result = self.tools.call(fn_name, fn_args)
                    result = tool_result.output
                    is_error = not tool_result.success
                    if is_error:
                        self.io.print_tool_error(result)
                    else:
                        self.io.print_tool_result(result)

                # Error nudge system — inject guidance when tools fail
                if is_error:
                    self._turn_error_counts[fn_name] = (
                        self._turn_error_counts.get(fn_name, 0) + 1)
                    err_count = self._turn_error_counts[fn_name]

                    nudge = None
                    if fn_name == "edit_file":
                        nudge = (
                            "[System: edit_file failed. The old_string may "
                            "not match exactly or may not be unique. Read "
                            "the file first to verify the exact text.]")
                    elif fn_name == "read_file" and "not found" in result:
                        nudge = (
                            "[System: File not found. Use glob_files or "
                            "list_directory to find the correct path.]")
                    elif err_count >= 2:
                        nudge = (
                            f"[System: {fn_name} has failed {err_count} "
                            f"times. Try a different approach or ask the "
                            f"user for help.]")

                    if nudge:
                        print(f"  {YELLOW}{DIM}{nudge}{RESET}")
                        try:
                            self.ctx.add("system", nudge,
                                         tag="error_nudge",
                                         partition="working")
                        except ContextFullError as e:
                            log.warning("Context full, skipped injection: %s", e)
                else:
                    self._turn_error_counts[fn_name] = 0

                # Track tool calls for episodic memory + analytics
                self._current_turn_tools.append({
                    "name": fn_name,
                    "args": fn_args,
                })
                self.stats.record_tool_call(fn_name)
                self.forensics.record("tool", f"{fn_name}",
                                      {"name": fn_name})
                self.crucible.record_provenance(fn_name, fn_args)

                # Smarter loop detection: per-file reads + per-tool counts
                turn_tool_counts[fn_name] = (
                    turn_tool_counts.get(fn_name, 0) + 1)
                if fn_name == "read_file":
                    fp = fn_args.get("file_path", "")
                    turn_file_reads[fp] = (
                        turn_file_reads.get(fp, 0) + 1)
                    if turn_file_reads[fp] >= 3:
                        nudge = (
                            f"[System: You have read {Path(fp).name} "
                            f"{turn_file_reads[fp]} times this turn. "
                            f"Its content is already in your context.]")
                        print(f"  {YELLOW}{DIM}{nudge}{RESET}")
                        try:
                            self.ctx.add("system", nudge,
                                         tag="loop_nudge",
                                         partition="working")
                        except ContextFullError as e:
                            log.warning("Context full, skipped injection: %s", e)
                if turn_tool_counts[fn_name] >= 5 and fn_name != "think":
                    nudge = (
                        f"[System: {fn_name} called "
                        f"{turn_tool_counts[fn_name]} times this turn. "
                        f"Consider a different approach.]")
                    print(f"  {YELLOW}{DIM}{nudge}{RESET}")
                    try:
                        self.ctx.add("system", nudge,
                                     tag="loop_nudge",
                                     partition="working")
                    except ContextFullError as e:
                        log.warning("Context full, skipped injection: %s", e)

                # Track files touched
                file_path = fn_args.get("file_path", "")
                if file_path and file_path not in self._current_turn_files:
                    self._current_turn_files.append(file_path)

                # Track cache savings
                if "[CACHED - unchanged" in result:
                    hit = self.cache.check(fn_args.get("file_path", ""))
                    if hit:
                        turn_cache_savings += hit["tokens_saved"]

                tag = f"tool:{fn_name}"

                tool_msg = f"[Tool: {fn_name}]\n{result}"
                try:
                    self.ctx.add(
                        "tool", tool_msg, tag=tag,
                        file_path=file_path if fn_name == "read_file" else "",
                        eviction_callback=evict_cb,
                    )
                except ContextFullError as e:
                    self.io.print_error(str(e))
                    return None

            if not full_response:
                try:
                    self.ctx.add("assistant", "(tool calls)", tag="tool_dispatch")
                except ContextFullError as e:
                    self.io.print_error(str(e))
                    return None

        # Loop hit max iterations — force idle and warn
        self._write_dashboard_state("idle")
        if self._dashboard and self._dashboard._running:
            self._dashboard.set_state("idle")
        self.io.print_warning(f"Agent loop hit safety limit ({max_iterations} iterations)")
        # Record billing for tokens consumed across all iterations
        self._turn_count += 1
        self._turn_prompt_tokens = total_prompt_tokens
        self._turn_eval_count = total_eval_count
        if total_prompt_tokens or total_eval_count:
            self.billing.record_turn(
                input_tokens=total_prompt_tokens,
                output_tokens=total_eval_count,
                cache_hit_tokens=turn_cache_savings,
            )
        return None

    # ── Plan Mode Execution ──

    def _run_plan_mode(self, user_input: str) -> Optional[str]:
        """Run plan mode: get plan from model, show to user, get approval.

        Returns:
            "executed" — plan was approved and executed
            "rejected" — user rejected the plan
            None       — plan mode produced no plan, fall through to normal
        """
        from forge.planner import PLAN_PROMPT

        # Step 1: Get the plan from the model
        plan_prompt = self.planner.get_plan_prompt(user_input)
        try:
            self.ctx.add("system", plan_prompt, tag="plan_request",
                         partition="working")
        except ContextFullError as e:
            self.io.print_error(str(e))
            return None

        print(f"\n  {CYAN}{BOLD}Generating plan...{RESET}\n")

        # Run a single LLM call (no tool execution)
        messages = self.ctx.get_messages()
        full_response = ""
        for chunk in self.llm.chat(messages, tools=[]):
            if chunk["type"] == "token":
                full_response += chunk["content"]
            elif chunk["type"] == "done":
                break
            elif chunk["type"] == "error":
                self.io.print_error(chunk["content"])
                return None

        if not full_response.strip():
            self.io.print_warning("Model produced no plan.")
            return None

        # Step 2: Parse and display the plan
        plan = self.planner.receive_plan(full_response)
        if not plan.steps:
            # Model didn't produce numbered steps — show raw output
            print(full_response)
            self.io.print_warning("Could not parse structured plan. "
                          "Proceeding with normal execution.")
            # Save the response to context and let normal flow handle it
            try:
                self.ctx.add("assistant", full_response,
                             tag="response", partition="working")
            except ContextFullError as e:
                log.warning("Context full, skipped injection: %s", e)
            return None

        # Show the formatted plan
        plan_display = self.planner.format_plan(plan)
        print(plan_display)

        # Step 3: Get user approval
        print(f"  {YELLOW}{BOLD}[A]{RESET}pprove  "
              f"{YELLOW}{BOLD}[S]{RESET}tep-by-step  "
              f"{YELLOW}{BOLD}[R]{RESET}eject  "
              f"{YELLOW}{BOLD}[E]{RESET}dit")
        sys.stdout.write(f"  {YELLOW}{BOLD}Choice:{RESET} ")
        sys.stdout.flush()

        try:
            choice = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            self.planner.reject()
            self.io.print_info("Plan rejected.")
            return "rejected"

        if choice in ("r", "reject"):
            self.planner.reject()
            self.io.print_info("Plan rejected.")
            # Remove the plan request from context
            return "rejected"

        if choice in ("e", "edit"):
            self.io.print_info("Enter your modified instructions "
                       "(the plan will be regenerated):")
            sys.stdout.write(f"  {CYAN}>{RESET} ")
            sys.stdout.flush()
            try:
                new_input = input().strip()
            except (EOFError, KeyboardInterrupt):
                self.planner.reject()
                return "rejected"
            if new_input:
                self.planner.reject()
                self.planner.arm()  # re-arm for the new input
                try:
                    self.ctx.add("user", new_input, tag="user_msg")
                except ContextFullError as e:
                    self.io.print_error(str(e))
                    return "rejected"
                return self._run_plan_mode(new_input)
            self.planner.reject()
            return "rejected"

        step_by_step = choice in ("s", "step", "step-by-step")
        self.planner.approve(step_by_step=step_by_step)

        # Step 4: Execute the plan
        print(f"\n  {GREEN}{BOLD}Plan approved. Executing...{RESET}\n")

        # Save plan to context as assistant response
        try:
            self.ctx.add("assistant", full_response,
                         tag="plan", partition="working")
        except ContextFullError as e:
            log.warning("Context full, skipped plan injection: %s", e)

        if step_by_step:
            return self._execute_plan_stepwise(user_input)
        else:
            return self._execute_plan_full(user_input)

    def _execute_plan_full(self, original_input: str) -> str:
        """Execute the full plan in one agent loop."""
        exec_prompt = self.planner.get_full_execution_prompt(original_input)
        try:
            self.ctx.add("user", exec_prompt, tag="plan_exec")
        except ContextFullError as e:
            self.io.print_error(str(e))
            return "rejected"

        # Reset per-turn tracking
        self._current_turn_tools = []
        self._current_turn_files = []
        self._turn_prompt_tokens = 0
        self._turn_eval_count = 0
        self._turn_error_counts = {}
        self.dedup.reset()

        self._current_checkpoint = TurnCheckpoint(
            context_entry_count=self.ctx.entry_count,
            context_total_tokens=self.ctx.total_tokens,
            timestamp=time.time(),
        )
        self._escape_monitor.reset()
        self._escape_monitor.start()

        self._agent_loop()

        self._escape_monitor.stop()
        self._current_checkpoint = None
        self.planner.complete()

        # Record turn
        last_response = self._get_last_assistant_response()
        self.memory.record_turn(
            user_message=original_input,
            assistant_response=last_response,
            tool_calls=self._current_turn_tools,
            files_touched=self._current_turn_files,
            tokens_used=self._turn_prompt_tokens + self._turn_eval_count,
        )
        self._auto_context_swap()
        return "executed"

    def _execute_plan_stepwise(self, original_input: str) -> str:
        """Execute the plan one step at a time with progress display."""
        plan = self.planner.current_plan
        if not plan:
            return "rejected"

        for step in plan.steps:
            self.planner.mark_step_in_progress(step.number)

            # Show progress
            print(self.planner.format_progress())
            print(f"\n  {CYAN}{BOLD}Step {step.number}:{RESET} "
                  f"{step.title}")

            step_prompt = self.planner.get_step_prompt(
                step, original_input)
            try:
                self.ctx.add("user", step_prompt, tag="plan_step")
            except ContextFullError as e:
                self.io.print_error(str(e))
                break

            # Reset per-turn tracking for this step
            self._current_turn_tools = []
            self._current_turn_files = []
            self._turn_prompt_tokens = 0
            self._turn_eval_count = 0
            self._turn_error_counts = {}
            self.dedup.reset()

            self._current_checkpoint = TurnCheckpoint(
                context_entry_count=self.ctx.entry_count,
                context_total_tokens=self.ctx.total_tokens,
                timestamp=time.time(),
            )
            self._escape_monitor.reset()
            self._escape_monitor.start()

            redirect = self._agent_loop()

            self._escape_monitor.stop()
            self._current_checkpoint = None

            if redirect:
                # User interrupted — stop step execution
                self.planner.skip_step(step.number)
                break

            self.planner.mark_step_done(step.number)

            # ── Plan step verification ──
            if self.plan_verifier.enabled:
                vr = self.plan_verifier.verify_step(step.number)
                print(self.plan_verifier.format_result(vr))

                # Store result on the step
                step.verified = vr.passed
                step.verification_result = {
                    "passed": vr.passed,
                    "checks": [
                        {"name": c.name, "passed": c.passed,
                         "duration_ms": c.duration_ms}
                        for c in vr.checks
                    ],
                }

                if not vr.passed:
                    if self.plan_verifier.mode == "repair":
                        # Inject repair prompt and run one more agent loop
                        repair_prompt = self.plan_verifier.get_repair_prompt(
                            vr, step.title)
                        try:
                            self.ctx.add("user", repair_prompt,
                                         tag="plan_repair")
                        except ContextFullError as e:
                            log.warning("Context full during repair: %s", e)
                        else:
                            # Restart escape monitor so user can interrupt repair
                            self._escape_monitor.reset()
                            self._escape_monitor.start()
                            self._agent_loop()
                            self._escape_monitor.stop()
                            # Re-verify after repair
                            vr2 = self.plan_verifier.verify_step(step.number)
                            print(self.plan_verifier.format_result(vr2))
                            if vr2.passed:
                                vr2.auto_fixed = True
                                step.verified = True

                    elif self.plan_verifier.mode == "strict":
                        # Rollback: restore files from checkpoint
                        if self._current_checkpoint:
                            cp = self._current_checkpoint
                            for fpath, backup in cp.file_backups.items():
                                try:
                                    if backup is None:
                                        Path(fpath).unlink(missing_ok=True)
                                    else:
                                        # Use filesystem.write_file for
                                        # atomic rollback writes
                                        filesystem.write_file(fpath, backup)
                                except Exception as ex:
                                    log.warning("Rollback failed for %s: %s",
                                                fpath, ex)
                            for fpath in cp.files_created:
                                try:
                                    Path(fpath).unlink(missing_ok=True)
                                except Exception:
                                    pass
                            vr.rolled_back = True
                            print(f"  {RED}{BOLD}Step {step.number} "
                                  f"rolled back{RESET}")
                        break

        # Show final progress + verification summary
        print(self.planner.format_progress())
        if self.plan_verifier.enabled:
            print(self.plan_verifier.format_summary())
        self.planner.complete()

        # Record combined turn
        last_response = self._get_last_assistant_response()
        self.memory.record_turn(
            user_message=original_input,
            assistant_response=last_response,
            tool_calls=self._current_turn_tools,
            files_touched=self._current_turn_files,
            tokens_used=self._turn_prompt_tokens + self._turn_eval_count,
        )
        self._auto_context_swap()
        return "executed"

    # ── Voice Interrupt (mid-processing) ──

    def _check_voice_interrupt(self) -> Optional[str]:
        """Check if voice input arrived during processing.

        Returns:
          - "stop" if the user wants to halt
          - A question string if it's a quick question to answer inline
          - None if nothing in the queue or message is noise/irrelevant
        """
        if self._voice is None:
            return None

        try:
            voice_text = self._voice_queue.get_nowait()
        except queue.Empty:
            return None

        if not voice_text or not voice_text.strip():
            return None

        text = voice_text.strip()
        print(f"\n{MAGENTA}[voice mid-turn]{RESET} {text}")

        # Classify the voice message using LLM for intelligent routing.
        # Keep the classification prompt tiny for speed.
        intent = self._classify_voice_intent(text)

        if intent == "stop":
            print(f"  {YELLOW}[voice → interrupt]{RESET}")
            self._escape_monitor._interrupted.set()
            return "stop"
        elif intent == "question":
            print(f"  {CYAN}[voice → answering inline...]{RESET}")
            self._answer_inline_question(text)
            return None  # Continue processing after answering
        else:
            # Noise, irrelevant, or talking to someone else
            print(f"  {DIM}[voice → ignored (not directed at me)]{RESET}")
            return None

    def _classify_voice_intent(self, text: str) -> str:
        """Classify voice input as 'stop', 'question', or 'ignore'.

        Uses a fast LLM call with a tiny prompt. Falls back to keyword
        detection if the LLM call would be too slow.
        """
        lower = text.lower().strip().rstrip(".!?")

        # Fast path: obvious stop commands (no LLM needed)
        # Build dynamic stop phrases using the persona's name
        persona = get_persona()
        name_lower = persona.name.lower()
        stop_phrases = {
            "stop", "hold on", "wait", "pause", "cancel", "never mind",
            "nevermind", "abort", "quit", "shut up", "enough",
            "stop that", "hold up", "hang on", "wait a minute",
            "wait a sec", "hey stop",
            f"{name_lower} stop", f"stop {name_lower}",
            f"hey {name_lower} stop", f"{name_lower} wait",
            f"{name_lower} hold on", f"{name_lower} pause",
        }
        for phrase in stop_phrases:
            if lower == phrase or lower.startswith(phrase + " "):
                return "stop"

        # Fast path: obvious noise (very short, no question marks,
        # no direct address)
        if len(text.split()) <= 2 and "?" not in text:
            # Two words or less with no question mark — likely noise
            # unless it's a command
            return "ignore"

        # Use LLM for intelligent classification
        classify_prompt = (
            "You are classifying a voice message that arrived while an AI "
            "assistant was busy processing a task. The user may be talking "
            "to the AI, or talking to someone/something else (TV, pet, etc).\n\n"
            f'Voice message: "{text}"\n\n'
            "Classify as exactly one word:\n"
            "- STOP — if the user wants the AI to stop/pause/wait\n"
            "- QUESTION — if the user is asking the AI a question or "
            "giving it new instructions\n"
            "- IGNORE — if this seems like background speech not directed "
            "at the AI (talking to TV, to themselves, ambient)\n\n"
            "Reply with ONLY the classification word:"
        )

        try:
            # Use a fast, non-streaming call
            result = ""
            for chunk in self.llm.chat(
                [{"role": "user", "content": classify_prompt}],
                tools=None,
                temperature=0.0,
                stream=False,
            ):
                if chunk["type"] == "token":
                    result += chunk["content"]

            classification = result.strip().upper().split()[0] if result.strip() else "IGNORE"

            if classification == "STOP":
                return "stop"
            elif classification == "QUESTION":
                return "question"
            else:
                return "ignore"
        except Exception as e:
            log.debug("Voice classification failed: %s", e)
            # Fallback: if it has a question mark, treat as question
            if "?" in text:
                return "question"
            return "ignore"

    def _answer_inline_question(self, question: str):
        """Answer a quick voice question without disrupting the main task.

        Sends a minimal prompt, prints the answer, then returns so the
        agent loop can continue where it left off.
        """
        try:
            # Mute VOX during response to prevent feedback loop
            if self._voice:
                self._voice._vox_muted = True

            brief_prompt = (
                "The user just asked a quick voice question while you were "
                "working on something else. Answer BRIEFLY (1-3 sentences max), "
                "then they'll let you get back to work.\n\n"
                f"Question: {question}"
            )

            print(f"\n{WHITE}", end="")
            answer_text = ""
            for chunk in self.llm.chat(
                [{"role": "system", "content": "Be extremely brief."},
                 {"role": "user", "content": brief_prompt}],
                tools=None,
                temperature=0.3,
                stream=True,
            ):
                if chunk["type"] == "token":
                    sys.stdout.write(chunk["content"])
                    sys.stdout.flush()
                    answer_text += chunk["content"]
            print(f"{RESET}")

            # Speak the answer if TTS is active
            if self._tts and self._tts.enabled:
                self._tts.speak(answer_text)

            # Add to context so the main task has awareness
            try:
                self.ctx.add("user", f"[Voice interrupt: {question}]",
                             tag="voice_interrupt", partition="working")
                self.ctx.add("assistant", answer_text.strip(),
                             tag="voice_answer", partition="working")
            except ContextFullError as e:
                log.warning("Context full, skipped injection: %s", e)

            print(f"{DIM}[resuming previous task...]{RESET}\n")
        except Exception as e:
            log.debug("Inline answer failed: %s", e)
            self.io.print_error(f"Couldn't answer: {e}")
        finally:
            if self._voice:
                self._voice._vox_muted = False

    # ── Interrupt + Rollback ──

    def _handle_interrupt(self, checkpoint: Optional[TurnCheckpoint],
                          partial_response: str) -> Optional[str]:
        """Handle an Escape-key interrupt. Shows status, prompts user.

        Returns:
          - "undo" if user wants rollback (caller handles it)
          - user's new input string if they want to redirect
          - None if they just want to stop
        """
        self._escape_monitor.stop()
        self._write_dashboard_state("idle")
        if self._dashboard and self._dashboard._running:
            self._dashboard.set_state("idle")

        # Gather status info
        word_count = len(partial_response.split()) if partial_response else 0
        entries_added = 0
        modified_files = []
        created_files = []

        if checkpoint:
            entries_added = self.ctx.entry_count - checkpoint.context_entry_count
            modified_files = [
                p for p, content in checkpoint.file_backups.items()
                if content is not None
            ]
            created_files = list(checkpoint.files_created)

        self.io.print_interrupt_banner(
            word_count=word_count,
            entries_added=entries_added,
            modified_files=modified_files,
            created_files=created_files,
        )

        # Prompt user for next action
        try:
            user_input = input(
                f"\n{GREEN}{BOLD}>{RESET} "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            user_input = ""

        if not user_input:
            return None

        if user_input.lower() == "undo":
            self._do_rollback(checkpoint)
            return "undo"

        # User typed new input — keep changes, return as redirect
        return user_input

    def _do_rollback(self, checkpoint: Optional[TurnCheckpoint]):
        """Roll back all changes from the current turn."""
        if checkpoint is None:
            self.io.print_warning("No checkpoint available for rollback.")
            return

        print(f"\n{YELLOW}{BOLD}Rolling back...{RESET}")

        # Restore files
        self._rollback_files(checkpoint)

        # Truncate context
        removed = self._rollback_context(checkpoint)

        print(f"\n{GREEN}{BOLD}Rollback complete.{RESET} "
              f"{DIM}State restored to before this turn.{RESET}")
        self.io.print_context_bar(self.ctx.status())

    def _rollback_files(self, checkpoint: TurnCheckpoint):
        """Restore files from checkpoint backups, delete newly created files."""
        # Delete files that were created this turn
        for fpath in checkpoint.files_created:
            try:
                p = Path(fpath)
                if p.exists():
                    p.unlink()
                    print(f"  {RED}Deleted:{RESET} {DIM}{p.name}{RESET}")
                # Invalidate cache for this file
                self.cache.invalidate(fpath)
            except Exception as e:
                log.debug("Rollback delete failed %s: %s", fpath, e)

        # Restore modified files to their original content
        for fpath, original_content in checkpoint.file_backups.items():
            if original_content is None:
                continue  # was a new file, already handled above
            try:
                Path(fpath).write_text(original_content, encoding="utf-8")
                print(f"  {CYAN}Restored:{RESET} {DIM}{Path(fpath).name}{RESET}")
                self.cache.invalidate(fpath)
            except Exception as e:
                log.debug("Rollback restore failed %s: %s", fpath, e)

    def _rollback_context(self, checkpoint: TurnCheckpoint) -> list:
        """Truncate context back to the checkpoint's entry count."""
        removed = self.ctx.truncate_to(checkpoint.context_entry_count)
        if removed:
            print(f"  {DIM}Removed {len(removed)} context entries{RESET}")
        return removed

    def _print_status_bar(self):
        """Print context bar + billing summary, push to dashboard."""
        self.io.print_context_bar(self.ctx.status())
        bs = self.billing.status()
        cs = self.cache.stats()
        parts = [
            f"[$$] Balance: ${bs['balance']:.2f}",
            f"Session: {bs['session_tokens']:,} tokens",
            f"Cache: {cs['tokens_saved']:,} saved ({cs['hit_rate']:.0f}% hit)",
        ]
        # Show swap count if any
        ts = self.memory.get_task_state()
        if ts and ts.context_swaps > 0:
            parts.append(f"Swaps: {ts.context_swaps}")
        print(f"{DIM}{' | '.join(parts)}{RESET}")

        # Continuity grade (shown after first swap)
        cg_status = self.continuity.format_status()
        if cg_status:
            print(f"{DIM}{cg_status}{RESET}")

        # Push live data to GUI dashboard if running
        if self._dashboard:
            self._push_dashboard_data()

    def _push_dashboard_data(self):
        """Push current stats to the GUI dashboard."""
        try:
            data = self._get_dashboard_snapshot()
            if data:
                self._dashboard.update_data(data)
        except Exception:
            pass

    def _write_dashboard_state(self, state: str, extra: dict = None):
        """Write animation state to cross-process file for FNC launcher.

        Uses atomic write (temp + rename) to avoid partial reads.
        """
        state_file = self._config_dir / "dashboard_state.json"
        payload = {
            "state": state,
            "timestamp": time.time(),
        }
        # Merge dashboard snapshot for launcher to display
        try:
            snapshot = self._get_dashboard_snapshot()
            if snapshot:
                payload.update(snapshot)
        except Exception:
            pass
        if extra:
            payload["extra"] = extra

        try:
            # Atomic write: write to temp file, then rename
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self._config_dir), suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f)
            # On Windows, os.replace is atomic within same volume
            os.replace(tmp_path, str(state_file))
        except Exception:
            # Non-critical — dashboard just won't update
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    def _inject_session_recap(self):
        """Load prior session journal entries and inject a recap into context.

        This gives the AI awareness of what happened in previous sessions
        so it can answer "what did we do last time?" and maintain continuity.
        """
        try:
            recent = self.memory.get_recent_entries(count=15)
            if not recent:
                return

            # Filter to entries from PRIOR sessions (not current)
            prior = [e for e in recent
                     if e.session_id != self.memory._session_id]
            if not prior:
                return

            lines = ["[Session Memory — prior session recap]\n"]

            # Group by session
            sessions = {}
            for e in prior:
                sessions.setdefault(e.session_id, []).append(e)

            for sid, entries in sessions.items():
                ts = entries[0].timestamp
                ts_str = time.strftime("%Y-%m-%d %H:%M",
                                       time.localtime(ts))
                lines.append(f"Session {sid[:8]} ({ts_str}):")
                for e in entries:
                    intent = e.user_intent.split("\n")[0][:120]
                    actions = ", ".join(e.actions_taken[:3]) or "conversation"
                    if len(actions) > 80:
                        actions = actions[:77] + "..."
                    response = e.assistant_response.split("\n")[0][:120]
                    lines.append(
                        f"  Turn {e.turn_number}: "
                        f"User: \"{intent}\" -> {actions}")
                    if response:
                        lines.append(f"    AI: {response}")
                    if e.files_touched:
                        files = ", ".join(
                            Path(f).name for f in e.files_touched[:5])
                        lines.append(f"    Files: {files}")

            # Task state from prior session
            ts = self.memory.get_task_state()
            if ts and ts.objective:
                lines.append(f"\nPrior objective: {ts.objective}")
                done = sum(1 for s in ts.subtasks
                           if s.get("status") == "done")
                total = len(ts.subtasks)
                if total:
                    lines.append(f"Progress: {done}/{total} subtasks")
                if ts.files_modified:
                    lines.append(
                        f"Files modified: "
                        f"{', '.join(Path(f).name for f in ts.files_modified[:10])}")
                if ts.decisions:
                    lines.append("Key decisions:")
                    for d in ts.decisions[-5:]:
                        lines.append(f"  - {d}")

            lines.append(
                "\nUse this context to maintain continuity. "
                "If the user asks what you discussed previously, "
                "refer to these entries.")

            recap = "\n".join(lines)
            self.ctx.add("system", recap, tag="session_memory", pinned=True)

            entry_count = len(prior)
            session_count = len(sessions)
            self.io.print_info(
                f"Session memory: loaded {entry_count} entries "
                f"from {session_count} prior session(s)")

        except Exception as exc:
            log.debug("Failed to inject session recap: %s", exc)

    def _init_semantic_index(self):
        """Initialize the semantic codebase index if embedding model is available."""
        self._write_dashboard_state("indexing")
        try:
            has_embed = self.llm.ensure_embed_model(auto_pull=False)
            if not has_embed:
                self._offer_embedding_model()
                # Re-check after offer
                has_embed = self.llm.ensure_embed_model(auto_pull=False)
                if not has_embed:
                    return

            self.index = CodebaseIndex(
                persist_dir=self._config_dir / "vectors",
                embed_fn=self.llm.embed,
            )
            # Wire embedding function to continuity monitor
            self.continuity._embed_fn = self.llm.embed

            idx_stats = self.index.stats()
            if idx_stats["total_chunks"] > 0:
                self.io.print_info(
                    f"Semantic index: {idx_stats['total_files']} files, "
                    f"{idx_stats['total_chunks']} chunks loaded")
            else:
                self.io.print_info("Semantic index: empty. Run /index to index codebase.")
        except Exception as e:
            log.warning("Failed to init semantic index: %s", e)
            self.io.print_warning(f"Semantic index unavailable: {e}")
        finally:
            self._write_dashboard_state("idle")

    def _offer_embedding_model(self):
        """Explain the embedding model and offer to pull it."""
        embed_model = str(self.config.get(
            "embedding_model", "nomic-embed-text"))

        print()
        print(f"{BOLD}{CYAN}{'=' * 56}{RESET}")
        print(f"{BOLD}{CYAN}  EMBEDDING MODEL — {embed_model}{RESET}")
        print(f"{BOLD}{CYAN}{'=' * 56}{RESET}")
        print(f"  {DIM}Tiny model (~274 MB) that unlocks major features:{RESET}")
        print()
        print(f"  {GREEN}*{RESET} Semantic Code Search (/search, /recall)")
        print(f"    {DIM}Find relevant code by meaning, not just keywords{RESET}")
        print()
        print(f"  {GREEN}*{RESET} Crucible Threat Detection (Layer 2)")
        print(f"    {DIM}Detect semantically anomalous content in files{RESET}")
        print()
        print(f"  {GREEN}*{RESET} Continuity Grade (auto-recovery)")
        print(f"    {DIM}Measure context quality and recover from swaps{RESET}")
        print()
        print(f"  {GREEN}*{RESET} Smart Context Injection")
        print(f"    {DIM}Auto-inject relevant code before each AI response{RESET}")
        print()
        print(f"  {DIM}Runs alongside your main model — barely touches VRAM.{RESET}")
        print()

        try:
            choice = input(
                f"  {GREEN}Pull {embed_model} now? [Y/n]: {RESET}"
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            choice = "n"

        if choice in ("", "y", "yes"):
            print(f"\n  {DIM}Downloading {embed_model}...{RESET}")
            try:
                last_status = ""
                for progress in self.llm.pull_model(embed_model):
                    if progress != last_status:
                        print(f"\r  {CYAN}{progress:50}{RESET}",
                              end="", flush=True)
                        last_status = progress
                print()
                print(f"  {GREEN}{BOLD}Embedding model ready!{RESET}\n")
            except KeyboardInterrupt:
                print(f"\n  {YELLOW}Download cancelled.{RESET}")
                self.io.print_info("You can pull it later with: /index")
            except Exception as e:
                self.io.print_error(f"Download failed: {e}")
                self.io.print_info("You can pull it later with: /index")
        else:
            self.io.print_info(
                f"Skipped. Pull it anytime with: /index"
            )
            print()

    def _inject_semantic_context(self, query: str):
        """Inject relevant code chunks from the semantic index before LLM call."""
        if self.index is None:
            return

        try:
            results = self.index.search(query, top_k=3)
        except Exception as e:
            log.debug("Semantic search failed: %s", e)
            return

        for r in results:
            if r["score"] < 0.35:
                continue

            # Skip files already in context
            already_in_ctx = False
            for entry in self.ctx._entries:
                if entry.file_path and Path(entry.file_path).resolve() == Path(r["file_path"]).resolve():
                    already_in_ctx = True
                    break
            if already_in_ctx:
                continue

            recall_text = (
                f"[Semantic Recall] {r['file_path']} "
                f"(lines {r['start_line']}-{r['end_line']}, "
                f"relevance: {r['score']:.2f})\n"
                f"```{r['language']}\n{r['content']}\n```"
            )
            self.ctx.inject_recall(recall_text, source=r["file_path"])

    def _continuity_recovery(self, level: str):
        """Re-read files and re-inject semantic recalls to restore context quality.

        Args:
            level: "mild" or "aggressive"
        """
        self._write_dashboard_state("indexing")  # magenta animation
        ts = self.memory.get_task_state()

        print(f"\n{MAGENTA}{BOLD}  Continuity recovery ({level})...{RESET}")

        # Mild: re-read modified files + semantic recalls for objective
        if ts and ts.files_modified:
            for fpath in ts.files_modified[-10:]:  # last 10 files
                try:
                    content = self.cache.read(fpath) if self.cache else None
                    if content is None:
                        p = Path(fpath)
                        if p.exists() and p.stat().st_size < 50000:
                            content = p.read_text(encoding="utf-8",
                                                  errors="replace")
                    if content:
                        recall_text = (
                            f"[Continuity Recovery] {fpath}\n"
                            f"```\n{content[:3000]}\n```"
                        )
                        self.ctx.inject_recall(recall_text, source=fpath)
                except Exception as e:
                    log.debug("Recovery file re-read failed %s: %s", fpath, e)

        if self.index and ts and ts.objective:
            try:
                results = self.index.search(ts.objective, top_k=3)
                for r in results:
                    if r["score"] >= 0.30:
                        recall_text = (
                            f"[Continuity Recall] {r['file_path']} "
                            f"(lines {r['start_line']}-{r['end_line']})\n"
                            f"```{r['language']}\n{r['content']}\n```"
                        )
                        self.ctx.inject_recall(
                            recall_text, source=r["file_path"])
            except Exception as e:
                log.debug("Recovery semantic recall failed: %s", e)

        # Aggressive: also re-inject subtask recalls
        if level == "aggressive" and self.index and ts:
            for subtask in ts.subtasks[-5:]:
                desc = subtask.get("description", "")
                if not desc:
                    continue
                try:
                    results = self.index.search(desc, top_k=2)
                    for r in results:
                        if r["score"] >= 0.35:
                            recall_text = (
                                f"[Subtask Recall] {r['file_path']} "
                                f"(lines {r['start_line']}-{r['end_line']})\n"
                                f"```{r['language']}\n{r['content']}\n```"
                            )
                            self.ctx.inject_recall(
                                recall_text, source=r["file_path"])
                except Exception:
                    pass

        recovered = sum(
            1 for e in self.ctx._entries
            if getattr(e, 'partition', '') == 'recall')
        print(f"  {GREEN}Injected {recovered} recall entries{RESET}")
        self._write_dashboard_state("idle")

    def _auto_context_swap(self):
        """Auto-swap context when threshold is reached — the key innovation."""
        SWAP_THRESHOLD = self.config.get("swap_threshold_pct", 85)
        pct = self.ctx.usage_pct
        if pct < SWAP_THRESHOLD:
            return

        self._write_dashboard_state("swapping")

        print()
        print(f"{BOLD}{YELLOW}{'=' * 50}{RESET}")
        print(f"{BOLD}{YELLOW}  AUTO CONTEXT SWAP{RESET}")
        print(f"{BOLD}{YELLOW}{'=' * 50}{RESET}")
        print(f"{DIM}  Context at {pct:.0f}% — swapping to free space...{RESET}")

        pre_tokens = self.ctx.total_tokens
        pre_entries = self.ctx.entry_count

        # 1. Journal all current context to episodic memory
        self.memory.record_eviction(self.ctx._entries)

        # 2. Extract last 3 turn pairs (working memory to preserve)
        working_pairs = self.ctx.get_working_memory(count=3)

        # 3. Generate swap summary from journal data
        swap_summary = self.memory.generate_swap_summary(self.ctx._entries)

        # 4. Clear all non-pinned entries
        cleared = self.ctx.clear()

        # 5. Inject swap summary as pinned system message
        self.ctx.add(
            "system", swap_summary,
            tag="swap_summary", pinned=True,
        )

        # 6. Inject semantic recalls for current objective
        ts = self.memory.get_task_state()
        if self.index and ts and ts.objective:
            try:
                results = self.index.search(ts.objective, top_k=3)
                for r in results:
                    if r["score"] >= 0.30:
                        recall_text = (
                            f"[Semantic Recall] {r['file_path']} "
                            f"(lines {r['start_line']}-{r['end_line']})\n"
                            f"```{r['language']}\n{r['content']}\n```"
                        )
                        self.ctx.inject_recall(recall_text, source=r["file_path"])
            except Exception as e:
                log.debug("Post-swap semantic recall failed: %s", e)

        # 7. Restore working memory (last 3 turn pairs)
        for entry in working_pairs:
            try:
                self.ctx.add(
                    entry.role, entry.content,
                    tag=entry.tag, partition="working",
                )
            except ContextFullError as e:
                log.warning("Context full during working memory restore: %s", e)
                break

        # 8. Update task state swap counter
        if ts:
            ts.context_swaps += 1
            ts.last_updated = time.time()
            self.memory._save_task_state()
        else:
            self.memory.update_task(objective="(auto-detected)")

        # 9. Report
        post_tokens = self.ctx.total_tokens
        post_entries = self.ctx.entry_count
        freed = pre_tokens - post_tokens
        recalls = sum(1 for e in self.ctx._entries if e.partition == "recall")

        print(f"  {GREEN}Freed: {freed:,} tokens "
              f"({pre_entries - post_entries} entries evicted){RESET}")
        print(f"  {CYAN}Kept: swap summary + {len(working_pairs)} "
              f"working memory entries + {recalls} semantic recalls{RESET}")
        print(f"  {DIM}Context now at {self.ctx.usage_pct:.0f}% "
              f"({post_tokens:,}/{self.ctx.max_tokens:,}){RESET}")
        print(f"{BOLD}{YELLOW}{'=' * 50}{RESET}")
        print(f"{DIM}  Session continues seamlessly. "
              f"Use /journal to review history.{RESET}\n")

        # Record swap in continuity monitor with recall scores
        recall_scores = []
        if self.index and ts and ts.objective:
            try:
                for e in self.ctx._entries:
                    if getattr(e, 'partition', '') == 'recall':
                        # Extract score from recall text if present
                        content = getattr(e, 'content', '')
                        if 'relevance:' in content:
                            import re
                            m = re.search(r'relevance:\s*([\d.]+)', content)
                            if m:
                                recall_scores.append(float(m.group(1)))
            except Exception:
                pass
        self.continuity.record_swap(self._turn_count, recall_scores)

        self._write_dashboard_state("idle")

    def _get_last_assistant_response(self) -> str:
        """Extract the last assistant response from context."""
        for entry in reversed(self.ctx._entries):
            if entry.role == "assistant" and entry.tag == "response":
                return entry.content[:500]
        return ""

    # ── Fallback tool call parser ──

    def _parse_text_tool_calls(self, text: str) -> list[dict]:
        """Parse tool calls from model text output.

        Some models output tool calls as JSON text instead of using
        Ollama's structured tool_calls. This fallback detects and
        parses them so tools still work.

        Looks for patterns like:
          {"name": "tool_name", "arguments": {...}}
        or wrapped in ```json ... ``` blocks.
        """
        import re

        tool_names = set(self.tools.list_tools())
        calls = []

        # Strip markdown code blocks
        cleaned = re.sub(r'```(?:json)?\s*', '', text)
        cleaned = re.sub(r'```', '', cleaned)

        # Find JSON objects that look like tool calls
        # Match balanced braces
        depth = 0
        start = -1
        candidates = []
        for i, ch in enumerate(cleaned):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    candidates.append(cleaned[start:i + 1])
                    start = -1

        for candidate in candidates:
            try:
                obj = json.loads(candidate)
            except (json.JSONDecodeError, ValueError):
                continue

            # Check if it looks like a tool call
            name = obj.get("name", "")
            args = obj.get("arguments", None)

            if name in tool_names and isinstance(args, dict):
                calls.append({
                    "function": {
                        "name": name,
                        "arguments": args,
                    }
                })

        if calls:
            log.info("Parsed %d tool call(s) from text response", len(calls))

        return calls

    def _strip_tool_json(self, text: str) -> str:
        """Remove tool-call JSON blocks from assistant text.

        When the model outputs tool calls as text (e.g. ```json { "name":
        "read_file", ...} ```), we execute them but need to strip the JSON
        from the saved context. Otherwise the model sees its own JSON on
        the next iteration and enters an infinite loop re-executing them.

        Keeps the surrounding natural language — only removes the JSON
        objects that match registered tool names.
        """
        import re

        tool_names = set(self.tools.list_tools())
        result = text

        # Remove ```json ... ``` blocks containing tool calls
        def replace_codeblock(m):
            content = m.group(1).strip()
            try:
                obj = json.loads(content)
                if (isinstance(obj, dict) and
                        obj.get("name", "") in tool_names):
                    return ""  # remove this block
            except (json.JSONDecodeError, ValueError):
                pass
            return m.group(0)  # keep non-tool code blocks

        result = re.sub(
            r'```(?:json)?\s*(.*?)```',
            replace_codeblock,
            result, flags=re.DOTALL)

        # Also remove bare JSON objects that look like tool calls
        depth = 0
        start = -1
        spans_to_remove = []
        for i, ch in enumerate(result):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    chunk = result[start:i + 1]
                    try:
                        obj = json.loads(chunk)
                        if (isinstance(obj, dict) and
                                obj.get("name", "") in tool_names and
                                isinstance(obj.get("arguments"), dict)):
                            spans_to_remove.append((start, i + 1))
                    except (json.JSONDecodeError, ValueError):
                        pass
                    start = -1

        # Remove spans in reverse order to preserve indices
        for s, e in reversed(spans_to_remove):
            result = result[:s] + result[e:]

        # Clean up leftover whitespace / empty lines
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result.strip()

    # ── Voice input ──

    def _init_voice(self):
        """Initialize voice input if dependencies are available."""
        try:
            from forge.audio.stt import VoiceInput, check_voice_deps
        except ImportError:
            return

        deps = check_voice_deps()
        if not deps["ready"]:
            if deps["missing"]:
                log.debug("Voice deps missing: %s", deps["missing"])
            return

        def on_transcription(text):
            """Voice callback — push transcribed text to the input queue."""
            print(f"\n{MAGENTA}[voice]{RESET} {text}")
            self._voice_queue.put(text)

        def on_state_change(state):
            """Update terminal indicator for voice state."""
            indicators = {
                "recording": f"{RED}[recording...]{RESET}",
                "transcribing": f"{YELLOW}[transcribing...]{RESET}",
            }
            if state in indicators:
                print(f"\r{indicators[state]}", end="", flush=True)
            elif state == "ready":
                # Clear the indicator
                print(f"\r{' ' * 30}\r", end="", flush=True)

        self._voice = VoiceInput(
            model_size="tiny",
            hotkey="`",
            mode="ptt",
            on_transcription=on_transcription,
            on_state_change=on_state_change,
        )

        if self._voice.initialize():
            self._voice.start_hotkey()
            persona = get_persona()
            self.io.print_info(f"Voice input ready — say \"{persona.name}, ...\" "
                       "or hold ` to speak")
            # Initialize TTS for voice responses
            try:
                from forge.audio.tts import TextToSpeech
                self._tts = TextToSpeech()
                if self._tts.enabled:
                    self.io.print_info("Voice narration enabled (responses will "
                               "be spoken when voice-activated)")
            except Exception as e:
                log.debug("TTS init failed: %s", e)
        else:
            self._voice = None

    def _get_input(self) -> str:
        """Get input from keyboard or voice queue.

        When voice is active, runs prompt_user() in a background thread
        so voice can interrupt.  Tracks the thread to avoid spawning
        duplicates — if a previous thread is still blocked on input(),
        we reuse its result instead of creating a competing thread that
        would steal stdin.
        """
        # Check if GUI changed voice mode
        self._check_voice_mode_file()

        # Lazily init keyboard thread tracking
        if not hasattr(self, '_kb_result_q'):
            self._kb_result_q = queue.Queue(maxsize=1)
            self._kb_thread = None

        # Check if a previous (orphaned) keyboard thread already captured
        # input — use it immediately instead of starting another prompt
        try:
            text = self._kb_result_q.get_nowait()
            self._kb_thread = None
            self._voice_initiated = False
            return text
        except queue.Empty:
            pass

        # Check if voice has queued something already
        try:
            text = self._voice_queue.get_nowait()
            return text.strip()
        except queue.Empty:
            pass

        # If no voice input is active, just block on keyboard
        if self._voice is None or not self._voice.ready:
            return self.io.prompt_user(self.cwd)

        # Voice is active — need to race keyboard vs voice.
        # Only start a new keyboard thread if no previous one is alive.
        if self._kb_thread is None or not self._kb_thread.is_alive():
            def _kb_work():
                try:
                    result = self.io.prompt_user(self.cwd)
                except Exception:
                    result = "/quit"
                self._kb_result_q.put(result)

            self._kb_thread = threading.Thread(
                target=_kb_work, daemon=True, name="ForgeKBInput")
            self._kb_thread.start()

        # Race keyboard queue against voice queue
        while True:
            self._check_voice_mode_file()
            try:
                text = self._kb_result_q.get(timeout=0.2)
                self._kb_thread = None
                self._voice_initiated = False
                return text
            except queue.Empty:
                pass
            try:
                text = self._voice_queue.get_nowait()
                self._voice_initiated = True
                # Keyboard thread is still blocked on input() — when
                # it finishes, the result goes to _kb_result_q and will
                # be picked up at the top of the next _get_input() call.
                return text.strip()
            except queue.Empty:
                continue

    def _check_voice_mode_file(self):
        """Pick up voice mode changes from the GUI toggle."""
        if not self._voice:
            return
        mode_file = self._config_dir / "voice_mode.txt"
        try:
            if mode_file.exists():
                new_mode = mode_file.read_text(encoding="utf-8").strip()
                if new_mode in ("ptt", "vox") and new_mode != self._voice.mode:
                    self._voice.mode = new_mode
                    label = ("Push-to-Talk" if new_mode == "ptt"
                             else "VOX (voice-activated)")
                    self.io.print_info(f"Voice mode switched to: {label}")
                mode_file.unlink(missing_ok=True)
        except Exception:
            pass

        # Check voice focus file — dashboard tells us who owns the mic
        self._check_voice_focus_file()

    def _check_voice_focus_file(self):
        """Check if dashboard has claimed or released voice focus."""
        focus_file = self._config_dir / "voice_focus.txt"
        try:
            if not focus_file.exists():
                return
            focus = focus_file.read_text(encoding="utf-8").strip()
            if focus == "dashboard" and self._voice:
                # Dashboard wants the mic — pause terminal voice
                self._voice.stop()
                self._voice = None
                log.debug("Voice paused — dashboard has focus")
            elif focus == "terminal" and not self._voice:
                # Terminal gets the mic back — re-init voice
                self._init_voice()
                log.debug("Voice resumed — terminal has focus")
        except Exception:
            pass

    def _check_voice_plan_mode(self):
        """Check if dashboard voice command activated plan mode."""
        plan_file = self._config_dir / "plan_mode_voice.txt"
        try:
            if not plan_file.exists():
                return
            state = plan_file.read_text(encoding="utf-8").strip()
            plan_file.unlink()  # consume the signal
            if state == "on":
                self.planner.mode = "manual"
                self.planner.arm()
                self.io.print_info("Plan mode armed (via voice).")
            elif state == "off":
                self.planner.mode = "off"
                self.planner.disarm()
                self.io.print_info("Plan mode disabled (via voice).")
        except Exception:
            pass

    def _check_config_trigger(self):
        """Check if dashboard saved new config; reload if trigger file exists."""
        trigger = self._config_dir / "config_changed.txt"
        try:
            if not trigger.exists():
                return
            trigger.unlink(missing_ok=True)
            self.config.reload()
            # Apply to subsystems
            if hasattr(self, 'safety') and self.safety:
                self.safety.level = self.config.get("safety_level", 1)
                self.safety.sandbox_enabled = self.config.get(
                    "sandbox_enabled", False)
                self.safety.sandbox_roots = self.config.get(
                    "sandbox_roots", [])
            if hasattr(self, 'router') and self.router:
                small = self.config.get("small_model", "")
                self.router.small_model = small
                self.router.enabled = (
                    bool(small) and self.config.get("router_enabled", False))
            if hasattr(self, 'dedup') and self.dedup:
                self.dedup.enabled = self.config.get("dedup_enabled", True)
                self.dedup.threshold = self.config.get(
                    "dedup_threshold", 0.92)
                self.dedup.window = self.config.get("dedup_window", 5)
            log.info("Config reloaded (triggered by dashboard settings)")
        except Exception:
            pass

    def _handle_command(self, cmd: str) -> bool:
        """Handle slash commands via CommandHandler.

        All command implementations live in forge/commands.py.
        The plugin system also gets a chance to handle commands.
        """
        try:
            # Let plugins handle first
            if hasattr(self, 'plugin_manager'):
                parts = cmd.strip().split(None, 1)
                command = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""
                if self.plugin_manager.dispatch_command(command, arg):
                    sys.stdout.flush()
                    return True
            handled = self._command_handler.handle(cmd)
            if not handled:
                # Don't let unrecognized /commands fall through to the AI
                slash_word = cmd.strip().split()[0] if cmd.strip() else cmd
                self.io.print_error(f"Unknown command: {slash_word}  "
                            f"(type /help for available commands)")
            # Flush after every command to ensure output is visible
            sys.stdout.flush()
            return True
        except SystemExit:
            raise  # let /quit propagate
        except Exception as exc:
            log.exception("Command handler error for: %s", cmd)
            self.io.print_error(f"Command failed: {exc}")
            sys.stdout.flush()
            return True  # consumed — don't send to model

    # _handle_command_LEGACY removed — all commands now in forge.commands.CommandHandler

    def _get_dashboard_snapshot(self) -> dict:
        """Build a snapshot dict for the GUI dashboard's polling callback."""
        try:
            ctx_status = self.ctx.status()
            bs = self.billing.status()
            cs = self.cache.stats()
            perf = self.stats.get_performance_trends(count=20)
            ts = self.memory.get_task_state()
            comp = self.billing.get_comparison()

            opus_cost = comp["comparisons"].get(
                "Claude Opus (with re-reads)", {}).get("cost", 0)

            return {
                "context": {
                    "usage_pct": ctx_status["usage_pct"],
                    "total_tokens": ctx_status["total_tokens"],
                    "max_tokens": ctx_status["max_tokens"],
                    "partitions": self.ctx.get_partition_stats(),
                },
                "performance": perf,
                "cache": {"hit_rate": cs.get("hit_rate", 0)},
                "swaps": ts.context_swaps if ts else 0,
                "session": {
                    "turns": self._turn_count,
                    "duration_m": bs.get("session_duration_m", 0),
                    "tokens": bs.get("session_tokens", 0),
                    "cost_saved": opus_cost,
                },
                "memory": {
                    "journal_entries": len(self.memory.get_session_entries()),
                    "index_chunks": (self.index.stats()["total_chunks"]
                                     if self.index else 0),
                    "status": "Active" if self._turn_count > 0 else "Ready",
                },
                "model": self.llm.model,
                "is_active": False,
                "continuity": {
                    "score": (self.continuity._current.score
                              if self.continuity._current else 100),
                    "grade": (self.continuity._current.grade
                              if self.continuity._current else "A"),
                    "swaps": self.continuity._swaps_total,
                    "enabled": self.continuity.enabled,
                    "score_history": [
                        s.score for s in self.continuity._history[-20:]
                    ],
                },
                "reliability": {
                    "score": self.reliability.get_reliability_score(),
                    "trend": self.reliability.get_trend(),
                    "current": self.reliability.get_current_session_health(
                        forensics=self.forensics,
                        continuity=self.continuity,
                        plan_verifier=self.plan_verifier,
                        billing=self.billing,
                        session_start=self._session_start,
                        turn_count=self._turn_count,
                    ),
                    "metrics": self.reliability.get_underlying_metrics(),
                },
            }
        except Exception:
            return {}

    def _print_exit_summary(self):
        """Print session summary on exit and record to stats."""
        elapsed = time.time() - self._session_start
        bs = self.billing.status()
        cs = self.cache.stats()
        comp = self.billing.get_comparison()

        # Record session to analytics
        journal_entries = len(self.memory.get_session_entries())
        ts = self.memory.get_task_state()
        swaps = ts.context_swaps if ts else 0

        try:
            self.stats.record_session_end(
                session_id=self.memory._session_id,
                start_time=self._session_start,
                turns=self._turn_count,
                input_tokens=bs["session_input"],
                output_tokens=bs["session_output"],
                cache_saved=bs["session_cached"],
                context_swaps=swaps,
                files_touched=len(self._current_turn_files),
                journal_entries=journal_entries,
                model=self.llm.model,
            )
        except Exception as e:
            log.debug("Failed to record session stats: %s", e)

        # Record reliability metrics for cross-session tracking
        try:
            self.reliability.record_session(
                forensics=self.forensics,
                continuity=self.continuity,
                plan_verifier=self.plan_verifier,
                billing=self.billing,
                session_start=self._session_start,
                turn_count=self._turn_count,
                model=self.llm.model,
            )
        except Exception as e:
            log.debug("Failed to record reliability metrics: %s", e)

        print(f"\n{BOLD}{'=' * 60}{RESET}")
        print(f"{BOLD}Session Summary{RESET}")
        print(f"  Duration:       {elapsed / 60:.1f} minutes")
        print(f"  Turns:          {self._turn_count}")
        print(f"  Tokens used:    {bs['session_tokens']:,}")
        print(f"  Tokens cached:  {GREEN}{bs['session_cached']:,}{RESET}")
        print(f"  Balance:        ${bs['balance']:.2f}")

        # Performance
        perf = self.stats.get_performance_trends()
        if perf["samples"] > 0:
            print(f"  Avg throughput: {perf['avg_tok_s']:.1f} tok/s "
                  f"({perf['trend']})")

        # Memory stats
        print(f"  Journal entries: {journal_entries}")
        if swaps > 0:
            print(f"  Context swaps:  {swaps} (seamless)")

        opus_cost = comp["comparisons"].get(
            "Claude Opus (with re-reads)", {}).get("cost", 0)
        if opus_cost > 0:
            print(f"\n  {BOLD}This session on Claude Opus: "
                  f"{RED}${opus_cost:.4f}{RESET}")
            print(f"  {BOLD}This session on Forge:       "
                  f"{GREEN}$0.00{RESET}")
            print(f"  {BOLD}You saved:                   "
                  f"{GREEN}${opus_cost:.4f}{RESET}")

        # Lifetime savings
        cost = self.stats.get_cost_analysis()
        if cost["total_sessions"] > 1:
            print(f"\n  {BOLD}Lifetime ({cost['total_sessions']} sessions): "
                  f"{GREEN}${cost['total_saved_vs_opus']:.4f} saved vs Opus{RESET}")

        # Save forensics report
        self.forensics.record_turn(bs["session_input"], bs["session_output"])
        report_path = self.forensics.save_report()
        if report_path:
            print(f"  {DIM}Forensics report: {report_path}{RESET}")

        # Telemetry upload (non-blocking, silent fail)
        if self.config.get("telemetry_enabled", False):
            try:
                from forge.telemetry import upload_telemetry
                upload_telemetry(
                    forensics=self.forensics,
                    memory=self.memory,
                    stats=self.stats,
                    billing=self.billing,
                    crucible=self.crucible,
                    continuity=self.continuity,
                    plan_verifier=self.plan_verifier,
                    reliability=getattr(self, "reliability", None),
                    session_start=self._session_start,
                    turn_count=self._turn_count,
                    model=self.llm.model,
                    cwd=self.cwd,
                    redact=self.config.get("telemetry_redact", True),
                    telemetry_url=self.config.get("telemetry_url", ""),
                    blocking=False,
                )
                print(f"  {DIM}Telemetry: uploaded{RESET}")
            except Exception:
                pass

        print(f"{BOLD}{'=' * 60}{RESET}\n")
