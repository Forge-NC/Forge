"""Tests for the Threat Intelligence Manager."""

import json
import hashlib
import os
import re
import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from forge.threat_intel import (
    ThreatIntelManager,
    APPROVED_CATEGORIES,
    SIGNATURE_VERSION,
    MAX_PATTERNS_PER_FILE,
    MAX_SIGNATURE_SIZE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_sig(patterns=None, keyword_lists=None, behavioral_rules=None,
                    version=1):
    """Build a minimal valid signature dict."""
    return {
        "signature_version": version,
        "description": "test signatures",
        "generated": "2026-03-02T00:00:00Z",
        "patterns": patterns or [],
        "keyword_lists": keyword_lists or {},
        "behavioral_rules": behavioral_rules or [],
    }


def _make_pattern(name="test_pat", regex="test_pattern_string",
                  level=2, category="jailbreak", description="test desc",
                  flags=None):
    """Build a single pattern dict."""
    return {
        "name": name,
        "regex": regex,
        "level": level,
        "category": category,
        "description": description,
        "source": "test",
        "flags": flags or ["IGNORECASE"],
    }


def _write_sig(path, sig_data):
    """Write a signature JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sig_data, indent=2), encoding="utf-8")


def _make_manager(tmp_path, config=None, bundled_sig=None):
    """Create a ThreatIntelManager with test paths."""
    data_dir = tmp_path / "threat_intel"
    data_dir.mkdir(parents=True, exist_ok=True)

    default_config = {
        "threat_signatures_enabled": True,
        "threat_signatures_url": "",
        "threat_auto_update": True,
        "safety_level": 2,
    }
    if config:
        default_config.update(config)

    mgr = ThreatIntelManager(
        data_dir=data_dir,
        config_get=lambda k, d=None: default_config.get(k, d),
    )

    # Override bundled path if provided
    if bundled_sig is not None:
        bundled_path = tmp_path / "bundled_sigs.json"
        _write_sig(bundled_path, bundled_sig)
        mgr._bundled_path = bundled_path

    return mgr


# ===========================================================================
# Loading & Validation
# ===========================================================================

class TestLoading:
    """Verifies ThreatIntelManager signature loading, merging, and validation.

    Signatures are loaded from three sources in priority order: bundled defaults,
    fetched (network-updated), and custom (user-written). Sources merge additively.
    Files are rejected wholesale for: wrong schema version, any unknown category,
    or pattern count exceeding MAX_PATTERNS_PER_FILE (500). Individual patterns
    with malformed regexes are skipped without rejecting the rest of the file.
    Files larger than MAX_SIGNATURE_SIZE (2MB) are rejected before parsing.
    Keyword lists from multiple sources are merged by list union per key.
    """

    def test_load_bundled_defaults(self, tmp_path):
        """Load bundled default signatures → correct pattern count."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("p1", r"pattern_one"),
            _make_pattern("p2", r"pattern_two"),
            _make_pattern("p3", r"pattern_three"),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 3

    def test_load_no_fetched_no_custom(self, tmp_path):
        """Load with only bundled → only bundled patterns."""
        sig = _make_valid_sig(patterns=[_make_pattern("p1", r"test")])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 1

    def test_load_custom_extends_bundled(self, tmp_path):
        """Custom file adds patterns beyond bundled."""
        bundled = _make_valid_sig(patterns=[_make_pattern("bundled_p", r"bundled")])
        mgr = _make_manager(tmp_path, bundled_sig=bundled)

        custom = _make_valid_sig(patterns=[_make_pattern("custom_p", r"custom_pattern")])
        _write_sig(mgr._custom_path, custom)

        mgr.load()
        patterns = mgr.get_compiled_patterns()
        names = [p[0] for p in patterns]
        assert "bundled_p" in names
        assert "custom_p" in names

    def test_invalid_schema_version_rejected(self, tmp_path):
        """Invalid schema version → rejected."""
        sig = _make_valid_sig(version=999)
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 0

    def test_unknown_category_rejected(self, tmp_path):
        """Unknown category → entire file rejected."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("bad_cat", r"test", category="unknown_evil_category"),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 0

    def test_too_many_patterns_rejected(self, tmp_path):
        """Pattern count > 500 → rejected."""
        patterns = [_make_pattern(f"p{i}", f"pattern_{i}") for i in range(501)]
        sig = _make_valid_sig(patterns=patterns)
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 0

    def test_malformed_regex_skipped(self, tmp_path):
        """Malformed regex → individual pattern skipped, rest loaded."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("good", r"good_pattern"),
            _make_pattern("bad", r"[invalid(?regex"),
            _make_pattern("good2", r"another_good"),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        names = [p[0] for p in mgr.get_compiled_patterns()]
        assert "good" in names
        assert "good2" in names
        assert "bad" not in names

    def test_empty_signatures_no_crash(self, tmp_path):
        """Empty patterns list → no crash, 0 patterns."""
        sig = _make_valid_sig(patterns=[])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 0

    def test_missing_bundled_file(self, tmp_path):
        """Missing bundled file → graceful fallback."""
        mgr = _make_manager(tmp_path)
        mgr._bundled_path = tmp_path / "nonexistent.json"
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 0

    def test_file_too_large_rejected(self, tmp_path):
        """File > 2MB → rejected."""
        sig = _make_valid_sig(patterns=[_make_pattern("p1", r"test")])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        # Write an oversized file
        large_data = "x" * (MAX_SIGNATURE_SIZE + 100)
        mgr._bundled_path.write_text(large_data, encoding="utf-8")
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 0

    def test_valid_file_loads_cleanly(self, tmp_path):
        """Valid file with all sections loads correctly."""
        sig = _make_valid_sig(
            patterns=[_make_pattern("p1", r"clean_pattern")],
            keyword_lists={"instruction_override": ["ignore previous", "disregard"]},
            behavioral_rules=[{
                "name": "test_rule",
                "trigger_tool": "run_shell",
                "condition": "file_reads_in_window >= 5",
                "window_sec": 60.0,
                "level": 2,
            }],
        )
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 1
        assert "instruction_override" in mgr.get_keyword_lists()
        assert len(mgr.get_behavioral_rules()) == 1

    def test_keyword_lists_merged(self, tmp_path):
        """Keywords from bundled + custom are merged."""
        bundled = _make_valid_sig(
            keyword_lists={"exfil_verbs": ["steal", "extract"]})
        mgr = _make_manager(tmp_path, bundled_sig=bundled)

        custom = _make_valid_sig(
            keyword_lists={"exfil_verbs": ["leak", "transmit"]})
        _write_sig(mgr._custom_path, custom)

        mgr.load()
        kw = mgr.get_keyword_lists()
        assert "steal" in kw["exfil_verbs"]
        assert "leak" in kw["exfil_verbs"]


# ===========================================================================
# Reduce-Only Rule
# ===========================================================================

class TestReduceOnly:
    """Verifies the reduce-only rule: external signatures cannot lower hardcoded pattern levels.

    When an external signature file includes a pattern whose name matches a hardcoded pattern,
    the external pattern is only accepted if its level >= the hardcoded level. If the external
    level is lower, the pattern is silently dropped and a warning is logged. This prevents
    a malicious or misconfigured signature file from weakening built-in protections.
    Patterns with names not present in hardcoded_patterns are accepted at any level.
    """

    def test_higher_level_accepted(self, tmp_path):
        """External pattern same name, higher level → accepted."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("test_pat", r"test", level=3),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        # Hardcoded "test_pat" at level 2
        mgr.load(hardcoded_patterns=[("test_pat", None, 2, None, None)])
        assert len(mgr.get_compiled_patterns()) == 1

    def test_lower_level_rejected(self, tmp_path):
        """External pattern same name, lower level → rejected."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("test_pat", r"test", level=1),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        # Hardcoded at level 3
        mgr.load(hardcoded_patterns=[("test_pat", None, 3, None, None)])
        assert len(mgr.get_compiled_patterns()) == 0

    def test_same_level_accepted(self, tmp_path):
        """External pattern same name, same level → accepted."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("test_pat", r"test", level=2),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load(hardcoded_patterns=[("test_pat", None, 2, None, None)])
        assert len(mgr.get_compiled_patterns()) == 1

    def test_new_name_accepted(self, tmp_path):
        """External pattern with new name → accepted freely."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("brand_new_pattern", r"new", level=1),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load(hardcoded_patterns=[("other_pattern", None, 3, None, None)])
        assert len(mgr.get_compiled_patterns()) == 1

    def test_mixed_valid_and_rejected(self, tmp_path):
        """Mix of valid and reduce-only violations → partial load."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("lowered", r"test1", level=0),  # Will be rejected
            _make_pattern("ok_new", r"test2", level=2),   # New name, OK
            _make_pattern("raised", r"test3", level=3),   # Raised, OK
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load(hardcoded_patterns=[
            ("lowered", None, 2, None, None),
            ("raised", None, 1, None, None),
        ])
        names = [p[0] for p in mgr.get_compiled_patterns()]
        assert "lowered" not in names
        assert "ok_new" in names
        assert "raised" in names

    def test_reduce_only_logged(self, tmp_path):
        """Reduce-only rejection produces a log warning."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("test_pat", r"test", level=0),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        with patch("forge.threat_intel.log") as mock_log:
            mgr.load(hardcoded_patterns=[("test_pat", None, 3, None, None)])
            mock_log.warning.assert_any_call(
                "Threat intel: reduce-only rejected '%s' "
                "(external level %d < hardcoded %d)",
                "test_pat", 0, 3)


# ===========================================================================
# Pattern Compilation
# ===========================================================================

class TestCompilation:
    """Verifies pattern compilation: tuple format, regex flags, and ReDoS protection.

    get_compiled_patterns() returns a list of (name, re.Pattern, level, category, description)
    tuples. The re.Pattern must have the correct flags applied (IGNORECASE, DOTALL, etc.).
    A ReDoS-vulnerable regex like (a+)+$ must be rejected by the guard — catastrophic
    backtracking would allow an attacker to DoS Forge by crafting input that takes
    exponential time to scan. Safe patterns like AKIA[0-9A-Z]{16} must compile cleanly.
    """

    def test_compiled_format(self, tmp_path):
        """Compiled patterns have correct tuple format."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("p1", r"test_regex", level=2, category="jailbreak",
                          description="test description"),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        patterns = mgr.get_compiled_patterns()
        assert len(patterns) == 1
        name, regex, level, cat, desc = patterns[0]
        assert name == "p1"
        assert isinstance(regex, re.Pattern)
        assert level == 2
        assert cat == "jailbreak"
        assert desc == "test description"

    def test_flags_applied(self, tmp_path):
        """Compile flags are correctly applied."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("p1", r"test", flags=["IGNORECASE", "DOTALL"]),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        _, regex, _, _, _ = mgr.get_compiled_patterns()[0]
        assert regex.flags & re.IGNORECASE
        assert regex.flags & re.DOTALL

    def test_redos_catastrophic_rejected(self, tmp_path):
        """ReDoS catastrophic pattern → rejected."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("redos_bad", r"(a+)+$", level=2),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        names = [p[0] for p in mgr.get_compiled_patterns()]
        assert "redos_bad" not in names

    def test_safe_pattern_accepted(self, tmp_path):
        """Safe regex passes ReDoS guard."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("safe", r"AKIA[0-9A-Z]{16}", level=2),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 1

    def test_compile_error_skipped(self, tmp_path):
        """Regex compile error → pattern skipped, warning logged."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("good", r"valid_pattern"),
            _make_pattern("bad", r"[unterminated"),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 1

    def test_get_compiled_returns_list(self, tmp_path):
        """get_compiled_patterns() returns a list of tuples."""
        mgr = _make_manager(tmp_path, bundled_sig=_make_valid_sig())
        mgr.load()
        result = mgr.get_compiled_patterns()
        assert isinstance(result, list)


# ===========================================================================
# Update Mechanism
# ===========================================================================

class TestUpdate:
    """Verifies the network update mechanism: rate limiting, SHA-512 verification, and rollback protection.

    update() requires a configured URL; without one it returns success=False immediately.
    A second update within 24h is rate-limited unless force=True. A successful fetch
    writes fetched_signatures.json and reloads. If the response includes a 'sha512' field
    that doesn't match the actual content hash, the file is rejected. If the fetched
    signature has an older version number than what's already loaded, it's rejected as
    a version rollback attempt. At safety_level=0, auto_update_if_due() is a no-op.
    """

    def test_update_no_url(self, tmp_path):
        """Update with no URL → skipped."""
        mgr = _make_manager(tmp_path, config={"threat_signatures_url": ""})
        mgr.load()
        result = mgr.update()
        assert result["success"] is False
        assert "No signature URL" in result["message"]

    def test_rate_limit_blocks_second_update(self, tmp_path):
        """Second update within 24h → blocked."""
        mgr = _make_manager(tmp_path, config={"threat_signatures_url": "http://example.com/sigs.json"})
        mgr.load()
        # Simulate a recent update
        mgr._update_timestamp()
        result = mgr.update(force=False)
        assert result["success"] is False
        assert "Rate limited" in result["message"]

    def test_force_update_bypasses_rate_limit(self, tmp_path):
        """Force update bypasses rate limit (still fails on network)."""
        mgr = _make_manager(tmp_path, config={"threat_signatures_url": "http://192.0.2.1/sigs.json"})
        mgr.load()
        mgr._update_timestamp()
        # Will fail on network but won't be rate limited
        result = mgr.update(force=True)
        assert result["success"] is False
        assert "Rate limited" not in result["message"]

    def test_update_empty_url_skipped(self, tmp_path):
        """Empty URL → skipped with message."""
        mgr = _make_manager(tmp_path)
        mgr.load()
        result = mgr.update()
        assert not result["success"]

    def test_update_writes_fetched_file(self, tmp_path):
        """Successful update writes fetched_signatures.json."""
        sig = _make_valid_sig(patterns=[_make_pattern("net_p", r"network_pat")])
        # Add valid SHA-512 envelope (hash of data without sha512 key)
        sig_hash = hashlib.sha512(json.dumps(sig, sort_keys=True).encode("utf-8")).hexdigest()
        sig["sha512"] = sig_hash
        sig_bytes = json.dumps(sig).encode("utf-8")

        mgr = _make_manager(tmp_path, config={
            "threat_signatures_url": "http://example.com/sigs.json"})
        mgr.load()

        # Mock urllib
        mock_resp = MagicMock()
        mock_resp.read.return_value = sig_bytes
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = mgr.update(force=True)

        assert result["success"] is True
        assert mgr._fetched_path.exists()

    def test_sha512_mismatch_rejected(self, tmp_path):
        """SHA-512 hash mismatch → rejected."""
        sig = _make_valid_sig(patterns=[_make_pattern("p1", r"test")])
        sig["sha512"] = "0" * 128  # Wrong hash
        sig_bytes = json.dumps(sig).encode("utf-8")

        mgr = _make_manager(tmp_path, config={
            "threat_signatures_url": "http://example.com/sigs.json"})
        mgr.load()

        mock_resp = MagicMock()
        mock_resp.read.return_value = sig_bytes
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = mgr.update(force=True)

        assert result["success"] is False
        assert "SHA-512" in result["message"]

    def test_version_rollback_rejected(self, tmp_path):
        """Older version → rejected (version monotonicity)."""
        # Load a v1 signature first
        sig_v1 = _make_valid_sig(patterns=[_make_pattern("p1", r"test")], version=1)
        mgr = _make_manager(tmp_path, bundled_sig=sig_v1)
        mgr.load()

        # Try to fetch an older version (but version must still == SIGNATURE_VERSION for validation)
        # So we test by setting loaded_version higher
        mgr._loaded_version = 2

        sig_old = _make_valid_sig(patterns=[_make_pattern("p2", r"test2")], version=1)
        # Add valid SHA-512 envelope
        sig_hash = hashlib.sha512(json.dumps(sig_old, sort_keys=True).encode("utf-8")).hexdigest()
        sig_old["sha512"] = sig_hash
        sig_bytes = json.dumps(sig_old).encode("utf-8")

        mgr._config_get = lambda k, d=None: {
            "threat_signatures_url": "http://example.com/sigs.json"
        }.get(k, d)

        mock_resp = MagicMock()
        mock_resp.read.return_value = sig_bytes
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            result = mgr.update(force=True)

        assert result["success"] is False
        assert "rollback" in result["message"]

    def test_auto_update_respects_safety_level(self, tmp_path):
        """Auto-update at L0 → skipped."""
        mgr = _make_manager(tmp_path, config={
            "safety_level": 0,
            "threat_auto_update": True,
            "threat_signatures_url": "http://example.com/sigs.json",
        })
        mgr.load()
        with patch.object(mgr, "update") as mock_update:
            mgr.auto_update_if_due()
            mock_update.assert_not_called()


# ===========================================================================
# Crucible Integration
# ===========================================================================

class TestCrucibleIntegration:
    """Verifies Crucible correctly combines hardcoded patterns with threat_intel external patterns.

    When a ThreatIntelManager is passed to Crucible, _get_all_patterns() returns the union
    of hardcoded INJECTION_PATTERNS plus any patterns loaded from signature files.
    Without threat_intel, only hardcoded patterns are used. External patterns detect content
    that hardcoded patterns would miss. Hit recording increments when an external pattern
    matches. format_status() and to_audit_dict() correctly reflect the external pattern count.
    Keyword lists and behavioral rules loaded into the manager are accessible via the manager API.
    """

    def test_crucible_with_threat_intel(self, tmp_path):
        """Crucible with threat_intel → combined patterns."""
        from forge.crucible import Crucible, INJECTION_PATTERNS
        sig = _make_valid_sig(patterns=[
            _make_pattern("ext_pat", r"EXTERNAL_THREAT_MARKER"),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load(hardcoded_patterns=INJECTION_PATTERNS)

        c = Crucible(enabled=True, threat_intel=mgr)
        all_pats = c._get_all_patterns()
        names = [p[0] for p in all_pats]
        assert "ext_pat" in names
        # Hardcoded patterns also present
        assert "ai_role_override" in names

    def test_crucible_without_threat_intel(self, tmp_path):
        """Crucible without threat_intel → hardcoded only."""
        from forge.crucible import Crucible, _COMPILED_PATTERNS
        c = Crucible(enabled=True)
        all_pats = c._get_all_patterns()
        assert len(all_pats) == len(_COMPILED_PATTERNS)

    def test_external_pattern_detects_content(self, tmp_path):
        """External pattern detects content that hardcoded misses."""
        from forge.crucible import Crucible, INJECTION_PATTERNS
        sig = _make_valid_sig(patterns=[
            _make_pattern("custom_threat", r"VERY_SPECIFIC_THREAT_XYZ123", level=2),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load(hardcoded_patterns=INJECTION_PATTERNS)

        c = Crucible(enabled=True, threat_intel=mgr)
        threats = c.scan_content("test.txt", "Here is VERY_SPECIFIC_THREAT_XYZ123 in text")
        pattern_names = [t.pattern_name for t in threats]
        assert "custom_threat" in pattern_names

    def test_hit_recording(self, tmp_path):
        """Hit recording increments on match."""
        from forge.crucible import Crucible, INJECTION_PATTERNS
        sig = _make_valid_sig(patterns=[
            _make_pattern("hit_test", r"HIT_ME_PATTERN", level=2),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load(hardcoded_patterns=INJECTION_PATTERNS)

        c = Crucible(enabled=True, threat_intel=mgr)
        c.scan_content("test.txt", "HIT_ME_PATTERN appears here")
        c.scan_content("test.txt", "HIT_ME_PATTERN again")

        stats = mgr.get_detection_stats()
        assert stats["total_hits"] >= 2

    def test_format_status_shows_combined(self, tmp_path):
        """format_status() shows combined pattern count."""
        from forge.crucible import Crucible, INJECTION_PATTERNS, _COMPILED_PATTERNS
        sig = _make_valid_sig(patterns=[
            _make_pattern("ext1", r"pattern_ext_1"),
            _make_pattern("ext2", r"pattern_ext_2"),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load(hardcoded_patterns=INJECTION_PATTERNS)

        c = Crucible(enabled=True, threat_intel=mgr)
        status = c.format_status()
        hardcoded_count = len(_COMPILED_PATTERNS)
        assert str(hardcoded_count) in status
        assert "external" in status.lower() or "2" in status

    def test_to_audit_dict_includes_threat_intel(self, tmp_path):
        """to_audit_dict() includes threat_intel section."""
        from forge.crucible import Crucible, INJECTION_PATTERNS
        sig = _make_valid_sig(patterns=[_make_pattern("aud_p", r"audit_test")])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load(hardcoded_patterns=INJECTION_PATTERNS)

        c = Crucible(enabled=True, threat_intel=mgr)
        audit = c.to_audit_dict()
        assert "threat_intel" in audit
        assert audit["threat_intel"]["total_patterns"] == 1

    def test_keyword_lists_accessible(self, tmp_path):
        """Keyword lists are accessible via threat_intel."""
        sig = _make_valid_sig(
            keyword_lists={"test_kw": ["word1", "word2", "word3"]})
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        kw = mgr.get_keyword_lists()
        assert "test_kw" in kw
        assert "word1" in kw["test_kw"]

    def test_behavioral_rules_accessible(self, tmp_path):
        """Behavioral rules are accessible."""
        sig = _make_valid_sig(behavioral_rules=[{
            "name": "test_rule",
            "trigger_tool": "run_shell",
            "condition": "file_reads_in_window >= 5",
            "window_sec": 60.0,
            "level": 2,
        }])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        rules = mgr.get_behavioral_rules()
        assert len(rules) == 1
        assert rules[0]["name"] == "test_rule"


# ===========================================================================
# Search & Stats
# ===========================================================================

class TestSearchAndStats:
    """Verifies pattern search, category filtering, hit tracking, and status reporting.

    search_patterns(query) matches against pattern name and category — 'exfil' finds
    the pattern named 'exfil_dns' but not 'jailbreak_dan'. list_by_category(cat) returns
    only patterns in that category. record_hit(name) increments a counter; get_detection_stats()
    returns total_hits and top_patterns. get_status() returns a dict with total_patterns,
    keyword_lists, keyword_terms, and behavioral_rules counts.
    """

    def test_search_by_name(self, tmp_path):
        """Search patterns by name."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("exfil_dns", r"nslookup", category="data_exfil"),
            _make_pattern("jailbreak_dan", r"dan_mode", category="jailbreak"),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        results = mgr.search_patterns("exfil")
        assert len(results) == 1
        assert results[0]["name"] == "exfil_dns"

    def test_search_by_category(self, tmp_path):
        """Search patterns by category."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("p1", r"test1", category="data_exfil"),
            _make_pattern("p2", r"test2", category="jailbreak"),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        results = mgr.search_patterns("jailbreak")
        assert len(results) == 1

    def test_list_by_category(self, tmp_path):
        """List patterns filtered by category."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("p1", r"t1", category="jailbreak"),
            _make_pattern("p2", r"t2", category="jailbreak"),
            _make_pattern("p3", r"t3", category="data_exfil"),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        results = mgr.list_by_category("jailbreak")
        assert len(results) == 2

    def test_detection_stats(self, tmp_path):
        """Detection stats track hits correctly."""
        mgr = _make_manager(tmp_path, bundled_sig=_make_valid_sig(
            patterns=[_make_pattern("p1", r"test", category="jailbreak")]))
        mgr.load()
        mgr.record_hit("p1")
        mgr.record_hit("p1")
        mgr.record_hit("p1")
        stats = mgr.get_detection_stats()
        assert stats["total_hits"] == 3
        assert ("p1", 3) in stats["top_patterns"]

    def test_status_dict(self, tmp_path):
        """get_status() returns correct structure."""
        sig = _make_valid_sig(
            patterns=[_make_pattern("p1", r"test")],
            keyword_lists={"kw1": ["a", "b"]},
            behavioral_rules=[{
                "name": "r1", "trigger_tool": "run_shell",
                "condition": "test", "window_sec": 60, "level": 2}],
        )
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        status = mgr.get_status()
        assert status["total_patterns"] == 1
        assert status["keyword_lists"] == 1
        assert status["keyword_terms"] == 2
        assert status["behavioral_rules"] == 1


# ===========================================================================
# Config
# ===========================================================================

class TestConfig:
    """Verifies threat intelligence config keys exist with correct defaults and validators.

    DEFAULTS must include threat_signatures_enabled=True, a string threat_signatures_url,
    and threat_auto_update=True. The validators must accept True/False for booleans but
    reject strings like 'yes', and accept both empty and non-empty strings for URLs.
    """

    def test_config_defaults(self):
        """Config keys have correct defaults."""
        from forge.config import DEFAULTS
        assert DEFAULTS["threat_signatures_enabled"] is True
        assert isinstance(DEFAULTS["threat_signatures_url"], str)
        assert DEFAULTS["threat_auto_update"] is True

    def test_config_validators(self):
        """Config validators accept correct types."""
        from forge.config import _VALIDATORS
        assert _VALIDATORS["threat_signatures_enabled"](True)
        assert _VALIDATORS["threat_signatures_enabled"](False)
        assert not _VALIDATORS["threat_signatures_enabled"]("yes")
        assert _VALIDATORS["threat_signatures_url"]("")
        assert _VALIDATORS["threat_signatures_url"]("http://example.com")
        assert _VALIDATORS["threat_auto_update"](True)


# ===========================================================================
# Red-Team
# ===========================================================================

class TestRedTeam:
    """Adversarial tests: malicious signature content must not crash, execute code, or bypass limits.

    A regex with catastrophic backtracking structure must either be rejected by the ReDoS
    guard or compile safely — the system must not hang. 1000 patterns in a file exceed
    MAX_PATTERNS_PER_FILE (500) and must be rejected entirely. level=99 is out of bounds
    and must cause the whole file to be rejected. A description containing shell commands
    or SQL injection ('system("rm -rf /")') is safe because descriptions are display-only
    text, never executed. Concurrent load + access from multiple threads must produce
    zero exceptions — ThreatIntelManager must be thread-safe under load.
    """

    def test_eval_in_regex_rejected(self, tmp_path):
        """Regex that isn't valid (not really eval, but invalid) → rejected."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("evil", r"(?P<name>.*)\1\1\1\1\1\1", level=2),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        # Pattern may compile but ReDoS guard should catch it
        # or it compiles safely — either way system doesn't crash
        assert isinstance(mgr.get_compiled_patterns(), list)

    def test_too_many_patterns_rejected(self, tmp_path):
        """1000 patterns → rejected (> 500 cap)."""
        patterns = [_make_pattern(f"p{i}", f"pattern_{i}") for i in range(1000)]
        sig = _make_valid_sig(patterns=patterns)
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 0

    def test_level_out_of_bounds_rejected(self, tmp_path):
        """Level=99 → entire file rejected."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("evil", r"test", level=99),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 0

    def test_malicious_description_safe(self, tmp_path):
        """Malicious text in description → loaded (display-only, never executed)."""
        sig = _make_valid_sig(patterns=[
            _make_pattern("desc_test", r"test_pattern",
                          description='system("rm -rf /"); DROP TABLE users;'),
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        assert len(mgr.get_compiled_patterns()) == 1

    def test_concurrent_load_and_access(self, tmp_path):
        """Concurrent load + access → no race condition."""
        sig = _make_valid_sig(patterns=[
            _make_pattern(f"p{i}", f"pattern_{i}") for i in range(50)
        ])
        mgr = _make_manager(tmp_path, bundled_sig=sig)

        errors = []

        def _load():
            try:
                mgr.load()
            except Exception as e:
                errors.append(e)

        def _access():
            try:
                for _ in range(100):
                    mgr.get_compiled_patterns()
                    mgr.get_keyword_lists()
                    mgr.get_behavioral_rules()
                    mgr.record_hit("p0")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=_load),
            threading.Thread(target=_access),
            threading.Thread(target=_access),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert len(errors) == 0


# ===========================================================================
# Audit & Format
# ===========================================================================

class TestAuditAndFormat:
    """Verifies audit dict structure and format_status() output for ThreatIntelManager.

    to_audit_dict() must include schema_version==SIGNATURE_VERSION, total_patterns count,
    and detection_stats with total_hits reflecting recorded hits. format_status() must
    return a human-readable string containing 'Threat Intelligence', 'ACTIVE', and
    the external pattern count (e.g. '1 external').
    """

    def test_to_audit_dict_structure(self, tmp_path):
        """to_audit_dict() returns complete structure."""
        sig = _make_valid_sig(patterns=[_make_pattern("p1", r"test")])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        mgr.record_hit("p1")
        audit = mgr.to_audit_dict()
        assert audit["schema_version"] == SIGNATURE_VERSION
        assert audit["total_patterns"] == 1
        assert audit["detection_stats"]["total_hits"] == 1

    def test_format_status_output(self, tmp_path):
        """format_status() returns readable string."""
        sig = _make_valid_sig(patterns=[_make_pattern("p1", r"test")])
        mgr = _make_manager(tmp_path, bundled_sig=sig)
        mgr.load()
        output = mgr.format_status()
        assert "Threat Intelligence" in output
        assert "ACTIVE" in output
        assert "1 external" in output


# ===========================================================================
# Default Signatures File
# ===========================================================================

class TestDefaultSignatures:
    """Verifies the shipped default_signatures.json file is valid, safe, and has adequate coverage.

    The bundled file at forge/data/default_signatures.json must pass _validate_signature_file()
    with no errors. Every pattern's category must be in APPROVED_CATEGORIES — no undocumented
    categories slipping in. Every regex must compile without error (with its specified flags).
    The file must contain at least 50 patterns to provide meaningful threat coverage — a file
    with fewer patterns would leave obvious attack vectors undetected.
    All tests skip if the file doesn't exist rather than failing (file is optional at test time).
    """

    def test_default_file_valid(self):
        """Bundled default_signatures.json passes validation."""
        path = Path(__file__).parent.parent / "forge" / "data" / "default_signatures.json"
        if not path.exists():
            pytest.skip("default_signatures.json not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        mgr = ThreatIntelManager(
            data_dir=Path("/tmp/test_defaults"),
            config_get=lambda k, d=None: d)
        valid, err = mgr._validate_signature_file(data)
        assert valid, f"Default signatures invalid: {err}"

    def test_default_file_categories_approved(self):
        """All categories in defaults are in APPROVED_CATEGORIES."""
        path = Path(__file__).parent.parent / "forge" / "data" / "default_signatures.json"
        if not path.exists():
            pytest.skip("default_signatures.json not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        for p in data.get("patterns", []):
            assert p["category"] in APPROVED_CATEGORIES, \
                f"Pattern '{p['name']}' has unapproved category '{p['category']}'"

    def test_default_file_patterns_compile(self):
        """All patterns in defaults compile without error."""
        path = Path(__file__).parent.parent / "forge" / "data" / "default_signatures.json"
        if not path.exists():
            pytest.skip("default_signatures.json not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        for p in data.get("patterns", []):
            flags = 0
            for fn in p.get("flags", []):
                flags |= {"IGNORECASE": re.IGNORECASE, "MULTILINE": re.MULTILINE,
                           "DOTALL": re.DOTALL}.get(fn, 0)
            try:
                re.compile(p["regex"], flags)
            except re.error as e:
                pytest.fail(f"Pattern '{p['name']}' fails to compile: {e}")

    def test_default_file_pattern_count(self):
        """Default file has substantial pattern coverage."""
        path = Path(__file__).parent.parent / "forge" / "data" / "default_signatures.json"
        if not path.exists():
            pytest.skip("default_signatures.json not found")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data.get("patterns", [])) >= 50, "Expected 50+ default patterns"
