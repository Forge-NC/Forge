"""Forge XP, Levels, Titles, and Achievements — gamification engine.

Tracks user progression through meaningful actions: adversarial testing,
model exploration, community contribution, and general usage. Designed
to be anti-farmable (daily caps, combo dedup, PoI validation) and to
persist offline with server sync when telemetry is enabled.

Level curve:  XP to next level = floor(75 * level^1.4)
Title unlocks at milestone levels (5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 75, 100).

Storage: ~/.forge/xp.json (local), server sync via xp_api.php.
"""

from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

# ── Level curve ───────────────────────────────────────────────────────────────

def xp_for_next_level(level: int) -> int:
    """XP required to advance from *level* to *level+1*."""
    return max(75, int(75 * (level ** 1.4)))


def total_xp_for_level(level: int) -> int:
    """Cumulative XP required to reach *level* from 0."""
    return sum(xp_for_next_level(n) for n in range(1, level))


def level_from_xp(total_xp: int) -> int:
    """Compute current level from total XP."""
    lvl = 1
    remaining = total_xp
    while True:
        needed = xp_for_next_level(lvl)
        if remaining < needed:
            return lvl
        remaining -= needed
        lvl += 1


def xp_progress(total_xp: int) -> tuple[int, int, int]:
    """Return (current_level, xp_into_level, xp_needed_for_next)."""
    lvl = 1
    remaining = total_xp
    while True:
        needed = xp_for_next_level(lvl)
        if remaining < needed:
            return lvl, remaining, needed
        remaining -= needed
        lvl += 1


# ── Titles ────────────────────────────────────────────────────────────────────

TITLES: list[tuple[int, str]] = [
    (5,   "Firestarter"),
    (10,  "Breaker"),
    (15,  "Crucible Tested"),
    (20,  "Matrix Runner"),
    (25,  "Voidhunter"),
    (30,  "Steel Sentinel"),
    (35,  "Forge Warden"),
    (40,  "Pattern Breaker"),
    (50,  "Neural Architect"),
    (60,  "Cortex Sovereign"),
    (75,  "Eternal Flame"),
    (100, "Origin"),
]


def title_for_level(level: int) -> str:
    """Return the highest title unlocked at *level*, or empty string."""
    result = ""
    for threshold, name in TITLES:
        if level >= threshold:
            result = name
    return result


def next_title(level: int) -> Optional[tuple[int, str]]:
    """Return (level_needed, title_name) for the next title, or None."""
    for threshold, name in TITLES:
        if level < threshold:
            return threshold, name
    return None


# ── XP Action definitions ─────────────────────────────────────────────────────

@dataclass
class XPAction:
    """Definition of an XP-earning action."""
    key: str
    base_xp: int
    daily_cap: int        # 0 = no daily cap (but may have lifetime cap)
    lifetime_cap: int     # 0 = no lifetime cap
    description: str


ACTIONS: dict[str, XPAction] = {
    "break_complete":    XPAction("break_complete",    500, 5,  0, "Complete a /break run"),
    "break_share":       XPAction("break_share",       250, 5,  0, "Upload a /break report"),
    "stress_complete":   XPAction("stress_complete",    200, 5,  0, "Complete a /stress run"),
    "assure_complete":   XPAction("assure_complete",    400, 3,  0, "Complete an /assure run"),
    "new_combo":         XPAction("new_combo",         1000, 0,  0, "Test a new model+GPU+machine combo"),
    "unique_failure":    XPAction("unique_failure",     750, 5,  0, "Discover a unique model failure"),
    "telemetry":         XPAction("telemetry",          150, 1,  0, "Contribute telemetry data"),
    "session_hour":      XPAction("session_hour",       200, 1,  0, "Complete a 1+ hour session"),
    "session_50_turns":  XPAction("session_50_turns",   150, 1,  0, "Complete a 50+ turn session"),
    "session_100_turns": XPAction("session_100_turns",  300, 1,  0, "Complete a 100+ turn session"),
    "poi_challenge":     XPAction("poi_challenge",      300, 5,  0, "Complete a Proof of Inference challenge"),
    "plugin_loaded":     XPAction("plugin_loaded",      100, 0, 10, "Load a unique user plugin"),
}


# ── Achievements ──────────────────────────────────────────────────────────────

@dataclass
class Achievement:
    """Definition of a one-time achievement."""
    id: str
    name: str
    description: str
    bonus_xp: int
    category: str   # discovery, breadth, depth, community, usage, power, aspirational


ACHIEVEMENTS: dict[str, Achievement] = {}

def _a(id: str, name: str, desc: str, xp: int, cat: str):
    ACHIEVEMENTS[id] = Achievement(id, name, desc, xp, cat)

# Discovery
_a("first_break",       "First Blood",           "Complete your first /break run",              500, "discovery")
_a("first_failure",     "Bug Hunter",             "Discover your first model failure",           750, "discovery")
_a("five_failures",     "Vulnerability Analyst",  "Discover 5 unique failures",                 1500, "discovery")
_a("twenty_failures",   "Red Team Specialist",    "Discover 20 unique failures",                3000, "discovery")
_a("perfect_break",     "Flawless",               "Achieve 100% on a full /break suite",        2000, "discovery")
_a("perfect_assure",    "Certified",              "Achieve 100% on a full /assure suite",       2000, "discovery")
_a("calibration_king",  "Self-Aware",             "Achieve 100% calibration on --self-rate",    1500, "discovery")

# Breadth
_a("models_3",          "Trifecta",               "Test 3 different models",                    1000, "breadth")
_a("models_5",          "Model Collector",         "Test 5 different models",                    2000, "breadth")
_a("models_10",         "Fleet Commander",         "Test 10 different models",                   4000, "breadth")
_a("models_20",         "Omniscient",              "Test 20 different models",                   7500, "breadth")

# Depth
_a("ten_breaks",        "Stress Tester",           "Run /break 10 times on the same model",     1500, "depth")
_a("full_audit",        "Full Audit",              "Run /break --autopsy --self-rate --assure --share --json",  1000, "depth")
_a("forensic_analyst",  "Forensic Analyst",        "Complete a /break --autopsy run",             750, "depth")
_a("clean_sweep",       "Clean Sweep",             "Pass all 8 assurance categories",            2500, "depth")

# Community
_a("first_share",       "Going Public",            "Share your first report to the Matrix",      1000, "community")
_a("ten_shares",        "Community Pillar",         "Share 10 reports to the Matrix",             2500, "community")
_a("data_donor",        "Data Donor",              "Enable telemetry and complete a session",      500, "community")
_a("faithful",          "Faithful Contributor",     "Contribute 10 telemetry sessions",           2000, "community")

# Usage milestones
_a("sessions_10",       "Regular",                 "Complete 10 sessions",                        1000, "usage")
_a("sessions_50",       "Veteran",                 "Complete 50 sessions",                        2500, "usage")
_a("sessions_100",      "Centurion",               "Complete 100 sessions",                       5000, "usage")
_a("turns_1000",        "Thousand Turns",          "Reach 1,000 lifetime turns",                  2000, "usage")
_a("turns_10000",       "Ten Thousand Strong",     "Reach 10,000 lifetime turns",                 5000, "usage")
_a("hours_10",          "Dedicated",               "Accumulate 10 hours of sessions",             1500, "usage")
_a("hours_100",         "Ironworker",              "Accumulate 100 hours of sessions",            4000, "usage")

# Power user
_a("first_plugin",      "Tinkerer",                "Load your first user plugin",                  750, "power")
_a("three_plugins",     "Plugin Crafter",           "Load 3 unique user plugins",                 2000, "power")
_a("proof_bearer",      "Proof Bearer",            "Complete your first PoI challenge",            1000, "power")
_a("verified_operator",  "Verified Operator",       "Complete 5 PoI challenges",                  2000, "power")

# Aspirational
_a("sessions_500",      "Half Millennium",         "Complete 500 sessions",                       10000, "aspirational")
_a("models_50",         "Architect of Models",      "Test 50 different models",                   15000, "aspirational")
_a("fifty_shares",      "Matrix Architect",         "Share 50 reports to the Matrix",              7500, "aspirational")
_a("completionist",     "Completionist",           "Unlock every other achievement",              20000, "aspirational")

del _a


# ── XP Engine ─────────────────────────────────────────────────────────────────

class XPEngine:
    """Manages XP accrual, level progression, achievements, and persistence."""

    def __init__(self, persist_dir: Path = None):
        self._dir = persist_dir or (Path.home() / ".forge")
        self._path = self._dir / "xp.json"
        self._lock = threading.Lock()

        # State
        self.total_xp: int = 0
        self.level: int = 1
        self.title: str = ""
        self.achievements: set[str] = set()
        self.daily_log: dict[str, dict[str, int]] = {}   # date -> {action: count}
        self.combo_registry: dict[str, list[str]] = {}    # combo_key -> [run_ids]
        self.lifetime: dict[str, Any] = {
            "breaks_total": 0,
            "assures_total": 0,
            "stresses_total": 0,
            "shares_total": 0,
            "failures_found": 0,
            "telemetry_sessions": 0,
            "poi_challenges": 0,
            "models_tested": [],
            "plugins_loaded": [],
            "total_sessions": 0,
            "total_turns": 0,
            "total_hours": 0.0,
            "break_per_model": {},     # model -> count (for depth achievements)
            "perfect_breaks": 0,
            "perfect_assures": 0,
            "autopsy_runs": 0,
            "calibration_best": 0.0,
        }
        self.xp_history: list[dict] = []
        self._max_history = 500
        self._pending_notifications: list[str] = []  # messages to show user

        self._load()

    # ── Award XP ──────────────────────────────────────────────────────────

    def award(self, action_key: str, *, amount: int = 0,
              model: str = "", run_id: str = "",
              combo_key: str = "", extra: dict = None) -> int:
        """Award XP for an action. Returns XP actually awarded (0 if capped)."""
        defn = ACTIONS.get(action_key)
        if defn is None:
            log.warning("Unknown XP action: %s", action_key)
            return 0

        xp = amount or defn.base_xp
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        with self._lock:
            # Daily cap check
            day_log = self.daily_log.setdefault(today, {})
            day_count = day_log.get(action_key, 0)
            if defn.daily_cap > 0 and day_count >= defn.daily_cap:
                return 0

            # Lifetime cap check
            if defn.lifetime_cap > 0:
                total_ever = sum(
                    v.get(action_key, 0)
                    for v in self.daily_log.values()
                )
                if total_ever >= defn.lifetime_cap:
                    return 0

            # Combo dedup check (for new_combo action)
            if action_key == "new_combo" and combo_key:
                if combo_key in self.combo_registry:
                    return 0
                self.combo_registry[combo_key] = [run_id] if run_id else []

            old_level = self.level
            old_title = self.title

            self.total_xp += xp
            day_log[action_key] = day_count + 1

            # Update level
            self.level = level_from_xp(self.total_xp)
            self.title = title_for_level(self.level)

            # Record history
            entry = {
                "ts": time.time(),
                "action": action_key,
                "xp": xp,
            }
            if model:
                entry["model"] = model
            if run_id:
                entry["run_id"] = run_id
            self.xp_history.append(entry)
            if len(self.xp_history) > self._max_history:
                self.xp_history = self.xp_history[-self._max_history:]

            # Notifications
            if self.level > old_level:
                self._pending_notifications.append(
                    f"  *** LEVEL UP! Level {self.level} reached! ***")
            if self.title and self.title != old_title:
                self._pending_notifications.append(
                    f"  *** Title unlocked: [{self.title}] ***")

            self._save()

        return xp

    # ── Lifetime counter updates ──────────────────────────────────────────

    def record_break(self, model: str, pass_rate: float, run_id: str = "",
                     shared: bool = False, autopsy: bool = False,
                     calibration: float = -1.0):
        """Record a /break completion and check related achievements."""
        with self._lock:
            self.lifetime["breaks_total"] += 1
            bpm = self.lifetime["break_per_model"]
            bpm[model] = bpm.get(model, 0) + 1

            if model not in self.lifetime["models_tested"]:
                self.lifetime["models_tested"].append(model)

            if pass_rate >= 1.0:
                self.lifetime["perfect_breaks"] += 1

            if autopsy:
                self.lifetime["autopsy_runs"] += 1

            if calibration > self.lifetime["calibration_best"]:
                self.lifetime["calibration_best"] = calibration

            if shared:
                self.lifetime["shares_total"] += 1

            self._save()

        # Award base XP (outside lock to avoid deadlock in award())
        self.award("break_complete", model=model, run_id=run_id)

        if shared:
            self.award("break_share", model=model, run_id=run_id)

        # Check achievements
        self._check_achievements()

    def record_assure(self, model: str, pass_rate: float,
                      category_pass_rates: dict = None,
                      calibration: float = -1.0):
        """Record an /assure completion."""
        with self._lock:
            self.lifetime["assures_total"] += 1
            if pass_rate >= 1.0:
                self.lifetime["perfect_assures"] += 1
            if calibration > self.lifetime["calibration_best"]:
                self.lifetime["calibration_best"] = calibration
            self._save()

        self.award("assure_complete", model=model)
        self._check_achievements()

    def record_stress(self, model: str):
        """Record a /stress completion."""
        with self._lock:
            self.lifetime["stresses_total"] += 1
            self._save()
        self.award("stress_complete", model=model)

    def record_failure(self, model: str, scenario_id: str):
        """Record discovery of a unique failure."""
        with self._lock:
            self.lifetime["failures_found"] += 1
            self._save()
        self.award("unique_failure", model=model)
        self._check_achievements()

    def record_session_end(self, duration_s: float, turns: int):
        """Record session end metrics for XP."""
        with self._lock:
            self.lifetime["total_sessions"] += 1
            self.lifetime["total_turns"] += turns
            self.lifetime["total_hours"] += duration_s / 3600.0
            self._save()

        if duration_s >= 3600:
            self.award("session_hour")
        if turns >= 100:
            self.award("session_100_turns")
        elif turns >= 50:
            self.award("session_50_turns")

        self._check_achievements()

    def record_telemetry(self):
        """Record a telemetry upload."""
        with self._lock:
            self.lifetime["telemetry_sessions"] += 1
            self._save()
        self.award("telemetry")
        self._check_achievements()

    def record_poi(self):
        """Record a Proof of Inference challenge completion."""
        with self._lock:
            self.lifetime["poi_challenges"] += 1
            self._save()
        self.award("poi_challenge")
        self._check_achievements()

    def record_plugin(self, plugin_name: str):
        """Record a user plugin load."""
        with self._lock:
            if plugin_name not in self.lifetime["plugins_loaded"]:
                self.lifetime["plugins_loaded"].append(plugin_name)
                self._save()
                # Award outside lock
                self.award("plugin_loaded")
                self._check_achievements()

    def record_new_combo(self, model: str, machine_id: str, gpu_name: str,
                         run_id: str = ""):
        """Record a new model+machine+GPU combo test."""
        combo_key = f"{model}:{machine_id}:{gpu_name}"
        self.award("new_combo", model=model, run_id=run_id,
                   combo_key=combo_key)

    # ── Achievement checking ──────────────────────────────────────────────

    def _check_achievements(self):
        """Evaluate all achievement conditions and unlock any that are met."""
        lt = self.lifetime
        newly_unlocked = []

        checks = {
            # Discovery
            "first_break":      lambda: lt["breaks_total"] >= 1,
            "first_failure":    lambda: lt["failures_found"] >= 1,
            "five_failures":    lambda: lt["failures_found"] >= 5,
            "twenty_failures":  lambda: lt["failures_found"] >= 20,
            "perfect_break":    lambda: lt["perfect_breaks"] >= 1,
            "perfect_assure":   lambda: lt["perfect_assures"] >= 1,
            "calibration_king": lambda: lt["calibration_best"] >= 1.0,
            # Breadth
            "models_3":         lambda: len(lt["models_tested"]) >= 3,
            "models_5":         lambda: len(lt["models_tested"]) >= 5,
            "models_10":        lambda: len(lt["models_tested"]) >= 10,
            "models_20":        lambda: len(lt["models_tested"]) >= 20,
            # Depth
            "ten_breaks":       lambda: any(v >= 10 for v in lt["break_per_model"].values()),
            "full_audit":       lambda: False,  # checked at award time in commands
            "forensic_analyst": lambda: lt["autopsy_runs"] >= 1,
            "clean_sweep":      lambda: False,  # checked at award time
            # Community
            "first_share":      lambda: lt["shares_total"] >= 1,
            "ten_shares":       lambda: lt["shares_total"] >= 10,
            "data_donor":       lambda: lt["telemetry_sessions"] >= 1,
            "faithful":         lambda: lt["telemetry_sessions"] >= 10,
            # Usage
            "sessions_10":      lambda: lt["total_sessions"] >= 10,
            "sessions_50":      lambda: lt["total_sessions"] >= 50,
            "sessions_100":     lambda: lt["total_sessions"] >= 100,
            "turns_1000":       lambda: lt["total_turns"] >= 1000,
            "turns_10000":      lambda: lt["total_turns"] >= 10000,
            "hours_10":         lambda: lt["total_hours"] >= 10,
            "hours_100":        lambda: lt["total_hours"] >= 100,
            # Power
            "first_plugin":     lambda: len(lt["plugins_loaded"]) >= 1,
            "three_plugins":    lambda: len(lt["plugins_loaded"]) >= 3,
            "proof_bearer":     lambda: lt["poi_challenges"] >= 1,
            "verified_operator": lambda: lt["poi_challenges"] >= 5,
            # Aspirational
            "sessions_500":     lambda: lt["total_sessions"] >= 500,
            "models_50":        lambda: len(lt["models_tested"]) >= 50,
            "fifty_shares":     lambda: lt["shares_total"] >= 50,
        }

        with self._lock:
            for aid, check_fn in checks.items():
                if aid in self.achievements:
                    continue
                try:
                    if check_fn():
                        self.achievements.add(aid)
                        ach = ACHIEVEMENTS[aid]
                        newly_unlocked.append(ach)
                except Exception:
                    pass

            # Completionist: all others unlocked
            if "completionist" not in self.achievements:
                all_others = set(ACHIEVEMENTS.keys()) - {"completionist"}
                if all_others.issubset(self.achievements):
                    self.achievements.add("completionist")
                    newly_unlocked.append(ACHIEVEMENTS["completionist"])

            self._save()

        # Award bonus XP for newly unlocked (outside lock)
        for ach in newly_unlocked:
            old_level = self.level
            with self._lock:
                self.total_xp += ach.bonus_xp
                self.level = level_from_xp(self.total_xp)
                self.title = title_for_level(self.level)
                if self.level > old_level:
                    self._pending_notifications.append(
                        f"  *** LEVEL UP! Level {self.level} reached! ***")
                new_title = title_for_level(self.level)
                if new_title and new_title != self.title:
                    self._pending_notifications.append(
                        f"  *** Title unlocked: [{new_title}] ***")
                self._save()
            self._pending_notifications.append(
                f"  ★ Achievement unlocked: {ach.name} (+{ach.bonus_xp:,} XP)")
            log.info("Achievement unlocked: %s (+%d XP)", ach.name, ach.bonus_xp)

    def unlock_achievement(self, aid: str):
        """Manually unlock an achievement (for special conditions in commands)."""
        if aid in self.achievements:
            return
        ach = ACHIEVEMENTS.get(aid)
        if not ach:
            return
        with self._lock:
            self.achievements.add(aid)
            self.total_xp += ach.bonus_xp
            self.level = level_from_xp(self.total_xp)
            self.title = title_for_level(self.level)
            self._save()
        self._pending_notifications.append(
            f"  ★ Achievement unlocked: {ach.name} (+{ach.bonus_xp:,} XP)")

    # ── Notifications ─────────────────────────────────────────────────────

    def drain_notifications(self) -> list[str]:
        """Return and clear pending notification messages."""
        with self._lock:
            msgs = list(self._pending_notifications)
            self._pending_notifications.clear()
        return msgs

    # ── Profile formatting ────────────────────────────────────────────────

    def format_profile(self, verbose: bool = False) -> str:
        """Return formatted profile string for /profile command."""
        lvl, xp_in, xp_need = xp_progress(self.total_xp)
        pct = xp_in / max(xp_need, 1)
        bar_len = 20
        filled = int(pct * bar_len)
        bar = "\u2588" * filled + "\u2591" * (bar_len - filled)

        lines = [
            "",
            "  Forge Profile",
            "  " + "=" * 50,
        ]

        if self.title:
            lines.append(f"  Title:    [{self.title}]")
        lines.append(f"  Level:    {lvl}          "
                     f"XP: {self.total_xp:,} / {total_xp_for_level(lvl + 1):,}")
        lines.append(f"  {bar}  {pct*100:.0f}%")

        nt = next_title(lvl)
        if nt:
            lines.append(f"  Next title: {nt[1]} (Level {nt[0]})")

        lines.append("")
        lines.append(f"  Achievements: {len(self.achievements)} / {len(ACHIEVEMENTS)}")

        if self.achievements:
            for aid in sorted(self.achievements):
                ach = ACHIEVEMENTS.get(aid)
                if ach:
                    lines.append(f"    \u2605 {ach.name:<24} {ach.description}")

        lt = self.lifetime
        lines.append("")
        lines.append("  Lifetime Stats:")
        lines.append(f"    Sessions: {lt['total_sessions']:<8} "
                     f"Turns: {lt['total_turns']:<8} "
                     f"Hours: {lt['total_hours']:.1f}")
        lines.append(f"    Breaks:   {lt['breaks_total']:<8} "
                     f"Models: {len(lt['models_tested']):<8} "
                     f"Shares: {lt['shares_total']}")
        lines.append(f"    Assures:  {lt['assures_total']:<8} "
                     f"Failures: {lt['failures_found']:<7} "
                     f"Plugins: {len(lt['plugins_loaded'])}")
        lines.append("")

        if verbose:
            lines.append("  All Achievements:")
            for aid, ach in sorted(ACHIEVEMENTS.items(),
                                    key=lambda x: x[1].category):
                mark = "\u2605" if aid in self.achievements else "\u2606"
                lines.append(f"    {mark} {ach.name:<24} {ach.description:<45} "
                             f"({ach.bonus_xp:,} XP)")
            lines.append("")

            lines.append("  Title Progression:")
            for threshold, tname in TITLES:
                mark = "\u2605" if lvl >= threshold else "\u2606"
                lines.append(f"    {mark} Level {threshold:<4} {tname}")
            lines.append("")

        return "\n".join(lines)

    def format_exit_summary(self) -> str:
        """Short XP line for the session exit summary."""
        lvl, xp_in, xp_need = xp_progress(self.total_xp)
        pct = int(xp_in / max(xp_need, 1) * 100)
        title_str = f" [{self.title}]" if self.title else ""
        return f"  XP:             Level {lvl}{title_str} ({self.total_xp:,} XP, {pct}% to next)"

    # ── Audit dict ────────────────────────────────────────────────────────

    def to_audit_dict(self) -> dict:
        """Return JSON-serializable snapshot for audit export."""
        return {
            "schema_version": 1,
            "total_xp": self.total_xp,
            "level": self.level,
            "title": self.title,
            "achievements": sorted(self.achievements),
            "lifetime": dict(self.lifetime),
        }

    # ── Persistence ───────────────────────────────────────────────────────

    def _save(self):
        """Persist XP state to disk. Caller must NOT hold self._lock
        if calling from outside, but internal callers hold it."""
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            data = {
                "schema_version": 1,
                "total_xp": self.total_xp,
                "level": self.level,
                "title": self.title,
                "achievements": sorted(self.achievements),
                "daily_log": self.daily_log,
                "combo_registry": self.combo_registry,
                "lifetime": self.lifetime,
                "xp_history": self.xp_history[-self._max_history:],
            }
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, default=str),
                           encoding="utf-8")
            tmp.replace(self._path)
        except OSError as e:
            log.debug("Failed to save XP: %s", e)

    def _load(self):
        """Load XP state from disk."""
        if not self._path.exists():
            self._run_migration()
            return

        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self.total_xp = raw.get("total_xp", 0)
            self.level = raw.get("level", 1)
            self.title = raw.get("title", "")
            self.achievements = set(raw.get("achievements", []))
            self.daily_log = raw.get("daily_log", {})
            self.combo_registry = raw.get("combo_registry", {})
            self.xp_history = raw.get("xp_history", [])

            lt = raw.get("lifetime", {})
            for k, default in self.lifetime.items():
                self.lifetime[k] = lt.get(k, default)

            # Recompute level/title from XP (authoritative)
            self.level = level_from_xp(self.total_xp)
            self.title = title_for_level(self.level)

        except (OSError, json.JSONDecodeError, KeyError) as e:
            log.warning("Failed to load XP, starting fresh: %s", e)

    def _run_migration(self):
        """One-time migration credit for existing users."""
        sessions_file = self._dir / "sessions.json"
        credit = 0
        if sessions_file.exists():
            try:
                data = json.loads(sessions_file.read_text(encoding="utf-8"))
                session_count = len(data) if isinstance(data, list) else 0
                credit = min(session_count * 50, 2500)
            except Exception:
                pass

        if credit > 0:
            self.total_xp = credit
            self.level = level_from_xp(self.total_xp)
            self.title = title_for_level(self.level)
            log.info("XP migration: awarded %d XP for %d prior sessions",
                     credit, credit // 50)
            self._save()

    # ── Prune old daily logs ──────────────────────────────────────────────

    def prune_daily_log(self, keep_days: int = 30):
        """Remove daily log entries older than *keep_days*."""
        cutoff = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        # Simple: keep last N entries by sorted date
        dates = sorted(self.daily_log.keys())
        if len(dates) > keep_days:
            for d in dates[:-keep_days]:
                del self.daily_log[d]
            self._save()
