"""Tests for audit round 3 — 16 bugs found and fixed."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock


# ── Bug #1: _session_file defined ──

class TestSessionFileInit:
    def test_engine_has_session_file(self):
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine.__init__)
        assert "self._session_file" in source

    def test_session_file_path(self):
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine.__init__)
        assert 'session.json' in source


# ── Bug #2: /compare keys ──

class TestCompareKeys:
    def test_comparison_has_input_output_cost(self, tmp_path):
        from forge.billing import BillingMeter
        bm = BillingMeter(persist_path=tmp_path / "billing.json")
        bm.record_turn(input_tokens=1000, output_tokens=500)
        comp = bm.get_comparison()
        for name, data in comp["comparisons"].items():
            assert "input_cost" in data, f"Missing input_cost in {name}"
            assert "output_cost" in data, f"Missing output_cost in {name}"
            assert "cost" in data, f"Missing cost in {name}"

    def test_forge_local_costs_zero(self, tmp_path):
        from forge.billing import BillingMeter
        bm = BillingMeter(persist_path=tmp_path / "billing.json")
        bm.record_turn(input_tokens=1000, output_tokens=500)
        comp = bm.get_comparison()
        forge = comp["comparisons"]["Forge (local)"]
        assert forge["input_cost"] == 0.0
        assert forge["output_cost"] == 0.0
        assert forge["cost"] == 0.0

    def test_costs_add_up(self, tmp_path):
        from forge.billing import BillingMeter
        bm = BillingMeter(persist_path=tmp_path / "billing.json")
        bm.record_turn(input_tokens=10000, output_tokens=5000)
        comp = bm.get_comparison()
        for name, data in comp["comparisons"].items():
            total = data["cost"]
            parts = data["input_cost"] + data["output_cost"]
            assert abs(total - parts) < 0.0001, (
                f"{name}: {total} != {parts}")


# ── Bug #3: _last_warning_pct ──

class TestLastWarningPct:
    def test_defined_in_init(self):
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine.__init__)
        assert "_last_warning_pct" in source


# ── Bug #4: passport attr names ──

class TestPassportAttrNames:
    def test_uses_public_attrs(self):
        import inspect
        from forge.passport import BPoS
        source = inspect.getsource(BPoS.collect_genome)
        # Should use public names, not private
        assert "engine.threat_intel" in source
        assert "engine.reliability" in source
        assert "engine.stats" in source
        # Should NOT use private names
        assert "engine._threat_intel" not in source
        assert "engine._reliability" not in source
        assert "engine._stats" not in source


# ── Bug #5: shipwright chunk format ──

class TestShipwrightChunkFormat:
    def test_reads_token_type_chunks(self):
        import inspect
        from forge.shipwright import Shipwright
        source = inspect.getsource(Shipwright._llm_classify)
        # Should check type == "token", not message.content
        assert '"type"' in source or "'type'" in source
        assert '"token"' in source or "'token'" in source
        # Should NOT use old Ollama raw format
        assert '"message"' not in source


# ── Bug #6: cache.read removed ──

class TestCacheReadRemoved:
    def test_no_cache_read_call(self):
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine._continuity_recovery)
        assert "cache.read(" not in source


# ── Bug #7: session-level file tracking ──

class TestSessionFileTracking:
    def test_session_files_in_init(self):
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine.__init__)
        assert "_session_files" in source

    def test_exit_summary_uses_session_files(self):
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine._print_exit_summary)
        assert "_session_files" in source


# ── Bug #8: /topup ValueError ──

class TestTopupValidation:
    def test_topup_handles_bad_input(self):
        import inspect
        from forge.commands import CommandHandler
        source = inspect.getsource(CommandHandler._cmd_topup)
        assert "ValueError" in source


# ── Bug #9: forensics._enabled removed ──

class TestForensicsEnabled:
    def test_no_forensics_enabled_set(self):
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine._apply_enterprise_defaults)
        assert "forensics._enabled" not in source


# ── Bug #10: /scan arg parsing ──

class TestScanArgParsing:
    def test_scan_parses_force_flag(self):
        import inspect
        from forge.commands import CommandHandler
        source = inspect.getsource(CommandHandler._cmd_scan)
        # Should handle force as separate word
        assert '"force"' in source or "'force'" in source
        assert '"--force"' in source or "'--force'" in source

    def test_scan_checks_digester(self):
        import inspect
        from forge.commands import CommandHandler
        source = inspect.getsource(CommandHandler._cmd_scan)
        assert "_digester" in source
        assert "None" in source or "not" in source


# ── Bug #11: get_entries_snapshot ──

class TestEntriesSnapshot:
    def test_context_has_snapshot_method(self):
        from forge.context import ContextWindow
        ctx = ContextWindow(max_tokens=1000)
        assert hasattr(ctx, "get_entries_snapshot")

    def test_snapshot_returns_copy(self):
        from forge.context import ContextWindow
        ctx = ContextWindow(max_tokens=1000)
        ctx.add("user", "hello")
        snap = ctx.get_entries_snapshot()
        assert len(snap) == 1
        snap.clear()  # Modifying copy
        assert ctx.entry_count == 1  # Original unchanged

    def test_engine_uses_snapshot(self):
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine._auto_context_swap)
        assert "get_entries_snapshot()" in source


# ── Bug #14: os.replace ──

class TestAtomicWrites:
    def test_memory_uses_replace(self):
        import inspect
        from forge.memory import EpisodicMemory
        source = inspect.getsource(EpisodicMemory)
        assert "os.replace(" in source
        assert "os.rename(" not in source

    def test_reliability_uses_replace(self):
        import inspect
        from forge.reliability import ReliabilityTracker
        source = inspect.getsource(ReliabilityTracker)
        assert "os.replace(" in source
        assert "os.rename(" not in source


# ── Bug #15: atomic billing save ──

class TestAtomicBillingSave:
    def test_billing_uses_tempfile(self):
        import inspect
        from forge.billing import BillingMeter
        source = inspect.getsource(BillingMeter._save)
        assert "tempfile.mkstemp" in source
        assert "os.replace(" in source

    def test_billing_save_load_roundtrip(self, tmp_path):
        from forge.billing import BillingMeter
        bm = BillingMeter(persist_path=tmp_path / "billing.json")
        bm.record_turn(input_tokens=100, output_tokens=50)
        bm.topup(25.0)
        # Force save
        bm._save()
        # Load into new instance
        bm2 = BillingMeter(persist_path=tmp_path / "billing.json")
        assert bm2.lifetime_input_tokens == 100
        assert bm2.lifetime_output_tokens == 50
