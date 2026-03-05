"""Tests for PluginManager thread-safety."""

import threading
import time
import pytest
from pathlib import Path
from forge.plugins import PluginManager
from forge.plugins.base import ForgePlugin


class SlowPlugin(ForgePlugin):
    name = "Slow"
    version = "1.0.0"
    description = "A slow plugin for testing."
    author = "test"

    def on_user_input(self, text: str) -> str:
        time.sleep(0.01)  # Simulate slow processing
        return text + " [slow]"


class FastPlugin(ForgePlugin):
    name = "Fast"
    version = "1.0.0"
    description = "A fast plugin for testing."
    author = "test"

    def on_user_input(self, text: str) -> str:
        return text + " [fast]"


class CrashPlugin(ForgePlugin):
    name = "Crash"
    version = "1.0.0"
    description = "Always crashes."
    author = "test"

    def on_user_input(self, text: str) -> str:
        raise RuntimeError("boom")


class TestPluginManagerLock:
    def test_has_lock(self):
        pm = PluginManager(plugin_dir=Path("/nonexistent"))
        assert hasattr(pm, "_lock")
        assert isinstance(pm._lock, type(threading.RLock()))

    def test_get_loaded_returns_copy(self):
        pm = PluginManager(plugin_dir=Path("/nonexistent"))
        pm._loaded.append(FastPlugin())
        loaded = pm.get_loaded()
        loaded.clear()  # Shouldn't affect internal list
        assert len(pm._loaded) == 1

    def test_concurrent_dispatch(self):
        """Multiple threads dispatching simultaneously should not crash."""
        pm = PluginManager(plugin_dir=Path("/nonexistent"))
        pm._loaded.append(SlowPlugin())
        pm._loaded.append(FastPlugin())

        results = []
        errors = []

        def dispatch_thread(text):
            try:
                result = pm.dispatch_user_input(text)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=dispatch_thread, args=(f"msg_{i}",))
            for i in range(10)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(errors) == 0, f"Errors during concurrent dispatch: {errors}"
        assert len(results) == 10

    def test_concurrent_dispatch_with_removal(self):
        """Auto-disable during concurrent dispatch should not crash."""
        pm = PluginManager(plugin_dir=Path("/nonexistent"))
        crash = CrashPlugin()
        crash._error_count = 4  # One more error will trigger auto-disable
        pm._loaded.append(crash)
        pm._loaded.append(FastPlugin())

        results = []
        errors = []

        def dispatch_thread(text):
            try:
                result = pm.dispatch_user_input(text)
                results.append(result)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=dispatch_thread, args=(f"msg_{i}",))
            for i in range(5)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # No crashes
        assert len(errors) == 0, f"Errors: {errors}"

    def test_sorted_by_priority_thread_safe(self):
        """_sorted_by_priority should snapshot _loaded under lock."""
        pm = PluginManager(plugin_dir=Path("/nonexistent"))
        pm._loaded.append(SlowPlugin())
        pm._loaded.append(FastPlugin())

        # Call from multiple threads
        results = []
        def get_sorted():
            r = pm._sorted_by_priority("on_user_input")
            results.append(len(r))

        threads = [threading.Thread(target=get_sorted) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        assert len(results) == 10
        assert all(r == 2 for r in results)
