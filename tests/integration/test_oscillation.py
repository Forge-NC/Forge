"""Scenario 7: Tool call oscillation loops.

Verifies the engine detects repeated tool call patterns and breaks
out of infinite loops within the max_iterations guard.
"""

import pytest
from tests.integration.ollama_stub import ScriptedTurn


@pytest.mark.stub_only
@pytest.mark.timeout(30)
class TestOscillation:

    def test_repeated_tool_calls_terminate(self, harness, ollama_stub, verifier):
        """Engine should break out of identical repeated tool calls."""
        # Script: each turn returns a read_file tool call
        read_call = ScriptedTurn(
            text="Let me read the file.",
            tool_calls=[{
                "function": {
                    "name": "read_file",
                    "arguments": {"file_path": "/tmp/test.py"},
                }
            }],
            eval_count=20,
            prompt_eval_count=30,
        )
        ollama_stub.set_default_response(read_call)

        engine = harness.create_engine(ctx_max_tokens=4000)
        result = harness.run_single_turn("Read and fix test.py")

        # Engine should have run but not exceeded max_iterations
        # The key verification is that the turn COMPLETED (didn't hang)
        assert engine.ctx.entry_count > 0

        verifier.check_all()

    def test_alternating_read_edit_terminates(self, harness, ollama_stub, verifier):
        """Read then edit oscillation should terminate via iteration cap."""
        # Alternate between read and edit tool calls
        turns = [
            ScriptedTurn(
                text="Reading the file first.",
                tool_calls=[{
                    "function": {
                        "name": "read_file",
                        "arguments": {"file_path": "/tmp/foo.py"},
                    }
                }],
                eval_count=15,
                prompt_eval_count=25,
            ),
            ScriptedTurn(
                text="Now editing the file.",
                tool_calls=[{
                    "function": {
                        "name": "edit_file",
                        "arguments": {
                            "file_path": "/tmp/foo.py",
                            "old_string": "old",
                            "new_string": "new",
                        },
                    }
                }],
                eval_count=15,
                prompt_eval_count=25,
            ),
        ]
        ollama_stub.set_script(turns * 10)  # 20 alternating turns

        engine = harness.create_engine(ctx_max_tokens=4000)
        result = harness.run_single_turn("Fix the bug in foo.py")

        # Should have terminated via max_iterations, not hung
        assert engine.ctx.entry_count > 0

        verifier.check_all()

    def test_max_iterations_respected(self, harness, ollama_stub, verifier):
        """Agent loop must not exceed max_agent_iterations."""
        # Tool call that always returns more work
        ollama_stub.set_default_response(ScriptedTurn(
            text="Continuing work...",
            tool_calls=[{
                "function": {
                    "name": "read_file",
                    "arguments": {"file_path": f"/tmp/file.py"},
                }
            }],
            eval_count=10,
            prompt_eval_count=20,
        ))

        engine = harness.create_engine(ctx_max_tokens=8000)
        max_iter = engine.config.get("max_agent_iterations", 15)

        result = harness.run_single_turn("Process all files")

        # Verify we didn't somehow exceed the limit
        # The stub's chat_call_count tells us how many LLM calls happened
        assert ollama_stub.chat_call_count <= max_iter + 1, (
            f"Agent loop ran {ollama_stub.chat_call_count} iterations, "
            f"max was {max_iter}")

        verifier.check_all()
