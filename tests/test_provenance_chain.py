"""Tests for HMAC-SHA512 provenance chain in Crucible."""

import pytest
from forge.crucible import Crucible


@pytest.fixture
def crucible():
    c = Crucible(enabled=True)
    return c


class TestProvenanceChain:
    def test_empty_chain_valid(self, crucible):
        valid, idx = crucible.verify_provenance_chain()
        assert valid is True
        assert idx == -1

    def test_single_entry_valid(self, crucible):
        crucible.record_provenance("read_file", {"path": "test.py"})
        valid, idx = crucible.verify_provenance_chain()
        assert valid is True
        assert idx == -1

    def test_three_entries_valid(self, crucible):
        crucible.record_provenance("read_file", {"path": "a.py"})
        crucible.record_provenance("edit_file", {"path": "a.py"})
        crucible.record_provenance("run_shell", {"command": "pytest"})
        valid, idx = crucible.verify_provenance_chain()
        assert valid is True
        assert idx == -1
        assert len(crucible.get_provenance_chain(last_n=99999)) == 3

    def test_tampered_entry_detected(self, crucible):
        crucible.record_provenance("read_file", {"path": "a.py"})
        crucible.record_provenance("edit_file", {"path": "a.py"})
        crucible.record_provenance("run_shell", {"command": "pytest"})
        # Tamper with the second entry
        crucible._provenance[1]["tool"] = "delete_file"
        valid, idx = crucible.verify_provenance_chain()
        assert valid is False
        assert idx == 1

    def test_tampered_first_entry(self, crucible):
        crucible.record_provenance("read_file", {"path": "a.py"})
        crucible.record_provenance("edit_file", {"path": "b.py"})
        crucible._provenance[0]["args_summary"] = "TAMPERED"
        valid, idx = crucible.verify_provenance_chain()
        assert valid is False
        assert idx == 0

    def test_genesis_block_zeros(self, crucible):
        crucible.record_provenance("read_file", {"path": "a.py"})
        entry = crucible._provenance[0]
        assert entry["prev_hash"] == ("00" * 64)

    def test_entries_have_hmac_fields(self, crucible):
        crucible.record_provenance("read_file", {"path": "a.py"})
        entry = crucible._provenance[0]
        assert "hmac" in entry
        assert "prev_hash" in entry
        assert len(entry["hmac"]) == 128  # SHA-512 hex = 128 chars

    def test_chain_survives_many_entries(self, crucible):
        for i in range(100):
            crucible.record_provenance("tool_call", {"index": i})
        valid, idx = crucible.verify_provenance_chain()
        assert valid is True
        assert idx == -1
        assert len(crucible.get_provenance_chain(last_n=99999)) == 100
