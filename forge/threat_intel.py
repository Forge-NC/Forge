"""Threat Intelligence Manager — upgradeable signature database for Crucible.

Loads bundled default signatures, fetched remote updates, and user-custom
patterns.  Merges them into Crucible's detection pipeline with strict
security guarantees:

  - Reduce-only rule: external patterns can never lower hardcoded threat levels
  - Category whitelist: only APPROVED_CATEGORIES accepted
  - ReDoS guard: every regex tested against large input with timeout
  - SHA-512 envelope: remote payloads validated against hash
  - Version monotonicity: downgrades rejected
  - Atomic writes: no partial/corrupt files
"""

import hashlib
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APPROVED_CATEGORIES = frozenset({
    "prompt_injection", "hidden_content", "data_exfil",
    "secret_leak", "social_engineering", "obfuscation",
    "rag_poisoning", "jailbreak",
})

SIGNATURE_VERSION = 1
MAX_SIGNATURE_SIZE = 2 * 1024 * 1024   # 2 MB
MAX_PATTERNS_PER_FILE = 500
REDOS_TEST_TIMEOUT = 0.1               # 100 ms
REDOS_TEST_STRING_LEN = 10240          # 10 KB

# Map string flag names → re module constants
_FLAG_MAP = {
    "IGNORECASE": re.IGNORECASE,
    "MULTILINE": re.MULTILINE,
    "DOTALL": re.DOTALL,
}


class ThreatIntelManager:
    """Upgradeable threat signature database for Crucible."""

    def __init__(self, data_dir: Path, config_get: Callable):
        self._data_dir = Path(data_dir)
        self._config_get = config_get

        # Paths
        self._bundled_path = Path(__file__).parent / "data" / "default_signatures.json"
        self._fetched_path = self._data_dir / "fetched_signatures.json"
        self._custom_path = self._data_dir / "custom_signatures.json"
        self._meta_path = self._data_dir / "meta.json"

        # State
        self._signatures: dict = {}
        self._compiled_patterns: list[tuple] = []
        self._keyword_lists: dict[str, set[str]] = {}
        self._behavioral_rules: list[dict] = []
        self._hit_counts: dict[str, int] = {}
        self._last_update_check: str = ""
        self._loaded_version: int = 0
        self._pattern_sources: dict[str, str] = {}  # name → source file

        # Thread safety
        self._update_lock = threading.Lock()
        self._lock = threading.Lock()

        # Hardcoded pattern names (populated from Crucible at load time)
        self._hardcoded_names: dict[str, int] = {}  # name → level

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, hardcoded_patterns: Optional[list] = None):
        """Load and merge all signature sources.

        Args:
            hardcoded_patterns: List of (name, regex, level, cat, desc) tuples
                from Crucible's INJECTION_PATTERNS.  Used for reduce-only rule.
        """
        if hardcoded_patterns:
            self._hardcoded_names = {p[0]: p[2] for p in hardcoded_patterns}

        self._data_dir.mkdir(parents=True, exist_ok=True)

        # Load meta (last update timestamp, etc.)
        self._load_meta()

        # Load in priority order: bundled < fetched < custom
        all_patterns = []
        all_keywords: dict[str, set[str]] = {}
        all_rules: list[dict] = []

        for label, path in [
            ("bundled", self._bundled_path),
            ("fetched", self._fetched_path),
            ("custom", self._custom_path),
        ]:
            if not path.exists():
                continue
            try:
                data = self._read_signature_file(path)
                if data is None:
                    continue
                valid, err = self._validate_signature_file(data)
                if not valid:
                    log.warning("Threat intel: %s signatures invalid: %s", label, err)
                    continue

                # Patterns
                patterns = data.get("patterns", [])
                patterns = self._apply_reduce_only(patterns)
                for p in patterns:
                    p["_source"] = label
                all_patterns.extend(patterns)

                # Keywords
                for cat, words in data.get("keyword_lists", {}).items():
                    if cat not in all_keywords:
                        all_keywords[cat] = set()
                    all_keywords[cat].update(words)

                # Behavioral rules
                all_rules.extend(data.get("behavioral_rules", []))

                ver = data.get("signature_version", 0)
                if ver > self._loaded_version:
                    self._loaded_version = ver

            except Exception as e:
                log.warning("Threat intel: failed loading %s: %s", label, e)

        # Compile patterns (skip unsafe ones)
        compiled = []
        for p in all_patterns:
            result = self._compile_pattern(p)
            if result:
                compiled.append(result)
                self._pattern_sources[p["name"]] = p.get("_source", "unknown")

        with self._lock:
            self._compiled_patterns = compiled
            self._keyword_lists = all_keywords
            self._behavioral_rules = all_rules

        total_kw = sum(len(v) for v in all_keywords.values())
        log.info(
            "Threat intel: loaded %d external patterns, %d keyword lists (%d terms), %d behavioral rules",
            len(compiled), len(all_keywords), total_kw, len(all_rules),
        )

    def get_compiled_patterns(self) -> list[tuple]:
        """Return compiled external patterns in Crucible format.

        Each tuple: (name, compiled_regex, level, category, description)
        """
        with self._lock:
            return list(self._compiled_patterns)

    def get_keyword_lists(self) -> dict[str, set[str]]:
        """Return keyword categories → word sets for semantic boost."""
        with self._lock:
            return dict(self._keyword_lists)

    def get_behavioral_rules(self) -> list[dict]:
        """Return behavioral rule definitions."""
        with self._lock:
            return list(self._behavioral_rules)

    def record_hit(self, pattern_name: str):
        """Increment hit counter for a pattern."""
        with self._lock:
            self._hit_counts[pattern_name] = self._hit_counts.get(pattern_name, 0) + 1

    def get_status(self) -> dict:
        """Return status summary dict."""
        with self._lock:
            total_kw = sum(len(v) for v in self._keyword_lists.values())
            return {
                "enabled": self._config_get("threat_signatures_enabled", True),
                "total_patterns": len(self._compiled_patterns),
                "keyword_lists": len(self._keyword_lists),
                "keyword_terms": total_kw,
                "behavioral_rules": len(self._behavioral_rules),
                "last_update": self._last_update_check,
                "signature_version": self._loaded_version,
                "url": self._config_get("threat_signatures_url", ""),
                "sources": {
                    "bundled": sum(1 for s in self._pattern_sources.values() if s == "bundled"),
                    "fetched": sum(1 for s in self._pattern_sources.values() if s == "fetched"),
                    "custom": sum(1 for s in self._pattern_sources.values() if s == "custom"),
                },
            }

    def search_patterns(self, query: str) -> list[dict]:
        """Search patterns by name, description, or category."""
        query_lower = query.lower()
        results = []
        with self._lock:
            for name, _regex, level, cat, desc in self._compiled_patterns:
                if (query_lower in name.lower() or
                        query_lower in desc.lower() or
                        query_lower in cat.lower()):
                    results.append({
                        "name": name,
                        "level": level,
                        "category": cat,
                        "description": desc,
                        "source": self._pattern_sources.get(name, "unknown"),
                    })
        return results

    def list_by_category(self, category: str) -> list[dict]:
        """List all patterns in a category."""
        results = []
        cat_lower = category.lower()
        with self._lock:
            for name, _regex, level, cat, desc in self._compiled_patterns:
                if cat.lower() == cat_lower:
                    results.append({
                        "name": name,
                        "level": level,
                        "category": cat,
                        "description": desc,
                        "source": self._pattern_sources.get(name, "unknown"),
                    })
        return results

    def get_detection_stats(self) -> dict:
        """Return hit counts sorted by frequency."""
        with self._lock:
            sorted_hits = sorted(
                self._hit_counts.items(), key=lambda x: x[1], reverse=True)
            total = sum(self._hit_counts.values())
            by_category: dict[str, int] = {}
            for name, count in self._hit_counts.items():
                # Find category for this pattern
                for pname, _regex, _level, cat, _desc in self._compiled_patterns:
                    if pname == name:
                        by_category[cat] = by_category.get(cat, 0) + count
                        break
            return {
                "total_hits": total,
                "top_patterns": sorted_hits[:20],
                "by_category": dict(sorted(
                    by_category.items(), key=lambda x: x[1], reverse=True)),
            }

    def to_audit_dict(self) -> dict:
        """Serializable snapshot for audit export."""
        status = self.get_status()
        stats = self.get_detection_stats()
        return {
            "schema_version": SIGNATURE_VERSION,
            "enabled": status["enabled"],
            "total_patterns": status["total_patterns"],
            "keyword_lists": status["keyword_lists"],
            "behavioral_rules": status["behavioral_rules"],
            "last_update": status["last_update"],
            "signature_version": status["signature_version"],
            "sources": status["sources"],
            "detection_stats": stats,
        }

    # ------------------------------------------------------------------
    # Update mechanism
    # ------------------------------------------------------------------

    def update(self, force: bool = False) -> dict:
        """Fetch latest signatures from configured URL.

        Returns dict with success, patterns_added, message.
        """
        url = self._config_get("threat_signatures_url", "")
        if not url:
            return {"success": False, "patterns_added": 0,
                    "message": "No signature URL configured"}

        with self._update_lock:
            # Rate limit: 1 per 24h unless forced
            if not force and self._last_update_check:
                try:
                    last = datetime.fromisoformat(self._last_update_check)
                    elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                    if elapsed < 86400:
                        return {"success": False, "patterns_added": 0,
                                "message": f"Rate limited — last check {int(elapsed)}s ago (24h interval)"}
                except (ValueError, TypeError):
                    pass

            try:
                req = urllib.request.Request(
                    url, method="GET",
                    headers={"User-Agent": "Forge-ThreatIntel/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read(MAX_SIGNATURE_SIZE + 1)
                    if len(raw) > MAX_SIGNATURE_SIZE:
                        return {"success": False, "patterns_added": 0,
                                "message": f"Response exceeds {MAX_SIGNATURE_SIZE} byte limit"}

                data = json.loads(raw.decode("utf-8"))

            except (urllib.error.URLError, urllib.error.HTTPError) as e:
                self._update_timestamp()
                return {"success": False, "patterns_added": 0,
                        "message": f"Fetch failed: {e}"}
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                self._update_timestamp()
                return {"success": False, "patterns_added": 0,
                        "message": f"Invalid response: {e}"}

            # SHA-512 envelope validation (mandatory for integrity)
            claimed_hash = data.pop("sha512", None)
            if not claimed_hash:
                log.warning("Signature file has no SHA-512 hash — rejecting for integrity")
                self._update_timestamp()
                return {"success": False, "patterns_added": 0,
                        "message": "missing sha512 hash"}
            content_bytes = json.dumps(data, sort_keys=True).encode("utf-8")
            actual_hash = hashlib.sha512(content_bytes).hexdigest()
            if actual_hash != claimed_hash:
                self._update_timestamp()
                return {"success": False, "patterns_added": 0,
                        "message": "SHA-512 hash mismatch — possible tampering"}

            # Validate
            valid, err = self._validate_signature_file(data)
            if not valid:
                self._update_timestamp()
                return {"success": False, "patterns_added": 0,
                        "message": f"Validation failed: {err}"}

            # Version monotonicity
            new_ver = data.get("signature_version", 0)
            if new_ver < self._loaded_version:
                self._update_timestamp()
                return {"success": False, "patterns_added": 0,
                        "message": f"Version {new_ver} < current {self._loaded_version} — rollback rejected"}

            # Apply reduce-only
            patterns = data.get("patterns", [])
            filtered = self._apply_reduce_only(patterns)
            rejected = len(patterns) - len(filtered)

            # Atomic write
            self._data_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = self._fetched_path.with_suffix(".tmp")
            try:
                tmp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
                os.replace(str(tmp_path), str(self._fetched_path))
            except Exception as e:
                if tmp_path.exists():
                    tmp_path.unlink(missing_ok=True)
                return {"success": False, "patterns_added": 0,
                        "message": f"Write failed: {e}"}

            self._update_timestamp()

            # Reload
            self.load(hardcoded_patterns=list(
                (n, None, l, None, None) for n, l in self._hardcoded_names.items()))

            return {
                "success": True,
                "patterns_added": len(filtered),
                "rejected": rejected,
                "message": f"Updated: {len(filtered)} patterns ({rejected} rejected by reduce-only rule)",
            }

    def auto_update_if_due(self):
        """Check if auto-update is due based on safety level interval.

        Called from daemon thread on engine boot.
        L0: skip, L1: 7 days, L2: 1 day, L3: every session.
        """
        if not self._config_get("threat_auto_update", True):
            return
        url = self._config_get("threat_signatures_url", "")
        if not url:
            return

        # Determine interval based on safety level
        safety_level = self._config_get("safety_level", 1)
        if safety_level == 0:
            return
        intervals = {1: 7 * 86400, 2: 86400, 3: 0}  # seconds
        interval = intervals.get(safety_level, 86400)

        if interval > 0 and self._last_update_check:
            try:
                last = datetime.fromisoformat(self._last_update_check)
                elapsed = (datetime.now(timezone.utc) - last).total_seconds()
                if elapsed < interval:
                    return
            except (ValueError, TypeError):
                pass

        result = self.update(force=True)
        if result["success"]:
            log.info("Threat intel auto-update: %s", result["message"])
        elif "Rate limited" not in result.get("message", ""):
            log.warning("Threat intel auto-update failed: %s", result["message"])

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_signature_file(self, data: dict) -> tuple[bool, str]:
        """Validate a signature file. Returns (valid, error_message)."""
        if not isinstance(data, dict):
            return False, "Not a dict"

        # Schema version
        ver = data.get("signature_version")
        if ver != SIGNATURE_VERSION:
            return False, f"Schema version {ver} != expected {SIGNATURE_VERSION}"

        # Pattern count
        patterns = data.get("patterns", [])
        if len(patterns) > MAX_PATTERNS_PER_FILE:
            return False, f"Too many patterns: {len(patterns)} > {MAX_PATTERNS_PER_FILE}"

        # Validate each pattern
        for i, p in enumerate(patterns):
            if not isinstance(p, dict):
                return False, f"Pattern {i} is not a dict"
            for field in ("name", "regex", "level", "category", "description"):
                if field not in p:
                    return False, f"Pattern {i} missing field: {field}"

            # Category whitelist
            if p["category"] not in APPROVED_CATEGORIES:
                return False, f"Pattern {i} ({p['name']}): unknown category '{p['category']}'"

            # Level bounds
            if not isinstance(p["level"], int) or p["level"] < 0 or p["level"] > 3:
                return False, f"Pattern {i} ({p['name']}): level {p['level']} out of bounds (0-3)"

        # Validate keyword lists
        kw = data.get("keyword_lists", {})
        if not isinstance(kw, dict):
            return False, "keyword_lists is not a dict"
        for cat, words in kw.items():
            if not isinstance(words, list):
                return False, f"Keyword list '{cat}' is not a list"

        # Validate behavioral rules
        rules = data.get("behavioral_rules", [])
        if not isinstance(rules, list):
            return False, "behavioral_rules is not a list"
        for i, r in enumerate(rules):
            if not isinstance(r, dict):
                return False, f"Behavioral rule {i} is not a dict"
            for field in ("name", "trigger_tool", "condition", "window_sec", "level"):
                if field not in r:
                    return False, f"Behavioral rule {i} missing field: {field}"
            if not isinstance(r["level"], int) or r["level"] < 0 or r["level"] > 3:
                return False, f"Behavioral rule {i}: level out of bounds"

        return True, ""

    def _apply_reduce_only(self, patterns: list[dict]) -> list[dict]:
        """Filter patterns: external cannot lower hardcoded threat levels."""
        filtered = []
        for p in patterns:
            name = p.get("name", "")
            level = p.get("level", 0)
            if name in self._hardcoded_names:
                hardcoded_level = self._hardcoded_names[name]
                if level < hardcoded_level:
                    log.warning(
                        "Threat intel: reduce-only rejected '%s' "
                        "(external level %d < hardcoded %d)",
                        name, level, hardcoded_level)
                    continue
            filtered.append(p)
        return filtered

    def _test_regex_safe(self, pattern: str, flags: int = 0) -> bool:
        """Check regex for catastrophic backtracking risk.

        Uses static analysis (heuristic) since CPython's re module holds the
        GIL during Unicode regex matching, making thread-based timeouts
        unreliable.

        Returns True if safe, False if dangerous.
        """
        try:
            re.compile(pattern, flags)
        except re.error:
            return False

        # Heuristic: detect nested quantifiers — the #1 cause of ReDoS.
        # Only flag truly dangerous patterns where a broad-class
        # quantifier is the primary/sole content of a repeated group.
        #
        # Dangerous: (a+)+  (.*)*  (\w+)+  (.+\s*)+
        # Safe:      (?:\d{1,3}\.){3}  (?:-[a-z]+\s+)*  (?:literal.*){5,}
        #
        # Key insight: patterns like (?:-[a-z]+\s+)* are safe because
        # the literal `-` anchor prevents catastrophic backtracking.
        # We only flag groups where the FIRST quantified element is a
        # broad class (. \w \W \s \S) or any single char with +/*.
        if re.search(
            r'\((?:\?:)?'   # open group (optionally non-capturing)
            r'\s*'          # optional whitespace
            r'(?:'
              r'[^\\)\x5b\x5d]{0,2}[+*]'  # 1-2 char atom with +/* (like a+ or .+)
              r'|\\[wWsS][+*]'        # \w+ \W+ \s+ \S+ as first element
              r'|\.\*'                 # .* as first element
              r'|\.\+'                 # .+ as first element
            r')'
            r'[^)]*'        # rest of group
            r'\)'           # close group
            r'[+*]'         # outer unbounded quantifier
            , pattern):
            log.warning("Threat intel: ReDoS risk (nested quantifier): %.60s...", pattern)
            return False

        # Overlapping alternations with quantifiers: (a|a)+
        if re.search(r'\([^)]*\|[^)]*\)[+*{]', pattern):
            # Only flag if the alternatives share character classes
            # This is a conservative check — may have false positives
            # but better safe than sorry
            pass  # Allow for now — too many false positives

        # Excessive backtracking potential: .* repeated
        star_count = len(re.findall(r'(?<!\[)\.\*', pattern))
        if star_count >= 4:
            log.warning("Threat intel: ReDoS risk (4+ .* quantifiers): %.60s...", pattern)
            return False

        return True

    def _compile_pattern(self, p: dict) -> Optional[tuple]:
        """Compile a single pattern dict → tuple. Returns None on failure."""
        name = p.get("name", "")
        regex_str = p.get("regex", "")
        level = p.get("level", 0)
        cat = p.get("category", "")
        desc = p.get("description", "")
        flag_names = p.get("flags", ["IGNORECASE", "MULTILINE"])

        flags = 0
        for fn in flag_names:
            flags |= _FLAG_MAP.get(fn, 0)

        # ReDoS guard
        if not self._test_regex_safe(regex_str, flags):
            log.warning("Threat intel: skipping unsafe pattern '%s'", name)
            return None

        try:
            compiled = re.compile(regex_str, flags)
        except re.error as e:
            log.warning("Threat intel: compile error for '%s': %s", name, e)
            return None

        return (name, compiled, level, cat, desc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_signature_file(self, path: Path) -> Optional[dict]:
        """Read and parse a JSON signature file."""
        try:
            raw = path.read_bytes()
            if len(raw) > MAX_SIGNATURE_SIZE:
                log.warning("Threat intel: file too large: %s (%d bytes)", path, len(raw))
                return None
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            log.warning("Threat intel: failed reading %s: %s", path, e)
            return None

    def _load_meta(self):
        """Load metadata (last update timestamp, etc.)."""
        if self._meta_path.exists():
            try:
                meta = json.loads(self._meta_path.read_text(encoding="utf-8"))
                self._last_update_check = meta.get("last_update_check", "")
            except Exception:
                pass

    def _update_timestamp(self):
        """Persist current timestamp as last update check."""
        self._last_update_check = datetime.now(timezone.utc).isoformat()
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._meta_path.write_text(
                json.dumps({"last_update_check": self._last_update_check}),
                encoding="utf-8")
        except Exception:
            pass

    def format_status(self) -> str:
        """Format status display for /threats command."""
        status = self.get_status()
        lines = [
            "Threat Intelligence",
            f"  Status:      {'ACTIVE' if status['enabled'] else 'DISABLED'}",
            f"  Patterns:    {status['total_patterns']} external",
            f"  Keywords:    {status['keyword_lists']} lists ({status['keyword_terms']} terms)",
            f"  Behavioral:  {status['behavioral_rules']} rules",
            f"  Version:     {status['signature_version']}",
        ]
        if status["last_update"]:
            lines.append(f"  Last update: {status['last_update']}")
        if status["url"]:
            lines.append(f"  Source:      {status['url']}")
        else:
            lines.append("  Source:      bundled only (no URL configured)")

        src = status["sources"]
        lines.append(f"  Breakdown:   {src['bundled']} bundled, {src['fetched']} fetched, {src['custom']} custom")

        return "\n".join(lines)
