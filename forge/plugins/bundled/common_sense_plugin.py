"""CommonSenseGuard — persistent behavioral rulebook for AI models.

A user-extensible rule system that ships with smart defaults and gets
injected into EVERY prompt, EVERY time, no exceptions, no forgetting.

Default rules:     forge/plugins/bundled/common_sense_defaults.yaml
User overrides:    ~/.forge/common_sense_rules.yaml

The rulebook covers:
  - Execution discipline (read before edit, act don't explain, complete all tasks)
  - Interpretation discipline (literal verb meanings, negative constraints)
  - Verification discipline (read source before describing, verify fixes)
  - Error recovery discipline (don't retry failed approaches, accept corrections)
  - 27 verb semantic definitions (cache ≠ optimize, fix ≠ delete, etc.)
  - Correction mode rules (injected when user is correcting a mistake)

NOT a duplicate of any existing Forge system:
  - AMI learns from failures AFTER they happen.  We prevent them BEFORE.
  - Quality scores responses AFTER generation.   We shape them BEFORE.
  - Crucible handles security threats.           We handle semantics.
  - Plan verifier runs tests after steps.        We enforce intent before steps.
  - None of those systems inject a persistent behavioral rulebook into prompts.

Users extend the rulebook by editing ~/.forge/common_sense_rules.yaml.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from forge.plugins.base import ForgePlugin

if TYPE_CHECKING:
    from forge.event_bus import ForgeEvent

log = logging.getLogger(__name__)

# Patterns that indicate the user is correcting a previous AI mistake
_CORRECTION_SIGNALS = re.compile(
    r'\b(I said|I meant|I asked for|that\'s not what|no,?\s+I|'
    r'I didn\'t say|not what I|I specifically|I already told|'
    r'why did you|why the fuck|what the fuck|did I say|'
    r'I don\'t want|that\'s wrong|you already|you just|'
    r'I told you|for the .* time|again\b.*wrong|still wrong|'
    r'still broken|still not|still doesn\'t|are you)\b',
    re.IGNORECASE,
)


def _load_yaml_simple(path: Path) -> dict:
    """Load a YAML file using PyYAML if available, else basic parser."""
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
        return yaml.safe_load(text) or {}
    except ImportError:
        pass
    # Minimal fallback parser for flat YAML lists — handles rules: [- "..."]
    # and verbs: {key: "..."} used in the defaults file.
    return _parse_yaml_fallback(text)


def _parse_yaml_fallback(text: str) -> dict:
    """Bare-minimum YAML-subset parser for the rules file format.

    Handles:
      rules:
        - "string"
        - >
          multiline string
      verbs:
        key: "string"
        key: >
          multiline string
      on_correction:
        - "string"
      disabled:
        - "string"
    """
    result: dict = {}
    current_key: str = ""
    current_list: list | None = None
    current_dict: dict | None = None
    current_item: list[str] = []
    indent_level = 0

    def _flush_item():
        nonlocal current_item
        if current_item:
            val = " ".join(current_item).strip()
            if val and current_list is not None:
                current_list.append(val)
            elif val and current_dict is not None and _dict_key:
                current_dict[_dict_key] = val
            current_item = []

    _dict_key = ""

    for line in text.split("\n"):
        stripped = line.strip()

        # Skip comments and blank lines
        if not stripped or stripped.startswith("#"):
            continue

        # Top-level key
        if not line[0].isspace() and stripped.endswith(":"):
            _flush_item()
            current_key = stripped[:-1].strip()
            if current_key in ("rules", "on_correction", "disabled"):
                current_list = []
                current_dict = None
                result[current_key] = current_list
            elif current_key == "verbs":
                current_dict = {}
                current_list = None
                result[current_key] = current_dict
            continue

        # List item
        if stripped.startswith("- "):
            _flush_item()
            val = stripped[2:].strip().strip('"').strip("'")
            if val == ">":
                current_item = []
            elif val:
                if current_list is not None:
                    current_list.append(val)
            continue

        # Dict key: value (under verbs:)
        if current_dict is not None and ":" in stripped and not stripped.startswith("-"):
            _flush_item()
            key, _, val = stripped.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val == ">":
                _dict_key = key
                current_item = []
            elif val:
                current_dict[key] = val
                _dict_key = ""
            else:
                _dict_key = key
                current_item = []
            continue

        # Continuation of multiline > value
        if stripped and current_item is not None:
            current_item.append(stripped)

    _flush_item()
    return result


class CommonSenseGuard(ForgePlugin):
    """Persistent behavioral rulebook — injected into every prompt.

    Loads rules from the bundled defaults file and optional user overrides.
    Injects the rules as a behavioral contract that the AI model sees
    with every single message, ensuring consistent behavior enforcement.
    """

    name = "CommonSenseGuard"
    version = "3.0.0"
    description = (
        "Persistent behavioral rulebook — enforces execution discipline, "
        "verb semantics, and scope control on every prompt"
    )
    author = "Forge"

    event_patterns = ["file.*"]

    def on_load(self, forge_engine: Any) -> None:
        self._engine = forge_engine
        self._files_read: set[str] = set()

        # Load rulebook
        bundled_path = Path(__file__).parent / "common_sense_defaults.yaml"
        config_dir = Path(getattr(forge_engine, "config_dir",
                                  Path.home() / ".forge"))
        user_path = config_dir / "common_sense_rules.yaml"

        defaults = _load_yaml_simple(bundled_path)
        user = _load_yaml_simple(user_path)

        # Merge: user rules supplement defaults, disabled removes
        disabled = set(user.get("disabled", []))
        self._rules: list[str] = [
            r for r in defaults.get("rules", []) if r not in disabled
        ] + user.get("rules", [])

        # Merge verbs: user overrides defaults
        self._verbs: dict[str, str] = {**defaults.get("verbs", {}),
                                        **user.get("verbs", {})}

        # Correction-mode rules
        self._correction_rules: list[str] = (
            defaults.get("on_correction", []) +
            user.get("on_correction", [])
        )

        # Build the static rules block (injected every time)
        self._rules_block = self._build_rules_block()

        log.info(
            "CommonSenseGuard loaded: %d rules, %d verbs, %d correction rules",
            len(self._rules), len(self._verbs), len(self._correction_rules),
        )

    def _build_rules_block(self) -> str:
        """Build the static portion of the rulebook injection."""
        lines = ["[Forge CommonSenseGuard — Behavioral Rulebook]"]
        for i, rule in enumerate(self._rules, 1):
            # Compact multiline rules into single lines
            clean = " ".join(rule.split())
            lines.append(f"  {i}. {clean}")
        lines.append("[End Rulebook]")
        return "\n".join(lines)

    # ── Event tracking ────────────────────────────────────────────────────

    def on_event(self, event: "ForgeEvent") -> None:
        if event.event_type == "file.read":
            path = event.data.get("path", "")
            if path:
                self._files_read.add(_norm(path))

    # ── PRIMARY: Rulebook injection on every prompt ───────────────────────

    def on_user_input(self, text: str) -> str:
        """Inject the behavioral rulebook into every user message.

        This is the entire mechanism. No detection heuristics, no threshold
        tuning, no AI decision-making about when to apply rules. The rules
        are ALWAYS there. The model sees them with every single message.

        Additionally:
        - If the user's message contains known verbs, inject their semantic
          definitions so the model knows exactly what each verb means.
        - If the user is correcting a mistake, inject correction-mode rules.
        """
        parts: list[str] = [text]
        injection: list[str] = []

        # 1. Static rules — always injected
        injection.append(self._rules_block)

        # 2. Verb semantics — injected when those verbs appear
        text_lower = text.lower()
        matched_verbs: list[tuple[str, str]] = []
        for verb, definition in self._verbs.items():
            # Match whole word only
            if re.search(rf'\b{re.escape(verb)}\b', text_lower):
                clean_def = " ".join(definition.split())
                matched_verbs.append((verb, clean_def))

        if matched_verbs:
            injection.append("[Verb Definitions]")
            for verb, defn in matched_verbs:
                injection.append(f'  "{verb}": {defn}')
            injection.append("[End Verb Definitions]")

        # 3. Correction mode — extra rules when user is correcting
        if _CORRECTION_SIGNALS.search(text):
            injection.append("[Correction Mode — ACTIVE]")
            for rule in self._correction_rules:
                clean = " ".join(rule.split())
                injection.append(f"  ! {clean}")
            injection.append("[End Correction Mode]")

        # Append all injections
        if injection:
            parts.append("\n" + "\n".join(injection))

        return "\n".join(parts)

    # ── SECONDARY: Read-before-write enforcement ──────────────────────────

    def on_tool_call(self, tool_name: str, args: dict) -> dict:
        """Enforce read-before-write at the tool boundary.

        This is mechanical enforcement, not a rule — the plugin literally
        tracks which files have been read and flags blind edits.
        """
        if tool_name in ("edit_file", "patch_file", "write_file"):
            path = args.get("path", "") or args.get("file_path", "")
            if path:
                norm = _norm(path)
                is_create = args.get("create", False)
                if norm not in self._files_read and not is_create:
                    self._emit_warning(
                        "edit_without_read",
                        f"Editing '{_short(path)}' without reading it first.",
                    )
        return args

    # ── Helpers ───────────────────────────────────────────────────────────

    def _emit_warning(self, category: str, message: str) -> None:
        if not self._engine:
            return
        bus = getattr(self._engine, "event_bus", None)
        if not bus:
            return
        try:
            bus.emit("common_sense.warning", {
                "category": category,
                "message": message,
                "severity": "warning",
                "turn": 0,
                "files": [],
                "tool": "",
            })
        except Exception:
            log.debug("Failed to emit common_sense.warning", exc_info=True)

    def get_status(self) -> dict:
        return {
            "rules_loaded": len(self._rules),
            "verbs_loaded": len(self._verbs),
            "correction_rules": len(self._correction_rules),
            "files_tracked": len(self._files_read),
        }


def _norm(path: str) -> str:
    return path.replace("\\", "/").lower().rstrip("/")


def _short(path: str) -> str:
    parts = path.replace("\\", "/").rsplit("/", 2)
    return "/".join(parts[-2:]) if len(parts) > 2 else path
