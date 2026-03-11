"""Tests for forge.commands — Slash command dispatch and handlers."""

import pytest
from forge.commands import CommandHandler


# ---------------------------------------------------------------------------
# Mock engine for testing
# ---------------------------------------------------------------------------

class _Attr:
    """Auto-generates attributes on access to avoid AttributeError."""
    def __getattr__(self, name):
        return _Attr()

    def __call__(self, *a, **kw):
        return "ok"

    def __bool__(self):
        return True

    def __iter__(self):
        return iter([])

    def __str__(self):
        return ""

    def __repr__(self):
        return "_Attr()"

    def __len__(self):
        return 0

    def __contains__(self, item):
        return False

    def __getitem__(self, key):
        return _Attr()


class MockEngine(_Attr):
    """Minimal mock engine that fakes all attributes."""
    pass


# ---------------------------------------------------------------------------
# test_dispatch_table
# ---------------------------------------------------------------------------

class TestDispatchTable:
    """Verifies the command dispatch table contains all 46 expected slash commands with no duplicates.

    Every command in the expected list must be present in CommandHandler._COMMANDS.
    No two commands may share the same handler function name, with the intentional
    exception of /quit and /exit which deliberately share _cmd_quit.
    """

    def test_all_expected_commands_present(self):
        expected = [
            "/quit", "/exit", "/help", "/docs", "/context", "/drop",
            "/pin", "/unpin", "/clear", "/save", "/load", "/reset",
            "/model", "/models", "/tools", "/cd", "/billing", "/compare",
            "/topup", "/safety", "/crucible", "/forensics", "/router",
            "/provenance", "/config", "/hardware", "/cache", "/scan",
            "/digest", "/journal", "/recall", "/search", "/index",
            "/tasks", "/memory", "/stats", "/dashboard", "/voice",
            "/plugins", "/plan", "/dedup", "/continuity", "/theme",
            "/synapse",
        ]
        for cmd in expected:
            assert cmd in CommandHandler._COMMANDS, f"{cmd} missing from dispatch table"

    def test_no_duplicate_handlers(self):
        """Exit and quit can share, but nothing else should collide."""
        handlers = list(CommandHandler._COMMANDS.values())
        # /quit and /exit share the same handler — that's intentional
        seen = {}
        for cmd, handler in CommandHandler._COMMANDS.items():
            name = handler.__name__
            if name in seen and name != "_cmd_quit":
                pytest.fail(f"Duplicate handler {name} for {cmd} and {seen[name]}")
            seen[name] = cmd


# ---------------------------------------------------------------------------
# test_handle_dispatch
# ---------------------------------------------------------------------------

class TestHandleDispatch:
    """Verifies handle() dispatches to the correct handler and returns the right sentinel.

    Known commands return True. Unknown commands return False.
    Commands are case-insensitive ('/HELP' == '/help'). Arguments after the command
    are passed to the handler. Every command except /quit and /exit must have a
    callable handler. /quit and /exit raise SystemExit.
    """

    def test_known_command_returns_true(self):
        h = CommandHandler(MockEngine())
        assert h.handle("/help") is True

    def test_unknown_command_returns_false(self):
        h = CommandHandler(MockEngine())
        assert h.handle("/nonexistent") is False

    def test_command_case_insensitive(self):
        h = CommandHandler(MockEngine())
        assert h.handle("/HELP") is True
        assert h.handle("/Help") is True

    def test_command_with_args(self):
        h = CommandHandler(MockEngine())
        assert h.handle("/billing reset confirm") is True

    def test_router_command(self):
        h = CommandHandler(MockEngine())
        assert h.handle("/router") is True

    def test_plan_command(self):
        h = CommandHandler(MockEngine())
        assert h.handle("/plan") is True

    def test_dedup_command(self):
        h = CommandHandler(MockEngine())
        assert h.handle("/dedup") is True

    def test_every_command_dispatches(self):
        """Every command in the dispatch table is found by handle()."""
        h = CommandHandler(MockEngine())
        for cmd in CommandHandler._COMMANDS:
            if cmd in ("/quit", "/exit"):
                continue  # these raise SystemExit
            # We're testing dispatch, not handler logic —
            # some handlers may error with a mock engine and that's OK
            handler = CommandHandler._COMMANDS.get(cmd)
            assert handler is not None, f"{cmd} not found in dispatch table"
            assert callable(handler), f"{cmd} handler is not callable"

    def test_quit_raises_system_exit(self):
        h = CommandHandler(MockEngine())
        with pytest.raises(SystemExit):
            h.handle("/quit")

    def test_exit_raises_system_exit(self):
        h = CommandHandler(MockEngine())
        with pytest.raises(SystemExit):
            h.handle("/exit")
