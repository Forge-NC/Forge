"""Slash command handlers — extracted from engine.py for maintainability.

Each command handler is a method on CommandHandler that receives the
engine reference. The engine calls handle_command() which dispatches
to the right handler.
"""

import os
import time
from pathlib import Path
from typing import Optional

from forge.context import ContextFullError
from forge.safety import LEVEL_NAMES, NAME_TO_LEVEL
from forge.crucible import ThreatLevel
from forge.ui.terminal import (
    RESET, DIM, BOLD, YELLOW, RED, CYAN, GREEN, MAGENTA, WHITE, GRAY,
)


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
            pass
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
            self.io.print_info(f"Current model: {e.llm.model}")
            ctx_len = e.llm.get_context_length()
            self.io.print_info(f"Context length: {ctx_len:,}")
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
        amount = float(arg) if arg else 50.0
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
        e = self.engine
        chain = e.crucible.get_provenance_chain()
        if not chain:
            self.io.print_info("No provenance data recorded this session.")
            return True
        print(e.crucible.format_provenance_display())
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
        path = arg if arg else e.cwd
        self.io.print_info(f"Scanning codebase at {path}...")
        try:
            from forge.tools.digest_tools import _scan_codebase
            summary = _scan_codebase(
                e._digester, path,
                force=("force" in arg.lower() if arg else False))
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

        target_dir = arg or e.cwd
        self.io.print_info(f"Indexing {target_dir}...")

        def progress(fpath, chunks):
            if chunks > 0:
                short = Path(fpath).name
                print(f"  {DIM}+{chunks} chunks: {short}{RESET}")

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
            print(f"\n{BOLD}Voice Input{RESET}")
            print(f"  Status: {GREEN}{state}{RESET}")
            print(f"  Mode:   {CYAN}{mode}{RESET}")
            print(f"  Hotkey: {CYAN}`{RESET} (backtick)")
            print(f"\n  {DIM}Commands:{RESET}")
            print(f"  {CYAN}/voice ptt{RESET}   Push-to-talk (hold ` to speak)")
            print(f"  {CYAN}/voice vox{RESET}   Voice-activated (auto-detect speech)")
            print(f"  {CYAN}/voice off{RESET}   Disable voice input")
            return True

        sub = arg.strip().lower()
        if sub == "ptt":
            e._voice.mode = "ptt"
            self.io.print_info("Voice mode: Push-to-Talk (hold ` to speak)")
        elif sub == "vox":
            e._voice.mode = "vox"
            self.io.print_info("Voice mode: VOX (voice-activated, auto-detect speech)")
        elif sub == "off":
            e._voice.stop()
            e._voice = None
            self.io.print_info("Voice input disabled.")
        else:
            self.io.print_error("Usage: /voice [ptt|vox|off]")
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

    # ── Audit export ──

    def _cmd_export(self, arg: str) -> bool:
        """Export full audit package as a zip bundle."""
        from forge.audit import AuditExporter
        e = self.engine

        redact = False
        path_override = None
        parts = arg.strip().split()
        for p in parts:
            if p == "--redact":
                redact = True
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
                session_start=e._session_start,
                turn_count=e._turn_count,
                model=e.llm.model,
                cwd=e.cwd,
            )
            out_path = exporter.export(package, path=path_override, redact=redact)
            print(exporter.format_summary(package))
            self.io.print_info(f"Audit exported: {out_path}")
            if redact:
                self.io.print_info("(Redacted mode — sensitive content stripped)")
        except Exception as ex:
            self.io.print_error(f"Export failed: {ex}")
        return True

    # ── Benchmark suite ──

    def _cmd_benchmark(self, arg: str) -> bool:
        """Run or inspect benchmark suite.

        Usage: /benchmark list | run [suite] | results [suite] | compare
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

        if sub == "run":
            suite_name = parts[1] if len(parts) > 1 else "refactoring"
            model = self.engine.llm.model if hasattr(self.engine, "llm") else ""
            config_hash = BenchmarkRunner.compute_config_hash(
                model=model,
                context_size=self.engine.config.get("context_size", 0),
                safety_level=self.engine.config.get("safety_level", 1),
                router_enabled=self.engine.config.get("router_enabled", False),
                dedup_enabled=self.engine.config.get("dedup_enabled", True),
                verify_mode=self.engine.config.get("plan_verify_mode", "off"),
            )
            scenarios = runner.list_scenarios(suite_name)
            if not scenarios:
                self.io.print_error(f"No scenarios found in suite '{suite_name}'.")
                return True
            self.io.print_info(
                f"Running {len(scenarios)} scenarios from '{suite_name}'...")
            result = runner.run_suite(suite_name, model=model,
                                      config_hash=config_hash)
            print(runner.format_results(result))
            path = runner.save_result(result)
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
            self.io.print_info("Benchmark comparison (older → newer):")
            for k, v in diff.items():
                if "delta" in k:
                    sign = "+" if v > 0 else ""
                    self.io.print_info(f"  {k}: {sign}{v:.3f}")
                else:
                    self.io.print_info(f"  {k}: {v}")
            return True

        self.io.print_error(
            "Usage: /benchmark list | run [suite] | results [suite] | compare")
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
        "/export": _cmd_export,
        "/benchmark": _cmd_benchmark,
    }
