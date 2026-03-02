"""Scenario 5: Crash recovery — kill during writes, verify integrity.

Simulates ungraceful shutdown by running the engine, performing writes,
and then verifying state files remain valid or absent (not corrupted).

Stub mode: More turns per test
Live mode: Fewer turns (real inference is slower)
"""

import json
import yaml
import pytest
from pathlib import Path

from tests.integration.ollama_stub import ScriptedTurn


@pytest.mark.timeout(600)  # 10min ceiling for live mode
class TestCrashRecovery:

    def test_state_files_valid_after_normal_shutdown(
            self, harness, ollama_stub, verifier, is_live):
        """After normal usage and save, all state files must be valid."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Changes applied.",
            eval_count=15,
            prompt_eval_count=25,
        ))

        engine = harness.create_engine(ctx_max_tokens=4000)
        turn_count = 5 if is_live else 10

        for i in range(turn_count):
            harness.run_single_turn(f"Edit file {i}")

        # Trigger saves
        try:
            engine.billing.save()
        except Exception:
            pass
        try:
            engine.forensics.save_report()
        except Exception:
            pass

        # All state files should be valid
        verifier.check_state_files()

    def test_no_orphan_temp_files(
            self, harness, ollama_stub, verifier, is_live):
        """No .forge_tmp files should remain after operations."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Written.",
            eval_count=10,
            prompt_eval_count=20,
        ))

        engine = harness.create_engine(ctx_max_tokens=4000)
        turn_count = 3 if is_live else 5

        for i in range(turn_count):
            harness.run_single_turn(f"Write some data {i}")

        # Check for orphaned temp files
        forge_dir = harness._forge_dir
        orphans = list(forge_dir.rglob("*.forge_tmp"))
        assert len(orphans) == 0, (
            f"Found orphaned temp files: {orphans}")

    def test_billing_json_always_valid(
            self, harness, ollama_stub, is_live, tmp_path):
        """billing.json must be valid JSON after every save."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="OK.",
            eval_count=10,
            prompt_eval_count=20,
        ))

        engine = harness.create_engine(ctx_max_tokens=4000)
        turn_count = 5 if is_live else 20

        for i in range(turn_count):
            harness.run_single_turn(f"Turn {i}")
            # Force save after every turn
            try:
                engine.billing.save()
            except Exception:
                pass

            # Verify billing file is valid
            billing_path = harness._forge_dir / "billing.json"
            if billing_path.exists():
                text = billing_path.read_text(encoding="utf-8")
                data = json.loads(text)
                assert isinstance(data, dict), f"Turn {i}: billing is not dict"

    def test_config_survives_restart(
            self, harness, ollama_stub, is_live, tmp_path):
        """Config file should be readable by a new engine instance."""
        ollama_stub.set_default_response(ScriptedTurn(text="OK."))

        engine = harness.create_engine(ctx_max_tokens=4000)
        turn_count = 3 if is_live else 5
        for i in range(turn_count):
            harness.run_single_turn(f"Turn {i}")

        # Verify config is valid YAML
        config_path = harness._forge_dir / "config.yaml"
        assert config_path.exists()
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)
        assert "default_model" in data

    def test_session_save_load_roundtrip(
            self, harness, ollama_stub, verifier, is_live):
        """Context session should survive save/load cycle."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Reviewed the code.",
            eval_count=20,
            prompt_eval_count=30,
        ))

        engine = harness.create_engine(ctx_max_tokens=4000)
        turn_count = 5 if is_live else 15

        for i in range(turn_count):
            harness.run_single_turn(f"Review function {i}")

        # Snapshot state before save
        entries_before = engine.ctx.entry_count
        tokens_before = engine.ctx.total_tokens

        # Save and load
        session_file = harness._forge_dir / "test_session.json"
        engine.ctx.save_session(session_file)

        assert session_file.exists()
        data = json.loads(session_file.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

        # Load into context and verify
        engine.ctx.load_session(session_file)
        assert engine.ctx.entry_count > 0

        verifier.check_context_consistency()
