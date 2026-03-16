"""Entry point for `python -m forge` or `forge` command."""

import argparse
import sys
import os
import logging


def _setup_crash_handler():
    """Enable faulthandler so native crashes (segfaults, illegal instructions)
    dump a traceback to ~/.forge/crash.log instead of dying silently."""
    import faulthandler
    try:
        crash_dir = os.path.join(os.path.expanduser("~"), ".forge")
        os.makedirs(crash_dir, exist_ok=True)
        crash_path = os.path.join(crash_dir, "crash.log")
        # Open in append mode so we keep history
        crash_file = open(crash_path, "a", encoding="utf-8")
        # Write timestamp header
        from datetime import datetime
        crash_file.write(f"\n=== faulthandler armed {datetime.now().isoformat()} ===\n")
        crash_file.flush()
        faulthandler.enable(file=crash_file, all_threads=True)
    except Exception:
        # Fallback: enable to stderr
        faulthandler.enable()


def main():
    _setup_crash_handler()

    parser = argparse.ArgumentParser(
        description="Forge — Local AI coding assistant",
    )
    parser.add_argument(
        "-V", "--version",
        action="version",
        version=f"%(prog)s {__import__('forge').__version__}",
    )
    parser.add_argument(
        "-m", "--model",
        default=None,
        help="Ollama model to use (default: qwen2.5-coder:14b)",
    )
    parser.add_argument(
        "-d", "--dir",
        default=None,
        help="Working directory (default: current directory)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--fnc", "--gui",
        action="store_true",
        dest="fnc",
        help="Launch Forge Neural Cortex GUI (primary entry point)",
    )
    parser.add_argument(
        "--gui-terminal",
        action="store_true",
        dest="gui_terminal",
        help="Launch GUI terminal window (in-process, with effects)",
    )
    args = parser.parse_args()

    # Setup logging — file + console so crashes leave a trail
    level = logging.DEBUG if args.verbose else logging.WARNING
    log_dir = os.path.join(os.path.expanduser("~"), ".forge")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "forge.log")
    handlers = [logging.StreamHandler()]
    try:
        # Rotate: keep last 2MB, then truncate
        file_h = logging.FileHandler(log_path, encoding="utf-8")
        # Cap file at 2MB — truncate on startup if too large
        try:
            if os.path.getsize(log_path) > 2 * 1024 * 1024:
                open(log_path, "w").close()
        except OSError:
            pass
        handlers.append(file_h)
    except Exception:
        pass
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )

    # FNC mode: launch the GUI launcher instead of terminal
    if args.fnc:
        from forge.ui.dashboard import launch_launcher, HAS_GUI_DEPS
        if not HAS_GUI_DEPS:
            print("FNC requires: pip install customtkinter Pillow numpy",
                  file=sys.stderr)
            sys.exit(1)
        launch_launcher()
        return

    # GUI Terminal mode: in-process terminal with visual effects
    if args.gui_terminal:
        from forge.ui.gui_terminal import launch_gui_terminal, HAS_CTK
        if not HAS_CTK:
            print("GUI Terminal requires: pip install customtkinter",
                  file=sys.stderr)
            sys.exit(1)
        launch_gui_terminal(model=args.model, cwd=args.dir)
        return

    # Set working directory
    if args.dir:
        cwd = os.path.abspath(args.dir)
        if os.path.isdir(cwd):
            os.chdir(cwd)
        else:
            print(f"Error: directory not found: {cwd}", file=sys.stderr)
            sys.exit(1)
    else:
        cwd = os.getcwd()

    # Track whether we were launched from a shortcut/GUI
    # (where the window would vanish on exit)
    _keep_open = os.environ.get("FORGE_KEEP_OPEN") == "1"

    from forge.engine import ForgeEngine
    engine = ForgeEngine(model=args.model, cwd=cwd)

    try:
        engine.run()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        try:
            engine._print_exit_summary()
        except Exception:
            pass
    except SystemExit:
        pass  # /quit raises SystemExit after exit summary — already handled
    except Exception as e:
        from forge.bug_reporter import capture_crash as _capture_crash
        _capture_crash(e)
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
        _keep_open = True  # Always pause on crash so user can read the error
        try:
            engine._print_exit_summary()
        except Exception:
            pass

    if _keep_open:
        try:
            if sys.stdin and sys.stdin.isatty():
                input("\nPress Enter to close...")
        except (EOFError, KeyboardInterrupt):
            pass


if __name__ == "__main__":
    main()
