"""Tests for RAG retrieval scanner in ForgeEngine."""

import pytest
from unittest.mock import MagicMock


def _make_engine(safety_level=1, rag_scanning=True, crucible_enabled=True):
    """Create a minimal mock engine with RAG scanning method."""
    engine = MagicMock()
    engine.safety = MagicMock()
    engine.safety.level = safety_level
    engine.config = MagicMock()
    engine.config.get = lambda k, d=None: {
        "rag_scanning": rag_scanning,
    }.get(k, d)
    engine.crucible = MagicMock()
    engine.crucible.enabled = crucible_enabled
    engine.forensics = MagicMock()
    engine.io = MagicMock()

    from forge.engine import ForgeEngine
    engine._scan_recall_content = ForgeEngine._scan_recall_content.__get__(engine)
    return engine


class TestRAGScanner:
    """Verifies _scan_recall_content() enforces safety-level-appropriate RAG scanning.

    L0: scan_content never called, always returns True.
    L1: threats logged to forensics.record, still injects (returns True).
    L2: print_warning called + forensics recorded, still injects (True).
    L3: print_warning called + returns False (blocked, not injected into context).
    Clean content at all levels → True with no side effects.
    rag_scanning=False or crucible disabled → scan never called, always True.
    forensics.record called with ('rag_scan', 'flagged') when threat found at L2.
    """

    def test_safety_l0_always_clean(self):
        engine = _make_engine(safety_level=0)
        result = engine._scan_recall_content("malicious content", "evil.py")
        assert result is True
        engine.crucible.scan_content.assert_not_called()

    def test_safety_l1_logs_and_injects(self):
        engine = _make_engine(safety_level=1)
        from forge.crucible import ThreatLevel
        threat = MagicMock()
        threat.level = ThreatLevel.WARNING
        threat.level_name = "WARNING"
        threat.pattern_name = "ssh_private_key"
        engine.crucible.scan_content.return_value = [threat]
        result = engine._scan_recall_content("-----BEGIN RSA PRIVATE KEY-----", "key.pem")
        assert result is True  # Still injects at L1
        engine.forensics.record.assert_called()

    def test_safety_l2_warns_and_injects(self):
        engine = _make_engine(safety_level=2)
        from forge.crucible import ThreatLevel
        threat = MagicMock()
        threat.level = ThreatLevel.WARNING
        threat.level_name = "WARNING"
        threat.pattern_name = "github_token"
        engine.crucible.scan_content.return_value = [threat]
        result = engine._scan_recall_content("ghp_abcdefghijklmnopqrstuvwxyz1234", "config.py")
        assert result is True  # Injects with warning at L2
        engine.io.print_warning.assert_called()

    def test_safety_l3_blocks(self):
        engine = _make_engine(safety_level=3)
        from forge.crucible import ThreatLevel
        threat = MagicMock()
        threat.level = ThreatLevel.WARNING
        threat.level_name = "WARNING"
        threat.pattern_name = "ssh_private_key"
        engine.crucible.scan_content.return_value = [threat]
        result = engine._scan_recall_content("-----BEGIN RSA PRIVATE KEY-----", "key.pem")
        assert result is False  # BLOCKED at L3
        engine.io.print_warning.assert_called()

    def test_clean_content_all_levels(self):
        for level in [0, 1, 2, 3]:
            engine = _make_engine(safety_level=level)
            engine.crucible.scan_content.return_value = []
            result = engine._scan_recall_content("def hello(): pass", "safe.py")
            assert result is True

    def test_scanning_disabled(self):
        engine = _make_engine(safety_level=3, rag_scanning=False)
        result = engine._scan_recall_content("-----BEGIN RSA PRIVATE KEY-----", "key.pem")
        assert result is True
        engine.crucible.scan_content.assert_not_called()

    def test_crucible_disabled(self):
        engine = _make_engine(safety_level=3, crucible_enabled=False)
        result = engine._scan_recall_content("malicious", "evil.py")
        assert result is True
        engine.crucible.scan_content.assert_not_called()

    def test_forensics_recorded_on_flag(self):
        engine = _make_engine(safety_level=2)
        from forge.crucible import ThreatLevel
        threat = MagicMock()
        threat.level = ThreatLevel.WARNING
        threat.level_name = "WARNING"
        threat.pattern_name = "aws_access_key"
        engine.crucible.scan_content.return_value = [threat]
        engine._scan_recall_content("AKIAIOSFODNN7EXAMPLE1", "config.py")
        engine.forensics.record.assert_called_once()
        call_args = engine.forensics.record.call_args
        assert call_args[0][0] == "rag_scan"
        assert call_args[0][1] == "flagged"
