"""Forge Documentation Window -- full help system in a Tkinter popup.

Non-modal Toplevel with sidebar navigation, real-time search,
and all documentation content inline. Dark theme matching the
Neural Cortex dashboard.

Usage:
    from forge.ui.docs_window import DocsWindow, bind_hotkey
    bind_hotkey(root)          # F1 opens the docs window
    DocsWindow.open(root)      # programmatic open
"""

import tkinter as tk
from tkinter import ttk, font as tkfont
import re
from typing import Optional

from forge.ui.themes import (
    get_docs_colors, get_fonts, add_theme_listener, remove_theme_listener,
    recolor_widget_tree,
)

# ──────────────────────────────────────────────────────────────────
# Color palette & fonts from central theme system
# ──────────────────────────────────────────────────────────────────

_C = get_docs_colors()

_F = get_fonts()
_FONT_BODY = _F["body"]
_FONT_BODY_BOLD = _F["body_bold"]
_FONT_HEADING = _F["heading"]
_FONT_SUBHEADING = _F["subheading"]
_FONT_MONO = _F["mono"]
_FONT_MONO_BOLD = _F["mono_bold"]
_FONT_MONO_SM = _F["mono_sm"]
_FONT_SIDEBAR = _F["sidebar"]
_FONT_SIDEBAR_BOLD = _F["sidebar_bold"]
_FONT_SEARCH = _F["search"]
_FONT_SMALL = _F["small"]
_FONT_TITLE = _F["doc_title"]


# ──────────────────────────────────────────────────────────────────
# Documentation content
# ──────────────────────────────────────────────────────────────────

def _build_docs() -> list[dict]:
    """Return ordered list of doc sections.

    Each section is::

        {
            "title": str,
            "icon":  str,           # sidebar icon character
            "blocks": [block, ...]  # content blocks
        }

    Block types:
        ("heading", text)
        ("subheading", text)
        ("paragraph", text)
        ("bullet", text)
        ("command", syntax, summary, detail, example_or_None)
        ("separator",)
        ("term", term, definition)
    """
    return [
        # ── Quick Start ──────────────────────────────────────────
        {
            "title": "Quick Start",
            "icon": ">",
            "blocks": [
                ("heading", "Getting Started with Forge"),
                ("paragraph",
                 "Forge is a fully local AI coding assistant that runs on your "
                 "hardware. No cloud API keys, no token metering, no data "
                 "leaving your machine. It uses Ollama-hosted models and "
                 "provides a rich terminal interface with context management, "
                 "tool use, memory, and security scanning."),
                ("subheading", "First Run"),
                ("bullet",
                 "Install Ollama and pull a model (e.g. deepseek-coder-v2, "
                 "qwen2.5-coder, codellama). Forge auto-detects available models."),
                ("bullet",
                 "Run 'forge' from your project directory. Forge scans the "
                 "working directory and loads context automatically."),
                ("bullet",
                 "Type natural language prompts or use /commands (see Commands "
                 "Reference). Everything that is not a /command is sent to the AI."),
                ("bullet",
                 "Press Escape during a response to interrupt. You can then "
                 "type 'undo' to rollback changes or enter new instructions."),
                ("subheading", "Recommended Workflow"),
                ("paragraph",
                 "1. Start Forge in your project root.\n"
                 "2. Use /scan to index the codebase structure.\n"
                 "3. Use /context to see token usage. Pin important files with /pin.\n"
                 "4. Ask the AI to read, write, refactor, or debug code.\n"
                 "5. Use /stats to see performance. Use /dashboard for the GUI monitor.\n"
                 "6. Use /save to snapshot your session for later."),
                ("subheading", "Key Concepts"),
                ("bullet",
                 "Context Window: A partitioned token budget that tracks what the AI "
                 "can see. Entries are evicted oldest-first when full, but pinned "
                 "entries survive eviction."),
                ("bullet",
                 "Tools: The AI can read/write files, run shell commands, search code, "
                 "and more. All tool calls are logged and can be audited via /forensics."),
                ("bullet",
                 "Safety System: Four configurable tiers control what the AI can do, "
                 "from fully unleashed to locked-down read-only mode."),
                ("bullet",
                 "Crucible: A threat scanner that monitors AI output for prompt injection, "
                 "data exfiltration, and other attacks. Runs transparently on every response."),
            ],
        },

        # ── Commands Reference ───────────────────────────────────
        {
            "title": "Commands Reference",
            "icon": "/",
            "blocks": [
                ("heading", "Slash Commands"),
                ("paragraph",
                 "All slash commands start with / and are processed locally by "
                 "Forge (they are not sent to the AI). Tab completion is "
                 "available for all commands. Arguments in [brackets] are optional."),

                # Context Management
                ("subheading", "Context Management"),
                ("command", "/context",
                 "Show detailed context window status",
                 "Displays a table of all entries in the context window, including "
                 "role, tag, token count, and pin status. Also shows overall usage "
                 "percentage and remaining token budget. Use this to understand "
                 "what the AI currently sees.",
                 "/context"),
                ("command", "/drop N",
                 "Drop context entry at index N",
                 "Removes a specific entry from the context window by its index "
                 "number (shown in /context output). Useful for removing stale or "
                 "irrelevant content to free up token budget. Pinned entries "
                 "cannot be dropped -- unpin them first.",
                 "/drop 5"),
                ("command", "/pin N",
                 "Pin entry so it survives eviction",
                 "Marks a context entry as pinned. Pinned entries are never "
                 "evicted when the context window fills up. Use this for critical "
                 "files, architecture docs, or important conversation context "
                 "that the AI should always have access to.",
                 "/pin 3"),
                ("command", "/unpin N",
                 "Remove pin from context entry",
                 "Removes the pin from a previously pinned entry, making it "
                 "eligible for eviction again. Use /context to see which "
                 "entries are currently pinned (marked with *).",
                 "/unpin 3"),
                ("command", "/clear",
                 "Clear all unpinned entries",
                 "Removes all context entries that are not pinned. Pinned entries "
                 "remain. This is useful when the context has accumulated a lot of "
                 "stale information and you want a partial reset without losing "
                 "critical pinned content.",
                 "/clear"),
                ("command", "/reset",
                 "Start completely fresh",
                 "Clears the entire context window, including pinned entries. Also "
                 "resets the conversation history. This is a hard reset -- use it "
                 "when you want to start a completely new task from scratch.",
                 "/reset"),
                ("separator",),

                # Session
                ("subheading", "Session Management"),
                ("command", "/save [file]",
                 "Save session to file",
                 "Saves the current context window, conversation history, and "
                 "configuration to a JSON file. If no filename is given, uses a "
                 "timestamped default. Sessions can be reloaded later with /load "
                 "to resume exactly where you left off.",
                 "/save my_refactor_session"),
                ("command", "/load [file]",
                 "Load session from file",
                 "Restores a previously saved session, including context window "
                 "entries, conversation history, and configuration. Replaces the "
                 "current session entirely. Shows available sessions if no "
                 "filename is given.",
                 "/load my_refactor_session"),
                ("command", "/model [name]",
                 "Show or switch the active model",
                 "Without arguments, shows the currently active model and its "
                 "parameters. With a model name, switches to that model. The new "
                 "model must be available in Ollama. Context window limits may "
                 "change when switching models.",
                 "/model qwen2.5-coder:32b"),
                ("command", "/models",
                 "List available Ollama models",
                 "Queries Ollama for all downloaded models and displays them with "
                 "size, parameter count, and quantization info. Models marked with "
                 "an asterisk (*) are currently loaded in memory.",
                 "/models"),
                ("separator",),

                # Tools & Search
                ("subheading", "Tools & Codebase Analysis"),
                ("command", "/tools",
                 "List available tools",
                 "Shows all tools the AI can use, including file operations, "
                 "shell commands, code search, and any custom tools. Each tool "
                 "shows its name, description, and parameter schema.",
                 "/tools"),
                ("command", "/scan [path]",
                 "Scan codebase structure",
                 "Analyzes the codebase and extracts structural information: "
                 "classes, functions, routes, database tables, imports, and "
                 "dependency graphs. The digest is stored for fast retrieval. "
                 "Defaults to the current working directory if no path given.",
                 "/scan src/"),
                ("command", "/digest [file]",
                 "Show digest statistics or file detail",
                 "Without arguments, shows summary statistics from the last "
                 "/scan: file count, total lines, language breakdown. With a "
                 "specific file path, shows the structural digest for that file "
                 "(classes, functions, dependencies).",
                 "/digest src/engine.py"),
                ("command", "/search <query>",
                 "Quick semantic search (file list)",
                 "Searches the semantic index for files matching the query. "
                 "Returns a ranked list of file paths. Faster than /recall "
                 "but shows less detail. Requires /index to have been run first.",
                 "/search authentication middleware"),
                ("command", "/index [path]",
                 "Index codebase for semantic search",
                 "Builds or updates the semantic embedding index for the codebase. "
                 "This enables /search and /recall commands. Indexes file content "
                 "into vector embeddings for similarity search. Can be scoped to "
                 "a specific path.",
                 "/index"),
                ("command", "/recall <query>",
                 "Semantic code search with previews",
                 "Searches the semantic index and shows code previews for each "
                 "match. More detailed than /search -- shows the relevant code "
                 "snippets with context lines. Results are ranked by semantic "
                 "similarity to the query.",
                 "/recall error handling in the API layer"),
                ("separator",),

                # Memory
                ("subheading", "Memory & Journal"),
                ("command", "/memory",
                 "Show all memory subsystem status",
                 "Displays the status of all memory subsystems: episodic memory "
                 "(conversation summaries), semantic index (code embeddings), "
                 "journal (persistent notes), and file cache. Shows entry counts, "
                 "token usage, and last update times.",
                 "/memory"),
                ("command", "/journal [N]",
                 "Show last N journal entries",
                 "Displays the most recent journal entries (default: 20). The "
                 "journal records decisions, learnings, and notes that Forge "
                 "writes automatically during work. Entries persist across "
                 "sessions and help maintain continuity.",
                 "/journal 50"),
                ("command", "/tasks",
                 "Show task state and progress",
                 "Displays the current task queue, active tasks, and their "
                 "progress. Tasks are created automatically when the AI breaks "
                 "down complex requests into steps, or can be created manually.",
                 "/tasks"),
                ("separator",),

                # Analytics & Dashboard
                ("subheading", "Analytics & Dashboard"),
                ("command", "/stats",
                 "Show full analytics",
                 "Displays comprehensive analytics: tokens generated, prompt "
                 "tokens processed, generation speed (tok/s), tool call counts "
                 "by type, session duration, estimated cost comparison, and "
                 "performance trends over time.",
                 "/stats"),
                ("command", "/dashboard",
                 "Launch Neural Cortex GUI monitor",
                 "Opens the Neural Cortex dashboard -- a graphical window with "
                 "a brain visualization that reflects the AI's current state "
                 "(thinking, tool execution, indexing, etc.). Also shows live "
                 "metrics cards for context, cache, and performance.",
                 "/dashboard"),
                ("command", "/synapse",
                 "Run synapse check -- cycle all Neural Cortex modes",
                 "Triggers a synapse check on the Neural Cortex dashboard. "
                 "Cycles through all 8 animation states (Boot, Idle, Thinking, "
                 "Executing, Indexing, Swapping, Error, Threat) with 2.5 second "
                 "dwell per mode. Each mode plays its associated sound effect "
                 "and the mode name is announced via TTS. The dashboard must be "
                 "running. Also available as a voice command: say 'synapse check'.",
                 "/synapse"),
                ("command", "/billing",
                 "Show sandbox billing summary",
                 "Displays the sandbox billing ledger: total tokens used, "
                 "estimated cost if this were a cloud API, remaining sandbox "
                 "balance. Forge runs locally so costs are simulated for "
                 "comparison purposes.",
                 "/billing"),
                ("command", "/billing reset confirm",
                 "Reset all lifetime stats to zero",
                 "Resets lifetime token counts, session counts, and balance "
                 "back to defaults. Requires 'confirm' for safety. Useful for "
                 "starting fresh after testing.",
                 "/billing reset confirm"),
                ("command", "/topup [amt]",
                 "Add sandbox funds",
                 "Adds simulated funds to the sandbox billing balance. Default "
                 "amount is $50. This is for tracking purposes only -- Forge "
                 "runs locally and incurs no actual API costs.",
                 "/topup 100"),
                ("command", "/compare",
                 "Compare costs: Forge vs Cloud",
                 "Shows a side-by-side cost comparison of your session if it "
                 "had been run on Claude API, OpenAI GPT-4, and other cloud "
                 "services. Calculates savings from running locally with Forge.",
                 "/compare"),
                ("separator",),

                # Safety & Config
                ("subheading", "Safety & Configuration"),
                ("command", "/safety",
                 "Show safety level and sandbox status",
                 "Displays the current safety tier, sandbox state (on/off), "
                 "allowed paths, and recent safety events. The safety system "
                 "controls what file operations the AI is permitted to perform.",
                 "/safety"),
                ("command", "/safety <level>",
                 "Set safety level",
                 "Changes the safety tier. Available levels: unleashed (no "
                 "restrictions), smart_guard (blocks destructive patterns), "
                 "confirm_writes (prompts before file writes), locked_down "
                 "(read-only, no shell commands).",
                 "/safety smart_guard"),
                ("command", "/safety sandbox on|off",
                 "Toggle filesystem sandboxing",
                 "Enables or disables the filesystem sandbox. When enabled, "
                 "file operations are restricted to the working directory and "
                 "explicitly allowed paths. Prevents accidental writes to "
                 "system directories.",
                 "/safety sandbox on"),
                ("command", "/safety allow <path>",
                 "Add path to sandbox allowlist",
                 "Adds a directory path to the sandbox allowlist. The AI can "
                 "read and write files within allowed paths even when sandboxing "
                 "is enabled. Paths must be absolute.",
                 "/safety allow C:/Users/me/shared_libs"),
                ("command", "/config",
                 "Show current configuration",
                 "Displays all configuration values: model settings, safety "
                 "level, sandbox paths, context window limits, cache settings, "
                 "voice configuration, and router settings. Values come from "
                 "config.yaml and runtime overrides.",
                 "/config"),
                ("command", "/config reload",
                 "Reload config.yaml from disk",
                 "Re-reads the config.yaml file and applies any changes. Useful "
                 "after manually editing the config file. Some settings (like "
                 "model changes) may require additional steps to take effect.",
                 "/config reload"),
                ("separator",),

                # Crucible
                ("subheading", "Crucible Threat Scanner"),
                ("command", "/crucible",
                 "Show Crucible status and detection stats",
                 "Displays whether the Crucible scanner is active, total scans "
                 "performed, threats detected, and detection breakdown by layer "
                 "(pattern, behavioral, semantic, canary). Also shows the current "
                 "threat level assessment.",
                 "/crucible"),
                ("command", "/crucible on|off",
                 "Enable or disable threat scanning",
                 "Toggles the Crucible threat scanner. When enabled, every AI "
                 "response and tool call is scanned for prompt injection, data "
                 "exfiltration, and other attack patterns. Recommended to keep "
                 "enabled.",
                 "/crucible on"),
                ("command", "/crucible log",
                 "Show threat detection log",
                 "Displays the history of all threat detections, including "
                 "timestamp, detection layer, severity, and the content that "
                 "triggered the alert. Useful for security auditing.",
                 "/crucible log"),
                ("command", "/crucible canary",
                 "Check honeypot canary integrity",
                 "Verifies that all honeypot canary tokens are intact. Canaries "
                 "are hidden markers placed in the context that should never "
                 "appear in AI output. If a canary is found in output, it "
                 "indicates a potential prompt injection attack.",
                 "/crucible canary"),
                ("separator",),

                # Forensics & Provenance
                ("subheading", "Forensics & Provenance"),
                ("command", "/forensics",
                 "Show session forensics summary",
                 "Displays a forensics summary of the current session: all tool "
                 "calls made, files read/written, shell commands executed, tokens "
                 "processed, and behavioral fingerprint of the AI's actions. "
                 "Useful for auditing what Forge did during a session.",
                 "/forensics"),
                ("command", "/forensics save",
                 "Save forensics report to disk",
                 "Exports a detailed forensics report as a JSON file. Includes "
                 "the complete tool call log, provenance chain, file diff history, "
                 "and behavioral analysis. Can be used for compliance or debugging.",
                 "/forensics save"),
                ("command", "/provenance",
                 "Show tool call provenance chain",
                 "Displays the causal chain of tool calls: which prompt led to "
                 "which tool call, which tool result led to the next action. "
                 "Shows the decision tree the AI followed during the session.",
                 "/provenance"),
                ("separator",),

                # Router
                ("subheading", "Model Router"),
                ("command", "/router",
                 "Show router status and routing stats",
                 "Displays whether multi-model routing is active, the assigned "
                 "big (complex) and small (simple) models, routing statistics "
                 "(how many prompts went to each model), and the complexity "
                 "scoring thresholds.",
                 "/router"),
                ("command", "/router on|off",
                 "Enable or disable multi-model routing",
                 "Toggles the model router. When enabled, Forge automatically "
                 "routes simple prompts to a faster/smaller model and complex "
                 "prompts to a larger model. Saves time on trivial queries.",
                 "/router on"),
                ("command", "/router big <model>",
                 "Set the big (complex task) model",
                 "Assigns the model to use for complex prompts that require "
                 "deep reasoning, large context, or multi-step tool use. "
                 "Should be your most capable model.",
                 "/router big qwen2.5-coder:32b"),
                ("command", "/router small <model>",
                 "Set the small (simple task) model",
                 "Assigns the model to use for simple prompts like short "
                 "questions, formatting, or quick lookups. Should be a fast, "
                 "lightweight model for quick responses.",
                 "/router small qwen2.5-coder:7b"),
                ("separator",),

                # Plan Mode
                ("subheading", "Plan Mode"),
                ("command", "/plan",
                 "Show plan mode status",
                 "Displays whether plan mode is active, the current mode "
                 "(off, manual, auto, always), and plan execution history.",
                 "/plan"),
                ("command", "/plan on",
                 "Arm plan mode for next prompt",
                 "The next prompt will generate a structured plan for review "
                 "before any code changes are made. You approve, edit, reject, "
                 "or step through the plan before execution.",
                 "/plan on"),
                ("command", "/plan auto",
                 "Auto-plan complex prompts",
                 "Automatically enters plan mode when the router scores a prompt "
                 "as complex. Simple prompts execute normally. Threshold is "
                 "configurable via plan_auto_threshold in config.yaml.",
                 "/plan auto"),
                ("command", "/plan off",
                 "Disable plan mode",
                 "Turns off plan mode entirely. Prompts execute immediately "
                 "without generating a plan first.",
                 "/plan off"),
                ("separator",),

                # Dedup
                ("subheading", "Tool Deduplication"),
                ("command", "/dedup",
                 "Show dedup status and stats",
                 "Displays dedup settings: enabled/disabled, similarity threshold, "
                 "window size, and suppression statistics.",
                 "/dedup"),
                ("command", "/dedup threshold <N>",
                 "Set similarity threshold",
                 "Sets the similarity threshold (0.0 to 1.0). Higher values are "
                 "stricter — only very similar calls are suppressed. Default is 0.92.",
                 "/dedup threshold 0.95"),
                ("separator",),

                # Voice
                ("subheading", "Voice Input"),
                ("command", "/voice",
                 "Show voice input status",
                 "Displays whether voice input is active, the current mode "
                 "(PTT or VOX), audio device info, and voice classification "
                 "settings. Also shows recent transcription accuracy metrics.",
                 "/voice"),
                ("command", "/voice ptt",
                 "Push-to-talk mode",
                 "Enables push-to-talk voice input. Hold the backtick key (`) "
                 "to record, release to send. Audio is transcribed locally and "
                 "classified as either a command or an inline question.",
                 "/voice ptt"),
                ("command", "/voice vox",
                 "Voice-activated mode",
                 "Enables voice-activated (VOX) input. Forge listens continuously "
                 "and auto-detects when you start speaking. Silence triggers "
                 "end-of-utterance detection and sends the transcription.",
                 "/voice vox"),
                ("command", "/voice off",
                 "Disable voice input",
                 "Turns off voice input and releases the audio device. Voice "
                 "can be re-enabled at any time with /voice ptt or /voice vox.",
                 "/voice off"),
                ("separator",),

                # System
                ("subheading", "System"),
                ("command", "/hardware",
                 "Show GPU/CPU/RAM and model recommendation",
                 "Detects and displays your hardware: GPU model and VRAM, CPU "
                 "cores and model, total/available RAM. Also recommends the "
                 "largest model your hardware can run based on available VRAM "
                 "and system memory.",
                 "/hardware"),
                ("command", "/cache",
                 "Show file cache statistics",
                 "Displays file cache status: number of cached files, total "
                 "token savings from cache hits, cache hit rate, and integrity "
                 "check results. The file cache avoids re-reading unchanged files.",
                 "/cache"),
                ("command", "/cache clear",
                 "Clear the file cache",
                 "Removes all entries from the file cache. Files will be re-read "
                 "from disk on next access. Use this if you suspect cache "
                 "corruption or after major codebase changes.",
                 "/cache clear"),
                ("command", "/cd [path]",
                 "Change working directory",
                 "Changes Forge's working directory. Affects where file operations "
                 "are relative to. Without arguments, shows the current directory. "
                 "Supports ~ for home directory and relative paths.",
                 "/cd src/backend"),
                ("command", "/help",
                 "Show command help in terminal",
                 "Displays a summary of all available slash commands organized "
                 "by category directly in the terminal. For the full "
                 "documentation GUI with search, press F1 or use /docs.",
                 "/help"),
                ("command", "/docs",
                 "Open the documentation window (F1)",
                 "Opens this searchable documentation GUI in a separate window. "
                 "Contains detailed explanations, examples, and a glossary. "
                 "Same as pressing F1. The window is non-modal -- it stays open "
                 "while you continue working in the terminal.",
                 "/docs"),
                ("command", "/plugins",
                 "Show loaded plugins and status",
                 "Displays all discovered and loaded plugins, their priority, "
                 "version, and which hooks they implement. Plugins extend "
                 "Forge with custom tools, commands, and event hooks.",
                 "/plugins"),
                ("command", "/quit",
                 "Exit Forge",
                 "Saves command history and exits Forge. Active sessions are "
                 "not auto-saved -- use /save first if you want to resume later. "
                 "Keyboard shortcut: Ctrl+C or Ctrl+D also exit.",
                 "/quit"),
            ],
        },

        # ── Safety System ────────────────────────────────────────
        {
            "title": "Safety System",
            "icon": "S",
            "blocks": [
                ("heading", "Safety Tiers"),
                ("paragraph",
                 "Forge has a four-tier safety system that controls what operations "
                 "the AI is allowed to perform. The safety level can be changed at "
                 "any time with /safety <level>. Each tier builds on the previous "
                 "one, adding more restrictions."),
                ("subheading", "Tier 1: Unleashed"),
                ("paragraph",
                 "No restrictions. The AI can read, write, and delete any file, "
                 "run any shell command, and access any path. This is maximum "
                 "productivity mode for experienced users working in isolated "
                 "environments (containers, VMs, disposable dev boxes). Not "
                 "recommended for production machines."),
                ("subheading", "Tier 2: Smart Guard (default)"),
                ("paragraph",
                 "Blocks obviously destructive patterns: rm -rf /, format commands, "
                 "registry edits, and known dangerous operations. Allows normal "
                 "development operations like file creation, editing, and running "
                 "build commands. This is the recommended default for most users."),
                ("subheading", "Tier 3: Confirm Writes"),
                ("paragraph",
                 "Prompts the user for confirmation before any file write, delete, "
                 "or shell command execution. The AI can still read files and "
                 "analyze code freely. Ideal for reviewing AI changes carefully "
                 "before they are applied."),
                ("subheading", "Tier 4: Locked Down"),
                ("paragraph",
                 "Read-only mode. The AI cannot write files, delete files, or "
                 "execute shell commands. It can only read files and provide "
                 "analysis, explanations, and suggestions. Use this when you "
                 "want AI assistance without any risk of modification."),
                ("subheading", "Filesystem Sandbox"),
                ("paragraph",
                 "Independent of the safety tier, the filesystem sandbox restricts "
                 "all file operations to the working directory and explicitly "
                 "allowed paths. Even in unleashed mode, the sandbox prevents "
                 "writes outside the project directory."),
                ("bullet",
                 "Enable/disable with /safety sandbox on|off"),
                ("bullet",
                 "Add allowed paths with /safety allow <path>"),
                ("bullet",
                 "The sandbox uses real path resolution to prevent symlink escapes"),
                ("bullet",
                 "Allowed paths must be absolute paths"),
            ],
        },

        # ── Crucible Threat Scanner ──────────────────────────────
        {
            "title": "Crucible Scanner",
            "icon": "X",
            "blocks": [
                ("heading", "Crucible Threat Scanner"),
                ("paragraph",
                 "The Crucible is Forge's multi-layered security scanner that "
                 "monitors AI output for malicious patterns. It runs transparently "
                 "on every AI response and tool call, adding negligible latency. "
                 "Threats are logged and can trigger automatic quarantine."),
                ("subheading", "Layer 1: Pattern Detection"),
                ("paragraph",
                 "Regex-based scanning for known attack patterns: prompt injection "
                 "markers (\"ignore previous instructions\"), shell injection "
                 "(backtick execution, $() substitution in filenames), path "
                 "traversal (../../etc/passwd), and data exfiltration patterns "
                 "(base64-encoded sensitive data, curl/wget to external URLs)."),
                ("subheading", "Layer 2: Behavioral Analysis"),
                ("paragraph",
                 "Tracks the AI's behavioral fingerprint across the session. "
                 "Detects sudden changes in behavior that may indicate a "
                 "successful prompt injection: unusual tool call patterns, "
                 "accessing files unrelated to the task, attempting to modify "
                 "system files, or generating suspiciously long base64 strings."),
                ("subheading", "Layer 3: Semantic Analysis"),
                ("paragraph",
                 "Analyzes the semantic intent of AI-generated shell commands "
                 "and code. Detects attempts to download and execute remote "
                 "scripts, establish reverse shells, modify SSH keys, or "
                 "install unauthorized packages. Uses heuristic scoring rather "
                 "than pattern matching."),
                ("subheading", "Layer 4: Canary System"),
                ("paragraph",
                 "Hidden honeypot tokens are placed in the context window. These "
                 "tokens should never appear in AI output -- if they do, it means "
                 "the AI is echoing raw context (a sign of prompt injection). "
                 "Canary violations trigger immediate alerts. Check canary "
                 "integrity with /crucible canary."),
                ("subheading", "Quarantine"),
                ("paragraph",
                 "When a threat is detected at high severity, the offending "
                 "content is moved to a quarantine partition in the context "
                 "window. Quarantined content is not included in future prompts "
                 "but is preserved for forensic analysis. Quarantine is automatic "
                 "and does not interrupt the workflow."),
                ("subheading", "Crucible Overlay"),
                ("paragraph",
                 "When a threat is detected during interactive use, the Crucible "
                 "avatar appears as a popup overlay in the bottom-right corner of "
                 "your screen. The overlay shows the threat level with a color-coded "
                 "border (red for CRITICAL, orange for WARNING, yellow for "
                 "SUSPICIOUS) and auto-dismisses when you make a choice in the "
                 "terminal. Click the overlay to dismiss it manually."),
            ],
        },

        # ── Model Router ─────────────────────────────────────────
        {
            "title": "Model Router",
            "icon": "R",
            "blocks": [
                ("heading", "Model Router"),
                ("paragraph",
                 "The model router enables dual-model operation: a fast, small "
                 "model handles simple queries while a larger, more capable model "
                 "handles complex tasks. This optimizes for both speed and quality."),
                ("subheading", "Complexity Scoring"),
                ("paragraph",
                 "Each user prompt is scored on a 0-100 complexity scale based on "
                 "multiple signals:"),
                ("bullet", "Token count and prompt length"),
                ("bullet", "Presence of code blocks or technical content"),
                ("bullet", "Number of files referenced or needed"),
                ("bullet", "Task type classification (explain, refactor, debug, create)"),
                ("bullet", "Estimated tool calls required"),
                ("bullet", "Conversation context depth"),
                ("paragraph",
                 "Prompts scoring below the threshold (default: 40) are routed to "
                 "the small model. Above the threshold, the big model is used."),
                ("subheading", "Setting Up Dual-Model Routing"),
                ("paragraph",
                 "1. Pull two models in Ollama: a large one (e.g. qwen2.5-coder:32b) "
                 "and a small one (e.g. qwen2.5-coder:7b).\n"
                 "2. Enable routing: /router on\n"
                 "3. Set models: /router big qwen2.5-coder:32b\n"
                 "4. Set models: /router small qwen2.5-coder:7b\n"
                 "5. Check stats: /router"),
                ("subheading", "Routing Statistics"),
                ("paragraph",
                 "Use /router to view routing stats: how many prompts went to each "
                 "model, average complexity scores, and time saved by using the "
                 "small model for simple queries."),
            ],
        },

        # ── Context Window ───────────────────────────────────────
        {
            "title": "Context Window",
            "icon": "W",
            "blocks": [
                ("heading", "Context Window Management"),
                ("paragraph",
                 "Forge's context window is a partitioned token budget that manages "
                 "everything the AI can see. Unlike cloud APIs that silently truncate "
                 "context, Forge gives you full visibility and control over what is "
                 "in the window."),
                ("subheading", "Partitions"),
                ("paragraph",
                 "The context window is divided into five partitions:"),
                ("bullet",
                 "Core: System prompt, tool definitions, and critical instructions. "
                 "Always present, never evicted."),
                ("bullet",
                 "Working: Active conversation messages and recent tool results. "
                 "This is the primary workspace."),
                ("bullet",
                 "Reference: Pinned files, documentation, and persistent context. "
                 "Survives eviction."),
                ("bullet",
                 "Recall: Semantic search results and memory retrievals. Loaded "
                 "on-demand and evicted first."),
                ("bullet",
                 "Quarantine: Threat-flagged content isolated by the Crucible. "
                 "Not sent to the AI but preserved for analysis."),
                ("subheading", "Eviction Strategy"),
                ("paragraph",
                 "When the context window reaches capacity, entries are evicted "
                 "in this order: recall entries first, then working entries "
                 "(oldest first). Pinned entries and core partition entries are "
                 "never evicted. The /context command shows current usage and "
                 "which entries would be evicted next."),
                ("subheading", "Context Swap"),
                ("paragraph",
                 "When a large amount of context needs to be swapped (e.g., "
                 "switching from one file to another), Forge performs a context "
                 "swap: evicting old content and loading new content in a single "
                 "operation. The Neural Cortex dashboard shows a flash animation "
                 "during swaps."),
                ("subheading", "Token Counting"),
                ("paragraph",
                 "Forge counts tokens using the model's actual tokenizer for "
                 "accuracy. Token counts are displayed in /context output and "
                 "the status bar. The status bar color changes from green to "
                 "yellow to red as usage increases."),
            ],
        },

        # ── Continuity Grade ──────────────────────────────────────
        {
            "title": "Continuity Grade",
            "icon": "G",
            "blocks": [
                ("heading", "Continuity Grade"),
                ("paragraph",
                 "Real-time measurement of AI context quality across context swaps. "
                 "When the context window fills up and swaps occur, nuance gets lost. "
                 "The Continuity Grade system detects this degradation and auto-recovers."),
                ("subheading", "Signals"),
                ("paragraph",
                 "Six deterministic signals are scored 0-100 and weighted into a "
                 "composite grade (A-F):"),
                ("bullet",
                 "Objective Alignment (25%): Cosine similarity between the original "
                 "objective and current context. Requires embedding model."),
                ("bullet",
                 "File Coverage (25%): Percentage of modified files still represented "
                 "in the context window."),
                ("bullet",
                 "Decision Retention (15%): Percentage of key decisions whose terms "
                 "are still findable in context."),
                ("bullet",
                 "Swap Freshness (15%): Exponential recovery curve after each swap, "
                 "penalized by total swap count."),
                ("bullet",
                 "Recall Quality (10%): Average relevance of post-swap semantic "
                 "recalls. Requires embedding model."),
                ("bullet",
                 "Working Memory Depth (10%): Ratio of substantive entries (>100 "
                 "tokens) in the working partition."),
                ("subheading", "Auto-Recovery"),
                ("paragraph",
                 "When the grade drops below the recovery threshold (default 60), "
                 "Forge triggers mild recovery: re-reads modified files and injects "
                 "semantic recalls for the current objective. Below the aggressive "
                 "threshold (default 40), it also re-injects subtask recalls. "
                 "Recovery has a 3-turn cooldown to prevent loops."),
                ("subheading", "Without Embeddings"),
                ("paragraph",
                 "If no embedding model is available, signals 1 and 5 are skipped "
                 "and weights redistribute to the remaining four signals. The system "
                 "still works, just with fewer data points."),
                ("subheading", "Commands"),
                ("bullet", "/continuity — Show grade breakdown and all signal values"),
                ("bullet", "/continuity history — Show last 10 continuity snapshots"),
                ("bullet", "/continuity set <N> — Set recovery threshold (0-100)"),
                ("bullet", "/continuity on|off — Enable or disable monitoring"),
            ],
        },

        # ── File Cache ───────────────────────────────────────────
        {
            "title": "File Cache",
            "icon": "C",
            "blocks": [
                ("heading", "File Cache System"),
                ("paragraph",
                 "The file cache stores tokenized representations of files to "
                 "avoid redundant disk reads and re-tokenization. This significantly "
                 "speeds up operations when the AI repeatedly references the same "
                 "files."),
                ("subheading", "How It Works"),
                ("bullet",
                 "When a file is read, its content and token count are cached in "
                 "memory, keyed by absolute path."),
                ("bullet",
                 "On subsequent reads, the cache checks the file's modification "
                 "time. If unchanged, the cached version is used."),
                ("bullet",
                 "If the file has been modified, the cache entry is invalidated "
                 "and the file is re-read from disk."),
                ("bullet",
                 "Cache statistics (/cache) show hit rate and token savings."),
                ("subheading", "Integrity Monitoring"),
                ("paragraph",
                 "The cache includes integrity checks to detect external file "
                 "modifications. When a file is modified outside of Forge (e.g., "
                 "by your editor), the cache detects the mtime change and "
                 "automatically invalidates the entry. This ensures the AI "
                 "always sees current file content."),
                ("subheading", "Cache Management"),
                ("bullet", "View stats: /cache"),
                ("bullet", "Clear cache: /cache clear"),
                ("bullet",
                 "The cache is stored in memory only and is cleared on exit."),
            ],
        },

        # ── Forensics ────────────────────────────────────────────
        {
            "title": "Forensics",
            "icon": "F",
            "blocks": [
                ("heading", "Session Forensics"),
                ("paragraph",
                 "Forge maintains a detailed audit trail of everything the AI "
                 "does during a session. This forensics data is useful for "
                 "debugging, compliance, and understanding AI behavior."),
                ("subheading", "Audit Trail"),
                ("paragraph",
                 "Every tool call is logged with: timestamp, tool name, "
                 "arguments, result summary, token cost, and execution time. "
                 "The trail shows the complete sequence of actions the AI took "
                 "and why (linked to the prompt that triggered each action)."),
                ("subheading", "Provenance Tracking"),
                ("paragraph",
                 "Provenance tracks the causal chain: which user prompt led "
                 "to which tool call, which tool result influenced the next "
                 "decision. This creates a decision tree showing the AI's "
                 "reasoning path. View with /provenance."),
                ("subheading", "Behavioral Fingerprinting"),
                ("paragraph",
                 "Forge builds a behavioral profile of the AI during each "
                 "session: typical tool usage patterns, response length "
                 "distribution, code-to-text ratio, and common action sequences. "
                 "This fingerprint is used by the Crucible to detect anomalous "
                 "behavior that may indicate prompt injection."),
                ("subheading", "Reports"),
                ("paragraph",
                 "Use /forensics save to export a comprehensive report as JSON. "
                 "The report includes the full audit trail, provenance chain, "
                 "behavioral fingerprint, file diff history, and session metadata."),
            ],
        },

        # ── Memory System ────────────────────────────────────────
        {
            "title": "Memory System",
            "icon": "M",
            "blocks": [
                ("heading", "Memory System"),
                ("paragraph",
                 "Forge's memory system provides persistence across sessions, "
                 "enabling the AI to recall past interactions, learned patterns, "
                 "and project-specific knowledge."),
                ("subheading", "Episodic Memory"),
                ("paragraph",
                 "Automatically captures conversation summaries at the end of "
                 "each session. When you start a new session in the same project, "
                 "relevant episodic memories are loaded into context, giving the "
                 "AI awareness of past work and decisions."),
                ("subheading", "Semantic Index"),
                ("paragraph",
                 "The semantic index (/index) creates vector embeddings of your "
                 "codebase. This enables natural language code search via /search "
                 "and /recall. The index is stored on disk and updated "
                 "incrementally when files change."),
                ("subheading", "Journal"),
                ("paragraph",
                 "The journal (/journal) is a persistent log of decisions, "
                 "learnings, and notes. Forge automatically writes journal entries "
                 "for significant events: architectural decisions, bug discoveries, "
                 "refactoring rationale. Entries persist across sessions and help "
                 "maintain continuity on long-running projects."),
                ("subheading", "Recall"),
                ("paragraph",
                 "The /recall command searches both the semantic index and episodic "
                 "memory to find relevant context. Results are loaded into the "
                 "recall partition of the context window. This is how Forge brings "
                 "past knowledge into the current conversation."),
            ],
        },

        # ── Voice Input ──────────────────────────────────────────
        {
            "title": "Voice Input",
            "icon": "V",
            "blocks": [
                ("heading", "Voice Input System"),
                ("paragraph",
                 "Forge supports voice input via local speech recognition. "
                 "Audio is processed entirely on-device -- no cloud transcription "
                 "services are used."),
                ("subheading", "Push-to-Talk (PTT) Mode"),
                ("paragraph",
                 "Hold the backtick key (`) to record. Release to send. The audio "
                 "is transcribed and either executed as a command or sent as a "
                 "prompt to the AI, depending on voice classification."),
                ("subheading", "Voice-Activated (VOX) Mode"),
                ("paragraph",
                 "Forge listens continuously and auto-detects speech onset. When "
                 "silence is detected after speech, the utterance is transcribed "
                 "and processed. VOX mode uses energy-based voice activity "
                 "detection with adaptive thresholds."),
                ("subheading", "Voice Classification"),
                ("paragraph",
                 "Transcribed speech is classified into categories:"),
                ("bullet",
                 "Commands: Utterances that map to slash commands (e.g., "
                 "'show me the context' maps to /context)."),
                ("bullet",
                 "Inline Questions: Quick questions asked during a response "
                 "(e.g., 'what does this function do?')."),
                ("bullet",
                 "Prompts: General instructions sent to the AI as regular input."),
                ("subheading", "Setup"),
                ("paragraph",
                 "Voice input requires a microphone and the whisper model. "
                 "Enable with /voice ptt or /voice vox. Disable with /voice off. "
                 "Check status with /voice."),
            ],
        },

        # ── Neural Cortex Dashboard ──────────────────────────────
        {
            "title": "Neural Cortex",
            "icon": "N",
            "blocks": [
                ("heading", "Neural Cortex Dashboard"),
                ("paragraph",
                 "The Neural Cortex dashboard (/dashboard) is a graphical "
                 "monitoring window featuring a brain visualization with "
                 "depth-aware animation that reflects the AI's current state."),
                ("subheading", "Animation States"),
                ("bullet",
                 "BOOT: Initial startup. Slow spiral animation in cyan. Shown "
                 "during model loading and initialization."),
                ("bullet",
                 "IDLE: Waiting for input. Gentle pulsing glow. The brain "
                 "breathes slowly with minimal activity."),
                ("bullet",
                 "THINKING: Processing a prompt. Multi-colored rapid waves "
                 "propagate through the neural pathways. Speed increases with "
                 "generation rate."),
                ("bullet",
                 "TOOL_EXEC: Executing a tool call. Green sweep animation "
                 "moves across the brain, indicating active file or shell "
                 "operations."),
                ("bullet",
                 "INDEXING: Building or updating the semantic index. Purple "
                 "multi-wave pattern indicates batch processing of files."),
                ("bullet",
                 "SWAPPING: Context swap in progress. Bright cyan flash "
                 "with low saturation, indicating memory reorganization."),
                ("bullet",
                 "ERROR: An error occurred. Red pulse animation. Indicates "
                 "a failed tool call, model error, or configuration problem."),
                ("bullet",
                 "THREAT: Crucible detected a threat. Angry red rapid flash "
                 "with high intensity. Indicates potential prompt injection "
                 "or security concern."),
                ("subheading", "Dashboard Cards"),
                ("paragraph",
                 "Below the brain visualization, dashboard cards show live "
                 "metrics: context window usage, file cache hit rate, "
                 "generation speed, active model, and safety status. Cards "
                 "update in real-time via a shared state file."),
                ("subheading", "Synapse Check"),
                ("paragraph",
                 "The synapse check (/synapse or voice command 'synapse check') "
                 "cycles through all 8 animation states in sequence with a 2.5 "
                 "second dwell on each mode. Each transition plays the mode's "
                 "sound effect and announces the mode name via text-to-speech. "
                 "Use this to verify all animations and sounds are working, or "
                 "just to look cool."),
                ("subheading", "Settings"),
                ("paragraph",
                 "The File menu on the dashboard menubar provides access to "
                 "Settings (Ctrl+,) where all configuration values can be "
                 "adjusted through a tabbed GUI interface. Changes are saved "
                 "to config.yaml and automatically picked up by the engine."),
            ],
        },

        # ── Themes ────────────────────────────────────────────────
        {
            "title": "Themes",
            "icon": "T",
            "blocks": [
                ("heading", "Theme System"),
                ("paragraph",
                 "Forge includes 12 built-in color themes that apply to the "
                 "Neural Cortex dashboard, settings dialog, model manager, test "
                 "runner, documentation window, and Crucible overlay. All colors "
                 "and fonts are centralized in a single theme module."),
                ("subheading", "Available Themes"),
                ("bullet", "Midnight — Dark navy with cyan accents (default)"),
                ("bullet", "Obsidian — Neutral charcoal with ice blue accents"),
                ("bullet", "Dracula — Classic purple-tinted dark theme"),
                ("bullet", "Solarized Dark — Warm teal, Ethan Schoonover's palette"),
                ("bullet", "Nord — Cool arctic blue-gray from Svalbard"),
                ("bullet", "Monokai — Warm dark with bright accents"),
                ("bullet", "Cyberpunk — Neon pink and cyan on true black"),
                ("bullet", "Matrix — Green phosphor terminal aesthetic"),
                ("bullet", "Amber — Retro amber phosphor display"),
                ("bullet", "Phosphor — Green CRT scanline aesthetic"),
                ("bullet", "Arctic — Light theme with blue accents"),
                ("bullet", "Sunset — Warm coral and orange tones"),
                ("bullet", "OD Green — Military olive drab palette"),
                ("bullet",
                 "Plasma — Electric glow with animated effects "
                 "(energy borders, particles, header pulses)"),
                ("subheading", "Switching Themes"),
                ("paragraph",
                 "Use the /theme command in the terminal or the Theme dropdown "
                 "in Settings (UI tab). Theme changes apply instantly to all "
                 "open windows via hot-swap — no restart needed."),
                ("subheading", "Visual Effects"),
                ("paragraph",
                 "Some themes (Plasma, Cyberpunk, Matrix) include animated "
                 "visual effects: glowing card borders that cycle through "
                 "accent colors, floating particles behind cards, energy "
                 "pulses on divider lines, and hover glow. Effects can be "
                 "disabled in Settings > UI > Visual Effects."),
                ("subheading", "Commands"),
                ("bullet", "/theme — List all available themes"),
                ("bullet", "/theme <name> — Switch to a theme"),
            ],
        },

        # ── Keyboard Shortcuts ───────────────────────────────────
        {
            "title": "Keyboard Shortcuts",
            "icon": "K",
            "blocks": [
                ("heading", "Keyboard Shortcuts"),
                ("subheading", "During AI Response"),
                ("command", "Escape",
                 "Interrupt the current response",
                 "Immediately stops the AI's response. Partial output and any "
                 "file changes made so far are preserved. You are then given "
                 "three options: type new instructions (redirect), type 'undo' "
                 "(rollback), or press Enter (stop).",
                 None),
                ("command", "undo (after Escape)",
                 "Rollback all changes from this turn",
                 "After interrupting with Escape, typing 'undo' reverts all "
                 "file modifications and creations made during the interrupted "
                 "turn. Context entries added during the turn are also removed.",
                 None),
                ("subheading", "Input"),
                ("command", "Tab",
                 "Autocomplete commands and file paths",
                 "Tab completion works for slash commands (/co -> /context) "
                 "and file paths. Press Tab once for the best match, twice "
                 "to see all possibilities.",
                 None),
                ("command", "Up / Down Arrow",
                 "Navigate command history",
                 "Cycle through previously entered commands. History persists "
                 "across sessions (saved to ~/.forge/cmd_history.txt).",
                 None),
                ("command", "Ctrl+C or Ctrl+D",
                 "Exit Forge",
                 "Sends the /quit command. History is saved before exit. "
                 "Equivalent to typing /quit.",
                 None),
                ("subheading", "Voice"),
                ("command", "` (backtick)",
                 "Push-to-talk (when voice PTT is enabled)",
                 "Hold the backtick key to record audio. Release to transcribe "
                 "and process the speech input. Only active when /voice ptt "
                 "mode is enabled.",
                 None),
                ("subheading", "Documentation"),
                ("command", "F1",
                 "Open this documentation window",
                 "Opens the Forge documentation window from anywhere in the "
                 "application. The window is non-modal and can be kept open "
                 "while working.",
                 None),
            ],
        },

        # ── Plugins ──────────────────────────────────────────────
        {
            "title": "Plugins",
            "icon": "P",
            "blocks": [
                ("heading", "Plugin System"),
                ("paragraph",
                 "Forge supports a plugin system for extending functionality. "
                 "Plugins can add custom tools, hook into events, and register "
                 "new slash commands -- all without modifying Forge's core code."),
                ("subheading", "Plugin Location"),
                ("paragraph",
                 "Place plugin .py files in ~/.forge/plugins/. Forge auto-discovers "
                 "and loads all valid plugins on startup. Each plugin file should "
                 "contain a class that extends ForgePlugin."),
                ("subheading", "Available Hooks"),
                ("bullet",
                 "on_load / on_unload: Called when the plugin is loaded or unloaded."),
                ("bullet",
                 "on_user_input: Intercept or modify user input before it reaches the AI."),
                ("bullet",
                 "on_response: Process AI responses before display."),
                ("bullet",
                 "on_tool_call / on_tool_result: Monitor tool execution."),
                ("bullet",
                 "on_file_read / on_file_write: React to file operations."),
                ("bullet",
                 "on_command: Handle custom slash commands."),
                ("bullet",
                 "register_tools: Add custom tools to the AI's toolset."),
                ("subheading", "Plugin Priority"),
                ("paragraph",
                 "Plugins can set a priority (0-100) on each hook method. Lower "
                 "numbers run first. Default priority is 50. Use priority to control "
                 "execution order when multiple plugins hook the same event."),
                ("subheading", "Management"),
                ("bullet", "View loaded plugins: /plugins"),
                ("bullet", "Plugin errors are logged but do not crash Forge."),
                ("bullet",
                 "Plugins are isolated: a failure in one plugin does not affect others."),
            ],
        },

        # ── Plan Mode ────────────────────────────────────────────
        {
            "title": "Plan Mode",
            "icon": "!",
            "blocks": [
                ("heading", "Plan Mode"),
                ("paragraph",
                 "Plan mode makes the AI generate a structured plan before "
                 "executing any changes. This prevents wasted effort, gives you "
                 "full control over what will happen, and enables step-by-step "
                 "execution with progress tracking."),
                ("subheading", "Modes"),
                ("bullet",
                 "Off: Plans are never generated (default). Use /plan on to arm "
                 "plan mode for the next prompt."),
                ("bullet",
                 "Manual: Plan mode is triggered by /plan on before a prompt. "
                 "Does not auto-trigger."),
                ("bullet",
                 "Auto: Plan mode triggers automatically for complex prompts "
                 "(based on the router's complexity score). Simple prompts "
                 "execute normally."),
                ("bullet",
                 "Always: Every prompt goes through plan mode."),
                ("subheading", "Plan Approval"),
                ("paragraph",
                 "When a plan is generated, you have four choices:"),
                ("bullet",
                 "[A]pprove: Execute the full plan immediately."),
                ("bullet",
                 "[S]tep-by-step: Execute one step at a time with progress "
                 "display. You can interrupt between steps."),
                ("bullet",
                 "[R]eject: Discard the plan and return to the prompt."),
                ("bullet",
                 "[E]dit: Modify your instructions and regenerate the plan."),
                ("subheading", "Voice Activation"),
                ("paragraph",
                 "Say 'plan mode' or 'enter plan mode' via voice to arm plan "
                 "mode. Say 'plan mode off' or 'just do it' to disable it. "
                 "Works in both PTT and VOX modes."),
                ("subheading", "Tool Deduplication"),
                ("paragraph",
                 "Forge automatically detects when the AI calls the same tool "
                 "with nearly identical arguments (e.g., writing the same note "
                 "5 times). Duplicate calls are suppressed and the AI is nudged "
                 "to try a different approach. Configure the similarity threshold "
                 "with /dedup threshold (default: 92%)."),
            ],
        },

        # ── Glossary ─────────────────────────────────────────────
        {
            "title": "Glossary",
            "icon": "A",
            "blocks": [
                ("heading", "Glossary"),
                ("paragraph",
                 "Alphabetical definitions of Forge-specific terms."),
                ("term", "Canary",
                 "A hidden honeypot token placed in the context window. If it "
                 "appears in AI output, it indicates a prompt injection attack. "
                 "Part of the Crucible Layer 4 detection."),
                ("term", "Context Window",
                 "The total token budget available for the AI conversation. "
                 "Divided into partitions (core, working, reference, recall, "
                 "quarantine). Managed with /context, /pin, /drop commands."),
                ("term", "Core Partition",
                 "The innermost context partition containing the system prompt, "
                 "tool definitions, and critical instructions. Never evicted."),
                ("term", "Crucible",
                 "Forge's multi-layered threat scanner. Monitors AI output for "
                 "prompt injection, data exfiltration, and other attacks using "
                 "four detection layers."),
                ("term", "Crucible Overlay",
                 "A popup avatar window that appears in the bottom-right corner "
                 "when the Crucible detects a threat. Shows the threat level with "
                 "color-coded border. Dismissed by clicking or making a choice."),
                ("term", "Dedup",
                 "Tool call deduplication system. Detects when the AI calls the "
                 "same tool with nearly identical arguments and suppresses the "
                 "duplicate. Configurable threshold via /dedup."),
                ("term", "Episodic Memory",
                 "Conversation summaries stored between sessions. Provides "
                 "continuity by loading relevant past interactions into context."),
                ("term", "Eviction",
                 "The process of removing context entries when the window is "
                 "full. Recall entries are evicted first, then oldest working "
                 "entries. Pinned entries are never evicted."),
                ("term", "Forensics",
                 "The session audit trail system. Records all tool calls, "
                 "file operations, and AI actions for debugging and compliance."),
                ("term", "Journal",
                 "A persistent log of decisions and learnings maintained by "
                 "Forge across sessions. Viewable with /journal."),
                ("term", "Model Router",
                 "Dual-model routing system that sends simple prompts to a fast "
                 "model and complex prompts to a capable model. Uses complexity "
                 "scoring to make routing decisions."),
                ("term", "Neural Cortex",
                 "The graphical dashboard window with brain visualization. Shows "
                 "AI state (thinking, executing, error) via animated neural "
                 "pathway rendering."),
                ("term", "Pinning",
                 "Marking a context entry so it survives eviction. Pinned entries "
                 "remain in context until manually unpinned or reset."),
                ("term", "Plan Mode",
                 "A structured planning system where the AI generates a step-by-step "
                 "plan before execution. Supports manual, auto, and always modes. "
                 "Activated with /plan."),
                ("term", "Plugin",
                 "An extension module placed in ~/.forge/plugins/. Plugins can add "
                 "tools, hook events, and register commands. Managed with /plugins."),
                ("term", "Provenance",
                 "The causal chain linking user prompts to AI actions. Shows which "
                 "prompt triggered which tool call and how results influenced "
                 "subsequent decisions."),
                ("term", "Quarantine",
                 "A context partition for threat-flagged content. Quarantined "
                 "entries are isolated from the AI but preserved for forensic "
                 "analysis."),
                ("term", "Recall",
                 "Semantic search across the codebase index and episodic memory. "
                 "Results are loaded into the recall partition of the context "
                 "window."),
                ("term", "Safety Tier",
                 "One of four configurable restriction levels: unleashed, "
                 "smart_guard, confirm_writes, locked_down. Controls what "
                 "operations the AI is allowed to perform."),
                ("term", "Sandbox",
                 "Filesystem isolation that restricts file operations to the "
                 "working directory and explicitly allowed paths. Independent "
                 "of safety tier."),
                ("term", "Semantic Index",
                 "Vector embeddings of the codebase created by /index. Enables "
                 "natural language code search via /search and /recall."),
                ("term", "Smart Guard",
                 "The default safety tier. Blocks obviously destructive patterns "
                 "while allowing normal development operations."),
                ("term", "Swap",
                 "A context operation that evicts old content and loads new content "
                 "in a single step. Triggered when switching between files or "
                 "topics that exceed the remaining token budget."),
                ("term", "Token",
                 "The fundamental unit of text for language models. Roughly 3/4 of "
                 "a word on average. Context window capacity and costs are measured "
                 "in tokens."),
            ],
        },
    ]


# ──────────────────────────────────────────────────────────────────
# Helper: flatten doc content into searchable text
# ──────────────────────────────────────────────────────────────────

def _block_text(block: tuple) -> str:
    """Return searchable plain-text for a single block."""
    kind = block[0]
    if kind == "separator":
        return ""
    if kind == "heading":
        return block[1]
    if kind == "subheading":
        return block[1]
    if kind == "paragraph":
        return block[1]
    if kind == "bullet":
        return block[1]
    if kind == "command":
        # syntax, summary, detail, example
        parts = [block[1], block[2], block[3]]
        if len(block) > 4 and block[4]:
            parts.append(block[4])
        return " ".join(parts)
    if kind == "term":
        return f"{block[1]} {block[2]}"
    return ""


# ──────────────────────────────────────────────────────────────────
# DocsWindow
# ──────────────────────────────────────────────────────────────────

class DocsWindow:
    """Forge documentation window -- Toplevel popup with sidebar + search."""

    _instance: Optional["DocsWindow"] = None

    @classmethod
    def open(cls, parent: tk.Misc = None):
        """Open (or focus) the docs window.  Only one instance at a time.

        When called without a parent (from the terminal via /docs), the
        window is created and its mainloop is run in a daemon thread so
        it doesn't block the terminal.
        """
        if cls._instance is not None:
            try:
                cls._instance._win.lift()
                cls._instance._win.focus_force()
                return cls._instance
            except tk.TclError:
                cls._instance = None

        if parent is not None:
            # Called from a GUI that already runs mainloop
            inst = cls(parent)
            cls._instance = inst
            return inst

        # Terminal mode — run Tk in a background thread
        import threading

        def _run():
            inst = cls(None)
            cls._instance = inst
            inst._win.mainloop()
            # Window was closed
            cls._instance = None

        t = threading.Thread(target=_run, daemon=True, name="ForgeDocsUI")
        t.start()

    # ── construction ─────────────────────────────────────────────

    def __init__(self, parent: tk.Misc = None):
        self._docs = _build_docs()
        self._parent = parent

        # ── Toplevel ──
        self._win = tk.Toplevel(parent) if parent else tk.Tk()
        self._win.title("Forge Documentation")
        self._win.configure(bg=_C["bg"])
        self._win.geometry("960x720")
        self._win.minsize(700, 480)
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

        # Try to set icon
        try:
            from pathlib import Path
            ico = Path(__file__).parent / "assets" / "icon.ico"
            if ico.exists():
                self._win.iconbitmap(str(ico))
        except Exception:
            pass

        # ── ttk style ──
        self._style = ttk.Style(self._win)
        self._configure_styles()

        # ── layout ──
        self._build_ui()
        self._populate_sidebar()
        self._render_all()

        # Register for live theme hot-swap
        self._theme_cb = self._apply_theme
        add_theme_listener(self._theme_cb)

        # Select the first section
        if self._docs:
            self._select_section(0)

    # ── ttk styles ───────────────────────────────────────────────

    def _configure_styles(self):
        s = self._style
        s.theme_use("clam")

        # General
        s.configure(".", background=_C["bg"], foreground=_C["fg"],
                     fieldbackground=_C["bg_input"], borderwidth=0,
                     font=_FONT_BODY)

        # Frames
        s.configure("Sidebar.TFrame", background=_C["bg_sidebar"])
        s.configure("Content.TFrame", background=_C["bg_content"])
        s.configure("Card.TFrame", background=_C["bg_card"])
        s.configure("TopBar.TFrame", background=_C["bg"])

        # Labels
        s.configure("Sidebar.TLabel",
                     background=_C["bg_sidebar"], foreground=_C["fg_dim"],
                     font=_FONT_SIDEBAR, padding=(12, 8))
        s.configure("SidebarSel.TLabel",
                     background=_C["bg_selected"], foreground=_C["accent"],
                     font=_FONT_SIDEBAR_BOLD, padding=(12, 8))
        s.configure("SidebarTitle.TLabel",
                     background=_C["bg_sidebar"], foreground=_C["fg_muted"],
                     font=_FONT_SMALL, padding=(12, 4))
        s.configure("SearchCount.TLabel",
                     background=_C["bg"], foreground=_C["fg_dim"],
                     font=_FONT_SMALL, padding=(4, 0))
        s.configure("Title.TLabel",
                     background=_C["bg"], foreground=_C["accent"],
                     font=_FONT_TITLE, padding=(0, 4))

        # Scrollbar
        s.configure("Dark.Vertical.TScrollbar",
                     background=_C["bg_card"],
                     troughcolor=_C["bg_content"],
                     arrowcolor=_C["fg_dim"],
                     borderwidth=0, relief="flat")
        s.map("Dark.Vertical.TScrollbar",
               background=[("active", _C["accent_dim"]),
                            ("!active", _C["bg_card"])])

        # Separator
        s.configure("Accent.TSeparator", background=_C["separator"])

    # ── UI construction ──────────────────────────────────────────

    def _build_ui(self):
        win = self._win

        # ── Top bar (search) ──
        top = ttk.Frame(win, style="TopBar.TFrame")
        top.pack(fill="x", padx=0, pady=0)

        # Title
        ttk.Label(top, text="FORGE DOCS", style="Title.TLabel").pack(
            side="left", padx=(16, 8))

        # Search bar
        search_frame = tk.Frame(top, bg=_C["bg_input"], highlightthickness=1,
                                highlightbackground=_C["border"],
                                highlightcolor=_C["accent"])
        search_frame.pack(side="left", fill="x", expand=True,
                          padx=(8, 8), pady=8)

        self._search_icon = tk.Label(search_frame, text=" /",
                                     bg=_C["bg_input"], fg=_C["accent"],
                                     font=_FONT_MONO_BOLD)
        self._search_icon.pack(side="left", padx=(4, 0))

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", self._on_search_changed)
        self._search_entry = tk.Entry(
            search_frame, textvariable=self._search_var,
            bg=_C["bg_input"], fg=_C["fg"], insertbackground=_C["accent"],
            font=_FONT_SEARCH, relief="flat", border=0)
        self._search_entry.pack(side="left", fill="x", expand=True,
                                padx=4, pady=4, ipady=2)
        self._search_entry.bind("<Escape>", lambda e: self._clear_search())

        self._result_count = ttk.Label(top, text="", style="SearchCount.TLabel")
        self._result_count.pack(side="left", padx=(0, 16))

        # Close button
        close_btn = tk.Label(top, text="  X  ", bg=_C["bg"], fg=_C["fg_dim"],
                             font=_FONT_BODY_BOLD, cursor="hand2")
        close_btn.pack(side="right", padx=(0, 8))
        close_btn.bind("<Button-1>", lambda e: self._on_close())
        close_btn.bind("<Enter>", lambda e: close_btn.configure(fg=_C["red"]))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(fg=_C["fg_dim"]))

        # ── Separator ──
        sep = tk.Frame(win, bg=_C["separator"], height=1)
        sep.pack(fill="x")

        # ── Body (sidebar + content) ──
        body = ttk.Frame(win, style="Content.TFrame")
        body.pack(fill="both", expand=True)

        # Sidebar
        self._sidebar_frame = tk.Frame(body, bg=_C["bg_sidebar"], width=220)
        self._sidebar_frame.pack(side="left", fill="y")
        self._sidebar_frame.pack_propagate(False)

        # Sidebar vertical separator
        sep2 = tk.Frame(body, bg=_C["border"], width=1)
        sep2.pack(side="left", fill="y")

        # Content pane
        content_outer = tk.Frame(body, bg=_C["bg_content"])
        content_outer.pack(side="left", fill="both", expand=True)

        # Scrollable content
        self._canvas = tk.Canvas(content_outer, bg=_C["bg_content"],
                                 highlightthickness=0, bd=0)
        self._scrollbar = ttk.Scrollbar(content_outer, orient="vertical",
                                        command=self._canvas.yview,
                                        style="Dark.Vertical.TScrollbar")
        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)
        def _on_yscroll(*args):
            self._scrollbar.set(*args)
            self._on_scroll_changed()
        self._canvas.configure(yscrollcommand=_on_yscroll)

        self._content_frame = tk.Frame(self._canvas, bg=_C["bg_content"])
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._content_frame, anchor="nw")

        self._content_frame.bind("<Configure>", self._on_content_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Mouse-wheel scrolling scoped to canvas
        self._canvas.bind("<Enter>", self._bind_mousewheel)
        self._canvas.bind("<Leave>", self._unbind_mousewheel)

        # Track sidebar labels
        self._sidebar_labels: list[tk.Label] = []
        self._selected_idx: int = -1

        # Track rendered widgets for search highlighting
        self._rendered_widgets: list[tuple[str, tk.Widget, str]] = []
        # (block_kind, widget, original_text)

    # ── Sidebar ──────────────────────────────────────────────────

    def _populate_sidebar(self):
        # Title
        header = tk.Label(self._sidebar_frame, text="SECTIONS",
                          bg=_C["bg_sidebar"], fg=_C["fg_muted"],
                          font=_FONT_SMALL, anchor="w")
        header.pack(fill="x", padx=16, pady=(12, 4))

        sep = tk.Frame(self._sidebar_frame, bg=_C["border"], height=1)
        sep.pack(fill="x", padx=12, pady=(0, 4))

        for i, section in enumerate(self._docs):
            lbl = tk.Label(
                self._sidebar_frame,
                text=f"  {section['icon']}   {section['title']}",
                bg=_C["bg_sidebar"], fg=_C["fg_dim"],
                font=_FONT_SIDEBAR, anchor="w", cursor="hand2",
                padx=12, pady=7)
            lbl.pack(fill="x")
            idx = i  # capture
            lbl.bind("<Button-1>", lambda e, ii=idx: self._select_section(ii))
            lbl.bind("<Enter>",
                     lambda e, lb=lbl: lb.configure(bg=_C["bg_hover"])
                     if lb != self._get_selected_label() else None)
            lbl.bind("<Leave>",
                     lambda e, lb=lbl: lb.configure(
                         bg=_C["bg_selected"] if lb == self._get_selected_label()
                         else _C["bg_sidebar"]))
            self._sidebar_labels.append(lbl)

    def _get_selected_label(self) -> Optional[tk.Label]:
        if 0 <= self._selected_idx < len(self._sidebar_labels):
            return self._sidebar_labels[self._selected_idx]
        return None

    def _highlight_sidebar(self, idx: int):
        """Update sidebar highlight visuals only (no scrolling)."""
        if idx == self._selected_idx:
            return
        # Deselect old
        if 0 <= self._selected_idx < len(self._sidebar_labels):
            old = self._sidebar_labels[self._selected_idx]
            old.configure(bg=_C["bg_sidebar"], fg=_C["fg_dim"],
                          font=_FONT_SIDEBAR)

        self._selected_idx = idx

        # Select new
        if 0 <= idx < len(self._sidebar_labels):
            lbl = self._sidebar_labels[idx]
            lbl.configure(bg=_C["bg_selected"], fg=_C["accent"],
                          font=_FONT_SIDEBAR_BOLD)

    def _select_section(self, idx: int):
        """Highlight sidebar entry and scroll content to that section."""
        self._highlight_sidebar(idx)
        self._scroll_to_section(idx)

    def _scroll_to_section(self, idx: int):
        """Scroll the content canvas so that the given section is visible."""
        tag = f"section_{idx}"
        # Find the first widget with this section index
        target_y = None
        for child in self._content_frame.winfo_children():
            if hasattr(child, "_section_idx") and child._section_idx == idx:
                target_y = child.winfo_y()
                break

        if target_y is not None:
            # Normalize to fraction of total scrollable area
            total_height = self._content_frame.winfo_reqheight()
            if total_height > 0:
                fraction = max(0.0, min(1.0, target_y / total_height))
                self._canvas.yview_moveto(fraction)

    def _on_scroll_changed(self):
        """Update sidebar highlight based on current scroll position."""
        try:
            yview_top = self._canvas.yview()[0]
            total_h = self._content_frame.winfo_reqheight()
            if total_h <= 0:
                return
            # Pixel position of the top of the visible area
            visible_top = yview_top * total_h
            # Find which section anchor is at or just above visible_top
            best_idx = 0
            for child in self._content_frame.winfo_children():
                if hasattr(child, "_section_idx"):
                    if child.winfo_y() <= visible_top + 30:
                        best_idx = child._section_idx
                    else:
                        break
            self._highlight_sidebar(best_idx)
        except Exception:
            pass

    # ── Content rendering ────────────────────────────────────────

    def _render_all(self):
        """Render all sections into the content frame."""
        for w in self._content_frame.winfo_children():
            w.destroy()
        self._rendered_widgets.clear()

        query = self._search_var.get().strip().lower()
        match_count = 0

        for sec_idx, section in enumerate(self._docs):
            # If searching, skip sections with no matches
            if query:
                section_text = " ".join(
                    _block_text(b) for b in section["blocks"]).lower()
                if query not in section_text:
                    continue

            # Section anchor label (invisible, used for scrolling)
            anchor = tk.Frame(self._content_frame, bg=_C["bg_content"],
                              height=0)
            anchor.pack(fill="x")
            anchor._section_idx = sec_idx

            for block in section["blocks"]:
                if query:
                    bt = _block_text(block).lower()
                    if query not in bt:
                        continue
                    match_count += 1

                self._render_block(block, sec_idx)

            # Section bottom spacing
            spacer = tk.Frame(self._content_frame, bg=_C["bg_content"],
                              height=24)
            spacer.pack(fill="x")

        # Update search count
        if query:
            self._result_count.configure(
                text=f"{match_count} result{'s' if match_count != 1 else ''}")
        else:
            self._result_count.configure(text="")

    def _render_block(self, block: tuple, section_idx: int):
        kind = block[0]
        pad_x = (32, 24)

        if kind == "heading":
            lbl = tk.Label(self._content_frame, text=block[1],
                           bg=_C["bg_content"], fg=_C["accent"],
                           font=_FONT_HEADING, anchor="w", justify="left")
            lbl.pack(fill="x", padx=pad_x, pady=(16, 4))
            lbl._section_idx = section_idx
            # Underline
            sep = tk.Frame(self._content_frame, bg=_C["accent_dim"], height=1)
            sep.pack(fill="x", padx=pad_x, pady=(0, 8))
            self._rendered_widgets.append(("heading", lbl, block[1]))

        elif kind == "subheading":
            lbl = tk.Label(self._content_frame, text=block[1],
                           bg=_C["bg_content"], fg=_C["accent"],
                           font=_FONT_SUBHEADING, anchor="w", justify="left")
            lbl.pack(fill="x", padx=pad_x, pady=(14, 4))
            self._rendered_widgets.append(("subheading", lbl, block[1]))

        elif kind == "paragraph":
            lbl = tk.Label(self._content_frame, text=block[1],
                           bg=_C["bg_content"], fg=_C["fg"],
                           font=_FONT_BODY, anchor="w", justify="left",
                           wraplength=620)
            lbl.pack(fill="x", padx=pad_x, pady=(2, 4))
            self._rendered_widgets.append(("paragraph", lbl, block[1]))

        elif kind == "bullet":
            row = tk.Frame(self._content_frame, bg=_C["bg_content"])
            row.pack(fill="x", padx=pad_x, pady=(1, 1))
            dot = tk.Label(row, text="  *  ", bg=_C["bg_content"],
                           fg=_C["accent"], font=_FONT_MONO_SM)
            dot.pack(side="left", anchor="n", pady=(2, 0))
            txt = tk.Label(row, text=block[1],
                           bg=_C["bg_content"], fg=_C["fg"],
                           font=_FONT_BODY, anchor="nw", justify="left",
                           wraplength=560)
            txt.pack(side="left", fill="x", expand=True)
            self._rendered_widgets.append(("bullet", txt, block[1]))

        elif kind == "command":
            self._render_command_block(block, pad_x)

        elif kind == "term":
            self._render_term_block(block, pad_x)

        elif kind == "separator":
            sep = tk.Frame(self._content_frame, bg=_C["separator"], height=1)
            sep.pack(fill="x", padx=(40, 32), pady=(12, 12))

    def _render_command_block(self, block: tuple, pad_x: tuple):
        """Render a command documentation entry."""
        syntax = block[1]
        summary = block[2]
        detail = block[3]
        example = block[4] if len(block) > 4 else None

        card = tk.Frame(self._content_frame, bg=_C["bg_card"],
                        highlightthickness=1, highlightbackground=_C["border"])
        card.pack(fill="x", padx=pad_x, pady=(4, 4))

        # Header row: syntax + summary
        header = tk.Frame(card, bg=_C["bg_card"])
        header.pack(fill="x", padx=12, pady=(8, 2))

        syn_lbl = tk.Label(header, text=syntax,
                           bg=_C["bg_card"], fg=_C["accent_glow"],
                           font=_FONT_MONO_BOLD, anchor="w")
        syn_lbl.pack(side="left")

        sum_lbl = tk.Label(header, text=f"  --  {summary}",
                           bg=_C["bg_card"], fg=_C["fg_dim"],
                           font=_FONT_BODY, anchor="w")
        sum_lbl.pack(side="left", fill="x", expand=True)

        # Detail
        det_lbl = tk.Label(card, text=detail,
                           bg=_C["bg_card"], fg=_C["fg"],
                           font=_FONT_BODY, anchor="w", justify="left",
                           wraplength=580)
        det_lbl.pack(fill="x", padx=12, pady=(2, 4))

        # Example
        if example:
            ex_frame = tk.Frame(card, bg="#1a1a35")
            ex_frame.pack(fill="x", padx=12, pady=(2, 8))
            tk.Label(ex_frame, text="Example: ",
                     bg="#1a1a35", fg=_C["fg_muted"],
                     font=_FONT_SMALL, anchor="w").pack(side="left", padx=(8, 0))
            tk.Label(ex_frame, text=example,
                     bg="#1a1a35", fg=_C["green"],
                     font=_FONT_MONO, anchor="w").pack(side="left", padx=(0, 8),
                                                        pady=2)
        else:
            # Small bottom padding if no example
            tk.Frame(card, bg=_C["bg_card"], height=4).pack()

        self._rendered_widgets.append(
            ("command", syn_lbl, f"{syntax} {summary} {detail}"))

    def _render_term_block(self, block: tuple, pad_x: tuple):
        """Render a glossary term entry."""
        term = block[1]
        defn = block[2]

        row = tk.Frame(self._content_frame, bg=_C["bg_content"])
        row.pack(fill="x", padx=pad_x, pady=(4, 4))

        term_lbl = tk.Label(row, text=term,
                            bg=_C["bg_content"], fg=_C["accent"],
                            font=_FONT_BODY_BOLD, anchor="nw", width=20,
                            justify="left")
        term_lbl.pack(side="left", anchor="n")

        defn_lbl = tk.Label(row, text=defn,
                            bg=_C["bg_content"], fg=_C["fg"],
                            font=_FONT_BODY, anchor="nw", justify="left",
                            wraplength=480)
        defn_lbl.pack(side="left", fill="x", expand=True)

        self._rendered_widgets.append(("term", term_lbl, f"{term} {defn}"))

    # ── Search ───────────────────────────────────────────────────

    def _on_search_changed(self, *args):
        """Called when search text changes. Re-render with filter."""
        self._render_all()
        # After rendering, highlight matches
        query = self._search_var.get().strip().lower()
        if query:
            self._highlight_matches(query)

    def _highlight_matches(self, query: str):
        """Highlight matching text in rendered widgets.

        Tkinter Labels don't support partial text coloring, so we
        change the entire label background for matching entries.
        """
        for kind, widget, text in self._rendered_widgets:
            if query in text.lower():
                try:
                    widget.configure(bg=_C["highlight_bg"])
                except tk.TclError:
                    pass

    def _clear_search(self):
        self._search_var.set("")
        self._search_entry.focus_set()

    # ── Canvas / scroll management ───────────────────────────────

    def _on_content_configure(self, event):
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self._canvas.itemconfigure(self._canvas_window, width=event.width)
        # Update wraplength for paragraph labels
        new_wrap = max(300, event.width - 80)
        for kind, widget, text in self._rendered_widgets:
            if kind in ("paragraph", "bullet"):
                try:
                    widget.configure(wraplength=new_wrap)
                except tk.TclError:
                    pass
            elif kind == "command":
                try:
                    widget.configure(wraplength=max(300, new_wrap - 40))
                except Exception:
                    pass

    def _bind_mousewheel(self, event):
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, event):
        self._canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ── Close ────────────────────────────────────────────────────

    def _apply_theme(self, color_map: dict):
        """Hot-swap theme colours on the docs window."""
        try:
            # Reconfigure ttk styles with new colours
            self._configure_styles()
            # Walk the plain-tk / ttk widget tree
            recolor_widget_tree(self._win, color_map)
        except Exception:
            pass

    def _on_close(self):
        if hasattr(self, "_theme_cb"):
            remove_theme_listener(self._theme_cb)
        DocsWindow._instance = None
        try:
            self._win.destroy()
        except tk.TclError:
            pass


# ──────────────────────────────────────────────────────────────────
# Hotkey binding  (F1)
# ──────────────────────────────────────────────────────────────────

def bind_hotkey(root: tk.Misc):
    """Bind F1 to open the docs window.

    Call this once at startup, passing the root Tk or Toplevel window.
    Works from the terminal or dashboard -- any widget that can receive
    key events.

    Usage::

        from forge.ui.docs_window import bind_hotkey
        bind_hotkey(root)
    """
    def _open_docs(event=None):
        DocsWindow.open(root)

    root.bind_all("<F1>", _open_docs)


# ──────────────────────────────────────────────────────────────────
# Standalone test
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    bind_hotkey(root)
    DocsWindow.open(root)
    root.mainloop()
