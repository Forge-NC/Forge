"""Voice command parser with fuzzy matching.

Detects commands like "launch terminal", "switch to vox",
"hey Jerry, open the terminal", etc. Handles mumbling via
fuzzy string matching.
"""

import difflib
import re
from typing import Optional, Tuple

# Command definitions: (canonical, aliases)
COMMANDS = {
    "launch_terminal": [
        "launch terminal", "open terminal", "start terminal",
        "launch the terminal", "open the terminal", "start the terminal",
        "fire up the terminal", "bring up terminal", "terminal",
        "launch forge", "open forge", "start forge",
    ],
    "switch_ptt": [
        "switch to push to talk", "push to talk", "push to talk mode",
        "switch to ptt", "ptt mode", "use push to talk",
    ],
    "switch_vox": [
        "switch to vox", "vox mode", "voice activated",
        "switch to voice", "auto listen", "use vox",
        "voice activation", "voice activated mode",
    ],
    "voice_off": [
        "voice off", "mute", "stop listening", "disable voice",
        "turn off voice", "shut up",
    ],
    "show_stats": [
        "show stats", "show statistics", "how are we doing",
        "show me the stats", "performance", "show performance",
    ],
    "show_help": [
        "help", "what can you do", "commands", "show commands",
        "what do you do",
    ],
    "plan_mode": [
        "plan mode", "enter plan mode", "use plan mode",
        "plan this", "plan it out", "make a plan",
        "planning mode", "start planning", "continue with planning",
        "plan first", "plan before you start", "let's plan",
    ],
    "plan_off": [
        "plan mode off", "stop planning", "no plan",
        "disable plan mode", "skip the plan", "just do it",
        "no planning", "turn off plan mode",
    ],
    "synapse_check": [
        "synapse check", "run synapse check", "do a synapse check",
        "synapse test", "run synapse test", "thought mode check",
        "mode check", "test the modes", "cycle modes",
        "test all modes", "run diagnostics", "neural check",
        "brain check", "cortex check",
    ],
}

# Flatten for fuzzy matching
_ALL_PHRASES: list[Tuple[str, str]] = []
for cmd, aliases in COMMANDS.items():
    for alias in aliases:
        _ALL_PHRASES.append((alias.lower(), cmd))


def parse_voice_command(text: str, persona_name: str = "Forge"
                        ) -> Tuple[Optional[str], str]:
    """Parse voice input for commands.

    Returns (command_name, remaining_text).
    command_name is None if no command detected — treat as chat.
    remaining_text has the persona name stripped if present.
    """
    if not text or not text.strip():
        return None, ""

    clean = text.strip()

    # Strip persona name prefix: "Hey Jerry, ..." → "..."
    name_lower = persona_name.lower()
    text_lower = clean.lower()

    # Remove greeting patterns with name
    for prefix in [
        f"hey {name_lower}",
        f"hi {name_lower}",
        f"yo {name_lower}",
        f"ok {name_lower}",
        f"okay {name_lower}",
        f"alright {name_lower}",
        f"{name_lower}",
    ]:
        if text_lower.startswith(prefix):
            rest = clean[len(prefix):].lstrip(" ,.")
            if rest:
                clean = rest
                text_lower = clean.lower()
            break

    # Try exact match first
    for alias, cmd in _ALL_PHRASES:
        if text_lower == alias or text_lower.rstrip(".!?") == alias:
            return cmd, ""

    # Try startswith match (command + extra words)
    for alias, cmd in sorted(_ALL_PHRASES, key=lambda x: -len(x[0])):
        if text_lower.startswith(alias):
            rest = clean[len(alias):].strip(" ,.")
            return cmd, rest

    # Try contains match for short commands embedded in longer speech
    for alias, cmd in sorted(_ALL_PHRASES, key=lambda x: -len(x[0])):
        if len(alias) > 8 and alias in text_lower:
            return cmd, ""

    # Fuzzy match — catch mumbled commands
    matches = difflib.get_close_matches(
        text_lower.rstrip(".!?"),
        [a for a, _ in _ALL_PHRASES],
        n=1, cutoff=0.6)
    if matches:
        for alias, cmd in _ALL_PHRASES:
            if alias == matches[0]:
                return cmd, ""

    # No command found — it's a chat message
    return None, clean
