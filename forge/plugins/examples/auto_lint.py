"""Auto-lint plugin — runs ruff on every saved .py file.

Install by copying to ~/.forge/plugins/auto_lint.py

Hooks:
  on_file_write  — runs ruff check on saved .py files
  on_command     — adds /lint command to run ruff on a path
"""

import subprocess
import logging
from forge.plugins.base import ForgePlugin

log = logging.getLogger(__name__)


class AutoLintPlugin(ForgePlugin):
    name = "AutoLint"
    version = "1.0.0"
    description = "Auto-runs ruff on saved Python files."
    author = "Forge Team"

    def on_file_write(self, path: str, content: str) -> str:
        """After a .py file is written, run ruff check on it."""
        if not path.endswith(".py"):
            return content

        try:
            result = subprocess.run(
                ["ruff", "check", "--select", "E,W,F", path],
                capture_output=True, text=True, timeout=10)
            if result.returncode != 0 and result.stdout.strip():
                lines = result.stdout.strip().splitlines()
                count = len(lines)
                preview = "\n".join(lines[:5])
                log.info("[AutoLint] %d issue(s) in %s:\n%s",
                         count, path, preview)
        except FileNotFoundError:
            pass  # ruff not installed
        except Exception as e:
            log.debug("[AutoLint] Failed: %s", e)

        return content

    def on_command(self, command: str, arg: str) -> bool:
        """Handle /lint [path] command."""
        if command != "lint":
            return False

        target = arg.strip() or "."
        try:
            result = subprocess.run(
                ["ruff", "check", target],
                capture_output=True, text=True, timeout=30)
            output = result.stdout.strip() or "No issues found."
            print(output)
        except FileNotFoundError:
            print("ruff is not installed. Install with: pip install ruff")
        except subprocess.TimeoutExpired:
            print("Lint timed out after 30s.")
        except Exception as e:
            print(f"Lint error: {e}")

        return True
