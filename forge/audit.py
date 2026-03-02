"""Deterministic audit log export — governance-grade zip bundles.

Bundles ALL session data into a chain-of-custody zip package:
  - manifest.json: hashes, versions, timestamps, machine info
  - audit.json: full structured session summary
  - logs/tool_calls.jsonl: one line per tool call event
  - logs/threats.jsonl: one line per threat event
  - logs/journal.jsonl: one line per journal entry
  - verification/results.json: plan verification results

Uses to_audit_dict() on each subsystem — never accesses private fields.

Supports redaction mode (--redact) that strips file contents and
user/assistant text, keeping only paths, timestamps, and metadata.

Output: ~/.forge/exports/forge_audit_YYYYMMDD_HHMMSS.zip
"""

import hashlib
import io
import json
import logging
import platform
import socket
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
FORGE_VERSION = "0.9.0"


class AuditExporter:
    """Assembles and exports a complete audit zip bundle."""

    def __init__(self, export_dir: Path = None):
        self._export_dir = export_dir or (Path.home() / ".forge" / "exports")

    def build_package(self, *, forensics, memory, stats, billing,
                      crucible, continuity, plan_verifier,
                      reliability=None,
                      session_start: float, turn_count: int,
                      model: str, cwd: str) -> dict:
        """Build the full audit package from subsystem to_audit_dict() calls.

        Never accesses private fields — only uses the stable API contract.
        """
        now = time.time()
        elapsed = now - session_start

        # Gather from each subsystem via stable API
        forensics_data = forensics.to_audit_dict()
        memory_data = memory.to_audit_dict()
        billing_data = billing.to_audit_dict()
        crucible_data = crucible.to_audit_dict()
        continuity_data = continuity.to_audit_dict()
        verifier_data = plan_verifier.to_audit_dict()
        stats_data = stats.to_audit_dict()

        package = {
            "session": {
                "session_id": forensics_data.get("session_id", ""),
                "start_time": session_start,
                "end_time": now,
                "duration_s": round(elapsed, 1),
                "turns": turn_count,
                "model": model,
                "working_directory": cwd,
                "tokens_in": forensics_data.get("tokens_in", 0),
                "tokens_out": forensics_data.get("tokens_out", 0),
            },
            "forensics": forensics_data,
            "memory": memory_data,
            "billing": billing_data,
            "threats": crucible_data,
            "continuity": continuity_data,
            "verification": verifier_data,
            "stats": stats_data,
        }

        # Reliability data (optional — graceful if tracker not provided)
        if reliability is not None:
            try:
                package["reliability"] = {
                    "score": reliability.get_reliability_score(),
                    "trend": reliability.get_trend(),
                    "metrics": reliability.get_underlying_metrics(),
                }
            except Exception:
                pass

        return package

    def export(self, package: dict, path: Path = None,
               redact: bool = False) -> Path:
        """Write the package as a zip bundle. Returns output path."""
        self._export_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if path is None:
            path = self._export_dir / f"forge_audit_{timestamp}.zip"

        if redact:
            package = self._redact(package)

        # Build zip contents
        files: dict[str, bytes] = {}

        # audit.json — full structured summary
        audit_json = json.dumps(package, indent=2, ensure_ascii=False,
                                default=str).encode("utf-8")
        files["audit.json"] = audit_json

        # logs/tool_calls.jsonl
        tool_events = [
            e for e in package.get("forensics", {}).get("events", [])
            if e.get("category") == "tool"
        ]
        files["logs/tool_calls.jsonl"] = self._to_jsonl(tool_events)

        # logs/threats.jsonl
        threat_log = package.get("threats", {}).get("threat_log", [])
        files["logs/threats.jsonl"] = self._to_jsonl(threat_log)

        # logs/journal.jsonl
        journal_entries = package.get("memory", {}).get("entries", [])
        files["logs/journal.jsonl"] = self._to_jsonl(journal_entries)

        # verification/results.json
        verification = package.get("verification", {})
        files["verification/results.json"] = json.dumps(
            verification, indent=2, default=str).encode("utf-8")

        # manifest.json — hashes, versions, machine info
        config_hash = hashlib.sha256(
            json.dumps(package.get("session", {}),
                       sort_keys=True).encode()
        ).hexdigest()[:16]

        file_hashes = {}
        for name, content in files.items():
            h = hashlib.sha256(content).hexdigest()
            file_hashes[name] = f"sha256:{h}"

        from forge.machine_id import get_machine_id, get_machine_label
        machine_id = get_machine_id()

        # Hardware info for fleet capability matrix
        try:
            from forge.hardware import get_hardware_summary
            hw = get_hardware_summary()
            gpu = hw.get("gpu") or {}
            hardware_info = {
                "gpu_name": gpu.get("name", "unknown"),
                "vram_total_mb": gpu.get("vram_total_mb", 0),
                "driver_version": gpu.get("driver_version", ""),
                "cuda_version": gpu.get("cuda_version", ""),
                "cpu": hw.get("cpu", ""),
                "ram_mb": hw.get("ram_mb", 0),
                "os_version": platform.platform(),
            }
        except Exception:
            hardware_info = {"gpu_name": "unknown"}

        manifest = {
            "forge_version": FORGE_VERSION,
            "schema_version": SCHEMA_VERSION,
            "export_timestamp": datetime.now().isoformat(),
            "machine_id": machine_id,
            "machine_label": get_machine_label(),
            "platform": platform.platform(),
            "model": package.get("session", {}).get("model", ""),
            "config_hash": config_hash,
            "redacted": redact,
            "file_hashes": file_hashes,
            "hardware": hardware_info,
        }
        manifest_bytes = json.dumps(
            manifest, indent=2, ensure_ascii=False).encode("utf-8")

        # stress/trendline.jsonl — harness stress test history (if available)
        forge_dir = Path.home() / ".forge"
        trendline_path = forge_dir / "harness_trend.jsonl"
        if trendline_path.exists():
            try:
                trendline_bytes = trendline_path.read_bytes()
                files["stress/trendline.jsonl"] = trendline_bytes
                # Include latest run summary if available
                runs_dir = forge_dir / "harness_runs"
                if runs_dir.exists():
                    run_dirs = sorted(runs_dir.iterdir(), reverse=True)
                    for rd in run_dirs:
                        summary = rd / "summary.json"
                        if summary.exists():
                            files["stress/latest_summary.json"] = \
                                summary.read_bytes()
                            break
                manifest["stress_test_results"] = True
            except Exception:
                pass

        # Write zip
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("manifest.json", manifest_bytes)
            for name, content in files.items():
                zf.writestr(name, content)

        path.write_bytes(buf.getvalue())
        log.info("Audit exported to %s (%d bytes)", path, len(buf.getvalue()))
        return path

    def format_summary(self, package: dict) -> str:
        """Terminal-friendly summary of what was exported."""
        from forge.ui.terminal import BOLD, RESET, DIM, GREEN, CYAN

        session = package.get("session", {})
        forensics = package.get("forensics", {})
        threats = package.get("threats", {})
        memory = package.get("memory", {})
        verification = package.get("verification", {})

        events = forensics.get("events", [])
        threat_log = threats.get("threat_log", [])
        entries = memory.get("entries", [])
        results = verification.get("results", [])
        verified = sum(1 for r in results if r.get("passed"))

        lines = [
            f"\n{BOLD}Audit Export Summary{RESET}",
            f"  Session:    {session.get('session_id', '?')}",
            f"  Duration:   {session.get('duration_s', 0) / 60:.1f} min",
            f"  Turns:      {session.get('turns', 0)}",
            f"  Model:      {session.get('model', '?')}",
            f"  Events:     {len(events)}",
            f"  Journal:    {len(entries)} entries",
            f"  Threats:    {len(threat_log)}",
        ]
        if results:
            lines.append(f"  Verified:   {verified}/{len(results)} steps")
        lines.append(f"  {DIM}Bundle ready for compliance review.{RESET}")
        return "\n".join(lines)

    # ── Internal helpers ──

    @staticmethod
    def _to_jsonl(items: list) -> bytes:
        """Convert a list of dicts to JSONL bytes."""
        lines = []
        for item in items:
            lines.append(json.dumps(item, ensure_ascii=False, default=str))
        return ("\n".join(lines) + "\n" if lines else "").encode("utf-8")

    @staticmethod
    def _redact(package: dict) -> dict:
        """Deep-copy the package with sensitive content replaced.

        Keeps: paths, timestamps, categories, risk levels, counts.
        Strips: file contents, user prompts, assistant responses,
                matched_text from threats, shell command text.
        """
        import copy
        p = copy.deepcopy(package)

        # Redact journal entries
        for entry in p.get("memory", {}).get("entries", []):
            entry["user_intent"] = "[REDACTED]"
            entry["assistant_response"] = "[REDACTED]"
            entry["key_decisions"] = "[REDACTED]"
            for ev in entry.get("evicted_content", []):
                ev["preview"] = "[REDACTED]"

        # Redact forensic event details (keep category/action/risk)
        for event in p.get("forensics", {}).get("events", []):
            details = event.get("details", {})
            # Keep path, strip content
            redacted_details = {}
            if "path" in details:
                redacted_details["path"] = details["path"]
            if "name" in details:
                redacted_details["name"] = details["name"]
            if "exit_code" in details:
                redacted_details["exit_code"] = details["exit_code"]
            event["details"] = redacted_details

        # Redact threat matched text
        for threat in p.get("threats", {}).get("threat_log", []):
            threat["matched_text"] = "[REDACTED]"

        # Redact shell commands
        for cmd in p.get("forensics", {}).get("summary", {}).get(
                "shell_commands", []):
            cmd["command"] = "[REDACTED]"

        return p
