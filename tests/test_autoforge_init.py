"""Tests for AutoForge, BPoS, and Shipwright initialization."""

import pytest
from pathlib import Path
from forge.autoforge import AutoForge
from forge.passport import BPoS
from forge.shipwright import Shipwright


class TestAutoForgeInit:
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
        # Community tier should allow basic features
        # The specific features depend on TIERS config
        result = bpos.is_feature_allowed("nonexistent_feature")
        assert result is False


class TestShipwrightInit:
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


class TestEngineInitializesSubsystems:
    """Verify engine.py __init__ creates _autoforge, _bpos, _shipwright."""

    def test_init_code_has_autoforge(self):
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine.__init__)
        assert "self._autoforge" in source
        assert "AutoForge(" in source

    def test_init_code_has_bpos(self):
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine.__init__)
        assert "self._bpos" in source
        assert "BPoS(" in source

    def test_init_code_has_shipwright(self):
        import inspect
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine.__init__)
        assert "self._shipwright" in source
        assert "Shipwright(" in source
