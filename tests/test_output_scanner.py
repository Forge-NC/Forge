"""Tests for LLM output scanner in ForgeEngine."""

import pytest
from unittest.mock import MagicMock, patch


def _make_engine(safety_level=1, output_scanning=True, crucible_enabled=True):
    """Create a minimal mock engine with security methods."""
    engine = MagicMock()
    engine.safety = MagicMock()
    engine.safety.level = safety_level
    engine.config = MagicMock()
    engine.config.get = lambda k, d=None: {
        "output_scanning": output_scanning,
    }.get(k, d)
    engine.crucible = MagicMock()
    engine.crucible.enabled = crucible_enabled
    engine.forensics = MagicMock()
    engine.io = MagicMock()

    # Bind the actual method
    from forge.engine import ForgeEngine
    engine._scan_llm_output = ForgeEngine._scan_llm_output.__get__(engine)
    return engine


class TestOutputScanner:
    """Verifies _scan_llm_output() escalates threat responses based on safety level.

    L0: scan_content never called (output scanning skipped entirely).
    L1: threats logged to forensics.record but no io.print_warning (silent).
    L2: io.print_warning called with 'Output scan' in the message.
    L3: multiple print_warning calls with at least one containing 'Safety L3'.
    Clean output with no threats → no warnings, no forensics records.
    output_scanning=False or crucible disabled → scan_content never called.
    Only WARNING+ threats trigger actions; SUSPICIOUS threats are filtered out.
    """

    def test_safety_l0_no_scan(self):
        engine = _make_engine(safety_level=0)
        engine._scan_llm_output("AKIAIOSFODNN7EXAMPLE1")
        engine.crucible.scan_content.assert_not_called()

    def test_safety_l1_logs_only(self):
        engine = _make_engine(safety_level=1)
        from forge.crucible import ThreatLevel
        threat = MagicMock()
        threat.level = ThreatLevel.WARNING
        threat.level_name = "WARNING"
        threat.category = "secret_leak"
        threat.pattern_name = "aws_access_key"
        threat.description = "AWS key"
        engine.crucible.scan_content.return_value = [threat]
        engine._scan_llm_output("AKIAIOSFODNN7EXAMPLE1")
        engine.forensics.record.assert_called()
        engine.io.print_warning.assert_not_called()

    def test_safety_l2_inline_warning(self):
        engine = _make_engine(safety_level=2)
        from forge.crucible import ThreatLevel
        threat = MagicMock()
        threat.level = ThreatLevel.WARNING
        threat.level_name = "WARNING"
        threat.category = "secret_leak"
        threat.pattern_name = "aws_access_key"
        threat.description = "AWS key detected"
        engine.crucible.scan_content.return_value = [threat]
        engine._scan_llm_output("AKIAIOSFODNN7EXAMPLE1")
        engine.io.print_warning.assert_called()
        warning_text = engine.io.print_warning.call_args[0][0]
        assert "Output scan" in warning_text

    def test_safety_l3_block_ack(self):
        engine = _make_engine(safety_level=3)
        from forge.crucible import ThreatLevel
        threat = MagicMock()
        threat.level = ThreatLevel.WARNING
        threat.level_name = "WARNING"
        threat.category = "secret_leak"
        threat.pattern_name = "aws_access_key"
        threat.description = "AWS key detected"
        engine.crucible.scan_content.return_value = [threat]
        engine._scan_llm_output("some text with AKIAIOSFODNN7EXAMPLE1")
        # Should have multiple print_warning calls: one per threat + L3 message
        assert engine.io.print_warning.call_count >= 2
        calls = [c[0][0] for c in engine.io.print_warning.call_args_list]
        assert any("Safety L3" in c for c in calls)

    def test_clean_output_no_action(self):
        engine = _make_engine(safety_level=2)
        engine.crucible.scan_content.return_value = []
        engine._scan_llm_output("This is a clean response about coding.")
        engine.io.print_warning.assert_not_called()
        engine.forensics.record.assert_not_called()

    def test_scanning_disabled(self):
        engine = _make_engine(safety_level=2, output_scanning=False)
        engine._scan_llm_output("AKIAIOSFODNN7EXAMPLE1")
        engine.crucible.scan_content.assert_not_called()

    def test_crucible_disabled(self):
        engine = _make_engine(safety_level=2, crucible_enabled=False)
        engine._scan_llm_output("AKIAIOSFODNN7EXAMPLE1")
        engine.crucible.scan_content.assert_not_called()

    def test_suspicious_level_filtered_out(self):
        """Only WARNING+ threats trigger output scanner actions."""
        engine = _make_engine(safety_level=2)
        from forge.crucible import ThreatLevel
        threat = MagicMock()
        threat.level = ThreatLevel.SUSPICIOUS  # Below WARNING
        threat.level_name = "SUSPICIOUS"
        engine.crucible.scan_content.return_value = [threat]
        engine._scan_llm_output("some suspicious content")
        engine.io.print_warning.assert_not_called()
        engine.forensics.record.assert_not_called()
