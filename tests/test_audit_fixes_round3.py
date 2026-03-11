"""Tests for audit round 3 bug fixes — behavioral verification only.

Each test exercises real subsystem behavior to confirm specific bugs
stay fixed.  No source inspection — every assertion runs actual code.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock


# ── Bug #2: /compare cost breakdown keys ──

class TestCompareKeys:
    """Verifies BillingMeter.get_comparison() returns per-model cost breakdowns.

    After recording a turn with 1000 input + 500 output tokens, every comparison
    entry must include 'input_cost', 'output_cost', and 'cost'.  Forge (local)
    costs must be exactly 0.0.  For paid providers, cost == input_cost + output_cost
    within floating-point tolerance.
    """

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


# ── Bug #11: get_entries_snapshot returns a copy ──

class TestEntriesSnapshot:
    """Verifies ContextWindow.get_entries_snapshot() returns an independent copy.

    Clearing the returned snapshot list must NOT affect the original context
    window's entries.  This prevents accidental mutation during context
    management operations that iterate while the engine is modifying state.
    """

    def test_snapshot_returns_independent_copy(self):
        from forge.context import ContextWindow
        ctx = ContextWindow(max_tokens=1000)
        ctx.add("user", "hello")
        snap = ctx.get_entries_snapshot()
        assert len(snap) == 1
        snap.clear()  # Modifying copy
        assert ctx.entry_count == 1  # Original unchanged


# ── Bug #15: atomic billing persistence ──

class TestAtomicBillingSave:
    """Verifies BillingMeter survives a save/load roundtrip without data loss.

    After recording a turn (100 input + 50 output tokens) and a $25 topup,
    forcing a save and reloading from the same path must restore the exact
    lifetime token counts.  This confirms the atomic write (tempfile + rename)
    path works end-to-end.
    """

    def test_billing_save_load_roundtrip(self, tmp_path):
        from forge.billing import BillingMeter
        bm = BillingMeter(persist_path=tmp_path / "billing.json")
        bm.record_turn(input_tokens=100, output_tokens=50)
        bm.topup(25.0)
        bm._save()
        # Load into new instance
        bm2 = BillingMeter(persist_path=tmp_path / "billing.json")
        assert bm2.lifetime_input_tokens == 100
        assert bm2.lifetime_output_tokens == 50
