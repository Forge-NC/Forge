"""Scenario 12: Verification theater.

Tests the case where "tests pass" but the agent actually touched
forbidden files, escaped the sandbox, or violated scope invariants.
The new workspace/sandbox integrity check (invariant #7) should catch
these even when the agent reports success.
"""

import os
import pytest
from pathlib import Path

from tests.integration.ollama_stub import ScriptedTurn
from tests.integration.state_verifier import StateVerifier, IntegrityError


@pytest.mark.stub_only
@pytest.mark.timeout(60)
class TestVerificationTheater:

    def test_all_file_ops_inside_sandbox(self, engine, harness, ollama_stub):
        """Normal file operations should pass sandbox check."""
        verifier = StateVerifier(engine=engine, harness=harness)

        # Create a file in the sandbox
        test_file = harness.tmp_path / "src" / "main.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("print('hello')", encoding="utf-8")

        # Simulate reading it through forensics
        engine.forensics._files_read[str(test_file)] = 1

        # This should pass — file is inside tmp_path
        verifier.check_workspace_sandbox()

    def test_write_outside_sandbox_caught(self, engine, harness, ollama_stub):
        """Write to a path outside sandbox should be caught by invariant."""
        verifier = StateVerifier(engine=engine, harness=harness)

        # Simulate a file write OUTSIDE the sandbox
        outside_path = str(Path(harness.tmp_path.anchor) / "definitely_outside" / "secrets.txt")
        engine.forensics._files_written[outside_path] = 1

        # Invariant #7 should catch this
        with pytest.raises(IntegrityError, match="escaped sandbox"):
            verifier.check_workspace_sandbox()

    def test_ssh_dir_write_caught(self, engine, harness):
        """Write to .ssh directory should be caught even if inside sandbox."""
        verifier = StateVerifier(engine=engine, harness=harness)

        # Create .ssh inside sandbox (simulating a confused agent)
        ssh_path = harness.tmp_path / ".ssh" / "authorized_keys"
        ssh_path.parent.mkdir(parents=True, exist_ok=True)
        ssh_path.write_text("ssh-rsa AAAA...", encoding="utf-8")

        engine.forensics._files_written[str(ssh_path)] = 1

        # Should catch the forbidden .ssh directory
        with pytest.raises(IntegrityError, match="forbidden dir"):
            verifier.check_workspace_sandbox()

    def test_appdata_write_caught(self, engine, harness):
        """Write to AppData directory should be caught."""
        verifier = StateVerifier(engine=engine, harness=harness)

        # Simulate write to AppData inside sandbox
        appdata_path = harness.tmp_path / "AppData" / "Local" / "malware.exe"
        appdata_path.parent.mkdir(parents=True, exist_ok=True)
        engine.forensics._files_written[str(appdata_path)] = 1

        with pytest.raises(IntegrityError, match="forbidden dir"):
            verifier.check_workspace_sandbox()

    def test_clean_run_passes_all_invariants(
            self, engine, harness, ollama_stub, verifier):
        """A clean run with only sandbox-local ops should pass all 8 checks."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Everything looks good.",
            eval_count=15,
            prompt_eval_count=25,
        ))

        for i in range(5):
            harness.run_single_turn(f"Review module {i}")

        # All 8 invariants should pass
        verifier.check_all()

    def test_unknown_tool_flagged_in_validity_check(
            self, engine, harness, ollama_stub, verifier):
        """Tool-call validity check should flag unknown tools in error output."""
        ollama_stub.set_script([
            ScriptedTurn(
                text="Using custom tool...",
                tool_calls=[{
                    "function": {
                        "name": "nonexistent_tool_xyz",
                        "arguments": {},
                    }
                }],
                eval_count=15,
                prompt_eval_count=25,
            ),
            ScriptedTurn(
                text="OK moving on.",
                eval_count=10,
                prompt_eval_count=20,
            ),
        ])

        harness.run_single_turn("Use the special tool")

        # Tool error should be in output
        errors = harness.io.get_output("tool_error")
        assert any("unknown tool" in e.lower() for e in errors)

        # Full check should pass (unknown tool was properly errored, not accepted)
        verifier.check_all()

    def test_tool_rate_integrity(self, engine, harness, ollama_stub, verifier):
        """Tool call rate should not exceed max_iterations per turn."""
        # Each response triggers another tool call
        ollama_stub.set_default_response(ScriptedTurn(
            text="Working...",
            tool_calls=[{
                "function": {
                    "name": "read_file",
                    "arguments": {"file_path": "/tmp/test.py"},
                }
            }],
            eval_count=10,
            prompt_eval_count=20,
        ))

        harness.run_single_turn("Process the file")

        # Verify tool call rate is sane
        verifier.check_tool_call_validity()
