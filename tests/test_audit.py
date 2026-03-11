"""Tests for the audit export zip bundle system."""

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from forge.audit import AuditExporter, SCHEMA_VERSION


def _make_mock_subsystems(tmp_path):
    """Create minimal mock subsystem objects with to_audit_dict()."""
    forensics = MagicMock()
    forensics.to_audit_dict.return_value = {
        "schema_version": 1,
        "session_id": "test_session",
        "session_start": 1000.0,
        "turns": 5,
        "tokens_in": 3000,
        "tokens_out": 1000,
        "events": [
            {"timestamp": 1001.0, "category": "tool", "action": "read file",
             "details": {"name": "read_file", "path": "main.py"}, "risk_level": 0},
            {"timestamp": 1002.0, "category": "file_read", "action": "read main.py",
             "details": {"path": "main.py"}, "risk_level": 0},
        ],
        "summary": {
            "files_read": {"main.py": 1},
            "files_written": {},
            "files_edited": {},
            "files_created": [],
            "tool_calls": {"read_file": 1},
            "shell_commands": [{"command": "git status", "exit_code": 0, "time": 1003.0}],
            "threats": [],
            "context_swaps": 0,
        },
    }

    memory = MagicMock()
    memory.to_audit_dict.return_value = {
        "schema_version": 1,
        "session_id": "abc123",
        "entries": [
            {"session_id": "abc123", "turn_number": 1, "timestamp": 1001.0,
             "user_intent": "fix bug", "actions_taken": ["read_file: main.py"],
             "files_touched": ["main.py"], "key_decisions": "",
             "assistant_response": "reading file", "tokens_used": 500,
             "evicted_content": []},
        ],
    }

    stats = MagicMock()
    stats.to_audit_dict.return_value = {
        "schema_version": 1,
        "perf_samples": [{"timestamp": 1001.0, "tok_per_sec": 45.0}],
        "tool_analytics": {"total_calls": 1, "by_tool": {"read_file": 1}},
        "context_efficiency": {},
    }

    billing = MagicMock()
    billing.to_audit_dict.return_value = {
        "schema_version": 1,
        "session_tokens": 4000,
        "session_input": 3000,
        "session_output": 1000,
        "session_cached": 500,
        "balance": 48.5,
        "comparisons": {},
    }

    crucible = MagicMock()
    crucible.to_audit_dict.return_value = {
        "schema_version": 1,
        "enabled": True,
        "total_scans": 3,
        "threats_found": 1,
        "threats_blocked": 0,
        "canary_leaked": False,
        "canary_leaks": 0,
        "threat_log": [
            {"level": 2, "level_name": "WARNING", "category": "test",
             "description": "test threat", "file_path": "evil.py",
             "matched_text": "bad stuff", "timestamp": 1002.0},
        ],
    }

    continuity = MagicMock()
    continuity.to_audit_dict.return_value = {
        "schema_version": 1,
        "enabled": True,
        "current_grade": "A",
        "current_score": 95.0,
        "swaps_total": 0,
        "turns_since_swap": 5,
        "history": [],
    }

    plan_verifier = MagicMock()
    plan_verifier.to_audit_dict.return_value = {
        "schema_version": 1,
        "mode": "off",
        "results": [],
    }

    return {
        "forensics": forensics,
        "memory": memory,
        "stats": stats,
        "billing": billing,
        "crucible": crucible,
        "continuity": continuity,
        "plan_verifier": plan_verifier,
    }


class TestBuildPackage:
    """Verifies AuditExporter.build_package() assembles all subsystem dicts into a complete package.

    build_package() calls to_audit_dict() on every subsystem (forensics, memory, stats, billing,
    crucible, continuity, plan_verifier) and assembles the results under canonical keys: session,
    forensics, memory, billing, threats, continuity, verification. The 'session' block must
    contain the model name, turn count, and working directory passed as arguments.
    Every subsystem's to_audit_dict() must be called exactly once per build_package() call.
    """

    def test_builds_successfully(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        pkg = exporter.build_package(
            **subs, session_start=1000.0, turn_count=5,
            model="test-model", cwd="/tmp/test")
        assert "session" in pkg
        assert "forensics" in pkg
        assert "memory" in pkg
        assert "billing" in pkg
        assert "threats" in pkg
        assert "continuity" in pkg
        assert "verification" in pkg

    def test_session_metadata(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        pkg = exporter.build_package(
            **subs, session_start=1000.0, turn_count=5,
            model="qwen2.5-coder:14b", cwd="/project")
        session = pkg["session"]
        assert session["model"] == "qwen2.5-coder:14b"
        assert session["turns"] == 5
        assert session["working_directory"] == "/project"

    def test_all_audit_dict_called(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        exporter.build_package(
            **subs, session_start=1000.0, turn_count=1,
            model="m", cwd=".")
        for name, mock in subs.items():
            mock.to_audit_dict.assert_called_once()


class TestExport:
    """Verifies export() writes a valid zip file with the correct internal structure.

    The zip must contain: manifest.json, audit.json, logs/tool_calls.jsonl,
    logs/threats.jsonl, logs/journal.jsonl, verification/results.json.
    The manifest must have schema_version==SCHEMA_VERSION, a 'file_hashes' dict,
    and every hash value must start with 'sha512:' for tamper-evidence.
    audit.json must parse as valid JSON with a 'session' key.
    Default filename starts with 'forge_audit_' and ends with '.zip'.
    A custom path override must be honored (output == the path passed).
    """

    def test_creates_zip(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        pkg = exporter.build_package(
            **subs, session_start=1000.0, turn_count=1,
            model="m", cwd=".")
        out = exporter.export(pkg)
        assert out.exists()
        assert out.suffix == ".zip"

    def test_zip_structure(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        pkg = exporter.build_package(
            **subs, session_start=1000.0, turn_count=1,
            model="m", cwd=".")
        out = exporter.export(pkg)

        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "audit.json" in names
            assert "logs/tool_calls.jsonl" in names
            assert "logs/threats.jsonl" in names
            assert "logs/journal.jsonl" in names
            assert "verification/results.json" in names

    def test_manifest_has_hashes(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        pkg = exporter.build_package(
            **subs, session_start=1000.0, turn_count=1,
            model="m", cwd=".")
        out = exporter.export(pkg)

        with zipfile.ZipFile(out) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["schema_version"] == SCHEMA_VERSION
            assert "file_hashes" in manifest
            assert "audit.json" in manifest["file_hashes"]
            for h in manifest["file_hashes"].values():
                assert h.startswith("sha512:")

    def test_audit_json_valid(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        pkg = exporter.build_package(
            **subs, session_start=1000.0, turn_count=1,
            model="m", cwd=".")
        out = exporter.export(pkg)

        with zipfile.ZipFile(out) as zf:
            data = json.loads(zf.read("audit.json"))
            assert "session" in data

    def test_path_override(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        pkg = exporter.build_package(
            **subs, session_start=1000.0, turn_count=1,
            model="m", cwd=".")
        custom_path = tmp_path / "custom_audit.zip"
        out = exporter.export(pkg, path=custom_path)
        assert out == custom_path
        assert custom_path.exists()

    def test_filename_format(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        pkg = exporter.build_package(
            **subs, session_start=1000.0, turn_count=1,
            model="m", cwd=".")
        out = exporter.export(pkg)
        assert out.name.startswith("forge_audit_")
        assert out.name.endswith(".zip")


class TestRedaction:
    """Verifies export(redact=True) strips private content before writing the zip.

    Redaction targets: memory entries' user_intent and assistant_response become '[REDACTED]',
    threat log matched_text becomes '[REDACTED]', and shell command strings become '[REDACTED]'.
    The manifest.json must have redacted=True so recipients know the file was sanitized.
    Redaction allows sharing audit bundles with third parties without leaking user code or messages.
    """

    def test_redacts_user_intent(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        pkg = exporter.build_package(
            **subs, session_start=1000.0, turn_count=1,
            model="m", cwd=".")
        out = exporter.export(pkg, redact=True)

        with zipfile.ZipFile(out) as zf:
            data = json.loads(zf.read("audit.json"))
            for entry in data["memory"]["entries"]:
                assert entry["user_intent"] == "[REDACTED]"
                assert entry["assistant_response"] == "[REDACTED]"

    def test_redacts_threat_matched_text(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        pkg = exporter.build_package(
            **subs, session_start=1000.0, turn_count=1,
            model="m", cwd=".")
        out = exporter.export(pkg, redact=True)

        with zipfile.ZipFile(out) as zf:
            data = json.loads(zf.read("audit.json"))
            for t in data["threats"]["threat_log"]:
                assert t["matched_text"] == "[REDACTED]"

    def test_redacts_shell_commands(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        pkg = exporter.build_package(
            **subs, session_start=1000.0, turn_count=1,
            model="m", cwd=".")
        out = exporter.export(pkg, redact=True)

        with zipfile.ZipFile(out) as zf:
            data = json.loads(zf.read("audit.json"))
            for cmd in data["forensics"]["summary"]["shell_commands"]:
                assert cmd["command"] == "[REDACTED]"

    def test_manifest_shows_redacted(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        pkg = exporter.build_package(
            **subs, session_start=1000.0, turn_count=1,
            model="m", cwd=".")
        out = exporter.export(pkg, redact=True)

        with zipfile.ZipFile(out) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["redacted"] is True


class TestFormatSummary:
    """Verifies format_summary() produces a human-readable text summary of the audit package.

    The output must contain the session ID (from forensics audit dict) and the turn count.
    """

    def test_contains_session_info(self, tmp_path):
        subs = _make_mock_subsystems(tmp_path)
        exporter = AuditExporter(export_dir=tmp_path)
        pkg = exporter.build_package(
            **subs, session_start=1000.0, turn_count=5,
            model="test", cwd=".")
        summary = exporter.format_summary(pkg)
        assert "test_session" in summary
        assert "5" in summary  # turns
