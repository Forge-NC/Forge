"""Forge Admin Panel -- update checker and collaborator/token management.

Provides two CTkToplevel dialog classes:
  UpdateCheckDialog   -- lightweight dialog to check for and apply git updates
  AdminPanelDialog    -- full admin dialog for GitHub collaborators and
                         telemetry token management

Both dialogs follow the standard Forge window pattern: theme-aware,
background-threaded subprocess calls, thread-safe UI updates.
"""

import hashlib
import json
import logging
import os
import re
import secrets
import subprocess
import threading
import webbrowser
from pathlib import Path
from typing import Optional

try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from forge.config import ForgeConfig
from forge.constants import TOKEN_ADMIN_URL
from forge.ui.themes import (
    get_colors, get_fonts,
    add_theme_listener, remove_theme_listener, recolor_widget_tree,
)

log = logging.getLogger(__name__)

# ── Colors & fonts from central theme system ──

COLORS = get_colors()

_F = get_fonts()
FONT_TITLE = _F["title"]
FONT_TITLE_SM = _F["title_sm"]
FONT_MONO = _F["mono"]
FONT_MONO_BOLD = _F["mono_bold"]
FONT_MONO_SM = _F["mono_sm"]
FONT_MONO_XS = _F["mono_xs"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_forge_root() -> str:
    """Return Forge's installation directory."""
    return str(Path(__file__).resolve().parents[2])


def _get_repo_nwo() -> Optional[str]:
    """Get owner/repo from git remote (e.g., 'Forge-NC/Forge').

    Parses both HTTPS and SSH remote URL formats.
    Returns None if the remote cannot be determined.
    """
    output = _run_git_at_forge(["remote", "get-url", "origin"])
    if not output or output.startswith("Error:"):
        return None
    url = output.strip()
    # HTTPS: https://github.com/owner/repo.git
    m = re.search(r"github\.com[/:]([^/]+)/([^/.]+?)(?:\.git)?$", url)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return None


def _run_gh(args: list, timeout: int = 15) -> tuple:
    """Run gh CLI command. Returns (success: bool, output: str)."""
    cmd = ["gh"] + args
    extra = {}
    if os.name == "nt":
        extra["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            **extra,
        )
        output = result.stdout.strip()
        if result.returncode != 0:
            err = result.stderr.strip() or output or f"gh exited with code {result.returncode}"
            return (False, err)
        return (True, output)
    except FileNotFoundError:
        return (False, "GitHub CLI (gh) not found. Install from https://cli.github.com/")
    except subprocess.TimeoutExpired:
        return (False, f"Command timed out after {timeout}s")
    except Exception as e:
        return (False, str(e))


def _run_git_at_forge(args: list, timeout: int = 15) -> str:
    """Run git command at Forge's own root directory.

    Returns the command output string, or an error message prefixed
    with 'Error:'.
    """
    cmd = ["git"] + args
    extra = {}
    if os.name == "nt":
        extra["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=_get_forge_root(),
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
            **extra,
        )
        parts = []
        if result.stdout:
            parts.append(result.stdout.rstrip())
        if result.stderr and result.returncode != 0:
            parts.append(result.stderr.rstrip())
        if result.returncode != 0 and not parts:
            return f"Error: git exited with code {result.returncode}"
        return "\n".join(parts) if parts else ""
    except FileNotFoundError:
        return "Error: git is not installed or not on PATH."
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# UpdateCheckDialog
# ---------------------------------------------------------------------------

class UpdateCheckDialog:
    """Lightweight dialog that checks for and applies updates from GitHub."""

    def __init__(self, parent):
        if not HAS_CTK:
            return

        self._parent = parent
        self._branch = "main"
        self._behind_count = 0

        # ── Window ──
        self._win = ctk.CTkToplevel(parent)
        self._win.title("Check for Updates")
        self._win.geometry("420x380")
        self._win.transient(parent)
        self._win.grab_set()
        self._win.configure(fg_color=COLORS["bg_dark"])
        self._win.resizable(False, False)
        self._win.protocol("WM_DELETE_WINDOW", self._close)

        # Theme listener
        self._theme_cb = lambda cm: self._win.after(0, self._apply_theme, cm)
        add_theme_listener(self._theme_cb)

        # Center on parent
        self._win.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - 420) // 2
        py = parent.winfo_y() + (parent.winfo_height() - 380) // 2
        self._win.geometry(f"+{max(0, px)}+{max(0, py)}")

        # ── Header ──
        ctk.CTkLabel(
            self._win, text="CHECK FOR UPDATES",
            font=ctk.CTkFont(*FONT_TITLE),
            text_color=COLORS["cyan"],
        ).pack(padx=16, pady=(16, 4), anchor="w")

        ctk.CTkFrame(
            self._win, fg_color=COLORS["border"],
            height=1, corner_radius=0,
        ).pack(fill="x", padx=16, pady=(0, 8))

        # ── Status section ──
        self._status_frame = ctk.CTkFrame(
            self._win, fg_color=COLORS["bg_panel"],
            corner_radius=6, border_width=1, border_color=COLORS["border"],
        )
        self._status_frame.pack(fill="x", padx=16, pady=(0, 8))

        self._branch_label = ctk.CTkLabel(
            self._status_frame, text="  Branch: ...",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"], anchor="w",
        )
        self._branch_label.pack(fill="x", padx=8, pady=(8, 2))

        self._status_label = ctk.CTkLabel(
            self._status_frame, text="  Checking...",
            font=ctk.CTkFont(*FONT_MONO),
            text_color=COLORS["yellow"], anchor="w",
        )
        self._status_label.pack(fill="x", padx=8, pady=(2, 8))

        # ── Changelog section ──
        ctk.CTkLabel(
            self._win, text="  Incoming commits:",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"], anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 2))

        self._changelog = ctk.CTkTextbox(
            self._win, height=120,
            font=ctk.CTkFont(*FONT_MONO_XS),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=4,
            state="disabled",
        )
        self._changelog.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # ── Button row ──
        btn_frame = ctk.CTkFrame(self._win, fg_color="transparent")
        btn_frame.pack(fill="x", padx=16, pady=(0, 12))

        self._update_btn = ctk.CTkButton(
            btn_frame, text="Update Now", width=140,
            fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            state="disabled",
            command=self._on_update,
        )
        self._update_btn.pack(side="left")

        ctk.CTkButton(
            btn_frame, text="Close", width=130,
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["bg_panel"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            command=self._close,
        ).pack(side="right")

        # ── Start check ──
        threading.Thread(target=self._check_updates, daemon=True).start()

    # ── Background check ──

    def _check_updates(self):
        """Fetch origin and count commits behind (runs in background thread)."""
        # Fetch
        fetch_out = _run_git_at_forge(["fetch", "origin"], timeout=20)
        if fetch_out.startswith("Error:"):
            self._win.after(0, self._show_error, fetch_out)
            return

        # Current branch
        branch_out = _run_git_at_forge(["rev-parse", "--abbrev-ref", "HEAD"])
        if branch_out.startswith("Error:"):
            self._win.after(0, self._show_error, branch_out)
            return
        branch = branch_out.strip() or "main"
        self._branch = branch

        # Count commits behind
        count_out = _run_git_at_forge(
            ["rev-list", "--count", f"HEAD..origin/{branch}"])
        if count_out.startswith("Error:"):
            self._win.after(0, self._show_error, count_out)
            return

        try:
            behind = int(count_out.strip())
        except ValueError:
            behind = 0
        self._behind_count = behind

        # Changelog (max 20 commits)
        changelog = ""
        if behind > 0:
            log_out = _run_git_at_forge(
                ["log", "--oneline", f"HEAD..origin/{branch}", "-20"])
            if not log_out.startswith("Error:"):
                changelog = log_out.strip()

        self._win.after(0, self._show_results, branch, behind, changelog)

    def _show_results(self, branch: str, behind: int, changelog: str):
        """Update UI with check results (called on main thread)."""
        self._branch_label.configure(text=f"  Branch: {branch}")

        if behind == 0:
            self._status_label.configure(
                text="  Forge is up to date",
                text_color=COLORS["green"],
            )
        else:
            plural = "s" if behind != 1 else ""
            self._status_label.configure(
                text=f"  {behind} update{plural} available",
                text_color=COLORS["yellow"],
            )
            self._update_btn.configure(state="normal")

        self._changelog.configure(state="normal")
        self._changelog.delete("1.0", "end")
        if changelog:
            self._changelog.insert("1.0", changelog)
        else:
            self._changelog.insert("1.0", "(no new commits)")
        self._changelog.configure(state="disabled")

    def _show_error(self, message: str):
        """Show an error in the status label (called on main thread)."""
        self._branch_label.configure(text="  Branch: unknown")
        self._status_label.configure(
            text=f"  {message}",
            text_color=COLORS["red"],
        )

    # ── Update action ──

    def _on_update(self):
        """Start the pull in a background thread."""
        self._update_btn.configure(state="disabled", text="Updating...")
        self._status_label.configure(
            text="  Pulling changes...",
            text_color=COLORS["yellow"],
        )
        threading.Thread(target=self._do_update, daemon=True).start()

    def _do_update(self):
        """Pull changes and optionally reinstall (runs in background thread)."""
        branch = self._branch
        count = self._behind_count

        # Pull
        pull_out = _run_git_at_forge(
            ["pull", "--ff-only", "origin", branch], timeout=30)
        if pull_out.startswith("Error:") or "fatal:" in pull_out.lower():
            self._win.after(0, self._show_update_error, pull_out)
            return

        # Check if pyproject.toml changed
        needs_reinstall = False
        changed_files = []
        if count > 0:
            diff_out = _run_git_at_forge(
                ["diff", "--name-only", f"HEAD~{count}", "HEAD"])
            if not diff_out.startswith("Error:"):
                changed_files = [
                    f.strip() for f in diff_out.strip().splitlines() if f.strip()
                ]
                needs_reinstall = "pyproject.toml" in changed_files

        # Reinstall if needed
        reinstall_msg = ""
        if needs_reinstall:
            try:
                extra = {}
                if os.name == "nt":
                    extra["creationflags"] = subprocess.CREATE_NO_WINDOW
                subprocess.run(
                    ["pip", "install", "-e", _get_forge_root(), "--quiet"],
                    capture_output=True, text=True, timeout=60, **extra,
                )
                reinstall_msg = " (dependencies updated)"
            except Exception as e:
                reinstall_msg = f" (pip install failed: {e})"

        # Determine if core files changed (suggest restart)
        core_patterns = ("forge/", "pyproject.toml", "setup.py", "setup.cfg")
        core_changed = [
            f for f in changed_files
            if any(f.startswith(p) or f == p for p in core_patterns)
        ]

        self._win.after(
            0, self._show_update_success,
            count, changed_files, core_changed, reinstall_msg,
        )

    def _show_update_success(self, count, changed, core_changed, reinstall_msg):
        """Show success message after update (called on main thread)."""
        plural = "s" if count != 1 else ""
        self._status_label.configure(
            text=f"  Updated {count} commit{plural}{reinstall_msg}",
            text_color=COLORS["green"],
        )
        self._update_btn.configure(text="Done", state="disabled")

        # Show changed files in changelog area
        self._changelog.configure(state="normal")
        self._changelog.delete("1.0", "end")
        if changed:
            self._changelog.insert("1.0", "Changed files:\n")
            for f in changed[:30]:
                self._changelog.insert("end", f"  {f}\n")
        if core_changed:
            self._changelog.insert(
                "end", "\nCore files changed -- restart Forge for full effect.\n"
            )
        self._changelog.configure(state="disabled")

    def _show_update_error(self, message: str):
        """Show pull error (called on main thread)."""
        self._status_label.configure(
            text=f"  Update failed",
            text_color=COLORS["red"],
        )
        self._update_btn.configure(text="Update Now", state="normal")

        self._changelog.configure(state="normal")
        self._changelog.delete("1.0", "end")
        self._changelog.insert("1.0", message)
        self._changelog.configure(state="disabled")

    # ── Theme / close ──

    def _apply_theme(self, color_map: dict):
        if self._win:
            recolor_widget_tree(self._win, color_map)

    def _close(self):
        if hasattr(self, "_theme_cb"):
            remove_theme_listener(self._theme_cb)
        try:
            self._win.grab_release()
        except Exception:
            pass
        try:
            self._win.destroy()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# AdminPanelDialog
# ---------------------------------------------------------------------------

class AdminPanelDialog:
    """Full admin dialog for GitHub collaborators and telemetry tokens."""

    def __init__(self, parent, config: ForgeConfig):
        if not HAS_CTK:
            return

        self._parent = parent
        self._config = config
        self._nwo = None  # owner/repo, resolved in background

        # ── Window ──
        self._win = ctk.CTkToplevel(parent)
        self._win.title("Forge Admin Panel")
        self._win.geometry("580x700")
        self._win.transient(parent)
        self._win.grab_set()
        self._win.configure(fg_color=COLORS["bg_dark"])
        self._win.resizable(True, True)
        self._win.minsize(520, 550)
        self._win.protocol("WM_DELETE_WINDOW", self._close)

        # Theme listener
        self._theme_cb = lambda cm: self._win.after(0, self._apply_theme, cm)
        add_theme_listener(self._theme_cb)

        # Center on parent
        self._win.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - 580) // 2
        py = parent.winfo_y() + (parent.winfo_height() - 700) // 2
        self._win.geometry(f"+{max(0, px)}+{max(0, py)}")

        # ── Header ──
        header = ctk.CTkFrame(
            self._win, fg_color=COLORS["bg_panel"],
            corner_radius=0, height=40,
            border_width=1, border_color=COLORS["border"],
        )
        header.pack(fill="x")
        header.pack_propagate(False)
        ctk.CTkLabel(
            header, text="  Forge Admin Panel",
            font=ctk.CTkFont(*FONT_TITLE_SM),
            text_color=COLORS["cyan"],
        ).pack(side="left", padx=8, pady=6)

        ctk.CTkFrame(
            self._win, fg_color=COLORS["border"],
            height=1, corner_radius=0,
        ).pack(fill="x")

        # ── Scrollable content ──
        self._scroll = ctk.CTkScrollableFrame(
            self._win, fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["cyan_dim"],
        )
        self._scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # Build sections
        self._build_collaborators_section()
        self._build_tokens_section()
        self._build_repo_section()

        # ── Close button ──
        btn_frame = ctk.CTkFrame(self._win, fg_color=COLORS["bg_dark"], height=46)
        btn_frame.pack(fill="x", padx=8, pady=(4, 8))
        ctk.CTkButton(
            btn_frame, text="Close", width=130,
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["bg_panel"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            command=self._close,
        ).pack(side="right", padx=4)

        # ── Resolve repo in background ──
        threading.Thread(target=self._resolve_repo, daemon=True).start()

    # ── Section builders ──────────────────────────────────────────

    def _build_collaborators_section(self):
        """Build the GitHub Collaborators section."""
        frame = self._scroll

        # Section header
        ctk.CTkLabel(
            frame, text="  GITHUB COLLABORATORS",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["cyan"], anchor="w",
        ).pack(fill="x", padx=12, pady=(12, 4))

        ctk.CTkFrame(
            frame, fg_color=COLORS["border"],
            height=1, corner_radius=0,
        ).pack(fill="x", padx=12, pady=(0, 6))

        # Invite row
        invite_row = ctk.CTkFrame(frame, fg_color="transparent")
        invite_row.pack(fill="x", padx=12, pady=(0, 4))

        self._collab_entry = ctk.CTkEntry(
            invite_row,
            placeholder_text="GitHub username",
            font=ctk.CTkFont(*FONT_MONO_SM),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=4,
            width=180, height=30,
        )
        self._collab_entry.pack(side="left", padx=(0, 4))

        self._role_var = ctk.StringVar(value="pull")
        self._role_menu = ctk.CTkOptionMenu(
            invite_row,
            variable=self._role_var,
            values=["pull", "push"],
            fg_color=COLORS["bg_card"],
            button_color=COLORS["cyan_dim"],
            button_hover_color=COLORS["cyan"],
            dropdown_fg_color=COLORS["bg_card"],
            dropdown_hover_color=COLORS["cyan_dim"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            dropdown_font=ctk.CTkFont(*FONT_MONO_SM),
            width=90,
        )
        self._role_menu.pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            invite_row, text="Invite", width=130,
            fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            command=self._invite_collaborator,
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            invite_row, text="Refresh", width=130,
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["bg_panel"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            command=self._refresh_collaborators,
        ).pack(side="right")

        # Collaborator list container
        self._collab_list_frame = ctk.CTkFrame(
            frame, fg_color=COLORS["bg_panel"],
            corner_radius=6, border_width=1, border_color=COLORS["border"],
        )
        self._collab_list_frame.pack(fill="x", padx=12, pady=(0, 4))

        self._collab_loading = ctk.CTkLabel(
            self._collab_list_frame,
            text="  Loading collaborators...",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"], anchor="w",
        )
        self._collab_loading.pack(fill="x", padx=8, pady=6)

        # Pending invitations container
        self._pending_label = ctk.CTkLabel(
            frame, text="  Pending invitations:",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"], anchor="w",
        )
        self._pending_label.pack(fill="x", padx=12, pady=(4, 0))

        self._pending_frame = ctk.CTkFrame(
            frame, fg_color=COLORS["bg_panel"],
            corner_radius=6, border_width=1, border_color=COLORS["border"],
        )
        self._pending_frame.pack(fill="x", padx=12, pady=(2, 4))

        self._pending_loading = ctk.CTkLabel(
            self._pending_frame,
            text="  --",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"], anchor="w",
        )
        self._pending_loading.pack(fill="x", padx=8, pady=4)

        # Status label
        self._collab_status = ctk.CTkLabel(
            frame, text="",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"], anchor="w",
        )
        self._collab_status.pack(fill="x", padx=12, pady=(0, 8))

    def _build_tokens_section(self):
        """Build the Telemetry Tokens section."""
        frame = self._scroll

        # Separator
        ctk.CTkFrame(
            frame, fg_color=COLORS["border"],
            height=1, corner_radius=0,
        ).pack(fill="x", padx=12, pady=(4, 0))

        # Section header
        ctk.CTkLabel(
            frame, text="  TELEMETRY TOKENS",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["cyan"], anchor="w",
        ).pack(fill="x", padx=12, pady=(12, 4))

        ctk.CTkFrame(
            frame, fg_color=COLORS["border"],
            height=1, corner_radius=0,
        ).pack(fill="x", padx=12, pady=(0, 6))

        # Generate row
        gen_row = ctk.CTkFrame(frame, fg_color="transparent")
        gen_row.pack(fill="x", padx=12, pady=(0, 4))

        self._token_label_entry = ctk.CTkEntry(
            gen_row,
            placeholder_text="Token label, e.g. tester-alice",
            font=ctk.CTkFont(*FONT_MONO_SM),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=4,
            width=260, height=30,
        )
        self._token_label_entry.pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            gen_row, text="Generate", width=130,
            fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            command=self._generate_token,
        ).pack(side="left")

        ctk.CTkButton(
            gen_row, text="Refresh", width=130,
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["bg_panel"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            command=self._refresh_tokens,
        ).pack(side="right")

        # Generated token display (hidden initially)
        self._token_display_frame = ctk.CTkFrame(
            frame, fg_color=COLORS["bg_panel"],
            corner_radius=6, border_width=1, border_color=COLORS["cyan_dim"],
        )
        # Not packed yet -- shown only after generation

        self._token_display_entry = ctk.CTkEntry(
            self._token_display_frame,
            font=ctk.CTkFont(*FONT_MONO_XS),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["green"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=4,
            width=380, height=28,
            state="disabled",
        )
        self._token_display_entry.pack(side="left", padx=(8, 4), pady=6)

        ctk.CTkButton(
            self._token_display_frame, text="Copy", width=130,
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["cyan_dim"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            command=self._copy_token,
        ).pack(side="left", padx=(0, 8), pady=6)

        self._last_generated_token = ""

        # Token status
        self._token_status = ctk.CTkLabel(
            frame, text="",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"], anchor="w",
        )
        self._token_status.pack(fill="x", padx=12, pady=(0, 8))

        # Token list from server
        self._token_list_frame = ctk.CTkFrame(
            frame, fg_color=COLORS["bg_panel"],
            corner_radius=6, border_width=1, border_color=COLORS["border"],
        )
        self._token_list_frame.pack(fill="x", padx=12, pady=(0, 8))

        self._token_list_loading = ctk.CTkLabel(
            self._token_list_frame,
            text="  Click Refresh to load tokens",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"], anchor="w",
        )
        self._token_list_loading.pack(fill="x", padx=8, pady=6)

    def _build_repo_section(self):
        """Build the Repository Info section."""
        frame = self._scroll

        # Separator
        ctk.CTkFrame(
            frame, fg_color=COLORS["border"],
            height=1, corner_radius=0,
        ).pack(fill="x", padx=12, pady=(4, 0))

        # Section header
        ctk.CTkLabel(
            frame, text="  REPOSITORY",
            font=ctk.CTkFont(*FONT_MONO_BOLD),
            text_color=COLORS["cyan"], anchor="w",
        ).pack(fill="x", padx=12, pady=(12, 4))

        ctk.CTkFrame(
            frame, fg_color=COLORS["border"],
            height=1, corner_radius=0,
        ).pack(fill="x", padx=12, pady=(0, 6))

        info_frame = ctk.CTkFrame(
            frame, fg_color=COLORS["bg_panel"],
            corner_radius=6, border_width=1, border_color=COLORS["border"],
        )
        info_frame.pack(fill="x", padx=12, pady=(0, 4))

        self._repo_url_label = ctk.CTkLabel(
            info_frame, text="  Repo: resolving...",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"], anchor="w",
        )
        self._repo_url_label.pack(fill="x", padx=8, pady=(8, 2))

        self._repo_branch_label = ctk.CTkLabel(
            info_frame, text="  Branch: ...",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"], anchor="w",
        )
        self._repo_branch_label.pack(fill="x", padx=8, pady=2)

        self._repo_user_label = ctk.CTkLabel(
            info_frame, text="  gh user: ...",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=COLORS["gray"], anchor="w",
        )
        self._repo_user_label.pack(fill="x", padx=8, pady=(2, 8))

        # Open on GitHub button
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 12))

        self._open_github_btn = ctk.CTkButton(
            btn_row, text="Open on GitHub", width=140,
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["cyan_dim"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            state="disabled",
            command=self._open_github,
        )
        self._open_github_btn.pack(side="left")

    # ── Background repo resolution ──────────────────────────────

    def _resolve_repo(self):
        """Resolve repository info in a background thread."""
        nwo = _get_repo_nwo()
        self._nwo = nwo

        branch_out = _run_git_at_forge(["rev-parse", "--abbrev-ref", "HEAD"])
        branch = branch_out.strip() if not branch_out.startswith("Error:") else "unknown"

        # gh auth status
        ok, user_out = _run_gh(["auth", "status"])
        gh_user = "not authenticated"
        if ok:
            # Parse "Logged in to github.com account <username>"
            m = re.search(r"account\s+(\S+)", user_out)
            if m:
                gh_user = m.group(1)
            else:
                gh_user = "(authenticated)"

        self._win.after(0, self._update_repo_info, nwo, branch, gh_user)

        # Auto-refresh collaborators if we have a repo
        if nwo:
            self._do_refresh_collaborators()

        # Auto-refresh token list
        self._do_refresh_tokens()

    def _update_repo_info(self, nwo, branch, gh_user):
        """Update repository info labels (called on main thread)."""
        if nwo:
            self._repo_url_label.configure(
                text=f"  Repo: https://github.com/{nwo}",
                text_color=COLORS["white"],
            )
            self._open_github_btn.configure(state="normal")
        else:
            self._repo_url_label.configure(
                text="  Repo: not a GitHub repository",
                text_color=COLORS["gray"],
            )

        self._repo_branch_label.configure(text=f"  Branch: {branch}")
        self._repo_user_label.configure(text=f"  gh user: {gh_user}")

    # ── Collaborators ──────────────────────────────────────────

    def _refresh_collaborators(self):
        """Kick off a background collaborator refresh."""
        self._collab_status.configure(
            text="  Refreshing...", text_color=COLORS["yellow"])
        threading.Thread(
            target=self._do_refresh_collaborators, daemon=True).start()

    def _do_refresh_collaborators(self):
        """Fetch collaborators and pending invitations (background thread)."""
        nwo = self._nwo
        if not nwo:
            self._win.after(0, self._show_collab_error,
                            "Repository not resolved. Is this a GitHub repo?")
            return

        # Fetch collaborators
        ok, collab_out = _run_gh(["api", f"repos/{nwo}/collaborators"])
        if not ok:
            self._win.after(0, self._show_collab_error, collab_out)
            return

        collabs = []
        try:
            data = json.loads(collab_out)
            for item in data:
                login = item.get("login", "")
                perms = item.get("permissions", {})
                role = "pull"
                if perms.get("admin"):
                    role = "admin"
                elif perms.get("push"):
                    role = "push"
                collabs.append((login, role))
        except (json.JSONDecodeError, TypeError):
            self._win.after(0, self._show_collab_error,
                            "Failed to parse collaborator data")
            return

        # Fetch pending invitations
        ok2, inv_out = _run_gh(["api", f"repos/{nwo}/invitations"])
        invitations = []
        if ok2:
            try:
                inv_data = json.loads(inv_out)
                for item in inv_data:
                    invitee = item.get("invitee", {})
                    login = invitee.get("login", "unknown")
                    inv_id = item.get("id", 0)
                    invitations.append((login, inv_id))
            except (json.JSONDecodeError, TypeError):
                pass

        self._win.after(0, self._populate_collaborators, collabs, invitations)

    def _populate_collaborators(self, collabs, invitations):
        """Rebuild collaborator list UI (called on main thread)."""
        # Clear existing
        for child in self._collab_list_frame.winfo_children():
            child.destroy()

        if not collabs:
            ctk.CTkLabel(
                self._collab_list_frame,
                text="  No collaborators found",
                font=ctk.CTkFont(*FONT_MONO_XS),
                text_color=COLORS["gray"], anchor="w",
            ).pack(fill="x", padx=8, pady=6)
        else:
            for login, role in collabs:
                row = ctk.CTkFrame(
                    self._collab_list_frame, fg_color="transparent")
                row.pack(fill="x", padx=8, pady=2)

                ctk.CTkLabel(
                    row, text=f"  {login}",
                    font=ctk.CTkFont(*FONT_MONO_SM),
                    text_color=COLORS["white"], anchor="w",
                ).pack(side="left")

                ctk.CTkLabel(
                    row, text=f"[{role}]",
                    font=ctk.CTkFont(*FONT_MONO_XS),
                    text_color=COLORS["gray"],
                ).pack(side="left", padx=(6, 0))

                rm_btn = ctk.CTkButton(
                    row, text="Remove", width=130,
                    fg_color=COLORS["bg_card"],
                    hover_color=COLORS["red"],
                    text_color=COLORS["white"],
                    font=ctk.CTkFont(*FONT_MONO_XS),
                    height=24,
                    command=lambda u=login: self._remove_collaborator(u),
                )
                rm_btn.pack(side="right")

        # Pending invitations
        for child in self._pending_frame.winfo_children():
            child.destroy()

        if not invitations:
            ctk.CTkLabel(
                self._pending_frame,
                text="  No pending invitations",
                font=ctk.CTkFont(*FONT_MONO_XS),
                text_color=COLORS["gray"], anchor="w",
            ).pack(fill="x", padx=8, pady=4)
        else:
            for login, inv_id in invitations:
                row = ctk.CTkFrame(self._pending_frame, fg_color="transparent")
                row.pack(fill="x", padx=8, pady=2)

                ctk.CTkLabel(
                    row, text=f"  {login}",
                    font=ctk.CTkFont(*FONT_MONO_SM),
                    text_color=COLORS["yellow"], anchor="w",
                ).pack(side="left")

                cancel_btn = ctk.CTkButton(
                    row, text="Cancel", width=130,
                    fg_color=COLORS["bg_card"],
                    hover_color=COLORS["red"],
                    text_color=COLORS["white"],
                    font=ctk.CTkFont(*FONT_MONO_XS),
                    height=24,
                    command=lambda i=inv_id: self._cancel_invitation(i),
                )
                cancel_btn.pack(side="right")

        self._collab_status.configure(
            text=f"  {len(collabs)} collaborator(s), "
                 f"{len(invitations)} pending",
            text_color=COLORS["gray"],
        )

    def _show_collab_error(self, message: str):
        """Show error in collaborator section (called on main thread)."""
        for child in self._collab_list_frame.winfo_children():
            child.destroy()
        ctk.CTkLabel(
            self._collab_list_frame,
            text=f"  {message}",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["red"], anchor="w",
            wraplength=500,
        ).pack(fill="x", padx=8, pady=6)
        self._collab_status.configure(text="", text_color=COLORS["gray"])

    def _invite_collaborator(self):
        """Invite a GitHub collaborator (starts background thread)."""
        username = self._collab_entry.get().strip()
        if not username:
            self._collab_status.configure(
                text="  Enter a GitHub username",
                text_color=COLORS["yellow"],
            )
            return
        role = self._role_var.get()
        nwo = self._nwo
        if not nwo:
            self._collab_status.configure(
                text="  Repository not resolved",
                text_color=COLORS["red"],
            )
            return

        self._collab_status.configure(
            text=f"  Inviting {username}...",
            text_color=COLORS["yellow"],
        )

        def _do_invite():
            ok, out = _run_gh([
                "api", "-X", "PUT",
                f"repos/{nwo}/collaborators/{username}",
                "-f", f"permission={role}",
            ])
            if ok:
                self._win.after(0, self._collab_status.configure,
                                {"text": f"  Invited {username} as {role}",
                                 "text_color": COLORS["green"]})
                self._win.after(0, lambda: self._collab_entry.delete(0, "end"))
                # Refresh list
                self._do_refresh_collaborators()
            else:
                self._win.after(0, self._collab_status.configure,
                                {"text": f"  Failed: {out}",
                                 "text_color": COLORS["red"]})

        threading.Thread(target=_do_invite, daemon=True).start()

    def _remove_collaborator(self, username: str):
        """Remove a GitHub collaborator (starts background thread)."""
        nwo = self._nwo
        if not nwo:
            return

        self._collab_status.configure(
            text=f"  Removing {username}...",
            text_color=COLORS["yellow"],
        )

        def _do_remove():
            ok, out = _run_gh([
                "api", "-X", "DELETE",
                f"repos/{nwo}/collaborators/{username}",
            ])
            if ok:
                self._win.after(0, self._collab_status.configure,
                                {"text": f"  Removed {username}",
                                 "text_color": COLORS["green"]})
                self._do_refresh_collaborators()
            else:
                self._win.after(0, self._collab_status.configure,
                                {"text": f"  Failed: {out}",
                                 "text_color": COLORS["red"]})

        threading.Thread(target=_do_remove, daemon=True).start()

    def _cancel_invitation(self, inv_id: int):
        """Cancel a pending GitHub invitation (starts background thread)."""
        nwo = self._nwo
        if not nwo:
            return

        self._collab_status.configure(
            text="  Cancelling invitation...",
            text_color=COLORS["yellow"],
        )

        def _do_cancel():
            ok, out = _run_gh([
                "api", "-X", "DELETE",
                f"repos/{nwo}/invitations/{inv_id}",
            ])
            if ok:
                self._win.after(0, self._collab_status.configure,
                                {"text": "  Invitation cancelled",
                                 "text_color": COLORS["green"]})
                self._do_refresh_collaborators()
            else:
                self._win.after(0, self._collab_status.configure,
                                {"text": f"  Failed: {out}",
                                 "text_color": COLORS["red"]})

        threading.Thread(target=_do_cancel, daemon=True).start()

    # ── Telemetry tokens ──────────────────────────────────────

    def _generate_token(self):
        """Generate a new telemetry token and register it server-side."""
        label = self._token_label_entry.get().strip()
        if not label:
            self._token_status.configure(
                text="  Enter a token label first",
                text_color=COLORS["yellow"],
            )
            return

        # Generate token
        token = secrets.token_hex(32)
        token_hash = hashlib.sha512(token.encode()).hexdigest()
        self._last_generated_token = token

        # Show token
        self._token_display_entry.configure(state="normal")
        self._token_display_entry.delete(0, "end")
        self._token_display_entry.insert(0, token)
        self._token_display_entry.configure(state="disabled")
        self._token_display_frame.pack(fill="x", padx=12, pady=(0, 4),
                                       after=self._token_label_entry.master)

        self._token_status.configure(
            text=f"  Token generated (hash prefix: {token_hash[:12]}...)",
            text_color=COLORS["green"],
        )

        # Register server-side (best-effort, background)
        def _do_register():
            admin_token = self._config.get("telemetry_token", "")
            url = TOKEN_ADMIN_URL
            try:
                import urllib.request
                payload = json.dumps({
                    "action": "register",
                    "token_hash": token_hash,
                    "label": label,
                }).encode("utf-8")
                req = urllib.request.Request(
                    url, data=payload, method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "X-Forge-Token": admin_token,
                    },
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    result = json.loads(resp.read())
                if result.get("success"):
                    self._win.after(0, self._token_status.configure,
                                    {"text": f"  Registered: {label} "
                                             f"(hash: {token_hash[:12]}...)",
                                     "text_color": COLORS["green"]})
                else:
                    err = result.get("error", "unknown")
                    self._win.after(0, self._token_status.configure,
                                    {"text": f"  Token generated locally. "
                                             f"Server registration failed: {err}",
                                     "text_color": COLORS["yellow"]})
            except Exception as e:
                self._win.after(0, self._token_status.configure,
                                {"text": f"  Token generated locally. "
                                         f"Server unreachable: {e}",
                                 "text_color": COLORS["yellow"]})

        threading.Thread(target=_do_register, daemon=True).start()

    def _copy_token(self):
        """Copy the last generated token to the clipboard."""
        if self._last_generated_token:
            try:
                self._win.clipboard_clear()
                self._win.clipboard_append(self._last_generated_token)
                self._token_status.configure(
                    text="  Copied to clipboard",
                    text_color=COLORS["green"],
                )
            except Exception:
                self._token_status.configure(
                    text="  Clipboard copy failed",
                    text_color=COLORS["red"],
                )

    # ── Token list management ─────────────────────────────────

    def _refresh_tokens(self):
        """Fetch token list from server (background thread)."""
        self._token_status.configure(
            text="  Loading tokens...", text_color=COLORS["yellow"])
        threading.Thread(target=self._do_refresh_tokens, daemon=True).start()

    def _do_refresh_tokens(self):
        """Fetch token list from server (background thread)."""
        admin_token = self._config.get("telemetry_token", "")
        url = TOKEN_ADMIN_URL
        try:
            import urllib.request
            req = urllib.request.Request(
                url, method="GET",
                headers={
                    "X-Forge-Token": admin_token,
                },
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                result = json.loads(resp.read())
            if result.get("success"):
                tokens = result.get("tokens", [])
                self._win.after(0, self._populate_token_list, tokens)
            else:
                err = result.get("error", "unknown")
                self._win.after(0, self._token_status.configure,
                                {"text": f"  Failed: {err}",
                                 "text_color": COLORS["red"]})
        except Exception as e:
            self._win.after(0, self._token_status.configure,
                            {"text": f"  Server unreachable: {e}",
                             "text_color": COLORS["red"]})

    def _populate_token_list(self, tokens):
        """Rebuild token list UI (called on main thread)."""
        for child in self._token_list_frame.winfo_children():
            child.destroy()

        if not tokens:
            ctk.CTkLabel(
                self._token_list_frame,
                text="  No tokens registered",
                font=ctk.CTkFont(*FONT_MONO_XS),
                text_color=COLORS["gray"], anchor="w",
            ).pack(fill="x", padx=8, pady=6)
            self._token_status.configure(
                text="  0 tokens", text_color=COLORS["gray"])
            return

        active = [t for t in tokens if not t.get("revoked")]
        revoked = [t for t in tokens if t.get("revoked")]

        for tok in active:
            self._build_token_row(tok)

        if revoked:
            ctk.CTkFrame(
                self._token_list_frame, fg_color=COLORS["border"],
                height=1, corner_radius=0,
            ).pack(fill="x", padx=8, pady=4)
            ctk.CTkLabel(
                self._token_list_frame,
                text="  Revoked:",
                font=ctk.CTkFont(*FONT_MONO_XS),
                text_color=COLORS["gray"], anchor="w",
            ).pack(fill="x", padx=8, pady=(0, 2))
            for tok in revoked:
                self._build_token_row(tok, revoked=True)

        self._token_status.configure(
            text=f"  {len(active)} active, {len(revoked)} revoked",
            text_color=COLORS["gray"])

    def _build_token_row(self, tok, revoked=False):
        """Build a single token row in the token list."""
        row = ctk.CTkFrame(self._token_list_frame, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=2)

        label = tok.get("label", "unknown")
        role = tok.get("role", "master")

        # Role badge color
        role_colors = {
            "origin": COLORS["cyan"],
            "admin": COLORS["yellow"],
            "master": COLORS["gray"],
            "puppet": COLORS["gray"],
        }
        badge_color = role_colors.get(role, COLORS["gray"])

        # Label
        lbl_color = COLORS["gray"] if revoked else COLORS["white"]
        ctk.CTkLabel(
            row, text=f"  {label}",
            font=ctk.CTkFont(*FONT_MONO_SM),
            text_color=lbl_color, anchor="w",
        ).pack(side="left")

        # Role badge
        ctk.CTkLabel(
            row, text=f"[{role}]",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=badge_color,
        ).pack(side="left", padx=(6, 0))

        if revoked:
            ctk.CTkLabel(
                row, text="REVOKED",
                font=ctk.CTkFont(*FONT_MONO_XS),
                text_color=COLORS["red"],
            ).pack(side="left", padx=(6, 0))
            return

        # Role dropdown (only for active tokens)
        role_var = ctk.StringVar(value=role)
        role_menu = ctk.CTkOptionMenu(
            row,
            variable=role_var,
            values=["master", "admin", "origin", "puppet"],
            fg_color=COLORS["bg_card"],
            button_color=COLORS["cyan_dim"],
            button_hover_color=COLORS["cyan"],
            dropdown_fg_color=COLORS["bg_card"],
            dropdown_hover_color=COLORS["cyan_dim"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_XS),
            dropdown_font=ctk.CTkFont(*FONT_MONO_XS),
            width=80,
            command=lambda new_role, lbl=label: self._change_role(lbl, new_role),
        )
        role_menu.pack(side="right", padx=(4, 0))

        # Revoke button
        ctk.CTkButton(
            row, text="Revoke", width=130,
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["red"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_XS),
            height=24,
            command=lambda hp=tok.get("hash_prefix", ""): self._revoke_token(hp),
        ).pack(side="right", padx=(4, 0))

    def _change_role(self, label, new_role):
        """Change a token's role (background thread)."""
        self._token_status.configure(
            text=f"  Changing {label} to {new_role}...",
            text_color=COLORS["yellow"])

        def _do():
            admin_token = self._config.get("telemetry_token", "")
            url = TOKEN_ADMIN_URL
            try:
                import urllib.request
                payload = json.dumps({
                    "action": "set_role",
                    "label": label,
                    "role": new_role,
                }).encode("utf-8")
                req = urllib.request.Request(
                    url, data=payload, method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "X-Forge-Token": admin_token,
                    },
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    result = json.loads(resp.read())
                if result.get("success"):
                    self._win.after(0, self._token_status.configure,
                                    {"text": f"  {label} is now {new_role}",
                                     "text_color": COLORS["green"]})
                    # Refresh list
                    self._do_refresh_tokens()
                else:
                    err = result.get("error", "unknown")
                    self._win.after(0, self._token_status.configure,
                                    {"text": f"  Failed: {err}",
                                     "text_color": COLORS["red"]})
            except Exception as e:
                self._win.after(0, self._token_status.configure,
                                {"text": f"  Failed: {e}",
                                 "text_color": COLORS["red"]})

        threading.Thread(target=_do, daemon=True).start()

    def _revoke_token(self, hash_prefix):
        """Revoke a token (background thread)."""
        if not hash_prefix:
            self._token_status.configure(
                text="  Cannot revoke: no hash prefix",
                text_color=COLORS["red"])
            return

        self._token_status.configure(
            text="  Revoking token...", text_color=COLORS["yellow"])

        def _do():
            admin_token = self._config.get("telemetry_token", "")
            url = TOKEN_ADMIN_URL
            try:
                import urllib.request
                payload = json.dumps({
                    "action": "revoke",
                    "token_hash": hash_prefix,
                }).encode("utf-8")
                req = urllib.request.Request(
                    url, data=payload, method="POST",
                    headers={
                        "Content-Type": "application/json",
                        "X-Forge-Token": admin_token,
                    },
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    result = json.loads(resp.read())
                if result.get("success"):
                    self._win.after(0, self._token_status.configure,
                                    {"text": "  Token revoked",
                                     "text_color": COLORS["green"]})
                    self._do_refresh_tokens()
                else:
                    err = result.get("error", "unknown")
                    self._win.after(0, self._token_status.configure,
                                    {"text": f"  Failed: {err}",
                                     "text_color": COLORS["red"]})
            except Exception as e:
                self._win.after(0, self._token_status.configure,
                                {"text": f"  Failed: {e}",
                                 "text_color": COLORS["red"]})

        threading.Thread(target=_do, daemon=True).start()

    # ── Repo actions ──────────────────────────────────────────

    def _open_github(self):
        """Open the repository on GitHub in the default browser."""
        if self._nwo:
            webbrowser.open(f"https://github.com/{self._nwo}")

    # ── Theme / close ──────────────────────────────────────────

    def _apply_theme(self, color_map: dict):
        if self._win:
            recolor_widget_tree(self._win, color_map)

    def _close(self):
        if hasattr(self, "_theme_cb"):
            remove_theme_listener(self._theme_cb)
        try:
            self._win.grab_release()
        except Exception:
            pass
        try:
            self._win.destroy()
        except Exception:
            pass
