"""Tests for AutoForge, BPoS, and Shipwright initialization and lifecycle.

Verifies constructor defaults, enable/disable toggling, config wiring,
edit recording, version detection from pyproject.toml, and feature gating.
"""

import pytest
from pathlib import Path
from forge.autoforge import AutoForge
from forge.passport import BPoS
from forge.shipwright import Shipwright


class TestAutoForgeInit:
    """Verifies AutoForge initialization defaults and basic enable/disable/record lifecycle.

    Fresh instance: _enabled=False, _pending and _commits are empty lists.
    enable() sets _enabled=True; disable() sets it back to False.
    config_get lambda is wired and callable.  record_edit() while enabled
    appends a pending edit with the correct path.
    """

    def test_init_defaults(self):
        af = AutoForge()
        assert af._enabled is False
        assert isinstance(af._pending, list)
        assert isinstance(af._commits, list)

    def test_enable_disable(self):
        af = AutoForge()
        af.enable()
        assert af._enabled is True
        af.disable()
        assert af._enabled is False

    def test_with_config_get(self):
        config = {"auto_commit": True}
        af = AutoForge(config_get=lambda k, d=None: config.get(k, d))
        assert af._config_get("auto_commit") is True

    def test_record_edit(self):
        af = AutoForge()
        af.enable()
        af.record_edit("test.py", "edit")
        assert len(af._pending) == 1
        assert af._pending[0].path == "test.py"


class TestBPoSInit:
    """Verifies BPoS initialization defaults and feature gate behavior.

    Fresh community instance: tier='community', _machine_id=''.  With machine_id
    kwarg: _machine_id set correctly.  tier_config is a dict.
    is_feature_allowed('nonexistent_feature') returns False (unknown features
    are denied by default).
    """

    def test_init_defaults(self, tmp_path):
        bpos = BPoS(data_dir=tmp_path)
        assert bpos.tier == "community"
        assert bpos._machine_id == ""

    def test_init_with_machine_id(self, tmp_path):
        bpos = BPoS(data_dir=tmp_path, machine_id="test-machine-123")
        assert bpos._machine_id == "test-machine-123"

    def test_community_tier_config(self, tmp_path):
        bpos = BPoS(data_dir=tmp_path)
        config = bpos.tier_config
        assert isinstance(config, dict)

    def test_is_feature_allowed(self, tmp_path):
        bpos = BPoS(data_dir=tmp_path)
        result = bpos.is_feature_allowed("nonexistent_feature")
        assert result is False


class TestShipwrightInit:
    """Verifies Shipwright initialization defaults and version detection.

    Fresh instance: _history=[].  With project_dir kwarg: _project_dir set.
    No pyproject.toml -> get_current_version() returns '0.0.0'.
    pyproject.toml with version='1.2.3' -> get_current_version() returns '1.2.3'.
    """

    def test_init_defaults(self, tmp_path):
        sw = Shipwright(data_dir=tmp_path / "shipwright")
        assert sw._history == []

    def test_init_with_project_dir(self, tmp_path):
        sw = Shipwright(
            project_dir=str(tmp_path),
            data_dir=tmp_path / "shipwright",
        )
        assert sw._project_dir == tmp_path

    def test_get_current_version_no_pyproject(self, tmp_path):
        sw = Shipwright(
            project_dir=str(tmp_path),
            data_dir=tmp_path / "shipwright",
        )
        assert sw.get_current_version() == "0.0.0"

    def test_get_current_version_with_pyproject(self, tmp_path):
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text('[project]\nversion = "1.2.3"\n')
        sw = Shipwright(
            project_dir=str(tmp_path),
            data_dir=tmp_path / "shipwright",
        )
        assert sw.get_current_version() == "1.2.3"
