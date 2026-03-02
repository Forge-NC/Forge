"""Scenario 11: Tool-call corruption.

Tests how the engine handles malformed, hallucinated, and corrupted
tool calls from the LLM — partial JSON, wrong schema, unknown tools,
duplicate fields. Verifies no garbage silently poisons state.
"""

import pytest
from tests.integration.ollama_stub import ScriptedTurn


@pytest.mark.stub_only
@pytest.mark.timeout(60)
class TestToolCorruption:

    def test_hallucinated_tool_name(self, harness, ollama_stub, verifier):
        """LLM calls a tool that doesn't exist. Engine should error gracefully."""
        ollama_stub.set_script([
            ScriptedTurn(
                text="I'll use a special tool for this.",
                tool_calls=[{
                    "function": {
                        "name": "quantum_analyze",
                        "arguments": {"target": "main.py"},
                    }
                }],
                eval_count=20,
                prompt_eval_count=30,
            ),
            # Follow-up: normal response after the failed tool call
            ScriptedTurn(
                text="The tool was not available. Let me try a different approach.",
                eval_count=20,
                prompt_eval_count=30,
            ),
        ])

        engine = harness.create_engine(ctx_max_tokens=4000)
        result = harness.run_single_turn("Analyze main.py")

        # Engine should have handled the unknown tool gracefully
        assert engine.ctx.entry_count > 0

        # The error output should contain "unknown tool"
        errors = harness.io.get_output("tool_error")
        assert any("unknown tool" in e.lower() for e in errors), (
            f"Expected 'unknown tool' error, got: {errors}")

        verifier.check_all()

    def test_empty_tool_name(self, harness, ollama_stub, verifier):
        """LLM sends a tool call with empty name."""
        ollama_stub.set_script([
            ScriptedTurn(
                text="Processing...",
                tool_calls=[{
                    "function": {
                        "name": "",
                        "arguments": {},
                    }
                }],
                eval_count=15,
                prompt_eval_count=25,
            ),
            ScriptedTurn(
                text="Done.",
                eval_count=10,
                prompt_eval_count=20,
            ),
        ])

        engine = harness.create_engine(ctx_max_tokens=4000)
        result = harness.run_single_turn("Do something")

        # Should not crash
        assert engine.ctx.entry_count > 0
        verifier.check_all()

    def test_malformed_arguments_string(self, harness, ollama_stub, verifier):
        """LLM sends arguments as a raw string instead of dict."""
        ollama_stub.set_script([
            ScriptedTurn(
                text="Let me read that file.",
                tool_calls=[{
                    "function": {
                        "name": "read_file",
                        "arguments": "this is not json at all!!!",
                    }
                }],
                eval_count=15,
                prompt_eval_count=25,
            ),
            ScriptedTurn(
                text="I see the issue.",
                eval_count=10,
                prompt_eval_count=20,
            ),
        ])

        engine = harness.create_engine(ctx_max_tokens=4000)
        result = harness.run_single_turn("Read the config")

        # Engine should handle malformed args without crashing
        assert engine.ctx.entry_count > 0
        verifier.check_all()

    def test_wrong_argument_types(self, harness, ollama_stub, verifier):
        """LLM sends wrong types for arguments (int instead of string)."""
        ollama_stub.set_script([
            ScriptedTurn(
                text="Reading file...",
                tool_calls=[{
                    "function": {
                        "name": "read_file",
                        "arguments": {"file_path": 12345},
                    }
                }],
                eval_count=15,
                prompt_eval_count=25,
            ),
            ScriptedTurn(
                text="That didn't work. Let me try properly.",
                eval_count=10,
                prompt_eval_count=20,
            ),
        ])

        engine = harness.create_engine(ctx_max_tokens=4000)
        result = harness.run_single_turn("Read file 12345")

        assert engine.ctx.entry_count > 0
        verifier.check_all()

    def test_duplicate_tool_calls_in_single_response(
            self, harness, ollama_stub, verifier):
        """LLM sends the same tool call multiple times in one response."""
        ollama_stub.set_script([
            ScriptedTurn(
                text="Let me check that.",
                tool_calls=[
                    {"function": {"name": "read_file",
                                  "arguments": {"file_path": "/tmp/foo.py"}}},
                    {"function": {"name": "read_file",
                                  "arguments": {"file_path": "/tmp/foo.py"}}},
                    {"function": {"name": "read_file",
                                  "arguments": {"file_path": "/tmp/foo.py"}}},
                ],
                eval_count=15,
                prompt_eval_count=25,
            ),
            ScriptedTurn(
                text="Got it.",
                eval_count=10,
                prompt_eval_count=20,
            ),
        ])

        engine = harness.create_engine(ctx_max_tokens=4000)
        result = harness.run_single_turn("Read foo.py three times")

        # Should handle via dedup — not crash
        assert engine.ctx.entry_count > 0
        verifier.check_all()

    def test_missing_function_key(self, harness, ollama_stub, verifier):
        """LLM sends tool call dict without 'function' key."""
        ollama_stub.set_script([
            ScriptedTurn(
                text="Executing...",
                tool_calls=[
                    {"name": "read_file", "arguments": {"file_path": "x.py"}},
                ],
                eval_count=15,
                prompt_eval_count=25,
            ),
            ScriptedTurn(
                text="Done.",
                eval_count=10,
                prompt_eval_count=20,
            ),
        ])

        engine = harness.create_engine(ctx_max_tokens=4000)
        result = harness.run_single_turn("Do it")

        # The stub wraps non-function dicts with {"function": tc},
        # so this should still work. Verify no crash.
        assert engine.ctx.entry_count > 0
        verifier.check_all()

    def test_rapid_tool_errors_dont_crash(self, harness, ollama_stub, verifier):
        """10 turns of tools that always error shouldn't crash engine."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Trying to read...",
            tool_calls=[{
                "function": {
                    "name": "read_file",
                    "arguments": {"file_path": "/nonexistent/path/file.py"},
                }
            }],
            eval_count=15,
            prompt_eval_count=25,
        ))

        engine = harness.create_engine(ctx_max_tokens=4000)

        for i in range(10):
            harness.run_single_turn(f"Try reading file {i}")

        # Engine should still be functional
        assert engine.ctx.entry_count > 0
        # Token accounting intact
        computed = sum(e.token_count for e in engine.ctx._entries)
        assert computed == engine.ctx._total_tokens

        verifier.check_all()

    def test_tool_corruption_then_normal(self, harness, ollama_stub, verifier):
        """Engine recovers to normal operation after corrupt tool calls."""
        ollama_stub.set_script([
            # Corrupt: hallucinated tool
            ScriptedTurn(
                text="Using special tool...",
                tool_calls=[{
                    "function": {
                        "name": "fake_nonexistent_tool",
                        "arguments": {"x": "y"},
                    }
                }],
                eval_count=15,
                prompt_eval_count=25,
            ),
            # Follow-up: normal response
            ScriptedTurn(
                text="Let me try differently.",
                eval_count=10,
                prompt_eval_count=20,
            ),
            # Second turn: completely normal
            ScriptedTurn(
                text="All done. The code looks correct.",
                eval_count=15,
                prompt_eval_count=25,
            ),
        ])

        engine = harness.create_engine(ctx_max_tokens=4000)
        result1 = harness.run_single_turn("Fix the bug")
        result2 = harness.run_single_turn("How does it look now?")

        # Second turn should work normally
        assert engine.ctx.entry_count > 2
        verifier.check_all()
