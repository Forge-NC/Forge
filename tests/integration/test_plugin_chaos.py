"""Scenario 4: Plugin failures at every hook.

Injects a plugin that crashes on every hook invocation.
Verifies the engine auto-disables it after 5 errors and
continues operating normally.
"""

import pytest
from pathlib import Path
from tests.integration.ollama_stub import ScriptedTurn


# Plugin that crashes on every hook
CRASH_PLUGIN_CODE = '''
from forge.plugins.base import ForgePlugin

class AlwaysCrashPlugin(ForgePlugin):
    name = "AlwaysCrash"
    version = "1.0.0"
    description = "Crashes on every hook"
    author = "StressTest"

    def on_user_input(self, text):
        raise RuntimeError("Crash in on_user_input!")

    def on_response(self, text):
        raise RuntimeError("Crash in on_response!")

    def on_tool_call(self, tool_name, args):
        raise RuntimeError("Crash in on_tool_call!")

    def on_tool_result(self, tool_name, result):
        raise RuntimeError("Crash in on_tool_result!")

    def on_file_read(self, path, content):
        raise RuntimeError("Crash in on_file_read!")

    def on_file_write(self, path, content):
        raise RuntimeError("Crash in on_file_write!")
'''

# Plugin that grows memory unbounded
LEAKY_PLUGIN_CODE = '''
from forge.plugins.base import ForgePlugin

class MemoryLeakPlugin(ForgePlugin):
    name = "MemoryLeak"
    version = "1.0.0"
    description = "Grows unbounded list on every hook"
    author = "StressTest"

    def on_load(self, engine):
        self._leak = []

    def on_user_input(self, text):
        # Grow a list by 1000 items each call
        self._leak.extend(range(1000))
        return text
'''


@pytest.mark.stub_only
@pytest.mark.timeout(60)
class TestPluginChaos:

    def test_crash_plugin_auto_disabled(self, harness, ollama_stub, tmp_path):
        """AlwaysCrashPlugin should be auto-disabled after 5 errors."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="Response from the engine.",
            eval_count=20,
            prompt_eval_count=30,
        ))

        # Write the crash plugin to the plugin directory
        plugin_dir = tmp_path / ".forge" / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "crash_plugin.py").write_text(
            CRASH_PLUGIN_CODE, encoding="utf-8")

        engine = harness.create_engine(ctx_max_tokens=4000)

        # The crash plugin should have been discovered and loaded
        loaded_names = [p.name for p in engine.plugin_manager.get_loaded()]
        assert "AlwaysCrash" in loaded_names, (
            f"AlwaysCrash not loaded. Got: {loaded_names}")

        # Run turns — plugin should crash and eventually be auto-disabled
        for i in range(10):
            harness.run_single_turn(f"Test turn {i}")

        # After 5+ errors, plugin should be auto-disabled
        loaded_names_after = [p.name for p in engine.plugin_manager.get_loaded()]
        assert "AlwaysCrash" not in loaded_names_after, (
            "AlwaysCrash should have been auto-disabled after 5 errors")

        # Engine should still be functional
        result = harness.run_single_turn("Are you still working?")
        assert len(result.errors) == 0 or result.response

    def test_leaky_plugin_doesnt_crash_engine(self, harness, ollama_stub, tmp_path):
        """MemoryLeakPlugin shouldn't crash the engine even if it grows."""
        ollama_stub.set_default_response(ScriptedTurn(
            text="OK.",
            eval_count=10,
            prompt_eval_count=20,
        ))

        plugin_dir = tmp_path / ".forge" / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "leaky_plugin.py").write_text(
            LEAKY_PLUGIN_CODE, encoding="utf-8")

        engine = harness.create_engine(ctx_max_tokens=4000)

        # Run 20 turns — leaky plugin grows but engine survives
        for i in range(20):
            result = harness.run_single_turn(f"Leaky turn {i}")

        # Engine still functional
        assert engine.ctx.entry_count > 0

    def test_plugin_cannot_access_safety(self, harness, ollama_stub, tmp_path):
        """Plugin receiving restricted proxy cannot reach engine.safety."""
        ollama_stub.set_default_response(ScriptedTurn(text="OK."))

        # Plugin that tries to access restricted attributes
        snoop_code = '''
from forge.plugins.base import ForgePlugin

class SnoopPlugin(ForgePlugin):
    name = "Snoop"
    version = "1.0.0"
    description = "Tries to access restricted attributes"
    author = "StressTest"
    access_error = None

    def on_load(self, engine):
        try:
            _ = engine.safety
            SnoopPlugin.access_error = "No error raised!"
        except AttributeError as e:
            SnoopPlugin.access_error = str(e)
'''
        plugin_dir = tmp_path / ".forge" / "plugins"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "snoop_plugin.py").write_text(
            snoop_code, encoding="utf-8")

        engine = harness.create_engine(ctx_max_tokens=4000)

        # The plugin tried to access engine.safety and should have got AttributeError
        loaded = engine.plugin_manager.get_loaded()
        snoop = [p for p in loaded if p.name == "Snoop"]
        if snoop:
            # Plugin loaded successfully, meaning it handled the error
            from tests.integration.harness import StressHarness
            # Check the class-level attribute
            import importlib
            for mod_name, mod in __import__('sys').modules.items():
                if 'snoop' in mod_name.lower():
                    for attr in dir(mod):
                        cls = getattr(mod, attr, None)
                        if hasattr(cls, 'access_error') and cls.access_error:
                            assert "access denied" in cls.access_error.lower() or \
                                   "not available" in cls.access_error.lower(), \
                                f"Expected access denied, got: {cls.access_error}"
                            break
