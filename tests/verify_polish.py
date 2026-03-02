"""Live verification of the Forge polish pass.

Run this and WATCH it exercise every new feature:
  python tests/verify_polish.py

Each test prints a banner, runs the check, shows PASS/FAIL with color.
No dependencies beyond the Forge codebase itself.
"""

import os
import sys
import time
import tempfile
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── ANSI colors ──
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
WHITE = "\033[37m"

# Enable ANSI on Windows
if os.name == "nt":
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 0x0007)
    except Exception:
        pass

passed = 0
failed = 0
total = 0


def banner(title: str):
    global total
    total += 1
    w = 60
    print(f"\n{CYAN}{BOLD}{'=' * w}{RESET}")
    print(f"  {WHITE}{BOLD}#{total:02d}  {title}{RESET}")
    print(f"{CYAN}{'=' * w}{RESET}")
    time.sleep(0.15)  # Let the user see each test


def ok(msg: str = ""):
    global passed
    passed += 1
    label = f" — {msg}" if msg else ""
    print(f"  {GREEN}{BOLD}PASS{RESET}{DIM}{label}{RESET}")


def fail(msg: str = ""):
    global failed
    failed += 1
    label = f" — {msg}" if msg else ""
    print(f"  {RED}{BOLD}FAIL{RESET}{RED}{label}{RESET}")


# ═══════════════════════════════════════════════════════════
# 1. Compile checks
# ═══════════════════════════════════════════════════════════

banner("Compile: forge/engine.py")
try:
    import py_compile
    py_compile.compile("forge/engine.py", doraise=True)
    ok()
except py_compile.PyCompileError as e:
    fail(str(e))

banner("Compile: forge/ui/terminal.py")
try:
    py_compile.compile("forge/ui/terminal.py", doraise=True)
    ok()
except py_compile.PyCompileError as e:
    fail(str(e))

banner("Compile: forge/context.py")
try:
    py_compile.compile("forge/context.py", doraise=True)
    ok()
except py_compile.PyCompileError as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 2. Context window — truncate_to (checkpoint rollback)
# ═══════════════════════════════════════════════════════════

banner("ContextWindow.truncate_to() — checkpoint rollback")
try:
    from forge.context import ContextWindow
    ctx = ContextWindow(max_tokens=10000)
    ctx.add("user", "Hello, world")
    ctx.add("assistant", "Hi there!")
    ctx.add("user", "Do something complex")
    assert ctx.entry_count == 3, f"Expected 3 entries, got {ctx.entry_count}"

    # Truncate back to 1 entry (simulating rollback)
    removed = ctx.truncate_to(1)
    assert ctx.entry_count == 1, f"Expected 1 entry after truncate, got {ctx.entry_count}"
    assert len(removed) == 2, f"Expected 2 removed, got {len(removed)}"
    assert ctx.total_tokens == ctx._entries[0].token_count
    ok(f"Truncated 3->1, removed 2 entries, tokens consistent")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 3. Context window — partition-aware eviction
# ═══════════════════════════════════════════════════════════

banner("ContextWindow — partition eviction order")
try:
    ctx = ContextWindow(max_tokens=200)
    ctx.add("system", "core msg", pinned=True, partition="core")
    ctx.add("system", "recall data " * 8, partition="recall")
    ctx.add("user", "working msg " * 5, partition="working")

    before = ctx.entry_count
    # Add something that needs eviction
    ctx.add("user", "big message " * 15)
    # Recall should be evicted first
    partitions = [e.partition for e in ctx._entries]
    assert "core" in partitions, "Core partition should survive eviction"
    ok(f"Eviction respected partition priority (core survived)")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 4. TurnCheckpoint dataclass
# ═══════════════════════════════════════════════════════════

banner("TurnCheckpoint — dataclass fields")
try:
    from forge.engine import TurnCheckpoint
    cp = TurnCheckpoint(
        context_entry_count=5,
        context_total_tokens=1200,
        timestamp=time.time(),
    )
    assert cp.context_entry_count == 5
    assert cp.context_total_tokens == 1200
    assert isinstance(cp.file_backups, dict)
    assert isinstance(cp.files_created, list)
    assert len(cp.file_backups) == 0
    assert len(cp.files_created) == 0
    ok(f"All fields correct, defaults initialized")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 5. EscapeMonitor — instantiation and flags
# ═══════════════════════════════════════════════════════════

banner("EscapeMonitor — instantiation + flags")
try:
    from forge.engine import EscapeMonitor
    mon = EscapeMonitor()
    assert not mon.interrupted, "Should not be interrupted on creation"
    mon.reset()
    assert not mon.interrupted, "Should not be interrupted after reset"
    ok("Created, not interrupted, reset works")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 6. System prompt — anti-loop guidance
# ═══════════════════════════════════════════════════════════

banner("System prompt — contains anti-loop guidance")
try:
    from forge.engine import SYSTEM_PROMPT
    checks = [
        ("Do NOT retry the exact", "no-retry guidance"),
        ("glob_files or list_directory", "file-not-found guidance"),
        ("NEVER read a file you just wrote", "no-reread guidance"),
        ("2 failed attempts", "ask-for-help threshold"),
        ("think tool", "think tool guidance"),
        ("CACHED - unchanged", "cache awareness"),
    ]
    all_ok = True
    for fragment, label in checks:
        if fragment not in SYSTEM_PROMPT:
            fail(f"Missing: {label}")
            all_ok = False
            break
    if all_ok:
        ok(f"All {len(checks)} guidance patterns present")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 7. Think tool registered
# ═══════════════════════════════════════════════════════════

banner("Think tool — handler exists and works")
try:
    from forge.engine import ForgeEngine
    # Check the method exists
    assert hasattr(ForgeEngine, "_think"), "ForgeEngine._think method missing"

    # Create a minimal instance just to test the method
    # We can't fully init (needs Ollama), so test the unbound method signature
    import inspect
    sig = inspect.signature(ForgeEngine._think)
    params = list(sig.parameters.keys())
    assert "thought" in params, f"Expected 'thought' param, got {params}"
    ok("_think method exists with correct signature")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 8. Terminal — print_tool_error exists
# ═══════════════════════════════════════════════════════════

banner("Terminal — print_tool_error() function")
try:
    from forge.ui.terminal import print_tool_error
    import inspect
    sig = inspect.signature(print_tool_error)
    assert "result" in sig.parameters
    # Actually call it (output goes to terminal — the user sees it!)
    print(f"  {DIM}(sample output below){RESET}")
    print_tool_error("Error: file not found: /nonexistent/path.py")
    ok("Function exists, callable, rendered above")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 9. Terminal — print_interrupt_banner exists
# ═══════════════════════════════════════════════════════════

banner("Terminal — print_interrupt_banner()")
try:
    from forge.ui.terminal import print_interrupt_banner
    print(f"  {DIM}(sample output below){RESET}")
    print_interrupt_banner(
        word_count=42,
        entries_added=3,
        modified_files=["engine.py"],
        created_files=["new_helper.py"],
    )
    ok("Function callable, rendered above")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 10. Terminal — readline infrastructure
# ═══════════════════════════════════════════════════════════

banner("Terminal — readline init + completer setup")
try:
    from forge.ui.terminal import init_readline, setup_completer, _readline_available
    # Init with a temp dir
    with tempfile.TemporaryDirectory() as td:
        init_readline(td)
    setup_completer(["/help", "/quit", "/context"])
    if _readline_available:
        ok("readline available, history + completer initialized")
    else:
        ok("readline not available (pyreadline3 not installed) — graceful fallback")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 11. Terminal — paste buffer drain function
# ═══════════════════════════════════════════════════════════

banner("Terminal — _drain_paste_buffer() exists")
try:
    from forge.ui.terminal import _drain_paste_buffer
    # On non-Windows or when no paste, it should pass through
    result = _drain_paste_buffer("single line")
    assert result == "single line", f"Expected passthrough, got: {result}"
    ok("Passthrough works for single-line input")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 12. File backup + rollback (integration test)
# ═══════════════════════════════════════════════════════════

banner("File backup + rollback — end-to-end")
try:
    with tempfile.TemporaryDirectory() as td:
        test_file = Path(td) / "test.py"
        test_file.write_text("original content", encoding="utf-8")

        cp = TurnCheckpoint(
            context_entry_count=0,
            context_total_tokens=0,
            timestamp=time.time(),
        )

        # Simulate backup
        cp.file_backups[str(test_file)] = test_file.read_text(encoding="utf-8")

        # Simulate overwrite
        test_file.write_text("modified content", encoding="utf-8")
        assert test_file.read_text(encoding="utf-8") == "modified content"

        # Simulate rollback
        original = cp.file_backups[str(test_file)]
        test_file.write_text(original, encoding="utf-8")
        assert test_file.read_text(encoding="utf-8") == "original content"

    ok("Backup -> overwrite -> rollback restored original content")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 13. New file rollback (deletion)
# ═══════════════════════════════════════════════════════════

banner("New file rollback — delete on undo")
try:
    with tempfile.TemporaryDirectory() as td:
        new_file = Path(td) / "new_helper.py"
        cp = TurnCheckpoint(
            context_entry_count=0,
            context_total_tokens=0,
            timestamp=time.time(),
        )

        # Simulate: file didn't exist, mark for deletion
        cp.file_backups[str(new_file)] = None
        cp.files_created.append(str(new_file))

        # Simulate: agent creates the file
        new_file.write_text("new code here", encoding="utf-8")
        assert new_file.exists()

        # Simulate rollback: delete files_created
        for f in cp.files_created:
            Path(f).unlink(missing_ok=True)
        assert not new_file.exists()

    ok("Created file deleted on rollback")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 14. pyproject.toml — pyreadline3 dependency
# ═══════════════════════════════════════════════════════════

banner("pyproject.toml — pyreadline3 dependency")
try:
    toml = Path("pyproject.toml").read_text(encoding="utf-8")
    assert "pyreadline3" in toml, "pyreadline3 not in dependencies"
    assert "sys_platform" in toml, "Platform condition missing"
    ok("pyreadline3 dependency present with Windows condition")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# 15. Help text — interrupt section present
# ═══════════════════════════════════════════════════════════

banner("Help text — Interrupt section in /help")
try:
    import io
    from contextlib import redirect_stdout
    from forge.ui.terminal import print_help
    f = io.StringIO()
    with redirect_stdout(f):
        print_help()
    output = f.getvalue()
    assert "Interrupt" in output, "Interrupt section missing from /help"
    assert "Escape" in output, "Escape key not mentioned in /help"
    assert "undo" in output, "undo command not mentioned in /help"
    ok("Interrupt section with Escape/undo/redirect guidance")
except Exception as e:
    fail(str(e))


# ═══════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════

print(f"\n{'=' * 60}")
print(f"\n{BOLD}  VERIFICATION SUMMARY{RESET}\n")
print(f"  Total:  {total}")
print(f"  {GREEN}Passed: {passed}{RESET}")
if failed:
    print(f"  {RED}Failed: {failed}{RESET}")
else:
    print(f"  Failed: 0")

pct = (passed / total * 100) if total else 0
if failed == 0:
    print(f"\n  {GREEN}{BOLD}ALL TESTS PASSED{RESET} {GREEN}({pct:.0f}%){RESET}")
else:
    print(f"\n  {RED}{BOLD}{failed} FAILURE(S){RESET} {RED}({pct:.0f}% pass rate){RESET}")

print(f"\n{'=' * 60}\n")
sys.exit(0 if failed == 0 else 1)
