"""Tests for data retention housekeeping in ForgeEngine."""

import os
import time
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch


def _make_engine(safety_level=2, retention_days=30):
    """Create a minimal mock engine with housekeeping method."""
    engine = MagicMock()
    engine.safety = MagicMock()
    engine.safety.level = safety_level
    engine.config = MagicMock()
    engine.config.get = lambda k, d=None: {
        "data_retention_days": retention_days,
    }.get(k, d)

    from forge.engine import ForgeEngine
    engine._run_housekeeping = ForgeEngine._run_housekeeping.__get__(engine)
    return engine


class TestHousekeeping:
    """Verifies _run_housekeeping() prunes stale files based on safety level and retention config.

    Safety L0 → no files pruned regardless of age. Safety L2, retention_days=30:
    file with 60-day-old mtime → deleted. Recent file (current mtime) → kept.
    retention_days=0 → pruning disabled, old files kept. Missing forensics/exports
    directories → no exception raised.
    """

    def test_safety_l0_no_pruning(self, tmp_path):
        engine = _make_engine(safety_level=0)
        forensics_dir = tmp_path / ".forge" / "forensics"
        forensics_dir.mkdir(parents=True)
        old_file = forensics_dir / "old.json"
        old_file.write_text("data")
        # Set old mtime
        old_time = time.time() - (365 * 86400)
        os.utime(old_file, (old_time, old_time))
        with patch("pathlib.Path.home", return_value=tmp_path):
            engine._run_housekeeping()
        assert old_file.exists()  # Not pruned at L0

    def test_old_files_pruned_at_l2(self, tmp_path):
        engine = _make_engine(safety_level=2, retention_days=30)
        forensics_dir = tmp_path / ".forge" / "forensics"
        forensics_dir.mkdir(parents=True)
        old_file = forensics_dir / "old.json"
        old_file.write_text("old data")
        old_time = time.time() - (60 * 86400)  # 60 days ago
        os.utime(old_file, (old_time, old_time))
        with patch("pathlib.Path.home", return_value=tmp_path):
            engine._run_housekeeping()
        assert not old_file.exists()  # Pruned (>30 days)

    def test_recent_files_kept(self, tmp_path):
        engine = _make_engine(safety_level=2, retention_days=30)
        forensics_dir = tmp_path / ".forge" / "forensics"
        forensics_dir.mkdir(parents=True)
        recent_file = forensics_dir / "recent.json"
        recent_file.write_text("recent data")
        # Default mtime is now — well within retention
        with patch("pathlib.Path.home", return_value=tmp_path):
            engine._run_housekeeping()
        assert recent_file.exists()  # Kept

    def test_retention_disabled(self, tmp_path):
        engine = _make_engine(safety_level=2, retention_days=0)
        forensics_dir = tmp_path / ".forge" / "forensics"
        forensics_dir.mkdir(parents=True)
        old_file = forensics_dir / "old.json"
        old_file.write_text("data")
        old_time = time.time() - (365 * 86400)
        os.utime(old_file, (old_time, old_time))
        with patch("pathlib.Path.home", return_value=tmp_path):
            engine._run_housekeeping()
        assert old_file.exists()  # Not pruned (disabled)

    def test_missing_directories_no_error(self, tmp_path):
        engine = _make_engine(safety_level=2, retention_days=30)
        # No forensics or exports dirs exist
        forge_dir = tmp_path / ".forge"
        forge_dir.mkdir(parents=True)
        with patch("pathlib.Path.home", return_value=tmp_path):
            engine._run_housekeeping()  # Should not raise
