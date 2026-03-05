"""Entry point for `python -m forge` or `forge` command."""

import argparse
import sys
import os
import logging


def main():
    parser = argparse.ArgumentParser(
        description="Forge — Local AI coding assistant",
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

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
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

    from forge.engine import ForgeEngine
    engine = ForgeEngine(model=args.model, cwd=cwd)

    try:
        engine.run()
    except KeyboardInterrupt:
        print("\nInterrupted.")
    except Exception as e:
        from forge.bug_reporter import capture_crash as _capture_crash
        _capture_crash(e)
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()

    # Keep console open so user can see errors
    # (especially when launched from the dashboard)
    try:
        if sys.stdin and sys.stdin.isatty():
            input("\nPress Enter to close...")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
