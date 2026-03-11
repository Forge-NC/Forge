"""Fleet Manager — Origin/Master/Puppet topology viewer and management dialog.

Dual-pane CTkToplevel following the model_manager pattern:
  Left pane (280px): Fleet tree with status indicators
  Right pane (fill): Selected node details, genome stats, git identity
"""

import json
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False

from forge.config import ForgeConfig
from forge.ui.themes import (
    get_colors, get_fonts, add_theme_listener, remove_theme_listener,
    recolor_widget_tree,
)
from forge.ui.window_geo import WindowGeo as _WG

log = logging.getLogger(__name__)

# Suppress console window flash on Windows when running git commands
_SP_FLAGS: dict = {}
if sys.platform == "win32":
    _SP_FLAGS["creationflags"] = subprocess.CREATE_NO_WINDOW

# ── Colors & fonts from central theme system ──

COLORS = get_colors()

_F = get_fonts()
FONT_MONO = _F["mono"]
FONT_MONO_SM = _F["mono_sm"]
FONT_MONO_XS = _F["mono_xs"]
FONT_MONO_BOLD = _F["mono_bold"]
FONT_TITLE = _F["title_sm"]


class PuppetManagerDialog:
    """Fleet management GUI — Origin/Master/Puppet topology viewer."""

    def __init__(self, parent: "ctk.CTk", config: ForgeConfig):
        if not HAS_CTK:
            return

        self._config = config
        self._parent = parent
        self._selected_mid: Optional[str] = None
        self._puppet_mgr = None
        self._effects = None

        # ── Window ──
        self._win = ctk.CTkToplevel(parent)
        self._win.title("Fleet Manager")
        self._win.geometry("820x660")
        self._win.minsize(720, 520)
        self._win.configure(fg_color=COLORS["bg_dark"])
        self._win.transient(parent)
        self._win.grab_set()
        self._win.resizable(True, True)
        self._win.protocol("WM_DELETE_WINDOW", self._on_close)

        # Theme listener
        self._theme_cb = lambda cm: self._win.after(
            0, self._apply_theme, cm)
        add_theme_listener(self._theme_cb)

        _WG.restore("fleet_manager", self._win, "820x660")
        _WG.track("fleet_manager", self._win)

        try:
            ico = Path(__file__).parent / "assets" / "forge.ico"
            if ico.exists():
                self._win.iconbitmap(str(ico))
        except Exception:
            pass

        self._build_window()
        self._init_effects()
        self._load_puppet_manager()
        self._refresh()

    # ── Build ──

    def _build_window(self):
        # Header
        header = ctk.CTkFrame(self._win, fg_color=COLORS["bg_panel"],
                              corner_radius=0, height=40,
                              border_width=1, border_color=COLORS["border"])
        header.pack(fill="x")
        header.pack_propagate(False)
        self._header = header

        ctk.CTkLabel(header, text="  Fleet Manager",
                     font=ctk.CTkFont(*FONT_TITLE),
                     text_color=COLORS["cyan"]).pack(
                         side="left", padx=8, pady=6)

        self._role_badge = ctk.CTkLabel(
            header, text="STANDALONE",
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["gray"])
        self._role_badge.pack(side="right", padx=12)

        # Divider
        self._header_div = ctk.CTkFrame(
            self._win, fg_color=COLORS["border"],
            height=1, corner_radius=0)
        self._header_div.pack(fill="x")

        # Body — dual pane
        body = ctk.CTkFrame(self._win, fg_color=COLORS["bg_dark"],
                            corner_radius=0)
        body.pack(fill="both", expand=True)

        # Left pane (280px)
        left = ctk.CTkFrame(body, fg_color=COLORS["bg_panel"],
                            width=280, corner_radius=0,
                            border_color=COLORS["border"],
                            border_width=1)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        self._left = left

        # Left header
        lhdr = ctk.CTkFrame(left, fg_color="transparent")
        lhdr.pack(fill="x", padx=8, pady=(8, 4))
        ctk.CTkLabel(lhdr, text="  FLEET",
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["gray"]).pack(side="left")
        ctk.CTkButton(lhdr, text="Refresh", width=70, height=24,
                      fg_color=COLORS["bg_card"],
                      hover_color=COLORS["cyan_dim"],
                      text_color=COLORS["white"],
                      font=ctk.CTkFont(*FONT_MONO_XS),
                      command=self._refresh).pack(side="right")

        # Left scroll area
        self._tree_scroll = ctk.CTkScrollableFrame(
            left, fg_color=COLORS["bg_panel"],
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["cyan_dim"])
        self._tree_scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # Left bottom buttons
        btn_frame = ctk.CTkFrame(left, fg_color="transparent")
        btn_frame.pack(fill="x", padx=8, pady=(4, 8))
        self._gen_btn = ctk.CTkButton(
            btn_frame, text="Generate Puppet", width=140, height=28,
            fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            font=ctk.CTkFont(*FONT_MONO_XS),
            command=self._on_generate)
        self._gen_btn.pack(side="left", padx=(0, 4))
        self._revoke_btn = ctk.CTkButton(
            btn_frame, text="Revoke", width=70, height=28,
            fg_color=COLORS["bg_card"],
            hover_color=COLORS["red"],
            text_color=COLORS["white"],
            font=ctk.CTkFont(*FONT_MONO_XS),
            command=self._on_revoke)
        self._revoke_btn.pack(side="left")

        # Right pane
        right = ctk.CTkFrame(body, fg_color=COLORS["bg_dark"],
                             corner_radius=0)
        right.pack(side="right", fill="both", expand=True)

        self._detail_scroll = ctk.CTkScrollableFrame(
            right, fg_color=COLORS["bg_dark"],
            scrollbar_button_color=COLORS["border"],
            scrollbar_button_hover_color=COLORS["cyan_dim"])
        self._detail_scroll.pack(fill="both", expand=True, padx=8, pady=8)

        # Placeholder for right pane
        self._detail_placeholder = ctk.CTkLabel(
            self._detail_scroll,
            text='Click "This Machine" to view details\n'
                 'and manage your fleet',
            font=ctk.CTkFont(*FONT_MONO),
            text_color=COLORS["text_dim"],
            justify="center")
        self._detail_placeholder.pack(pady=40)

    # ── Puppet Manager ──

    def _load_puppet_manager(self):
        """Lazily import and create PuppetManager."""
        try:
            from forge.puppet import PuppetManager
            from forge.machine_id import get_machine_id
            bpos = None
            try:
                from forge.passport import BPoS
                bpos = BPoS(
                    data_dir=Path.home() / ".forge",
                    machine_id=get_machine_id())
            except Exception:
                pass
            self._puppet_mgr = PuppetManager(
                data_dir=Path.home() / ".forge" / "puppets",
                bpos=bpos, machine_id=get_machine_id())
        except Exception as e:
            log.debug("PuppetManager init: %s", e)

    # ── Tree ──

    def _refresh(self):
        """Refresh fleet tree in background thread."""
        def _bg():
            puppets = []
            role = "standalone"
            if self._puppet_mgr:
                self._puppet_mgr.refresh_puppet_status()
                puppets = self._puppet_mgr.list_puppets()
                role = self._puppet_mgr.role.value
            self._win.after(0, lambda: self._populate_tree(puppets, role))

        threading.Thread(target=_bg, daemon=True,
                         name="FleetRefresh").start()

    def _populate_tree(self, puppets, role: str):
        """Build the tree UI (main thread)."""
        # Clear existing
        for child in self._tree_scroll.winfo_children():
            child.destroy()

        # Update role badge
        role_labels = {
            "master": "MASTER",
            "puppet": "PUPPET",
            "standalone": "STANDALONE",
        }
        role_colors = {
            "master": COLORS["cyan"],
            "puppet": COLORS["green"],
            "standalone": COLORS["gray"],
        }
        self._role_badge.configure(
            text=role_labels.get(role, role.upper()),
            text_color=role_colors.get(role, COLORS["gray"]))

        # Show seat info for masters
        if role == "master" and self._puppet_mgr:
            summary = self._puppet_mgr.get_seat_summary()
            if summary["puppet_limit"] > 0:
                seat_frame = ctk.CTkFrame(
                    self._tree_scroll, fg_color=COLORS["bg_card"],
                    corner_radius=4)
                seat_frame.pack(fill="x", padx=2, pady=(2, 6))
                ctk.CTkLabel(
                    seat_frame,
                    text=f"Seats: {summary['seats_used']}/{summary['puppet_limit']}",
                    font=ctk.CTkFont(*FONT_MONO_XS),
                    text_color=COLORS["text_dim"]).pack(
                        side="left", padx=8, pady=4)
                pct = summary['seats_used'] / max(1, summary['puppet_limit'])
                bar = ctk.CTkProgressBar(
                    seat_frame, height=8, corner_radius=4, width=80,
                    fg_color=COLORS["bg_dark"],
                    progress_color=COLORS["cyan"] if pct < 0.9
                    else COLORS["yellow"])
                bar.pack(side="right", padx=8, pady=4)
                bar.set(pct)

        # This Machine node
        self._add_tree_node(
            machine_id="self",
            name="This Machine",
            status=role,
            tier="--",
            maturity=0,
            is_self=True)

        # Puppet nodes
        for p in puppets:
            self._add_tree_node(
                machine_id=p.machine_id,
                name=p.name,
                status=p.status,
                tier=p.passport_tier,
                maturity=p.genome_maturity_pct,
                is_self=False)

        if not puppets and role == "master":
            ctk.CTkLabel(
                self._tree_scroll,
                text="  No puppets yet — use Generate Puppet",
                font=ctk.CTkFont(*FONT_MONO_XS),
                text_color=COLORS["text_dim"]).pack(anchor="w", pady=4)

        # Update button visibility
        can_generate = role == "master"
        self._gen_btn.configure(
            state="normal" if can_generate else "disabled")

    def _add_tree_node(self, machine_id: str, name: str,
                       status: str, tier: str, maturity: int,
                       is_self: bool = False):
        """Add a single node to the fleet tree."""
        node = ctk.CTkFrame(self._tree_scroll,
                            fg_color=COLORS["bg_card"],
                            corner_radius=4, height=36,
                            cursor="hand2")
        node.pack(fill="x", padx=2, pady=2)
        node.pack_propagate(False)

        # Status dot
        status_colors = {
            "active": COLORS["green"],
            "master": COLORS["cyan"],
            "puppet": COLORS["green"],
            "standalone": COLORS["gray"],
            "stale": COLORS["yellow"],
            "revoked": COLORS["red"],
        }
        dot_color = status_colors.get(status, COLORS["gray"])
        ctk.CTkLabel(node, text="\u25cf", width=16,
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=dot_color).pack(
                         side="left", padx=(6, 2))

        # Name
        name_color = COLORS["cyan"] if is_self else COLORS["white"]
        ctk.CTkLabel(node, text=name,
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=name_color,
                     anchor="w").pack(side="left", fill="x", expand=True)

        # Maturity badge
        if not is_self and maturity > 0:
            ctk.CTkLabel(node, text=f"{maturity}%", width=36,
                         font=ctk.CTkFont(*FONT_MONO_XS),
                         text_color=COLORS["cyan_dim"]).pack(
                             side="right", padx=4)

        # Click handler
        mid = machine_id

        def _on_click(e, _mid=mid, _is_self=is_self):
            self._selected_mid = _mid
            self._show_detail(_mid, _is_self)

        node.bind("<Button-1>", _on_click)
        for child in node.winfo_children():
            child.bind("<Button-1>", _on_click)

    # ── Detail Pane ──

    def _show_detail(self, machine_id: str, is_self: bool):
        """Show detail for selected node."""
        for child in self._detail_scroll.winfo_children():
            child.destroy()

        if is_self:
            self._show_self_detail()
        else:
            self._show_puppet_detail(machine_id)

    def _show_self_detail(self):
        """Show detail for this machine — role-appropriate view."""
        parent = self._detail_scroll
        pm = self._puppet_mgr

        ctk.CTkLabel(parent, text="This Machine",
                     font=ctk.CTkFont(*FONT_TITLE),
                     text_color=COLORS["cyan"]).pack(
                         anchor="w", pady=(0, 4))

        role = pm.role.value if pm else "standalone"
        role_labels = {
            "standalone": ("Standalone", COLORS["gray"]),
            "master": ("Master", COLORS["cyan"]),
            "puppet": ("Puppet", COLORS["green"]),
        }
        role_text, role_color = role_labels.get(
            role, (role, COLORS["gray"]))
        self._detail_row(parent, "Role", role_text,
                         val_color=role_color)

        # Machine ID — full, untruncated
        mid = pm._machine_id if pm else "?"
        self._detail_row(parent, "Machine ID", mid)

        # ── Standalone view ──
        if role == "standalone":
            ctk.CTkLabel(
                parent,
                text=("Not part of a fleet. Activate a Master passport "
                      "from your Forge purchase, or join an existing "
                      "fleet with a Puppet passport."),
                wraplength=420,
                font=ctk.CTkFont(*FONT_MONO_XS),
                text_color=COLORS["text_dim"],
                anchor="w", justify="left").pack(
                    anchor="w", pady=(0, 6))

            self._show_bpos_info(parent, role)

            ctk.CTkFrame(parent, fg_color=COLORS["border"], height=1
                         ).pack(fill="x", pady=8)
            ctk.CTkLabel(
                parent, text="Activate License",
                font=ctk.CTkFont(*FONT_MONO_BOLD),
                text_color=COLORS["cyan"]).pack(anchor="w", pady=(0, 2))
            ctk.CTkLabel(
                parent,
                text=("If you purchased Forge, download your Master "
                      "passport file and activate it here. This gives "
                      "you Master status with puppet seats."),
                wraplength=420,
                font=ctk.CTkFont(*FONT_MONO_XS),
                text_color=COLORS["text_dim"],
                anchor="w", justify="left").pack(anchor="w", pady=(0, 6))

            act_row = ctk.CTkFrame(parent, fg_color="transparent")
            act_row.pack(fill="x", pady=2)
            ctk.CTkButton(
                act_row, text="Activate Passport...",
                width=180, height=28,
                fg_color=COLORS["cyan_dim"],
                hover_color=COLORS["cyan"],
                text_color=COLORS["bg_dark"],
                font=ctk.CTkFont(*FONT_MONO_SM),
                command=self._on_activate_passport).pack(side="left")

            ctk.CTkButton(
                act_row, text="Join as Puppet...",
                width=160, height=28,
                fg_color=COLORS["bg_card"],
                hover_color=COLORS["cyan_dim"],
                text_color=COLORS["white"],
                font=ctk.CTkFont(*FONT_MONO_SM),
                command=self._on_join_puppet).pack(
                    side="left", padx=(8, 0))

        # ── Master view ──
        elif role == "master":
            if pm:
                self._detail_row(parent, "Tier",
                                 pm.master_tier.title(),
                                 val_color=COLORS["cyan"])
                summary = pm.get_seat_summary()
                self._detail_row(
                    parent, "Seats",
                    f"{summary['seats_used']}/{summary['puppet_limit']} "
                    f"puppet seats used")
                self._detail_row(
                    parent, "Available",
                    f"{summary['seats_available']} seats remaining",
                    val_color=COLORS["green"] if summary['seats_available']
                    else COLORS["yellow"])
                if pm.account_id:
                    self._detail_row(parent, "Account", pm.account_id)

            ctk.CTkLabel(
                parent,
                text=("You are a Master. Generate puppet passports "
                      "for your other machines or team members. Each "
                      "puppet uses one seat from your allocation."),
                wraplength=420,
                font=ctk.CTkFont(*FONT_MONO_XS),
                text_color=COLORS["text_dim"],
                anchor="w", justify="left").pack(
                    anchor="w", pady=(4, 6))

            self._show_bpos_info(parent, role)

        # ── Puppet view ──
        elif role == "puppet":
            if pm:
                self._detail_row(parent, "Tier",
                                 pm.master_tier.title(),
                                 val_color=COLORS["green"])
                self._detail_row(parent, "Seat", pm._seat_id)
                self._detail_row(parent, "Master", pm._master_id)

            ctk.CTkLabel(
                parent,
                text=("This machine runs as a Puppet under a Master. "
                      "Your license and genome are managed by your "
                      "Master's fleet."),
                wraplength=420,
                font=ctk.CTkFont(*FONT_MONO_XS),
                text_color=COLORS["text_dim"],
                anchor="w", justify="left").pack(
                    anchor="w", pady=(4, 6))

            self._show_bpos_info(parent, role)

        # ── Git Identity (all roles) ──
        ctk.CTkFrame(parent, fg_color=COLORS["border"], height=1
                     ).pack(fill="x", pady=8)
        ctk.CTkLabel(parent, text="Git Identity",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan"]).pack(
                         anchor="w", pady=(0, 2))
        ctk.CTkLabel(
            parent,
            text=("Used by AutoForge (/autocommit) when committing "
                  "to your project repos."),
            wraplength=420,
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["text_dim"],
            anchor="w", justify="left").pack(anchor="w", pady=(0, 4))

        git_name = self._git_config("user.name")
        git_email = self._git_config("user.email")

        name_row = ctk.CTkFrame(parent, fg_color="transparent")
        name_row.pack(fill="x", pady=2)
        ctk.CTkLabel(name_row, text="Name", width=80,
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["gray"],
                     anchor="w").pack(side="left")
        self._git_name_entry = ctk.CTkEntry(
            name_row, font=ctk.CTkFont(*FONT_MONO_SM),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=4,
            width=250, height=28)
        self._git_name_entry.insert(0, git_name)
        self._git_name_entry.pack(side="left", padx=(4, 0))

        email_row = ctk.CTkFrame(parent, fg_color="transparent")
        email_row.pack(fill="x", pady=2)
        ctk.CTkLabel(email_row, text="Email", width=80,
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["gray"],
                     anchor="w").pack(side="left")
        self._git_email_entry = ctk.CTkEntry(
            email_row, font=ctk.CTkFont(*FONT_MONO_SM),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            border_width=1, corner_radius=4,
            width=250, height=28)
        self._git_email_entry.insert(0, git_email)
        self._git_email_entry.pack(side="left", padx=(4, 0))

        ctk.CTkButton(
            parent, text="Save Git Identity", width=140, height=28,
            fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            command=self._save_git_identity).pack(anchor="w", pady=(8, 0))

    def _show_bpos_info(self, parent, role: str):
        """Show BPoS genome stats section."""
        if not self._puppet_mgr or not self._puppet_mgr._bpos:
            return
        bpos = self._puppet_mgr._bpos

        ctk.CTkFrame(parent, fg_color=COLORS["border"], height=1
                     ).pack(fill="x", pady=8)
        ctk.CTkLabel(parent, text="Genome",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan"]).pack(
                         anchor="w", pady=(0, 4))

        mat = int(bpos.get_genome_maturity() * 100)
        bar_frame = ctk.CTkFrame(parent, fg_color="transparent")
        bar_frame.pack(fill="x", pady=2)
        ctk.CTkLabel(bar_frame, text="Maturity", width=80,
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["gray"],
                     anchor="w").pack(side="left")
        bar = ctk.CTkProgressBar(
            bar_frame, height=10, corner_radius=4, width=180,
            fg_color=COLORS["bg_dark"],
            progress_color=COLORS["cyan"])
        bar.pack(side="left", padx=(4, 8))
        bar.set(mat / 100.0)
        ctk.CTkLabel(bar_frame, text=f"{mat}%",
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["white"],
                     width=40).pack(side="left")

        # Fall back to billing/reliability when genome hasn't accumulated data
        session_count = bpos._genome.session_count
        if session_count == 0:
            try:
                import json as _j
                bp = bpos._data_dir / "billing.json"
                if bp.exists():
                    session_count = _j.loads(
                        bp.read_text(encoding="utf-8")
                    ).get("lifetime_sessions", 0)
            except Exception:
                pass

        ami_patterns = bpos._genome.ami_failure_catalog_size
        reliability = bpos._genome.reliability_score
        if reliability == 0.0:
            try:
                import json as _j
                rp = bpos._data_dir / "reliability.json"
                if rp.exists():
                    sessions = _j.loads(
                        rp.read_text(encoding="utf-8")
                    ).get("sessions", [])
                    if sessions:
                        scores = [s.get("composite_score", 0) for s in sessions[-5:]]
                        reliability = sum(scores) / len(scores) if scores else 0.0
            except Exception:
                pass

        self._detail_row(parent, "Sessions", str(session_count))
        self._detail_row(parent, "AMI Patterns", str(ami_patterns))
        self._detail_row(parent, "Reliability",
                         f"{reliability:.1f}" if reliability else "—")

    def _show_puppet_detail(self, machine_id: str):
        """Show detail for a puppet node."""
        parent = self._detail_scroll

        if not self._puppet_mgr:
            return

        puppets = {p.machine_id: p
                   for p in self._puppet_mgr.list_puppets()}
        p = puppets.get(machine_id)
        if not p:
            ctk.CTkLabel(parent, text="Puppet not found",
                         font=ctk.CTkFont(*FONT_MONO),
                         text_color=COLORS["red"]).pack(pady=20)
            return

        # Header
        ctk.CTkLabel(parent, text=p.name,
                     font=ctk.CTkFont(*FONT_TITLE),
                     text_color=COLORS["white"]).pack(
                         anchor="w", pady=(0, 4))

        # Status badge
        status_colors = {
            "active": COLORS["green"],
            "stale": COLORS["yellow"],
            "revoked": COLORS["red"],
        }
        ctk.CTkLabel(parent, text=p.status.upper(),
                     font=ctk.CTkFont(*FONT_MONO_XS),
                     text_color=status_colors.get(p.status,
                                                  COLORS["gray"])
                     ).pack(anchor="w")

        # Stats
        self._detail_row(parent, "Machine ID", p.machine_id)
        self._detail_row(parent, "Tier", p.passport_tier)
        self._detail_row(parent, "Sessions", str(p.session_count))
        if p.seat_id:
            self._detail_row(parent, "Seat", p.seat_id)

        # Last seen
        if p.last_seen > 0:
            ago = time.time() - p.last_seen
            if ago < 60:
                seen_str = "just now"
            elif ago < 3600:
                seen_str = f"{int(ago / 60)}m ago"
            elif ago < 86400:
                seen_str = f"{int(ago / 3600)}h ago"
            else:
                seen_str = f"{int(ago / 86400)}d ago"
            self._detail_row(parent, "Last Seen", seen_str)

        # Genome maturity bar
        ctk.CTkFrame(parent, fg_color=COLORS["border"], height=1
                     ).pack(fill="x", pady=8)
        ctk.CTkLabel(parent, text="Genome Maturity",
                     font=ctk.CTkFont(*FONT_MONO_BOLD),
                     text_color=COLORS["cyan"]).pack(
                         anchor="w", pady=(0, 4))

        bar_frame = ctk.CTkFrame(parent, fg_color="transparent")
        bar_frame.pack(fill="x", pady=2)
        bar = ctk.CTkProgressBar(
            bar_frame, height=12, corner_radius=4,
            fg_color=COLORS["bg_dark"],
            progress_color=COLORS["cyan"])
        bar.pack(side="left", fill="x", expand=True)
        bar.set(p.genome_maturity_pct / 100.0)
        ctk.CTkLabel(bar_frame, text=f"{p.genome_maturity_pct}%",
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["white"],
                     width=40).pack(side="right")

        # Genome details (if available from sync dir)
        genome = self._puppet_mgr.get_puppet_genome(p.machine_id)
        if genome:
            ctk.CTkFrame(parent, fg_color=COLORS["border"], height=1
                         ).pack(fill="x", pady=8)
            ctk.CTkLabel(parent, text="Genome Details",
                         font=ctk.CTkFont(*FONT_MONO_BOLD),
                         text_color=COLORS["cyan"]).pack(
                             anchor="w", pady=(0, 4))
            for key in ["session_count", "ami_failure_catalog_size",
                        "ami_model_profiles", "ami_average_quality",
                        "reliability_score", "threat_scans_total",
                        "tool_success_rate"]:
                val = genome.get(key, "--")
                if isinstance(val, float):
                    val = f"{val:.2f}"
                label = key.replace("_", " ").title()
                self._detail_row(parent, label, str(val))

    def _detail_row(self, parent, label: str, value: str,
                    val_color: str | None = None):
        """Add a label: value row to the detail pane."""
        row = ctk.CTkFrame(parent, fg_color="transparent", height=22)
        row.pack(fill="x", pady=1)
        row.pack_propagate(False)
        ctk.CTkLabel(row, text=label, width=120, anchor="w",
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["gray"]).pack(side="left")
        ctk.CTkLabel(row, text=value, anchor="w",
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=val_color or COLORS["white"]).pack(
                         side="left", fill="x", expand=True)

    # ── Git identity ──

    def _git_config(self, key: str) -> str:
        """Read a git config value."""
        try:
            result = subprocess.run(
                ["git", "config", "--global", key],
                capture_output=True, text=True, timeout=5,
                **_SP_FLAGS)
            return result.stdout.strip() if result.returncode == 0 else ""
        except Exception:
            return ""

    def _save_git_identity(self):
        """Save git user.name and user.email."""
        name = self._git_name_entry.get().strip()
        email = self._git_email_entry.get().strip()

        def _bg():
            msgs = []
            errors = []
            try:
                if name:
                    r = subprocess.run(
                        ["git", "config", "--global", "user.name", name],
                        capture_output=True, text=True, timeout=5,
                        **_SP_FLAGS)
                    if r.returncode == 0:
                        msgs.append(f"Name: {name}")
                    else:
                        errors.append(f"name: {r.stderr.strip()}")
                if email:
                    r = subprocess.run(
                        ["git", "config", "--global", "user.email", email],
                        capture_output=True, text=True, timeout=5,
                        **_SP_FLAGS)
                    if r.returncode == 0:
                        msgs.append(f"Email: {email}")
                    else:
                        errors.append(f"email: {r.stderr.strip()}")
                if errors:
                    self._win.after(0, lambda: self._flash_msg(
                        "Error: " + "; ".join(errors), COLORS["red"]))
                elif msgs:
                    msg = "Saved: " + ", ".join(msgs)
                    self._win.after(0, lambda: self._flash_msg(
                        msg, COLORS["green"]))
            except Exception as e:
                self._win.after(0, lambda: self._flash_msg(
                    f"Error: {e}", COLORS["red"]))

        threading.Thread(target=_bg, daemon=True).start()

    # ── Actions ──

    def _on_activate_passport(self):
        """Open file picker to activate a Master passport."""
        if not self._puppet_mgr:
            self._flash_msg("PuppetManager not initialized", COLORS["red"])
            return

        try:
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title="Select Master Passport File",
                filetypes=[("JSON files", "*.json"),
                           ("All files", "*.*")],
                parent=self._win)
            if not path:
                return

            self._flash_msg("Activating with server...", COLORS["cyan"])

            def _bg():
                ok, msg = self._puppet_mgr.activate_master(path)
                color = COLORS["green"] if ok else COLORS["red"]
                self._win.after(0, lambda: self._flash_msg(msg, color))
                if ok:
                    self._win.after(200, self._refresh)
                    self._win.after(400, lambda: self._show_detail(
                        "self", True))

            threading.Thread(target=_bg, daemon=True).start()
        except Exception as e:
            self._flash_msg(f"Error: {e}", COLORS["red"])

    def _on_join_puppet(self):
        """Open file picker to join as a Puppet."""
        if not self._puppet_mgr:
            self._flash_msg("PuppetManager not initialized", COLORS["red"])
            return

        try:
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title="Select Puppet Passport File",
                filetypes=[("JSON files", "*.json"),
                           ("All files", "*.*")],
                parent=self._win)
            if not path:
                return

            self._flash_msg("Joining fleet...", COLORS["cyan"])

            def _bg():
                ok, msg = self._puppet_mgr.init_as_puppet(path)
                color = COLORS["green"] if ok else COLORS["red"]
                self._win.after(0, lambda: self._flash_msg(msg, color))
                if ok:
                    self._win.after(200, self._refresh)
                    self._win.after(400, lambda: self._show_detail(
                        "self", True))

            threading.Thread(target=_bg, daemon=True).start()
        except Exception as e:
            self._flash_msg(f"Error: {e}", COLORS["red"])

    def _on_generate(self):
        """Generate a puppet passport from Master's seat pool."""
        if not self._puppet_mgr:
            self._flash_msg("PuppetManager not initialized", COLORS["red"])
            return

        role = self._puppet_mgr.role.value if self._puppet_mgr else ""
        if role != "master":
            self._flash_msg(
                "Activate a Master passport first",
                COLORS["yellow"])
            return

        # Check seats
        summary = self._puppet_mgr.get_seat_summary()
        if summary["seats_available"] <= 0:
            self._flash_msg(
                f"No puppet seats available "
                f"({summary['seats_used']}/{summary['puppet_limit']} used)",
                COLORS["yellow"])
            return

        dialog = ctk.CTkToplevel(self._win)
        dialog.title("Generate Puppet Passport")
        dialog.geometry("360x200")
        dialog.configure(fg_color=COLORS["bg_dark"])
        dialog.transient(self._win)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog,
            text=(f"Generate a puppet passport for another machine. "
                  f"You have {summary['seats_available']} seat(s) "
                  f"remaining."),
            wraplength=320,
            font=ctk.CTkFont(*FONT_MONO_XS),
            text_color=COLORS["text_dim"],
            anchor="w", justify="left").pack(
                anchor="w", padx=16, pady=(12, 8))

        ctk.CTkLabel(dialog, text="Puppet Name",
                     font=ctk.CTkFont(*FONT_MONO_SM),
                     text_color=COLORS["gray"]).pack(
                         anchor="w", padx=16, pady=(4, 2))
        name_entry = ctk.CTkEntry(
            dialog, font=ctk.CTkFont(*FONT_MONO_SM),
            fg_color=COLORS["bg_card"],
            text_color=COLORS["white"],
            border_color=COLORS["border"],
            placeholder_text="e.g. DevBox, Laptop-2",
            width=300, height=28)
        name_entry.pack(padx=16)

        def _do_generate():
            name = name_entry.get().strip()
            if not name:
                return
            path = self._puppet_mgr.generate_puppet_passport(name)
            dialog.destroy()
            if path:
                self._flash_msg(
                    f"Passport saved: {path.name}", COLORS["green"])
                self._refresh()
            else:
                self._flash_msg(
                    "Failed to generate passport.", COLORS["red"])

        ctk.CTkButton(
            dialog, text="Generate Passport", width=160, height=28,
            fg_color=COLORS["cyan_dim"],
            hover_color=COLORS["cyan"],
            text_color=COLORS["bg_dark"],
            font=ctk.CTkFont(*FONT_MONO_SM),
            command=_do_generate).pack(pady=(12, 0))

    def _on_revoke(self):
        """Revoke the currently selected puppet."""
        if not self._selected_mid or self._selected_mid == "self":
            self._flash_msg("Select a puppet first", COLORS["yellow"])
            return
        if not self._puppet_mgr:
            return
        if self._puppet_mgr.revoke_puppet(self._selected_mid):
            self._flash_msg(
                f"Revoked: {self._selected_mid}",
                COLORS["green"])
            self._refresh()
        else:
            self._flash_msg("Puppet not found", COLORS["red"])

    # ── Helpers ──

    def _flash_msg(self, text: str, color: str):
        """Brief flash message at top of detail pane."""
        lbl = ctk.CTkLabel(self._win, text=text,
                           font=ctk.CTkFont(*FONT_MONO_SM),
                           text_color=color)
        lbl.place(relx=0.5, rely=0.96, anchor="center")
        self._win.after(3000, lbl.destroy)

    def _init_effects(self):
        """Set up visual effects (optional)."""
        try:
            from forge.ui.effects import EffectsEngine
            fx_enabled = self._config.get("effects_enabled", True)
            self._effects = EffectsEngine(self._win, enabled=fx_enabled)
            self._effects.register_card(self._header, self._header_div)
            self._effects.register_window_edge_glow(self._win)
            self._effects.register_window_border_color(self._win)
            self._effects.start()
        except Exception:
            pass

    def _apply_theme(self, color_map: dict):
        if self._win:
            recolor_widget_tree(self._win, color_map)

    def _on_close(self):
        remove_theme_listener(self._theme_cb)
        if self._effects:
            try:
                self._effects.shutdown()
            except Exception:
                pass
        self._win.destroy()
