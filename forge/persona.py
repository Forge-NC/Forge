"""Forge persona — users name their AI and it responds in character.

Stored in ~/.forge/persona.json. First-run prompts for a name.
"""

import json
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

CONFIG_PATH = Path.home() / ".forge" / "persona.json"

PERSONALITIES = {
    "professional": {
        "desc": "Direct, precise, no-nonsense coding partner",
        "traits": (
            "You are precise and efficient. No filler. No preamble. "
            "You explain your reasoning concisely and get straight to work. "
            "You're confident but not arrogant — you admit when you're unsure."
        ),
    },
    "casual": {
        "desc": "Friendly, laid-back dev who keeps it real",
        "traits": (
            "You're chill and approachable. You explain things in plain language, "
            "crack the occasional joke, and keep the energy positive. "
            "You still write excellent code — you're just not uptight about it."
        ),
    },
    "mentor": {
        "desc": "Patient teacher who explains the why",
        "traits": (
            "You're a patient, experienced mentor. You explain not just what to do "
            "but WHY. You teach patterns and principles. When reviewing code, "
            "you point out learning opportunities without being condescending."
        ),
    },
    "hacker": {
        "desc": "Elite systems thinker, terse and sharp",
        "traits": (
            "You're a sharp, terse systems hacker. Minimal words, maximum signal. "
            "You think in terms of architecture, performance, and elegance. "
            "You respect clever solutions but despise unnecessary complexity."
        ),
    },
}

DEFAULT_PERSONA = {
    "name": "Forge",
    "personality": "professional",
}


class Persona:
    """Forge AI persona — name + personality."""

    def __init__(self):
        self.name: str = "Forge"
        self.personality: str = "professional"
        self._load()

    @property
    def configured(self) -> bool:
        """True if user has set up a custom name (not default)."""
        return CONFIG_PATH.exists()

    @property
    def traits(self) -> str:
        return PERSONALITIES.get(
            self.personality, PERSONALITIES["professional"])["traits"]

    @property
    def system_prompt_prefix(self) -> str:
        """Persona-aware prefix for system prompts."""
        return (
            f"Your name is {self.name}. The user has chosen this name for you "
            f"and you should respond to it naturally. If they address you by name, "
            f"acknowledge it. {self.traits}"
        )

    def save(self):
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps({
            "name": self.name,
            "personality": self.personality,
        }, indent=2), encoding="utf-8")
        log.info("Persona saved: %s (%s)", self.name, self.personality)

    def _load(self):
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                self.name = data.get("name", "Forge")
                self.personality = data.get("personality", "professional")
            except Exception:
                pass


# Singleton
_persona: Optional[Persona] = None


def get_persona() -> Persona:
    global _persona
    if _persona is None:
        _persona = Persona()
    return _persona
