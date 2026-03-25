"""Slash command handlers — extracted from engine.py for maintainability.

Each command handler is a method on CommandHandler that receives the
engine reference. The engine calls handle_command() which dispatches
to the right handler.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

from forge.constants import TOKEN_ADMIN_URL, ASSURANCE_URL
from forge.crucible import ThreatLevel
from forge.ui.terminal import (
    RESET, DIM, BOLD, YELLOW, RED, CYAN, GREEN, MAGENTA, WHITE, GRAY,
)

log = logging.getLogger(__name__)


class CommandHandler:
    """Handles all slash commands, delegating to the engine for state access."""

    def __init__(self, engine):
        self.engine = engine
        self.io = engine.io  # shortcut for terminal I/O

    def handle(self, cmd: str) -> bool:
        """Handle a slash command. Returns True if handled, False if unknown."""
        parts = cmd.strip().split(None, 1)
        command = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        handler = self._COMMANDS.get(command)
        if handler:
            handler(self, arg)
            return True
        return False

    # ── System commands ──

    def _cmd_quit(self, arg: str) -> bool:
        e = self.engine
        if e._voice:
            e._voice.stop()
        try:
            e.ctx.save_session(e._session_file)
            self.io.print_info(f"Session auto-saved to {e._session_file}")
        except Exception:
            log.debug("Session auto-save on exit failed", exc_info=True)
        e._print_exit_summary()
        raise SystemExit(0)

    def _cmd_help(self, arg: str) -> bool:
        import sys
        self.io.print_help()
        sys.stdout.flush()
        return True

    def _cmd_docs(self, arg: str) -> bool:
        """Open the documentation window (F1)."""
        try:
            from forge.ui.docs_window import DocsWindow
            DocsWindow.open()
            self.io.print_info("Documentation window opened.")
        except ImportError:
            self.io.print_error("Documentation window not available.")
        except Exception as ex:
            self.io.print_error(f"Failed to open docs: {ex}")
        return True

    # ── Context commands ──

    def _cmd_context(self, arg: str) -> bool:
        e = self.engine
        status = e.ctx.status()
        self.io.print_context_bar(status)
        self.io.print_context_detail(e.ctx.list_entries())
        print(f"\n{DIM}Token usage by type:{RESET}")
        for tag, tokens in sorted(
                status["by_tag"].items(), key=lambda x: -x[1]):
            print(f"  {tag:20} {tokens:>8,} tokens")
        if status["evictions"]:
            print(f"\n{YELLOW}Auto-evictions: {status['evictions']}{RESET}")
        return True

    def _cmd_drop(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            self.io.print_error("Usage: /drop <index>")
            return True
        try:
            idx = int(arg)
        except ValueError:
            self.io.print_error("Index must be a number")
            return True
        entry = e.ctx.drop(idx)
        if entry:
            self.io.print_info(f"Dropped entry {idx}: [{entry.role}] "
                       f"{entry.token_count} tokens freed")
            self.io.print_context_bar(e.ctx.status())
        else:
            self.io.print_error(f"Invalid index: {idx}")
        return True

    def _cmd_pin(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            self.io.print_error("Usage: /pin <index>")
            return True
        idx = int(arg) if arg.isdigit() else -1
        if e.ctx.pin(idx):
            self.io.print_info(f"Pinned entry {idx}")
        else:
            self.io.print_error("Invalid index")
        return True

    def _cmd_unpin(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            self.io.print_error("Usage: /unpin <index>")
            return True
        idx = int(arg) if arg.isdigit() else -1
        if e.ctx.unpin(idx):
            self.io.print_info(f"Unpinned entry {idx}")
        else:
            self.io.print_error("Invalid index")
        return True

    def _cmd_clear(self, arg: str) -> bool:
        e = self.engine
        count = e.ctx.clear()
        self.io.print_info(f"Cleared {count} entries")
        self.io.print_context_bar(e.ctx.status())
        return True

    # ── Session commands ──

    def _cmd_save(self, arg: str) -> bool:
        e = self.engine
        path = Path(arg) if arg else e._session_file
        try:
            e.ctx.save_session(path)
            self.io.print_info(f"Session saved to {path}")
        except Exception as ex:
            self.io.print_error(f"Save failed: {ex}")
        return True

    def _cmd_load(self, arg: str) -> bool:
        e = self.engine
        path = Path(arg) if arg else e._session_file
        if not path.exists():
            self.io.print_error(f"File not found: {path}")
            return True
        try:
            count = e.ctx.load_session(path)
            self.io.print_info(f"Loaded {count} entries from {path}")
            self.io.print_context_bar(e.ctx.status())
        except Exception as ex:
            self.io.print_error(f"Load failed: {ex}")
        return True

    def _cmd_reset(self, arg: str) -> bool:
        e = self.engine
        from forge.engine import SYSTEM_PROMPT
        from forge.memory import EpisodicMemory
        e.ctx.clear()
        platform = "Windows" if os.name == "nt" else "Linux"
        sys_prompt = SYSTEM_PROMPT.format(platform=platform, cwd=e.cwd)
        e.ctx.add("system", sys_prompt, tag="system", pinned=True)
        e._turn_count = 0
        e._total_generated = 0
        e._last_warning_pct = 0
        e.memory = EpisodicMemory(
            persist_dir=e._config_dir / "journal")
        e.dedup.reset()  # full reset — clear all dedup history
        self.io.print_info("Session reset. Context cleared. "
                   "Cache & journal preserved.")
        self.io.print_context_bar(e.ctx.status())
        return True

    # ── Model commands ──

    def _cmd_model(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            provider = e.config.get("backend_provider", "ollama")
            self.io.print_info(f"Current model: {e.llm.model} (provider: {provider})")
            ctx_len = e.llm.get_context_length()
            self.io.print_info(f"Context length: {ctx_len:,}")
            return True
        # Support provider:model syntax (e.g., "openai:gpt-4o", "anthropic:claude-sonnet-4-6")
        if ":" in arg and arg.split(":")[0] in ("openai", "anthropic", "ollama"):
            provider, model_name = arg.split(":", 1)
            e.config.set("backend_provider", provider)
            e.llm = e._create_backend(model_name)
            ctx_len = e.llm.get_context_length()
            e.ctx.max_tokens = int(ctx_len * 0.8)
            self.io.print_info(
                f"Switched to: {model_name} (provider: {provider}, "
                f"context: {ctx_len:,})")
            return True
        # Standard model switch within current provider
        available = e.llm.list_models()
        if available and arg not in available:
            self.io.print_error(f"Model '{arg}' not found. Use /models to see available models.")
            return True
        e.llm.model = arg
        ctx_len = e.llm.get_context_length()
        e.ctx.max_tokens = int(ctx_len * 0.8)
        self.io.print_info(f"Switched to: {arg} (context: {ctx_len:,})")
        return True

    def _cmd_models(self, arg: str) -> bool:
        e = self.engine
        models = e.llm.list_models()
        if models:
            self.io.print_info("Available models:")
            for m in models:
                marker = f" {GREEN}*{RESET}" if m == e.llm.model else ""
                print(f"  {m}{marker}")
        else:
            self.io.print_error("No models found in Ollama")
        return True

    # ── Tools commands ──

    def _cmd_tools(self, arg: str) -> bool:
        e = self.engine
        self.io.print_info("Available tools:")
        for name in e.tools.list_tools():
            desc = e.tools.get_description(name)
            print(f"  {CYAN}{name:20}{RESET} {desc}")
        return True

    def _cmd_cd(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            self.io.print_info(f"Current: {e.cwd}")
            return True
        new_cwd = Path(arg).resolve()
        if new_cwd.is_dir():
            e.cwd = str(new_cwd)
            os.chdir(e.cwd)
            self.io.print_info(f"Changed to: {e.cwd}")
        else:
            self.io.print_error(f"Not a directory: {new_cwd}")
        return True

    # ── Billing commands ──

    def _cmd_billing(self, arg: str) -> bool:
        e = self.engine
        sub = arg.strip().lower()

        if sub.startswith("reset"):
            parts = sub.split()
            if len(parts) >= 2 and parts[1] == "confirm":
                e.billing.reset_lifetime()
                self.io.print_info("Lifetime billing stats reset to zero.")
            else:
                self.io.print_warning(
                    "This resets ALL lifetime token/session stats to zero.")
                self.io.print_info("Type: /billing reset confirm")
            return True

        bs = e.billing.status()
        print(f"\n{BOLD}Sandbox Billing{RESET}")
        print(f"  Balance:          {GREEN}${bs['balance']:.4f}{RESET}")
        print(f"  Session tokens:   {bs['session_tokens']:,} "
              f"({bs['session_input']:,} in / {bs['session_output']:,} out)")
        print(f"  Session cached:   {bs['session_cached']:,} tokens NOT spent")
        print(f"  Session duration: {bs['session_duration_m']:.1f} minutes")
        print(f"  Turns:            {bs['turns']}")
        print(f"  Avg cost/turn:    ${bs['cost_per_turn_avg']:.4f}")
        print(f"  Lifetime tokens:  {bs['lifetime_tokens']:,}")
        print(f"  Lifetime sessions:{bs['lifetime_sessions']}")
        return True

    def _cmd_compare(self, arg: str) -> bool:
        e = self.engine
        comp = e.billing.get_comparison()
        print(f"\n{BOLD}Cost Comparison — This Session{RESET}")
        print(f"  Tokens: {comp['session_input_tokens']:,} input + "
              f"{comp['session_output_tokens']:,} output")
        print(f"  Cache saved: {comp['cache_tokens_saved']:,} tokens "
              f"(would cost ${comp['savings_from_cache']:.4f} on Opus)")
        print()
        print(f"  {'Service':38} {'Input':>10} {'Output':>10} {'Total':>10}")
        print(f"  {'-' * 70}")
        for name, data in comp["comparisons"].items():
            print(f"  {name:38} "
                  f"${data['input_cost']:>9.4f} "
                  f"${data['output_cost']:>9.4f} "
                  f"${data['cost']:>9.4f}")
        print(f"\n  {GREEN}{BOLD}Forge: $0.00{RESET} "
              f"{DIM}(local model, your hardware){RESET}")
        return True

    def _cmd_topup(self, arg: str) -> bool:
        e = self.engine
        try:
            amount = float(arg) if arg else 50.0
        except ValueError:
            self.io.print_error("Usage: /topup <amount> (e.g., /topup 100)")
            return True
        e.billing.topup(amount)
        self.io.print_info(f"Added ${amount:.2f} to sandbox balance. "
                   f"New balance: ${e.billing.balance:.2f}")
        return True

    # ── Safety & Config commands ──

    def _cmd_safety(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            print(e.safety.format_status())
            return True
        parts_s = arg.strip().split(None, 1)
        subcmd = parts_s[0].lower()
        subarg = parts_s[1].strip() if len(parts_s) > 1 else ""

        if subcmd == "sandbox":
            if subarg == "on":
                e.safety.sandbox_enabled = True
                if not e.safety.sandbox_roots:
                    e.safety.sandbox_roots = [e.cwd]
                e.config.set("sandbox_enabled", True)
                e.config.save()
                self.io.print_info(f"Sandbox enabled. Roots: "
                           f"{', '.join(e.safety.sandbox_roots)}")
            elif subarg == "off":
                e.safety.sandbox_enabled = False
                e.config.set("sandbox_enabled", False)
                e.config.save()
                self.io.print_info("Sandbox disabled.")
            else:
                self.io.print_error("Usage: /safety sandbox on|off")
            return True

        if subcmd == "allow":
            if not subarg:
                self.io.print_error("Usage: /safety allow <path>")
                return True
            resolved = str(Path(subarg).resolve())
            if resolved not in e.safety.sandbox_roots:
                e.safety.sandbox_roots.append(resolved)
                roots = e.config.get("sandbox_roots", [])
                roots.append(resolved)
                e.config.set("sandbox_roots", roots)
                e.config.save()
            self.io.print_info(f"Added sandbox root: {resolved}")
            return True

        result = e.safety.set_level(subcmd)
        e.config.set("safety_level", e.safety.level)
        e.config.save()
        self.io.print_info(result)
        return True

    def _cmd_crucible(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            print(e.crucible.format_status())
            return True
        subcmd_c = arg.strip().lower()
        if subcmd_c == "on":
            e.crucible.enabled = True
            self.io.print_info("Crucible enabled.")
        elif subcmd_c == "off":
            e.crucible.enabled = False
            self.io.print_info("Crucible disabled.")
        elif subcmd_c == "log":
            if not e.crucible._threat_log:
                self.io.print_info("No threats detected this session.")
            else:
                print(f"\n{BOLD}Crucible Threat Log{RESET}")
                for i, t in enumerate(e.crucible._threat_log, 1):
                    lc = RED if t.level >= ThreatLevel.CRITICAL else YELLOW
                    fname = Path(t.file_path).name if t.file_path else "behavioral"
                    print(f"  {i:3}. {lc}{t.level_name:10}{RESET} "
                          f"{DIM}{fname}:{t.line_start}{RESET} "
                          f"{t.category} — {t.description[:60]}")
        elif subcmd_c == "canary":
            if e.crucible._canary_leaked:
                print(f"  {RED}{BOLD}CANARY LEAKED{RESET} — "
                      f"session integrity compromised")
            else:
                print(f"  {GREEN}Canary intact{RESET} — "
                      f"no prompt injection detected")
        else:
            self.io.print_error("Usage: /crucible [on|off|log|canary]")
        return True

    def _cmd_forensics(self, arg: str) -> bool:
        e = self.engine
        if arg and arg.lower() == "save":
            path = e.forensics.save_report()
            if path:
                self.io.print_info(f"Forensics report saved: {path}")
            else:
                self.io.print_error("Failed to save forensics report.")
            return True
        print(e.forensics.format_summary())
        return True

    def _cmd_router(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            print(e.router.format_status())
            return True
        parts_r = arg.strip().split(None, 1)
        subcmd_r = parts_r[0].lower()
        subarg_r = parts_r[1].strip() if len(parts_r) > 1 else ""

        if subcmd_r == "on":
            if not e.router.small_model:
                self.io.print_error("Set a small model first: /router small <model>")
            else:
                e.router.enabled = True
                e.config.set("router_enabled", True)
                e.config.save()
                self.io.print_info(f"Router enabled. Big: {e.router.big_model}, "
                           f"Small: {e.router.small_model}")
        elif subcmd_r == "off":
            e.router.enabled = False
            e.config.set("router_enabled", False)
            e.config.save()
            self.io.print_info("Router disabled. Using big model for all tasks.")
        elif subcmd_r == "big":
            if not subarg_r:
                self.io.print_error("Usage: /router big <model_name>")
            else:
                e.router.big_model = subarg_r
                e.config.set("default_model", subarg_r)
                e.config.save()
                self.io.print_info(f"Big model set to: {subarg_r}")
        elif subcmd_r == "small":
            if not subarg_r:
                self.io.print_error("Usage: /router small <model_name>")
            else:
                e.router.small_model = subarg_r
                e.config.set("small_model", subarg_r)
                e.config.save()
                self.io.print_info(f"Small model set to: {subarg_r}")
        else:
            self.io.print_error("Usage: /router [on|off|big <model>|small <model>]")
        return True

    def _cmd_provenance(self, arg: str) -> bool:
        from forge.ui.terminal import GREEN, RED, RESET, DIM
        e = self.engine
        chain = e.crucible.get_provenance_chain()
        if not chain:
            self.io.print_info("No provenance data recorded this session.")
            return True
        print(e.crucible.format_provenance_display())
        # Chain integrity verification (HMAC-SHA512)
        valid, break_idx = e.crucible.verify_provenance_chain()
        total = len(e.crucible.get_provenance_chain(last_n=99999))
        if valid:
            print(f"\n  {GREEN}Chain integrity: VERIFIED "
                  f"({total} links, HMAC-SHA512){RESET}")
        else:
            print(f"\n  {RED}Chain integrity: BROKEN at link "
                  f"{break_idx} of {total}{RESET}")
        return True

    def _cmd_threats(self, arg: str) -> bool:
        from forge.ui.terminal import (
            BOLD, RESET, DIM, GREEN, YELLOW, RED, CYAN, WHITE
        )
        e = self.engine
        ti = e.threat_intel

        if not arg:
            # Status overview
            from forge.crucible import _COMPILED_PATTERNS
            hardcoded = len(_COMPILED_PATTERNS)
            external = len(ti.get_compiled_patterns())
            status = ti.get_status()

            print(f"\n{BOLD}Threat Intelligence{RESET}")
            sc = GREEN if status["enabled"] else RED
            print(f"  Status:      {sc}{BOLD}{'ACTIVE' if status['enabled'] else 'DISABLED'}{RESET}")
            print(f"  Patterns:    {hardcoded} hardcoded + {external} external ({hardcoded + external} total)")
            print(f"  Keywords:    {status['keyword_lists']} lists ({status['keyword_terms']} terms)")
            print(f"  Behavioral:  {status['behavioral_rules']} rules")
            print(f"  Version:     {status['signature_version']}")
            if status["last_update"]:
                print(f"  Last update: {status['last_update']}")
            url = status["url"]
            if url:
                print(f"  Source:      {url}")
            else:
                print(f"  Source:      {DIM}bundled only (no URL configured){RESET}")
            src = status["sources"]
            print(f"  Breakdown:   {src['bundled']} bundled, {src['fetched']} fetched, {src['custom']} custom")
            print(f"\n  {DIM}Commands: /threats update | list [category] | search <query> | stats{RESET}")
            return True

        sub = arg.strip().lower()

        if sub == "update":
            url = e.config.get("threat_signatures_url", "")
            if not url:
                self.io.print_warning("No signature URL configured. Set threat_signatures_url in config.")
                return True
            print(f"  Fetching signatures from {url}...")
            result = ti.update(force=True)
            if result["success"]:
                print(f"  {GREEN}{result['message']}{RESET}")
            else:
                print(f"  {RED}{result['message']}{RESET}")
            return True

        if sub == "stats":
            stats = ti.get_detection_stats()
            print(f"\n{BOLD}Detection Statistics (this session):{RESET}")
            print(f"  Total hits: {stats['total_hits']}")
            if stats["top_patterns"]:
                print(f"\n  {BOLD}Top patterns:{RESET}")
                for name, count in stats["top_patterns"][:10]:
                    print(f"    {name:40} {YELLOW}{count}{RESET}")
            if stats["by_category"]:
                print(f"\n  {BOLD}By category:{RESET}")
                for cat, count in stats["by_category"].items():
                    print(f"    {cat:25} {count}")
            if not stats["top_patterns"]:
                print(f"  {DIM}No detections yet.{RESET}")
            return True

        if sub.startswith("list"):
            parts = sub.split(None, 1)
            category = parts[1] if len(parts) > 1 else None
            if category:
                results = ti.list_by_category(category)
                if not results:
                    self.io.print_info(f"No patterns in category '{category}'")
                    return True
                print(f"\n{BOLD}{category}{RESET} ({len(results)} patterns):")
            else:
                results = ti.search_patterns("")  # All patterns
                if not results:
                    self.io.print_info("No external patterns loaded.")
                    return True
                print(f"\n{BOLD}All external patterns{RESET} ({len(results)}):")
            for p in results:
                lc = RED if p["level"] == 3 else YELLOW if p["level"] == 2 else DIM
                level_names = {0: "CLEAN", 1: "SUSPICIOUS", 2: "WARNING", 3: "CRITICAL"}
                ln = level_names.get(p["level"], "?")
                print(f"  {p['name']:40} {lc}[{ln}]{RESET}  {p['description'][:50]}")
            return True

        if sub.startswith("search"):
            parts = sub.split(None, 1)
            if len(parts) < 2:
                self.io.print_error("Usage: /threats search <query>")
                return True
            query = parts[1]
            results = ti.search_patterns(query)
            if not results:
                print(f"  {DIM}No patterns matching '{query}'{RESET}")
                return True
            print(f"\n{BOLD}Results for \"{query}\":{RESET}")
            for p in results:
                lc = RED if p["level"] == 3 else YELLOW if p["level"] == 2 else DIM
                level_names = {0: "CLEAN", 1: "SUSPICIOUS", 2: "WARNING", 3: "CRITICAL"}
                ln = level_names.get(p["level"], "?")
                print(f"  {p['name']:40} {lc}[{ln}]{RESET}  {p['description'][:50]}")
            return True

        self.io.print_error("Usage: /threats [update | list [category] | search <query> | stats]")
        return True

    def _cmd_config(self, arg: str) -> bool:
        e = self.engine
        if arg and arg.lower() == "reload":
            e.config.reload()
            e.safety.level = e.config.get("safety_level", 1)
            e.safety.sandbox_enabled = e.config.get("sandbox_enabled", False)
            e.safety.sandbox_roots = e.config.get("sandbox_roots", [])
            small = e.config.get("small_model", "")
            e.router.small_model = small
            e.router.enabled = bool(small) and e.config.get(
                "router_enabled", False)
            self.io.print_info("Config reloaded from disk.")
            return True
        print(f"\n{BOLD}Forge Configuration{RESET}")
        print(f"  {DIM}File: {e.config.path}{RESET}")
        print(f"  Safety: {e.safety.level_name} ({e.safety.level})")
        print(f"  Sandbox: {'ON' if e.safety.sandbox_enabled else 'OFF'}")
        print(f"  Model: {e.config.get('default_model')}")
        sm = e.config.get('small_model', '')
        print(f"  Small model: {sm or '(not set)'}")
        print(f"  Router: {'ON' if e.router.enabled else 'OFF'}")
        print(f"  Max iterations: {e.config.get('max_agent_iterations')}")
        print(f"  Shell timeout: {e.config.get('shell_timeout')}s")
        print(f"  Swap threshold: {e.config.get('swap_threshold_pct')}%")
        print(f"\n  {DIM}Edit: {e.config.path}{RESET}")
        print(f"  {DIM}Reload: /config reload{RESET}")
        return True

    # ── Hardware & Cache ──

    def _cmd_hardware(self, arg: str) -> bool:
        e = self.engine
        from forge.hardware import (
            get_hardware_summary, format_hardware_report,
            calculate_max_context, format_context_report,
        )
        print(f"\n{DIM}Scanning hardware...{RESET}")
        hw = get_hardware_summary()
        e._hw_summary = hw
        print(f"\n{BOLD}{format_hardware_report(hw)}{RESET}")
        if hw.get("vram_gb", 0) > 0:
            ctx_info = calculate_max_context(hw["vram_gb"], e.llm.model)
            print(f"\n{BOLD}{format_context_report(ctx_info)}{RESET}")
        print()
        return True

    def _cmd_cache(self, arg: str) -> bool:
        e = self.engine
        if arg and arg.lower() == "clear":
            e.cache.invalidate_all()
            self.io.print_info("File cache cleared.")
            return True
        cs = e.cache.stats()
        print(f"\n{BOLD}File Cache{RESET}")
        print(f"  Cached files:   {cs['cached_files']}")
        print(f"  Hits:           {cs['hits']}")
        print(f"  Misses:         {cs['misses']}")
        print(f"  Hit rate:       {cs['hit_rate']:.1f}%")
        print(f"  Tokens saved:   {GREEN}{cs['tokens_saved']:,}{RESET}")
        print(f"  Total cached:   {cs['total_cached_tokens']:,} tokens")
        files = e.cache.cached_files_list()
        if files:
            print(f"\n  {'File':50} {'Tokens':>8} {'Reads':>6} {'Hash':>14}")
            print(f"  {'-'*80}")
            for f in files[:30]:
                short = f["path"]
                if len(short) > 48:
                    short = "..." + short[-45:]
                print(f"  {short:50} {f['tokens']:>8,} "
                      f"{f['reads']:>6} {f['hash']:>14}")
            if len(files) > 30:
                print(f"  ... and {len(files) - 30} more")
        return True

    # ── Scan & Digest ──

    def _cmd_scan(self, arg: str) -> bool:
        e = self.engine
        if not hasattr(e, '_digester') or e._digester is None:
            self.io.print_error("Codebase digester not initialized.")
            return True
        parts = arg.strip().split() if arg else []
        force = False
        path = e.cwd
        for part in parts:
            if part.lower() in ("force", "--force"):
                force = True
            else:
                path = part
        self.io.print_info(
            f"Scanning codebase at {path}"
            f"{' (forced)' if force else ''}...")
        try:
            from forge.tools.digest_tools import _scan_codebase
            summary = _scan_codebase(e._digester, path, force=force)
            print(f"\n{summary[:3000]}")
            if len(summary) > 3000:
                print(f"\n{DIM}... ({len(summary) - 3000} more chars){RESET}")
        except Exception as ex:
            self.io.print_error(f"Scan failed: {ex}")
        return True

    def _cmd_digest(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            d = e._digester.get_digest()
            if not d or not d.files:
                self.io.print_info("No codebase scanned yet. Use /scan [path].")
                return True
            print(f"\n{BOLD}Codebase Digest{RESET}")
            print(f"  Root:      {d.root}")
            print(f"  Files:     {d.total_files}")
            print(f"  Lines:     {d.total_lines:,}")
            print(f"  Symbols:   {d.total_symbols}")
            print(f"  Languages: {', '.join(f'{v} {k}' for k, v in sorted(d.by_language.items(), key=lambda x: -x[1])[:8])}")
            print(f"  Scan time: {d.scan_time:.1f}s")
            if d.notes:
                print(f"  Notes:     {len(d.notes)} saved")
        else:
            from forge.tools.digest_tools import _digest_file
            result = _digest_file(e._digester, arg)
            print(f"\n{result}")
        return True

    # ── Memory commands ──

    def _cmd_journal(self, arg: str) -> bool:
        e = self.engine
        entries = e.memory.get_recent_entries(
            count=int(arg) if arg and arg.isdigit() else 20)
        print(e.memory.format_journal_display(entries))
        return True

    def _cmd_recall(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            self.io.print_error("Usage: /recall <query>")
            return True
        if e.index is None:
            self.io.print_error("Semantic index not initialized. Run /index first.")
            return True
        results = e.index.search(arg, top_k=5)
        if not results:
            self.io.print_info("No results found.")
            return True
        print(f"\n{BOLD}Semantic Recall: \"{arg}\"{RESET}")
        for i, r in enumerate(results, 1):
            score_color = GREEN if r["score"] >= 0.5 else (
                CYAN if r["score"] >= 0.35 else DIM)
            short_path = r["file_path"]
            if len(short_path) > 60:
                short_path = "..." + short_path[-57:]
            print(f"\n  {score_color}{i}. [{r['score']:.3f}]{RESET} "
                  f"{BOLD}{short_path}{RESET} "
                  f"{DIM}(lines {r['start_line']}-{r['end_line']}){RESET}")
            preview = r["content"].split("\n")
            for line in preview[:8]:
                print(f"    {DIM}{line}{RESET}")
            if len(preview) > 8:
                print(f"    {DIM}... ({len(preview) - 8} more lines){RESET}")
        return True

    def _cmd_search(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            self.io.print_error("Usage: /search <query>")
            return True
        if e.index is None:
            self.io.print_error("Semantic index not initialized. Run /index first.")
            return True
        results = e.index.search(arg, top_k=10)
        if not results:
            self.io.print_info("No results found.")
            return True
        print(f"\n{BOLD}Code Search: \"{arg}\"{RESET}")
        for i, r in enumerate(results, 1):
            short_path = r["file_path"]
            if len(short_path) > 50:
                short_path = "..." + short_path[-47:]
            print(f"  {CYAN}{i:2}.{RESET} [{r['score']:.3f}] "
                  f"{short_path} "
                  f"{DIM}L{r['start_line']}-{r['end_line']}{RESET}")
        return True

    def _cmd_index(self, arg: str) -> bool:
        e = self.engine
        self.io.print_info("Checking embedding model...")
        has_embed = e.llm.ensure_embed_model(auto_pull=True)
        if not has_embed:
            self.io.print_error("Failed to download nomic-embed-text.")
            return True

        if e.index is None:
            from forge.index import CodebaseIndex
            e.index = CodebaseIndex(
                persist_dir=e._config_dir / "vectors",
                embed_fn=e.llm.embed,
            )

        # --rebuild: clear cached hashes to force full re-chunk + re-embed
        rebuild = False
        parts = (arg or "").strip().split()
        if "--rebuild" in parts:
            rebuild = True
            parts.remove("--rebuild")

        target_dir = " ".join(parts) if parts else e.cwd

        if rebuild:
            e.index._file_hashes.clear()
            e.index._metadata.clear()
            e.index._vectors = None
            self.io.print_info("Cleared index — full rebuild...")

        self.io.print_info(f"Indexing {target_dir}...")

        def progress(fpath, chunks):
            if chunks > 0:
                short = Path(fpath).name
                print(f"  {DIM}+{chunks} chunks: {short}{RESET}")
            elif fpath.startswith("[embedding"):
                print(f"  {DIM}{fpath}{RESET}", flush=True)

        stats = e.index.index_directory(target_dir, callback=progress)
        print(f"\n{BOLD}Indexing complete:{RESET}")
        print(f"  Files indexed:   {GREEN}{stats['files_indexed']}{RESET}")
        print(f"  Chunks created:  {stats['chunks_created']}")
        print(f"  Files unchanged: {stats['files_unchanged']}")
        print(f"  Files skipped:   {stats['files_skipped']}")
        idx_stats = e.index.stats()
        print(f"  Total index:     {idx_stats['total_chunks']} chunks, "
              f"{idx_stats['index_size_mb']:.1f}MB")
        return True

    def _cmd_tasks(self, arg: str) -> bool:
        e = self.engine
        ts = e.memory.get_task_state()
        if ts is None:
            self.io.print_info("No task state tracked yet.")
            self.io.print_info("Forge auto-tracks objectives after the first swap.")
            return True
        print(f"\n{BOLD}Task State{RESET}")
        print(f"  Objective:     {ts.objective or '(not set)'}")
        print(f"  Subtasks:      {len(ts.subtasks)}")
        done = sum(1 for s in ts.subtasks if s.get('status') == 'done')
        if ts.subtasks:
            print(f"  Progress:      {done}/{len(ts.subtasks)} done")
            for s in ts.subtasks[-10:]:
                status = s.get("status", "pending")
                mark = f"{GREEN}+" if status == "done" else f"{YELLOW}-"
                print(f"    {mark} {s.get('description', '?')}{RESET}")
        print(f"  Files touched: {len(ts.files_modified)}")
        if ts.files_modified:
            for f in ts.files_modified[-10:]:
                print(f"    {DIM}{f}{RESET}")
        print(f"  Context swaps: {ts.context_swaps}")
        print(f"  Decisions:     {len(ts.decisions)}")
        for d in ts.decisions[-5:]:
            print(f"    {DIM}- {d}{RESET}")
        return True

    def _cmd_memory(self, arg: str) -> bool:
        e = self.engine
        print(f"\n{BOLD}Forge Memory System{RESET}")
        print(f"\n  {BOLD}Episodic Memory:{RESET}")
        entries = e.memory.get_session_entries()
        print(f"    Session ID:     {e.memory._session_id}")
        print(f"    Journal entries: {len(entries)}")
        print(f"    Journal file:   {e.memory._journal_file}")

        print(f"\n  {BOLD}Semantic Index:{RESET}")
        if e.index:
            idx = e.index.stats()
            print(f"    Files indexed:  {idx['total_files']}")
            print(f"    Total chunks:   {idx['total_chunks']}")
            print(f"    Index size:     {idx['index_size_mb']:.1f}MB")
            print(f"    Embed model:    {idx['embedding_model']}")
        else:
            print(f"    {DIM}Not initialized. Run /index to set up.{RESET}")

        print(f"\n  {BOLD}Context Partitions:{RESET}")
        pstats = e.ctx.get_partition_stats()
        for part in ("core", "working", "reference", "recall", "quarantine"):
            if part in pstats:
                ps = pstats[part]
                print(f"    {part:12} {ps['tokens']:>8,} tokens "
                      f"({ps['entries']} entries)")

        ts = e.memory.get_task_state()
        print(f"\n  {BOLD}Task State:{RESET}")
        if ts:
            print(f"    Objective:      {ts.objective or '(not set)'}")
            print(f"    Context swaps:  {ts.context_swaps}")
        else:
            print(f"    {DIM}No task tracked yet.{RESET}")
        print()
        return True

    # ── Analytics ──

    def _cmd_stats(self, arg: str) -> bool:
        if arg and arg.strip().lower() == "reliability":
            print(self.engine.reliability.format_terminal())
            return True
        print(self.engine.stats.format_stats_display())
        return True

    def _cmd_dashboard(self, arg: str) -> bool:
        e = self.engine
        try:
            from forge.ui.dashboard import ForgeDashboard, HAS_GUI_DEPS
            if not HAS_GUI_DEPS:
                self.io.print_error("Dashboard requires: pip install customtkinter Pillow")
                return True
            if ForgeDashboard.is_alive():
                self.io.print_info("Dashboard is already open.")
                return True
            brain_path = arg if arg else None
            e._dashboard = ForgeDashboard(
                get_data_fn=lambda: e._get_dashboard_snapshot(),
                brain_path=brain_path,
            )
            e._dashboard.launch(blocking=False)
            self.io.print_info("Neural Cortex dashboard launched.")
        except ImportError:
            self.io.print_error("Dashboard requires: pip install customtkinter Pillow")
        except Exception as ex:
            self.io.print_error(f"Dashboard failed: {ex}")
        return True

    # ── Voice ──

    def _cmd_voice(self, arg: str) -> bool:
        e = self.engine
        if e._voice is None:
            e._init_voice()
            if e._voice is None:
                self.io.print_error("Voice input not available.")
                try:
                    from forge.audio.stt import check_voice_deps
                    deps = check_voice_deps()
                    if deps["missing"]:
                        self.io.print_info(f"Missing: pip install {' '.join(deps['missing'])}")
                except ImportError:
                    self.io.print_info("Install: pip install faster-whisper sounddevice pynput")
                return True

        if not arg:
            mode = e._voice.mode.upper()
            state = "active" if e._voice.ready else "inactive"
            tts_label = e._tts.engine_label if e._tts else "None"
            print(f"\n{BOLD}Voice Input{RESET}")
            print(f"  Status: {GREEN}{state}{RESET}")
            print(f"  Mode:   {CYAN}{mode}{RESET}")
            print(f"  TTS:    {CYAN}{tts_label}{RESET}")
            print(f"  Hotkey: {CYAN}`{RESET} (backtick)")
            print(f"\n  {DIM}Commands:{RESET}")
            print(f"  {CYAN}/voice ptt{RESET}          Push-to-talk (hold ` to speak)")
            print(f"  {CYAN}/voice vox{RESET}          Voice-activated (auto-detect)")
            print(f"  {CYAN}/voice engine edge{RESET}  Cloud neural voices (high quality)")
            print(f"  {CYAN}/voice engine local{RESET} Offline system voices (no internet)")
            print(f"  {CYAN}/voice off{RESET}          Disable voice input")
            return True

        sub = arg.strip().lower()
        if sub == "ptt":
            e._voice.mode = "ptt"
            self.io.print_info("Voice mode: Push-to-Talk (hold ` to speak)")
        elif sub == "vox":
            e._voice.mode = "vox"
            self.io.print_info("Voice mode: VOX (voice-activated, auto-detect speech)")
        elif sub.startswith("engine"):
            parts = sub.split()
            if len(parts) >= 2 and parts[1] in ("edge", "local"):
                engine_choice = parts[1]
                if e._tts:
                    e._tts.engine = engine_choice
                    self.io.print_info(f"TTS engine: {e._tts.engine_label}")
                    # Save preference to config
                    try:
                        e.config.set("tts_engine", engine_choice)
                        e.config.save()
                    except Exception:
                        log.debug("TTS engine config save failed", exc_info=True)
                else:
                    self.io.print_error("TTS not initialized.")
            else:
                self.io.print_error("Usage: /voice engine [edge|local]")
        elif sub == "off":
            e._voice.stop()
            e._voice = None
            self.io.print_info("Voice input disabled.")
        else:
            self.io.print_error("Usage: /voice [ptt|vox|engine|off]")
        return True

    # ── Plugins ──

    def _cmd_plugins(self, arg: str) -> bool:
        e = self.engine
        if hasattr(e, 'plugin_manager'):
            print(e.plugin_manager.format_status())
        else:
            self.io.print_info("Plugin system not initialized.")
        return True

    # ── Plan mode ──

    def _cmd_plan(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            print(e.planner.format_status())
            return True

        sub = arg.strip().lower()
        if sub == "on":
            e.planner.mode = "manual"
            e.planner.arm()
            self.io.print_info("Plan mode armed — next prompt will generate a plan.")
        elif sub == "off":
            e.planner.mode = "off"
            e.planner.disarm()
            self.io.print_info("Plan mode disabled.")
        elif sub == "auto":
            e.planner.mode = "auto"
            self.io.print_info(f"Plan mode: auto (threshold: "
                       f"{e.planner.auto_threshold})")
        elif sub == "always":
            e.planner.mode = "always"
            self.io.print_info("Plan mode: always (every prompt generates a plan)")
        elif sub == "manual":
            e.planner.mode = "manual"
            self.io.print_info("Plan mode: manual (use /plan on before a prompt)")
        elif sub.startswith("verify"):
            parts = sub.split(None, 1)
            if len(parts) < 2:
                mode = e.plan_verifier.mode
                tests = "on" if e.plan_verifier.run_tests else "off"
                lint = "on" if e.plan_verifier.run_lint else "off"
                print(f"\n{BOLD}Plan Verification{RESET}")
                print(f"  Mode:  {GREEN}{mode}{RESET}")
                print(f"  Tests: {tests}")
                print(f"  Lint:  {lint}")
                print(f"  Timeout: {e.plan_verifier.max_test_time}s")
                print(f"\n{DIM}Usage: /plan verify [off|report|repair|strict]{RESET}")
            else:
                vmode = parts[1].strip().lower()
                if vmode in ("off", "report", "repair", "strict"):
                    e.plan_verifier.mode = vmode
                    e.config.set("plan_verify_mode", vmode)
                    self.io.print_info(f"Plan verification: {vmode}")
                else:
                    self.io.print_error(
                        "Usage: /plan verify [off|report|repair|strict]")
        else:
            self.io.print_error(
                "Usage: /plan [on|off|auto|always|manual|verify]")
        return True

    # ── Dedup ──

    def _cmd_dedup(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            print(e.dedup.format_status())
            return True

        sub = arg.strip().lower()
        if sub == "on":
            e.dedup.enabled = True
            self.io.print_info("Tool deduplication enabled.")
        elif sub == "off":
            e.dedup.enabled = False
            self.io.print_info("Tool deduplication disabled.")
        elif sub.startswith("threshold"):
            parts = sub.split()
            if len(parts) >= 2:
                try:
                    val = float(parts[1])
                    if 0.0 <= val <= 1.0:
                        e.dedup.threshold = val
                        self.io.print_info(f"Dedup threshold set to {val:.0%}")
                    else:
                        self.io.print_error("Threshold must be between 0.0 and 1.0")
                except ValueError:
                    self.io.print_error("Invalid threshold value.")
            else:
                self.io.print_info(f"Current threshold: {e.dedup.threshold:.0%}")
        else:
            self.io.print_error("Usage: /dedup [on|off|threshold <0.0-1.0>]")
        return True

    # ── Theme ──

    def _cmd_theme(self, arg: str) -> bool:
        e = self.engine
        from forge.ui.themes import (
            list_themes, get_theme, set_theme, THEME_LABELS,
        )
        if not arg:
            current = get_theme()
            print(f"\n{BOLD}UI Themes{RESET}")
            print(f"  Current: {GREEN}{THEME_LABELS.get(current, current)}{RESET}")
            print()
            for name in list_themes():
                label = THEME_LABELS.get(name, name)
                marker = f" {GREEN}*{RESET}" if name == current else ""
                print(f"  {CYAN}{name:18}{RESET} {label}{marker}")
            print(f"\n{DIM}Usage: /theme <name>{RESET}")
            return True

        name = arg.strip().lower()
        if name not in list_themes():
            self.io.print_error(f"Unknown theme: {name}")
            self.io.print_info(f"Available: {', '.join(list_themes())}")
            return True

        set_theme(name)
        e.config.set("theme", name)
        e.config.save()
        label = THEME_LABELS.get(name, name)
        self.io.print_info(f"Theme set to: {label}")
        return True

    # ── Continuity Grade ──

    def _cmd_continuity(self, arg: str) -> bool:
        e = self.engine
        if not arg:
            print(e.continuity.format_detail())
            return True

        sub = arg.strip().lower()
        if sub == "history":
            print(e.continuity.format_history())
        elif sub.startswith("set"):
            parts = sub.split()
            if len(parts) >= 2:
                try:
                    val = int(parts[1])
                    if 0 <= val <= 100:
                        e.continuity.threshold = val
                        e.config.set("continuity_threshold", val)
                        e.config.save()
                        self.io.print_info(f"Continuity recovery threshold set to {val}")
                    else:
                        self.io.print_error("Threshold must be between 0 and 100")
                except ValueError:
                    self.io.print_error("Invalid threshold value.")
            else:
                self.io.print_info(f"Current threshold: {e.continuity.threshold}")
        elif sub == "on":
            e.continuity.enabled = True
            e.config.set("continuity_enabled", True)
            e.config.save()
            self.io.print_info("Continuity Grade enabled.")
        elif sub == "off":
            e.continuity.enabled = False
            e.config.set("continuity_enabled", False)
            e.config.save()
            self.io.print_info("Continuity Grade disabled.")
        else:
            self.io.print_error("Usage: /continuity [history|set <N>|on|off]")
        return True

    # ── Adaptive Model Intelligence ──

    def _cmd_ami(self, arg: str) -> bool:
        """Adaptive Model Intelligence status and controls.

        Subcommands:
          /ami          — Status overview
          /ami probe    — Re-probe model capabilities
          /ami reset    — Clear failure catalog and learned patterns
          /ami stats    — Detailed analytics
        """
        e = self.engine
        if not hasattr(e, 'ami'):
            self.io.print_error("AMI not initialized.")
            return True

        sub = arg.strip().lower() if arg else ""

        if not sub:
            print(e.ami.format_status())
            return True

        if sub == "probe":
            model = e.llm.model
            self.io.print_info(f"Probing {model}...")
            caps = e.ami.probe_model_capabilities(model, force=True)
            if caps:
                native_s = "YES" if caps.supports_native_tools else "NO"
                json_s = "YES" if caps.supports_json_format else "NO"
                text_s = "YES" if caps.supports_text_tool_calls else "PARTIAL"
                self.io.print_info(f"  Native tool calling: {native_s}")
                self.io.print_info(f"  JSON format mode:    {json_s}")
                self.io.print_info(f"  Text JSON parsing:   {text_s}")
                self.io.print_info(f"  Preferred format:    {caps.preferred_tool_format}")
                self.io.print_info("Capabilities cached.")
            else:
                self.io.print_warning("Probe failed — LLM may not be available.")
            return True

        if sub == "reset":
            e.ami._failure_catalog.clear()
            e.ami._turn_history.clear()
            from forge.ami import AMIStats
            e.ami._stats = AMIStats()
            e.ami._persist_state()
            self.io.print_info("AMI failure catalog and learned patterns cleared.")
            return True

        if sub == "stats":
            status = e.ami.get_status()
            q = status["quality"]
            r = status["retries"]
            s = e.ami._stats
            print(f"\nAMI Session Statistics:")
            print(f"  Total turns:        {s.total_turns}")
            print(f"  Retries triggered:  {r['total']} "
                  f"({r['total']/max(1,s.total_turns)*100:.0f}%)")
            rate = r['recovery_rate']
            print(f"  Recovery rate:      {rate:.0%} "
                  f"({r['succeeded']}/{r['total']})" if r['total'] else
                  f"  Recovery rate:      N/A")
            print(f"  Tier 1 (parse):     {r['tier1']['attempts']} attempts, "
                  f"{r['tier1']['successes']} success")
            print(f"  Tier 2 (constrain): {r['tier2']['attempts']} attempts, "
                  f"{r['tier2']['successes']} success")
            print(f"  Tier 3 (reset):     {r['tier3']['attempts']} attempts, "
                  f"{r['tier3']['successes']} success")
            if s.total_turns > 0:
                print(f"  Avg quality:        {q['average']:.2f}")
                print(f"  Worst quality:      {q['worst']:.2f}")
                print(f"  Best quality:       {q['best']:.2f}")
            return True

        self.io.print_error("Usage: /ami [probe|reset|stats]")
        return True

    # ── Synapse check ──

    def _cmd_synapse(self, arg: str) -> bool:
        """Trigger a synapse check — cycles all Neural Cortex thought modes."""
        from pathlib import Path
        trigger = Path.home() / ".forge" / "synapse_check.txt"
        try:
            trigger.write_text("run", encoding="utf-8")
            self.io.print_info("Synapse check triggered on Neural Cortex dashboard.")
            self.io.print_info("(Dashboard must be running to see the animation cycle.)")
        except Exception as exc:
            self.io.print_error(f"Failed to trigger synapse check: {exc}")
        return True

    # ── Bug Reporter ──

    def _cmd_report(self, arg: str) -> bool:
        """Manually file a bug report via the Bug Reporter.

        Usage: /report <description of the issue>
        """
        e = self.engine
        if not arg.strip():
            self.io.print_error("Usage: /report <description of the issue>")
            return True

        # Check gh CLI availability
        import subprocess
        try:
            result = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                self.io.print_error(
                    "GitHub CLI not authenticated. Run: gh auth login")
                return True
        except FileNotFoundError:
            self.io.print_error(
                "GitHub CLI (gh) not found. Install from: "
                "https://cli.github.com/")
            return True
        except Exception as ex:
            self.io.print_error(f"Failed to check gh auth: {ex}")
            return True

        reporter = getattr(e, "bug_reporter", None)
        if not reporter:
            self.io.print_error("Bug reporter not initialized.")
            return True

        self.io.print_info("Filing bug report...")
        url = reporter.file_manual_report(arg.strip())
        if url:
            self.io.print_info(f"Bug report filed: {url}")
        else:
            self.io.print_error("Failed to file bug report.")
        return True

    # ── Audit export ──

    def _cmd_export(self, arg: str) -> bool:
        """Export full audit package as a zip bundle.

        Flags: --redact (strip sensitive content), --upload (send to server)
        """
        from forge.audit import AuditExporter
        e = self.engine

        redact = False
        upload = False
        path_override = None
        parts = arg.strip().split()
        for p in parts:
            if p == "--redact":
                redact = True
            elif p == "--upload":
                upload = True
            elif not p.startswith("-"):
                path_override = Path(p)

        exporter = AuditExporter()
        try:
            package = exporter.build_package(
                forensics=e.forensics,
                memory=e.memory,
                stats=e.stats,
                billing=e.billing,
                crucible=e.crucible,
                continuity=e.continuity,
                plan_verifier=e.plan_verifier,
                reliability=getattr(e, "reliability", None),
                bug_reporter=getattr(e, "bug_reporter", None),
                ami=getattr(e, "ami", None),
                shipwright=getattr(e, "_shipwright", None),
                autoforge=getattr(e, "_autoforge", None),
                bpos=getattr(e, "_bpos", None),
                tools=getattr(e, "tools", None),
                session_start=e._session_start,
                turn_count=e._turn_count,
                model=e.llm.model,
                cwd=e.cwd,
            )

            if not upload:
                out_path = exporter.export(
                    package, path=path_override, redact=redact)
                print(exporter.format_summary(package))
                self.io.print_info(f"Audit exported: {out_path}")
                if redact:
                    self.io.print_info(
                        "(Redacted mode — sensitive content stripped)")
            else:
                from forge.telemetry import upload_telemetry
                use_redact = redact or e.config.get("telemetry_redact", True)
                self.io.print_info("Uploading audit bundle...")
                upload_telemetry(
                    forensics=e.forensics,
                    memory=e.memory,
                    stats=e.stats,
                    billing=e.billing,
                    crucible=e.crucible,
                    continuity=e.continuity,
                    plan_verifier=e.plan_verifier,
                    reliability=getattr(e, "reliability", None),
                    session_start=e._session_start,
                    turn_count=e._turn_count,
                    model=e.llm.model,
                    cwd=e.cwd,
                    redact=use_redact,
                    telemetry_url=e.config.get("telemetry_url", ""),
                    blocking=True,
                )
                label = "Upload complete (redacted)" if use_redact \
                    else "Upload complete"
                self.io.print_info(label)
        except Exception as ex:
            self.io.print_error(f"Export failed: {ex}")
        return True

    # ── Benchmark suite ──

    def _cmd_benchmark(self, arg: str) -> bool:
        """Run or inspect benchmark suite.

        Usage: /benchmark list | run [suite] | live [suite] | results [suite]
                          | compare | report
        """
        from forge.benchmark import BenchmarkRunner

        runner = BenchmarkRunner()
        parts = arg.strip().split()
        sub = parts[0] if parts else "list"

        if sub == "list":
            suites = runner.list_suites()
            if not suites:
                self.io.print_info("No benchmark suites found.")
                return True
            self.io.print_info("Available suites:")
            for s in suites:
                scenarios = runner.list_scenarios(s)
                self.io.print_info(f"  {s} ({len(scenarios)} scenarios)")
            return True

        if sub == "run" or sub == "live":
            suite_name = parts[1] if len(parts) > 1 else "refactoring"
            e = self.engine
            model = e.llm.model if hasattr(e, "llm") else ""
            config_hash = BenchmarkRunner.compute_config_hash(
                model=model,
                context_size=e.config.get("context_size", 0),
                safety_level=e.config.get("safety_level", 1),
                router_enabled=e.config.get("router_enabled", False),
                dedup_enabled=e.config.get("dedup_enabled", True),
                verify_mode=e.config.get("plan_verify_mode", "off"),
            )
            scenarios = runner.list_scenarios(suite_name)
            if not scenarios:
                self.io.print_error(f"No scenarios found in suite '{suite_name}'.")
                return True

            # Live execution: send prompts to actual LLM backend
            self.io.print_info(
                f"Running {len(scenarios)} scenarios from '{suite_name}' "
                f"(live, model={model})...")
            result = runner.run_suite_live(
                suite_name, backend=e.llm,
                system_prompt=None, config_hash=config_hash)
            # Format and display results
            passed = sum(1 for r in result.results if r.passed)
            total = len(result.results)
            print(f"\n{BOLD}Benchmark Results: {suite_name}{RESET}")
            print(f"  Model:  {result.model}")
            print(f"  Passed: {GREEN}{passed}{RESET}/{total} "
                  f"({passed / total * 100:.0f}%)" if total else "")
            print(f"  Avg quality: {sum(r.quality_score for r in result.results) / max(total, 1):.2f}")
            for r in result.results:
                icon = f"{GREEN}PASS{RESET}" if r.passed else f"{RED}FAIL{RESET}"
                print(f"    [{icon}] {r.scenario_name} "
                      f"({r.duration_s:.1f}s, q={r.quality_score:.2f})")
                if r.error:
                    print(f"      {DIM}{r.error[:80]}{RESET}")
            # Save result
            from dataclasses import asdict
            save_data = asdict(result)
            save_data["suite_name"] = suite_name
            save_data["timestamp"] = time.time()
            save_data["config_hash"] = config_hash
            save_data["pass_rate"] = passed / max(total, 1)
            results_dir = Path.home() / ".forge" / "benchmark_results"
            results_dir.mkdir(parents=True, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            path = results_dir / f"{suite_name}_{ts}.json"
            import json as _json
            path.write_text(_json.dumps(save_data, default=str, indent=2),
                            encoding="utf-8")
            self.io.print_info(f"Results saved: {path}")
            return True

        if sub == "results":
            suite_filter = parts[1] if len(parts) > 1 else None
            results = runner.load_results(suite=suite_filter, count=10)
            if not results:
                self.io.print_info("No benchmark results found.")
                return True
            for r in results:
                passed = sum(1 for s in r.get("results", [])
                             if s.get("passed"))
                total = len(r.get("results", []))
                ts = time.strftime("%Y-%m-%d %H:%M",
                                   time.localtime(r.get("timestamp", 0)))
                self.io.print_info(
                    f"  {ts}  {r.get('suite_name', '?')}  "
                    f"{passed}/{total} passed  "
                    f"({r.get('pass_rate', 0) * 100:.0f}%)  "
                    f"model={r.get('model', '?')}")
            return True

        if sub == "compare":
            results = runner.load_results(count=2)
            if len(results) < 2:
                self.io.print_info(
                    "Need at least 2 results to compare. Run benchmarks first.")
                return True
            diff = runner.compare_results(results[1], results[0])
            self.io.print_info("Benchmark comparison (older -> newer):")
            for k, v in diff.items():
                if "delta" in k:
                    sign = "+" if v > 0 else ""
                    self.io.print_info(f"  {k}: {sign}{v:.3f}")
                else:
                    self.io.print_info(f"  {k}: {v}")
            return True

        if sub == "report":
            from forge.benchmark_report import build_comparison_report, save_report
            results = runner.load_results(count=10)
            if not results:
                self.io.print_info("No benchmark results to report. Run benchmarks first.")
                return True
            html = build_comparison_report(results)
            report_dir = Path.home() / ".forge" / "exports"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_path = report_dir / "benchmark_report.html"
            save_report(html, report_path)
            self.io.print_info(f"Report saved: {report_path}")
            # Try to open in browser
            try:
                import webbrowser
                webbrowser.open(str(report_path))
            except Exception:
                log.debug("Failed to open benchmark report in browser", exc_info=True)
            return True

        self.io.print_error(
            "Usage: /benchmark list | run [suite] | results [suite] "
            "| compare | report")
        return True

    # ── Update & Admin commands ──

    def _cmd_update(self, arg: str) -> bool:
        """Check for and apply updates from the remote repository."""
        import subprocess
        from forge.tools.git_tools import _run_git, is_git_repo

        forge_root = str(Path(__file__).resolve().parents[1])

        if not is_git_repo(forge_root):
            self.io.print_error("Forge is not installed from a git repository.")
            return True

        self.io.print_info("Checking for updates...")
        fetch_out = _run_git(["fetch", "origin"], forge_root, timeout=15)
        if fetch_out.startswith("Error:"):
            self.io.print_error(f"Fetch failed: {fetch_out}")
            return True

        branch_out = _run_git(
            ["rev-parse", "--abbrev-ref", "HEAD"], forge_root)
        branch = branch_out.strip() if not branch_out.startswith("Error:") \
            else "master"
        remote_ref = f"origin/{branch}"

        behind_out = _run_git(
            ["rev-list", "--count", f"HEAD..{remote_ref}"], forge_root)
        try:
            behind_count = int(behind_out.strip())
        except ValueError:
            behind_count = 0

        if behind_count == 0:
            print(f"\n  {GREEN}Forge is up to date.{RESET}")
            return True

        self.io.print_info(f"{behind_count} new commit(s) available.")
        changelog = _run_git(
            ["log", "--oneline", f"HEAD..{remote_ref}"], forge_root)
        print(f"\n{DIM}Incoming changes:{RESET}")
        for line in changelog.strip().split("\n")[:15]:
            print(f"  {line}")
        if behind_count > 15:
            print(f"  {DIM}... and {behind_count - 15} more{RESET}")

        if arg.strip().lower() != "--yes":
            print(f"\n{YELLOW}Run /update --yes to apply these changes.{RESET}")
            return True

        self.io.print_info("Pulling updates...")
        pull_out = _run_git(
            ["pull", "--ff-only", "origin", branch],
            forge_root, timeout=30)
        if "Error:" in pull_out or "fatal:" in pull_out.lower():
            self.io.print_error(f"Pull failed: {pull_out}")
            self.io.print_info(
                "Try resolving manually: cd to Forge dir, run 'git pull'")
            return True

        print(f"\n  {GREEN}Updated successfully.{RESET}")

        changed = _run_git(
            ["diff", "--name-only", f"HEAD~{behind_count}", "HEAD"],
            forge_root)
        changed_files = changed.strip().split("\n") \
            if changed.strip() else []

        if "pyproject.toml" in changed_files:
            self.io.print_info(
                "pyproject.toml changed -- reinstalling dependencies...")
            venv_py = Path(forge_root) / ".venv" / "Scripts" / "python.exe"
            if not venv_py.exists():
                venv_py = Path(forge_root) / ".venv" / "bin" / "python"
            if venv_py.exists():
                extra = {}
                if os.name == "nt":
                    extra["creationflags"] = subprocess.CREATE_NO_WINDOW
                try:
                    subprocess.run(
                        [str(venv_py), "-m", "pip", "install", "-e",
                         forge_root, "--quiet"],
                        capture_output=True, timeout=120, **extra)
                    self.io.print_info("Dependencies updated.")
                except Exception as ex:
                    self.io.print_error(f"pip install failed: {ex}")

        core = {"forge/engine.py", "forge/commands.py", "forge/config.py",
                "forge/context.py", "forge/__main__.py", "forge/__init__.py"}
        core_hit = [f for f in changed_files if f in core]
        if core_hit:
            print(f"\n{YELLOW}Core files changed: {', '.join(core_hit)}")
            print(f"Restart Forge to use the new code.{RESET}")
        else:
            self.io.print_info("No core files changed -- update is live.")
        return True

    def _cmd_admin(self, arg: str) -> bool:
        """GitHub collaborator management and token administration."""
        import subprocess
        import json as _json
        import secrets
        import hashlib

        forge_root = str(Path(__file__).resolve().parents[1])

        # Detect repo owner/name from git remote
        extra = {}
        if os.name == "nt":
            extra["creationflags"] = subprocess.CREATE_NO_WINDOW

        def _gh(gh_args, timeout=15):
            try:
                r = subprocess.run(
                    ["gh"] + gh_args, capture_output=True, text=True,
                    timeout=timeout, **extra)
                return r.returncode == 0, r.stdout.strip()
            except FileNotFoundError:
                return False, "gh CLI not found. Install: https://cli.github.com"
            except subprocess.TimeoutExpired:
                return False, "Command timed out"

        def _get_nwo():
            from forge.tools.git_tools import _run_git
            url = _run_git(["remote", "get-url", "origin"], forge_root)
            if url.startswith("Error:"):
                return None
            url = url.strip().rstrip("/")
            if url.endswith(".git"):
                url = url[:-4]
            if "github.com/" in url:
                return url.split("github.com/")[-1]
            if "github.com:" in url:
                return url.split("github.com:")[-1]
            return None

        nwo = _get_nwo()

        e = self.engine
        if e.config.get("license_tier", "community") != "origin":
            self.io.print_error("/admin is Origin-only.")
            return True

        parts = arg.strip().split(None, 1)
        sub = parts[0].lower() if parts else "list"
        subarg = parts[1].strip() if len(parts) > 1 else ""

        if sub == "list":
            if not nwo:
                self.io.print_error("Cannot detect GitHub repo from remote.")
                return True
            ok, out = _gh(["api", f"repos/{nwo}/collaborators"])
            if not ok:
                self.io.print_error(f"Failed: {out}")
                return True
            try:
                collabs = _json.loads(out)
            except _json.JSONDecodeError:
                self.io.print_error("Invalid response from GitHub.")
                return True
            print(f"\n{BOLD}Collaborators on {nwo}:{RESET}")
            for c in collabs:
                login = c.get("login", "?")
                role = c.get("role_name", c.get("permissions", {}).get("admin") and "admin" or "push")
                print(f"  {CYAN}{login:20}{RESET} {DIM}{role}{RESET}")
            if not collabs:
                print(f"  {DIM}(none){RESET}")

        elif sub == "invite":
            if not subarg:
                self.io.print_error("Usage: /admin invite <github-username>")
                return True
            if not nwo:
                self.io.print_error("Cannot detect GitHub repo from remote.")
                return True
            ok, out = _gh(["api", "-X", "PUT",
                          f"repos/{nwo}/collaborators/{subarg}",
                          "-f", "permission=pull"])
            if ok:
                print(f"  {GREEN}Invitation sent to {subarg} (read-only access).{RESET}")
            else:
                self.io.print_error(f"Failed: {out}")

        elif sub == "remove":
            if not subarg:
                self.io.print_error("Usage: /admin remove <github-username>")
                return True
            if not nwo:
                self.io.print_error("Cannot detect GitHub repo from remote.")
                return True
            ok, out = _gh(["api", "-X", "DELETE",
                          f"repos/{nwo}/collaborators/{subarg}"])
            if ok:
                print(f"  {GREEN}Removed {subarg} from {nwo}.{RESET}")
            else:
                self.io.print_error(f"Failed: {out}")

        elif sub == "pending":
            if not nwo:
                self.io.print_error("Cannot detect GitHub repo from remote.")
                return True
            ok, out = _gh(["api", f"repos/{nwo}/invitations"])
            if not ok:
                self.io.print_error(f"Failed: {out}")
                return True
            try:
                invites = _json.loads(out)
            except _json.JSONDecodeError:
                self.io.print_error("Invalid response from GitHub.")
                return True
            print(f"\n{BOLD}Pending invitations:{RESET}")
            for inv in invites:
                invitee = inv.get("invitee", {}).get("login", "?")
                print(f"  {CYAN}{invitee:20}{RESET} "
                      f"{DIM}id={inv.get('id')}{RESET}")
            if not invites:
                print(f"  {DIM}(none){RESET}")

        elif sub == "token":
            if not subarg:
                self.io.print_error("Usage: /admin token <label>")
                return True
            label = subarg.replace(" ", "-")
            token = secrets.token_hex(32)
            token_hash = hashlib.sha512(token.encode()).hexdigest()

            # Attempt server registration
            admin_token = self.engine.config.get("telemetry_token", "")
            server_ok = False
            if admin_token:
                try:
                    import requests
                    resp = requests.post(TOKEN_ADMIN_URL, json={
                        "action": "register",
                        "token_hash": token_hash,
                        "label": label,
                    }, headers={"X-Forge-Token": admin_token}, timeout=5)
                    if resp.status_code == 200:
                        server_ok = True
                except Exception:
                    log.debug("Team token server registration failed", exc_info=True)

            # Detect repo URL for onboarding instructions
            repo_url = ""
            if nwo:
                repo_url = f"https://github.com/{nwo}.git"

            print(f"\n{BOLD}Generated telemetry token for {CYAN}{label}{RESET}")
            print()
            print(f"  {BOLD}--- Send these instructions to your tester ---{RESET}")
            print()
            print(f"  1. Install Python 3.10+ from {CYAN}https://python.org{RESET}")
            print(f"  2. Install Ollama from {CYAN}https://ollama.com{RESET}")
            if nwo:
                print(f"  3. Accept the GitHub invite you received by email")
                print(f"  4. Run this command:")
                print()
                print(f"     {GREEN}git clone {repo_url} && cd Forge && "
                      f"python install.py --token {token} "
                      f"--label \"{label}\"{RESET}")
            else:
                print(f"  3. Run this command:")
                print()
                print(f"     {GREEN}cd Forge && python install.py "
                      f"--token {token} --label \"{label}\"{RESET}")
            print()
            print(f"  5. Double-click {CYAN}Forge NC{RESET} on your desktop")
            print()
            print(f"  {DIM}Token:  {token}{RESET}")
            print(f"  {DIM}Hash:   {token_hash}{RESET}")
            if server_ok:
                print(f"  {GREEN}Registered on server: yes{RESET}")
            else:
                if admin_token:
                    print(f"  {YELLOW}Registered on server: failed "
                          f"(add hash to tokens.json manually){RESET}")
                else:
                    print(f"  {YELLOW}Registered on server: no "
                          f"(no telemetry_token in config){RESET}")

        elif sub == "role":
            if not subarg or len(subarg.split()) < 2:
                self.io.print_error(
                    "Usage: /admin role <label> <origin|admin|master|puppet>")
                return True
            parts_r = subarg.split(None, 1)
            role_label = parts_r[0]
            role_value = parts_r[1].lower().strip()
            if role_value not in ("origin", "admin", "master", "puppet"):
                self.io.print_error(
                    f"Invalid role '{role_value}'. "
                    f"Must be: origin, admin, master, or puppet")
                return True

            admin_token = self.engine.config.get("telemetry_token", "")
            if not admin_token:
                self.io.print_error(
                    "No telemetry_token in config. "
                    "Only Origin can change roles.")
                return True

            try:
                import requests
                resp = requests.post(TOKEN_ADMIN_URL, json={
                    "action": "set_role",
                    "label": role_label,
                    "role": role_value,
                }, headers={"X-Forge-Token": admin_token}, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("success"):
                        print(f"  {GREEN}{role_label} is now "
                              f"{role_value}.{RESET}")
                    else:
                        self.io.print_error(
                            f"Failed: {data.get('error', 'unknown')}")
                else:
                    self.io.print_error(
                        f"Server returned {resp.status_code}")
            except Exception as ex:
                self.io.print_error(f"Failed: {ex}")

        else:
            self.io.print_error(
                "Usage: /admin [list | invite <user> | remove <user> "
                "| pending | token <label> | role <label> <role>]")
        return True

    # ── Command dispatch table ──

    _COMMANDS = {
        "/quit": _cmd_quit,
        "/exit": _cmd_quit,
        "/help": _cmd_help,
        "/docs": _cmd_docs,
        "/context": _cmd_context,
        "/drop": _cmd_drop,
        "/pin": _cmd_pin,
        "/unpin": _cmd_unpin,
        "/clear": _cmd_clear,
        "/save": _cmd_save,
        "/load": _cmd_load,
        "/reset": _cmd_reset,
        "/model": _cmd_model,
        "/models": _cmd_models,
        "/tools": _cmd_tools,
        "/cd": _cmd_cd,
        "/billing": _cmd_billing,
        "/compare": _cmd_compare,
        "/topup": _cmd_topup,
        "/safety": _cmd_safety,
        "/crucible": _cmd_crucible,
        "/forensics": _cmd_forensics,
        "/router": _cmd_router,
        "/provenance": _cmd_provenance,
        "/config": _cmd_config,
        "/hardware": _cmd_hardware,
        "/cache": _cmd_cache,
        "/scan": _cmd_scan,
        "/digest": _cmd_digest,
        "/journal": _cmd_journal,
        "/recall": _cmd_recall,
        "/search": _cmd_search,
        "/index": _cmd_index,
        "/tasks": _cmd_tasks,
        "/memory": _cmd_memory,
        "/stats": _cmd_stats,
        "/dashboard": _cmd_dashboard,
        "/voice": _cmd_voice,
        "/plugins": _cmd_plugins,
        "/plan": _cmd_plan,
        "/dedup": _cmd_dedup,
        "/continuity": _cmd_continuity,
        "/theme": _cmd_theme,
        "/synapse": _cmd_synapse,
        "/report": _cmd_report,
        "/export": _cmd_export,
        "/benchmark": _cmd_benchmark,
        "/update": _cmd_update,
        "/admin": _cmd_admin,
        "/threats": _cmd_threats,
        "/ami": _cmd_ami,
    }

    # ── Shipwright commands ──

    def _cmd_ship(self, arg: str) -> bool:
        e = self.engine
        if hasattr(e, '_bpos') and e._bpos and not e._bpos.is_feature_allowed("shipwright"):
            self.io.print_error("Shipwright requires Pro or Power tier. Run /license for details.")
            return True
        if not hasattr(e, '_shipwright') or not e._shipwright:
            from forge.shipwright import Shipwright
            e._shipwright = Shipwright(
                project_dir=e.cwd,
                llm_backend=e.llm,
                push_after_release=e.config.get("push_on_ship", False),
            )
        sw = e._shipwright
        sub = arg.strip().lower().split()[0] if arg.strip() else "status"

        if sub == "status":
            print(f"\n{sw.format_status()}")
        elif sub == "push":
            parts = arg.strip().split()
            toggle = parts[1].lower() if len(parts) > 1 else ""
            if toggle == "on":
                e.config.set("push_on_ship", True)
                e.config.save()
                sw._push_after_release = True
                self.io.print_info("Shipwright push enabled. /ship go will push to origin.")
            elif toggle == "off":
                e.config.set("push_on_ship", False)
                e.config.save()
                sw._push_after_release = False
                self.io.print_info("Shipwright push disabled.")
            else:
                state = "on" if sw._push_after_release else "off"
                self.io.print_info(f"Shipwright push is {state}. Use /ship push on|off.")
        elif sub == "dry":
            result = sw.release(dry_run=True)
            if result["status"] == "no_release":
                self.io.print_info(result["reason"])
            else:
                print(f"\n{BOLD}Dry Run:{RESET}")
                print(f"  {result['current']} -> {result['next']} ({result['bump']})")
                print(f"  {result['commits']} commits")
                print(f"\n{result['changelog']}")
        elif sub == "preflight":
            self.io.print_info("Running preflight checks...")
            results = sw.run_preflight()
            for name, passed, msg in results:
                icon = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
                print(f"  [{icon}] {name}: {msg}")
            all_pass = all(p for _, p, _ in results)
            if all_pass:
                self.io.print_info("All preflight checks passed.")
            else:
                self.io.print_error("Some preflight checks failed.")
        elif sub == "go":
            self.io.print_info("Executing release...")
            result = sw.release(dry_run=False)
            if result["status"] == "no_release":
                self.io.print_info(result["reason"])
            elif result["status"] == "released":
                self.io.print_info(
                    f"Released {result['tag']} "
                    f"({result['current']} -> {result['next']})")
                print(f"\n{result['changelog']}")
                if result.get("pushed"):
                    self.io.print_info("Pushed to origin — testers can /update.")
                elif result.get("push_error"):
                    self.io.print_error(
                        f"Push failed (no credentials?): {result['push_error']}"
                        "\n  Run: git push origin HEAD --tags")
        elif sub == "changelog":
            commits = sw.get_unreleased_commits()
            commits = sw.classify_commits(commits)
            next_ver, _ = sw.compute_next_version(commits)
            changelog = sw.generate_changelog(commits, next_ver)
            print(f"\n{changelog}")
        elif sub == "history":
            print(f"\n{sw.format_history()}")
        else:
            self.io.print_error(
                "Usage: /ship [status | dry | preflight | go | changelog | history]")
        return True

    # ── AutoForge commands ──

    def _cmd_autocommit(self, arg: str) -> bool:
        e = self.engine
        if not hasattr(e, '_autoforge') or not e._autoforge:
            from forge.autoforge import AutoForge
            e._autoforge = AutoForge(
                project_dir=e.cwd,
                config_get=e.config.get,
            )
        af = e._autoforge
        sub = arg.strip().lower() if arg.strip() else ""

        if sub == "on":
            if hasattr(e, '_bpos') and e._bpos and not e._bpos.is_feature_allowed("auto_commit"):
                self.io.print_error("AutoForge requires Pro or Power tier. Run /license for details.")
                return True
            af.enable()
            e.config.set("auto_commit", True)
            e.config.save()
            self.io.print_info("AutoForge enabled. File edits will be auto-committed.")
        elif sub == "off":
            af.disable()
            e.config.set("auto_commit", False)
            e.config.save()
            self.io.print_info("AutoForge disabled.")
        elif sub == "push":
            parts = arg.strip().split()
            toggle = parts[1].lower() if len(parts) > 1 else ""
            if toggle == "on":
                e.config.set("push_on_commit", True)
                e.config.save()
                self.io.print_info("AutoForge push enabled. Commits will be pushed to origin.")
            elif toggle == "off":
                e.config.set("push_on_commit", False)
                e.config.save()
                self.io.print_info("AutoForge push disabled.")
            else:
                state = "on" if e.config.get("push_on_commit", False) else "off"
                self.io.print_info(f"AutoForge push is {state}. Use /autocommit push on|off.")
        elif sub == "status":
            print(f"\n{af.format_status()}")
        elif sub == "hook":
            from forge.autoforge import generate_hook_script
            script = generate_hook_script(e.cwd)
            hook_dir = Path(e.cwd) / ".claude" / "hooks"
            hook_dir.mkdir(parents=True, exist_ok=True)
            hook_path = hook_dir / "auto_commit.py"
            hook_path.write_text(script, encoding="utf-8")
            self.io.print_info(f"Hook script written to {hook_path}")
            self.io.print_info("Add to .claude/settings.json to activate.")
        else:
            print(f"\n{af.format_status()}")
            self.io.print_info("Usage: /autocommit [on | off | push on|off | status | hook]")
        return True

    # ── License / BPoS commands ──

    def _cmd_license(self, arg: str) -> bool:
        e = self.engine
        if not hasattr(e, '_bpos') or not e._bpos:
            from forge.passport import BPoS
            from forge.machine_id import get_machine_id
            e._bpos = BPoS(
                data_dir=Path.home() / ".forge",
                machine_id=get_machine_id(),
            )
        bpos = e._bpos
        sub = arg.strip().lower().split()[0] if arg.strip() else "status"

        if sub == "status":
            print(f"\n{bpos.format_status()}")
        elif sub == "activate":
            # Activation requires a passport JSON file
            parts = arg.strip().split(None, 1)
            if len(parts) < 2:
                self.io.print_error("Usage: /license activate <passport.json>")
                return True
            passport_file = Path(parts[1])
            if not passport_file.exists():
                self.io.print_error(f"File not found: {passport_file}")
                return True
            try:
                import json
                data = json.loads(passport_file.read_text(encoding="utf-8"))
                ok, msg = bpos.activate(data)
                if ok:
                    self.io.print_info(msg)
                else:
                    self.io.print_error(msg)
            except Exception as ex:
                self.io.print_error(f"Activation failed: {ex}")
        elif sub == "deactivate":
            ok, msg = bpos.deactivate()
            if ok:
                self.io.print_info(msg)
            else:
                self.io.print_error(msg)
        elif sub == "genome":
            snapshot = bpos.collect_genome(e)
            maturity = bpos.get_genome_maturity()
            print(f"\n{BOLD}Forge Genome{RESET}")
            print(f"  Maturity: {int(maturity * 100)}%")
            print(f"  Sessions: {bpos._genome.session_count}")
            print(f"  AMI patterns: {snapshot.ami_failure_catalog_size}")
            print(f"  Model profiles: {snapshot.ami_model_profiles}")
            print(f"  Avg quality: {snapshot.ami_average_quality:.2f}")
            print(f"  Reliability: {snapshot.reliability_score:.1f}")
            print(f"  Threat scans: {bpos._genome.threat_scans_total}")
        elif sub == "team":
            # Team genome sync sub-commands
            parts2 = arg.strip().split()
            team_sub = parts2[1] if len(parts2) > 1 else "status"

            if not bpos.is_feature_allowed("genome_sync"):
                self.io.print_error(
                    "Team genome sync requires Pro tier or higher.")
                return True

            if team_sub == "push":
                ok, msg = bpos.push_team_genome()
                if ok:
                    self.io.print_info(f"Team genome pushed: {msg}")
                else:
                    self.io.print_error(f"Push failed: {msg}")
            elif team_sub == "pull":
                ok = bpos.pull_team_genome()
                if ok:
                    self.io.print_info("Team genome pulled and merged.")
                else:
                    self.io.print_error("Pull failed (check server connection).")
            else:
                # Status
                sync_ok = bpos.is_feature_allowed("genome_sync")
                print(f"\n{BOLD}Team Genome Sync{RESET}")
                print(f"  Enabled: {GREEN}yes{RESET}" if sync_ok
                      else f"  Enabled: {DIM}no{RESET}")
                print(f"  Tier:    {bpos.tier}")
                print(f"\n  /license team push  — push local genome to team")
                print(f"  /license team pull  — pull team genome and merge")
        elif sub == "tiers":
            from forge.passport import get_tiers
            tiers = get_tiers()
            for key, cfg in tiers.items():
                marker = f" {GREEN}*{RESET}" if key == bpos.tier else ""
                price = cfg.get('price_display', cfg.get('price', ''))
                print(f"\n  {BOLD}{cfg.get('label', key)}{RESET} ({price}){marker}")
                skip = {"label", "price", "price_display",
                        "price_cents", "stripe_price_id"}
                for feat, val in cfg.items():
                    if feat in skip:
                        continue
                    icon = f"{GREEN}yes{RESET}" if val else f"{DIM}no{RESET}"
                    if isinstance(val, int):
                        icon = str(val)
                    print(f"    {feat}: {icon}")
        else:
            self.io.print_error(
                "Usage: /license [status | activate <file> | deactivate "
                "| genome | team [push|pull] | tiers]")
        return True

    # ── Puppet / Fleet commands ──

    def _cmd_puppet(self, arg: str) -> bool:
        e = self.engine
        if not hasattr(e, '_puppet_mgr') or not e._puppet_mgr:
            from forge.puppet import PuppetManager
            from forge.machine_id import get_machine_id
            bpos = getattr(e, '_bpos', None)
            e._puppet_mgr = PuppetManager(
                data_dir=Path.home() / ".forge" / "puppets",
                bpos=bpos,
                machine_id=get_machine_id(),
            )
        pm = e._puppet_mgr

        parts = arg.strip().split() if arg.strip() else ["status"]
        sub = parts[0].lower()

        if sub == "status":
            print(f"\n{pm.format_status()}")

        elif sub == "activate":
            if len(parts) < 2:
                self.io.print_error(
                    "Usage: /puppet activate <passport.json>")
                return True
            self.io.print_info("Activating passport with server...")
            ok, msg = pm.activate_master(parts[1])
            if ok:
                self.io.print_info(msg)
            else:
                self.io.print_error(msg)

        elif sub == "generate":
            if len(parts) < 2:
                self.io.print_error("Usage: /puppet generate <name>")
                return True
            name = parts[1]
            path = pm.generate_puppet_passport(name)
            if path:
                self.io.print_info(f"Puppet passport created: {path}")
                self.io.print_info(
                    "Give this file to the puppet machine. They run: "
                    "/puppet join <file>")
            else:
                summary = pm.get_seat_summary()
                self.io.print_error(
                    f"Failed. Must be Master with available seats. "
                    f"({summary['seats_used']}/{summary['puppet_limit']} "
                    f"used)")

        elif sub == "join":
            if len(parts) < 2:
                self.io.print_error(
                    "Usage: /puppet join <puppet_passport.json>")
                return True
            # Optional sync_dir as second arg (backward compat)
            sync = parts[2] if len(parts) > 2 else None
            ok, msg = pm.init_as_puppet(parts[1], sync_dir=sync)
            if ok:
                self.io.print_info(msg)
            else:
                self.io.print_error(msg)

        elif sub == "list":
            puppets = pm.refresh_puppet_status()
            if not puppets:
                print("  No puppets registered.")
            else:
                for p in puppets:
                    icon = {"active": f"{GREEN}+{RESET}",
                            "stale": f"{YELLOW}?{RESET}",
                            "revoked": f"{RED}x{RESET}"}.get(
                                p.status, "?")
                    print(f"  [{icon}] {p.name} ({p.machine_id}) "
                          f"{p.passport_tier} "
                          f"genome: {p.genome_maturity_pct}% "
                          f"sessions: {p.session_count}")

        elif sub == "revoke":
            if len(parts) < 2:
                self.io.print_error("Usage: /puppet revoke <machine_id>")
                return True
            if pm.revoke_puppet(parts[1]):
                self.io.print_info(f"Revoked puppet: {parts[1]}")
            else:
                self.io.print_error(f"Puppet not found: {parts[1]}")

        elif sub == "sync":
            if not hasattr(e, '_bpos') or not e._bpos:
                self.io.print_error("BPoS not initialized")
                return True
            from dataclasses import asdict
            genome = asdict(e._bpos._genome)
            if pm.sync_to_master(genome):
                self.io.print_info("Genome synced to master")
            else:
                self.io.print_error(
                    "Sync failed. Are you registered as a puppet?")

        elif sub == "seats":
            summary = pm.get_seat_summary()
            print(f"\n  Seats total: {summary['seats_total']}")
            print(f"  Puppet limit: {summary['puppet_limit']}")
            print(f"  Seats used: {summary['seats_used']}")
            print(f"  Available: {summary['seats_available']}")

        elif sub == "master":
            # Backward compat: local fleet master mode
            if len(parts) < 2:
                self.io.print_error("Usage: /puppet master <sync_dir>")
                return True
            sync_dir = parts[1]
            if pm.init_as_master(sync_dir):
                self.io.print_info(
                    f"Initialized as local fleet master. Sync: {sync_dir}")
            else:
                self.io.print_error("Failed to initialize as master.")

        else:
            self.io.print_error(
                "Usage: /puppet [status | activate <file> | "
                "generate <name> | join <file> | list | "
                "revoke <id> | sync | seats]")
        return True

    def _cmd_assure(self, arg: str) -> bool:
        """Run AI assurance scenario suite and generate a signed audit report.

        Usage:
          /assure            — run full suite against current model
          /assure --share    — run and upload report to assurance server
          /assure list       — list saved reports
          /assure show <id>  — show a saved report
          /assure categories — list available scenario categories
          /assure run <cat>  — run only scenarios in <cat>
        """
        e = self.engine
        parts = arg.strip().split(None, 1)
        sub = parts[0].lower() if parts else ""
        sub_arg = parts[1] if len(parts) > 1 else ""

        if sub == "list":
            from forge.assurance_report import list_reports
            from pathlib import Path
            reports = list_reports(Path(e._config_dir))
            if not reports:
                self.io.print_info("No assurance reports saved yet.")
            else:
                self.io.print_info(f"Assurance reports ({len(reports)} saved):")
                for r in reports[:20]:
                    import datetime
                    ts = datetime.datetime.fromtimestamp(r['generated_at']).strftime('%Y-%m-%d %H:%M')
                    pct = round(r['pass_rate'] * 100, 1)
                    self.io.print_info(
                        f"  {r['run_id']}  {r['model']}  {pct}%  {ts}"
                    )
            return True

        if sub == "show":
            if not sub_arg:
                self.io.print_error("Usage: /assure show <run_id>")
                return True
            from forge.assurance_report import load_report, _render_markdown
            from pathlib import Path
            report = load_report(sub_arg, Path(e._config_dir))
            if report is None:
                self.io.print_error(f"Report not found: {sub_arg}")
            else:
                print(_render_markdown(report))
            return True

        if sub == "categories":
            from forge.assurance import get_scenario_categories
            bpos = getattr(e, '_bpos', None)
            tier = bpos.tier if bpos else "community"
            cats = get_scenario_categories(tier=tier)
            self.io.print_info("Assurance scenario categories:")
            for c in cats:
                self.io.print_info(f"  {c}")
            return True

        # Run assurance suite
        categories = [sub_arg] if sub == "run" and sub_arg else None
        label = f"category '{sub_arg}'" if categories else "full suite"
        self.io.print_info(f"Running AI assurance {label} against '{e.llm.model}'...")

        try:
            from forge.assurance import AssuranceRunner
            from forge.assurance_report import generate_report
            from pathlib import Path

            bpos = getattr(e, '_bpos', None)
            machine_id  = getattr(e, '_machine_id', "") or ""
            passport_id = ""
            if bpos and hasattr(bpos, '_passport') and bpos._passport:
                passport_id = bpos._passport.passport_id or ""

            runner = AssuranceRunner(
                config_dir=Path(e._config_dir),
                machine_id=machine_id,
                passport_id=passport_id,
            )

            # Embed current behavioral fingerprint if available
            fp_scores = {}
            if hasattr(e, '_latest_fingerprint'):
                fp_scores = e._latest_fingerprint

            import time as _time
            _assure_t0 = _time.time()

            def _assure_prog(current, total, scenario_id, passed, latency_ms):
                elapsed = _time.time() - _assure_t0
                mark = "+" if passed else "x"
                pct = int(current / max(total, 1) * 100)
                avg_per = elapsed / max(current, 1)
                remain = avg_per * (total - current) / 60
                filled = int(pct / 100 * 20)
                bar = "\u2588" * filled + "\u2591" * (20 - filled)
                print(
                    f"  [{bar}] {pct:>3}%  {current}/{total}  "
                    f"[{mark}] {scenario_id:<35}  "
                    f"{latency_ms/1000:.1f}s  "
                    f"({elapsed/60:.1f}m elapsed, ~{remain:.1f}m left)",
                    flush=True)

            tier = bpos.tier if bpos else "community"
            run = runner.run(e.llm, e.llm.model,
                             categories=categories,
                             fingerprint_scores=fp_scores,
                             self_rate=e.config.get("assurance_self_rate", False),
                             tier=tier,
                             progress_callback=_assure_prog)
            report = generate_report(run, config_dir=Path(e._config_dir))

            pct = round(report['pass_rate'] * 100, 1)
            verdict = ("PASS" if report['pass_rate'] >= 1.0 else
                       "PARTIAL PASS" if report['pass_rate'] >= 0.75 else "FAIL")
            self.io.print_info(
                f"Assurance complete: {pct}% — {verdict}  "
                f"({report['scenarios_passed']}/{report['scenarios_run']} scenarios passed)"
            )
            self.io.print_info(f"Report saved: {report['run_id']}")

            # Fire PASS animation if all scenarios passed
            if report['pass_rate'] >= 1.0:
                e.event_bus.emit("assurance.pass", {
                    "score": pct,
                    "model": e.llm.model,
                })

            # Calibration score (self-assessment mode only)
            cal = run.calibration_score
            if cal >= 0:
                self.io.print_info(
                    f"Calibration: {round(cal*100,1)}%  "
                    f"(model correctly predicted its own pass/fail rate)"
                )
                # Surface any failure explanations
                explained = [r for r in run.results if r.self_error_analysis]
                for r in explained:
                    self.io.print_info(
                        f"  [{r.scenario_id}] confidence={r.self_confidence}/10  "
                        f"analysis: {r.self_error_analysis}"
                    )

            # Per-category summary
            for cat, rate in sorted(report['category_pass_rates'].items()):
                mark = "✓" if rate >= 1.0 else ("~" if rate > 0 else "✗")
                self.io.print_info(f"  {mark} {cat}: {round(rate*100,1)}%")

            # ── XP awards ─────────────────────────────────────────────
            xp = getattr(e, 'xp_engine', None)
            if xp and e.config.get("xp_enabled", True):
                try:
                    xp.record_assure(
                        model=e.llm.model,
                        pass_rate=report['pass_rate'],
                        category_pass_rates=report.get('category_pass_rates'),
                        calibration=cal if cal >= 0 else -1.0,
                    )
                    # Clean sweep achievement
                    if report.get('category_pass_rates'):
                        if all(v >= 1.0 for v in report['category_pass_rates'].values()):
                            xp.unlock_achievement("clean_sweep")
                    for note in xp.drain_notifications():
                        self.io.print_info(note)
                except Exception:
                    log.debug("XP assure award failed", exc_info=True)

            # Upload only if user opted in via telemetry or --share flag
            share = "--share" in arg
            auto_share = e.config.get("telemetry_enabled", False)
            if share or auto_share:
                assurance_url = e.config.get("assurance_url", "")
                if not assurance_url:
                    if share:
                        self.io.print_warning(
                            "No assurance_url configured. Set it in config to share reports.")
                else:
                    try:
                        import requests
                        resp = requests.post(
                            assurance_url,
                            json=report,
                            timeout=20,
                        )
                        if resp.status_code == 200:
                            if share:
                                self.io.print_info("Report uploaded to assurance server.")
                            else:
                                self.io.print_info("Assurance report contributed (telemetry opt-in).")
                        else:
                            self.io.print_warning(f"Upload returned HTTP {resp.status_code}")
                    except Exception as upload_err:
                        self.io.print_warning(f"Upload failed: {upload_err}")

        except Exception as exc:
            import traceback
            self.io.print_error(f"Assurance run failed: {exc}")
            log.debug("Assurance error", exc_info=True)
        return True

    def _cmd_break(self, arg: str) -> bool:
        """Run the Forge Reliability Suite against the current model.

        Usage:
          /break              — full suite (31+ scenarios + fingerprint)
          /break --autopsy    — full suite + detailed failure-mode breakdown
          /break --self-rate  — model grades its own responses (calibration score)
          /break --assure     — full break + full assurance in one pass
          /break --share      — run and upload signed report(s) to the Matrix
          /break --json       — output JSON instead of formatted text
          /break --full       — alias for --autopsy --self-rate --assure --share --json

        Flags are combinable: /break --autopsy --assure --self-rate --share

        If telemetry_enabled is true in config, results are automatically
        contributed to the Forge Matrix (decentralized model leaderboard).
        """
        e = self.engine
        # --full expands to all flags
        if "--full" in arg:
            arg += " --autopsy --self-rate --assure --share --json"
        share = "--share" in arg
        as_json = "--json" in arg
        autopsy = "--autopsy" in arg
        self_rate = "--self-rate" in arg
        run_assure = "--assure" in arg
        mode = "full"

        # Show active flags
        flags = []
        if autopsy:    flags.append("autopsy")
        if self_rate:  flags.append("self-rate")
        if run_assure: flags.append("assure")
        if share:      flags.append("share")
        if as_json:    flags.append("json")
        flag_str = f"  Flags: {', '.join(flags)}" if flags else ""

        # Estimate: ~20s per scenario on typical GPU, ~40s with self-rate
        est_per_scenario = 40 if self_rate else 20
        est_scenarios = 38  # full suite default
        est_total = est_scenarios * est_per_scenario
        if run_assure:
            est_total *= 2  # double for assure pass
        est_min = est_total / 60

        self.io.print_info(
            f"Running Forge Break Suite against '{e.llm.model}'...")
        if flag_str:
            self.io.print_info(flag_str)
        self.io.print_info(
            f"  Estimated: ~{est_scenarios} scenarios, ~{est_min:.0f} min"
            f" (varies by model/GPU)")

        try:
            import time as _time
            from forge.break_runner import BreakRunner, format_break_output, format_autopsy_output
            from pathlib import Path

            _break_start = _time.time()

            def _break_progress(current, total, scenario_id, passed, latency_ms):
                elapsed = _time.time() - _break_start
                elapsed_m = elapsed / 60
                mark = "+" if passed else "x"
                pct = int(current / max(total, 1) * 100)
                # Estimate remaining from average latency so far
                avg_per = elapsed / max(current, 1)
                remaining = avg_per * (total - current)
                remain_m = remaining / 60
                bar_len = 20
                filled = int(pct / 100 * bar_len)
                bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
                print(
                    f"  [{bar}] {pct:>3}%  {current}/{total}  "
                    f"[{mark}] {scenario_id:<35}  "
                    f"{latency_ms/1000:.1f}s  "
                    f"({elapsed_m:.1f}m elapsed, ~{remain_m:.1f}m left)",
                    flush=True)
                # Emit event so Neural Cortex animates
                try:
                    e.event_bus.emit("break.progress", {
                        "current": current,
                        "total": total,
                        "scenario_id": scenario_id,
                        "passed": passed,
                        "pct": pct,
                    })
                except Exception:
                    log.debug("Event bus break.progress emit failed", exc_info=True)

            bpos = getattr(e, '_bpos', None)
            machine_id  = getattr(e, '_machine_id', "") or ""
            passport_id = ""
            if bpos and hasattr(bpos, '_passport') and bpos._passport:
                passport_id = bpos._passport.passport_id or ""

            runner = BreakRunner(
                config_dir=Path(e._config_dir),
                machine_id=machine_id,
                passport_id=passport_id,
            )
            tier = bpos.tier if bpos else "community"
            result = runner.run(e.llm, e.llm.model, mode=mode,
                                self_rate=self_rate, tier=tier,
                                progress_callback=_break_progress)

            if as_json:
                import json
                combined = {"break": result.report}
            else:
                print(format_break_output(result))
                if autopsy:
                    print(format_autopsy_output(result))

            # Fire PASS animation if all scenarios passed
            if result.pass_rate >= 1.0:
                e.event_bus.emit("assurance.pass", {
                    "score": result.reliability_score_pct,
                    "model": result.model,
                })

            # ── XP awards ─────────────────────────────────────────────
            xp = getattr(e, 'xp_engine', None)
            if xp and e.config.get("xp_enabled", True):
                try:
                    xp.record_break(
                        model=e.llm.model,
                        pass_rate=result.pass_rate,
                        run_id=getattr(result, 'run_id', ''),
                        shared=share or e.config.get("telemetry_enabled", False),
                        autopsy=autopsy,
                        calibration=getattr(result, 'calibration_score', -1.0),
                    )
                    # New combo detection
                    bpos = getattr(e, '_bpos', None)
                    if bpos:
                        from forge.machine_id import get_machine_id
                        mid = get_machine_id()
                        gpu = ""
                        try:
                            from forge.hardware import detect_gpu
                            gpu = detect_gpu().get("name", "")
                        except Exception:
                            log.debug("GPU detection failed for XP combo", exc_info=True)
                        xp.record_new_combo(
                            model=e.llm.model,
                            machine_id=mid,
                            gpu_name=gpu,
                            run_id=getattr(result, 'run_id', ''),
                        )
                    # Print any XP notifications
                    for note in xp.drain_notifications():
                        self.io.print_info(note)
                except Exception:
                    log.debug("XP break award failed", exc_info=True)

            # ── Assurance combo ────────────────────────────────────────
            assure_report = None
            if run_assure:
                self.io.print_info(
                    f"\nRunning AI Assurance Suite against '{e.llm.model}'...")
                from forge.assurance import AssuranceRunner
                from forge.assurance_report import generate_report

                _assure_start = _time.time()

                def _assure_progress(current, total, scenario_id, passed, latency_ms):
                    elapsed = _time.time() - _assure_start
                    elapsed_m = elapsed / 60
                    mark = "+" if passed else "x"
                    pct = int(current / max(total, 1) * 100)
                    avg_per = elapsed / max(current, 1)
                    remaining = avg_per * (total - current)
                    remain_m = remaining / 60
                    bar_len = 20
                    filled = int(pct / 100 * bar_len)
                    bar = "\u2588" * filled + "\u2591" * (bar_len - filled)
                    print(
                        f"  [{bar}] {pct:>3}%  {current}/{total}  "
                        f"[{mark}] {scenario_id:<35}  "
                        f"{latency_ms/1000:.1f}s  "
                        f"({elapsed_m:.1f}m elapsed, ~{remain_m:.1f}m left)",
                        flush=True)
                    try:
                        e.event_bus.emit("break.progress", {
                            "current": current, "total": total,
                            "scenario_id": scenario_id, "passed": passed,
                            "pct": pct,
                        })
                    except Exception:
                        log.debug("Event bus break.progress emit failed (break suite)", exc_info=True)

                fp_scores = {}
                if hasattr(e, '_latest_fingerprint'):
                    fp_scores = e._latest_fingerprint

                assure_runner = AssuranceRunner(
                    config_dir=Path(e._config_dir),
                    machine_id=machine_id,
                    passport_id=passport_id,
                )
                tier = bpos.tier if bpos else "community"
                assure_run = assure_runner.run(
                    e.llm, e.llm.model,
                    fingerprint_scores=fp_scores,
                    self_rate=self_rate,
                    tier=tier,
                    progress_callback=_assure_progress,
                )
                assure_report = generate_report(
                    assure_run, config_dir=Path(e._config_dir))

                if as_json:
                    combined["assure"] = assure_report
                else:
                    pct = round(assure_report['pass_rate'] * 100, 1)
                    verdict = ("PASS" if assure_report['pass_rate'] >= 1.0 else
                               "PARTIAL PASS" if assure_report['pass_rate'] >= 0.75
                               else "FAIL")
                    self.io.print_info(
                        f"Assurance complete: {pct}% -- {verdict}  "
                        f"({assure_report['scenarios_passed']}/"
                        f"{assure_report['scenarios_run']} scenarios passed)")
                    self.io.print_info(
                        f"Report saved: {assure_report['run_id']}")
                    for cat, rate in sorted(
                            assure_report['category_pass_rates'].items()):
                        mark = "+" if rate >= 1.0 else (
                            "~" if rate > 0 else "x")
                        self.io.print_info(
                            f"  {mark} {cat}: {round(rate*100,1)}%")

                    if assure_run.calibration_score >= 0:
                        cal = round(assure_run.calibration_score * 100, 1)
                        self.io.print_info(
                            f"  Assurance Calibration: {cal}%")

                    # Combined summary
                    break_pct = result.reliability_score_pct
                    combined_pct = round((break_pct + pct) / 2, 1)
                    print(f"\n  {'='*50}")
                    print(f"  Combined Forge Matrix Score: {combined_pct}%")
                    print(f"    Break:     {break_pct}%")
                    print(f"    Assurance: {pct}%")
                    print(f"  {'='*50}")

                # XP: assure portion of the combo
                xp = getattr(e, 'xp_engine', None)
                if xp and e.config.get("xp_enabled", True):
                    try:
                        xp.record_assure(
                            model=e.llm.model,
                            pass_rate=assure_report['pass_rate'],
                            category_pass_rates=assure_report.get('category_pass_rates'),
                        )
                        # Full Audit: only if ALL 5 flags were used
                        if all([autopsy, self_rate, run_assure, share, as_json]):
                            xp.unlock_achievement("full_audit")
                        for note in xp.drain_notifications():
                            self.io.print_info(note)
                    except Exception:
                        log.debug("XP assure combo award failed", exc_info=True)

            if as_json:
                import json
                print(json.dumps(combined, indent=2))

            # ── Upload (always goes to Forge Matrix) ─────────────────
            auto_share = e.config.get("telemetry_enabled", False)
            if share or auto_share:
                share_url = e.config.get("assurance_url", "") or ASSURANCE_URL
                if not share_url:
                    if share:
                        self.io.print_warning(
                            "No assurance_url configured. Set it in config to share reports.")
                else:
                    url = runner.share_report(result, share_url)
                    if url:
                        if share:
                            self.io.print_info(f"Break report shared: {url}")
                        else:
                            self.io.print_info(f"Matrix contribution uploaded: {url}")
                    elif share:
                        self.io.print_warning("Break share upload failed.")

                    if assure_report and share_url:
                        try:
                            import requests
                            resp = requests.post(
                                share_url,
                                json=assure_report,
                                timeout=20,
                            )
                            if resp.status_code == 200:
                                self.io.print_info(
                                    "Assurance report uploaded to Matrix.")
                            else:
                                self.io.print_warning(
                                    f"Assurance upload returned HTTP {resp.status_code}")
                        except Exception as upload_err:
                            self.io.print_warning(
                                f"Assurance upload failed: {upload_err}")

        except Exception as exc:
            self.io.print_error(f"Break suite failed: {exc}")
            log.debug("forge break error", exc_info=True)
        return True

    def _cmd_autopsy(self, arg: str) -> bool:
        """Alias for /break --autopsy. Kept for backward compatibility."""
        new_arg = arg.strip()
        if "--autopsy" not in new_arg:
            new_arg = f"--autopsy {new_arg}".strip()
        return self._cmd_break(new_arg)

    def _cmd_stress(self, arg: str) -> bool:
        """Run the minimal 3-category Forge Stress Suite (CI-compatible, < 30s).

        Exits the process with code 1 if any scenario fails (for CI pipelines).

        Usage:
          /stress          — run minimal suite, print pass/fail
          /stress --json   — output JSON result
          /stress --ci     — exit non-zero on failure (for shell scripts)
        """
        e = self.engine
        as_json = "--json" in arg
        ci_mode = "--ci" in arg

        self.io.print_info(
            f"Running Forge Stress Suite against '{e.llm.model}'...")

        try:
            from forge.break_runner import BreakRunner, format_break_output
            from pathlib import Path

            bpos = getattr(e, '_bpos', None)
            machine_id  = getattr(e, '_machine_id', "") or ""
            passport_id = ""
            if bpos and hasattr(bpos, '_passport') and bpos._passport:
                passport_id = bpos._passport.passport_id or ""

            runner = BreakRunner(
                config_dir=Path(e._config_dir),
                machine_id=machine_id,
                passport_id=passport_id,
            )
            result = runner.run(e.llm, e.llm.model, mode="stress",
                                include_fingerprint=False)

            if as_json:
                import json
                print(json.dumps(result.report, indent=2))
            else:
                print(format_break_output(result))

            # ── XP awards ─────────────────────────────────────────────
            xp = getattr(e, 'xp_engine', None)
            if xp and e.config.get("xp_enabled", True):
                try:
                    xp.record_stress(model=e.llm.model)
                    for note in xp.drain_notifications():
                        self.io.print_info(note)
                except Exception:
                    log.debug("XP stress award failed", exc_info=True)

            if ci_mode and result.pass_rate < 1.0:
                import sys
                sys.exit(1)

        except Exception as exc:
            self.io.print_error(f"Stress suite failed: {exc}")
            log.debug("forge stress error", exc_info=True)
        return True

    def _cmd_profile(self, arg: str) -> bool:
        """Show your Forge XP profile, level, title, and achievements.

        Usage:
          /profile           — summary view
          /profile --all     — full view with all achievements and title progression
        """
        e = self.engine
        xp = getattr(e, 'xp_engine', None)
        if not xp:
            self.io.print_warning("XP system is not enabled.")
            return True

        verbose = "--all" in arg or "-v" in arg
        print(xp.format_profile(verbose=verbose))
        return True

    # Register commands defined after the _COMMANDS dict
    _COMMANDS["/ship"] = _cmd_ship
    _COMMANDS["/autocommit"] = _cmd_autocommit
    _COMMANDS["/license"] = _cmd_license
    _COMMANDS["/puppet"] = _cmd_puppet
    _COMMANDS["/assure"] = _cmd_assure
    _COMMANDS["/break"] = _cmd_break
    _COMMANDS["/autopsy"] = _cmd_autopsy
    _COMMANDS["/stress"] = _cmd_stress
    _COMMANDS["/profile"] = _cmd_profile
