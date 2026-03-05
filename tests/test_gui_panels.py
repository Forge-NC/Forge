"""Tests for GUI panel source code — settings tabs, dashboard cards, engine wiring."""

import inspect


class TestSettingsTabs:
    def test_forge_tab_exists(self):
        from forge.ui.settings_dialog import ForgeSettingsDialog
        assert hasattr(ForgeSettingsDialog, '_build_forge_tab')

    def test_license_tab_exists(self):
        from forge.ui.settings_dialog import ForgeSettingsDialog
        assert hasattr(ForgeSettingsDialog, '_build_license_tab')

    def test_forge_tab_has_auto_commit(self):
        from forge.ui.settings_dialog import ForgeSettingsDialog
        source = inspect.getsource(ForgeSettingsDialog._build_forge_tab)
        assert "auto_commit" in source

    def test_forge_tab_has_shipwright(self):
        from forge.ui.settings_dialog import ForgeSettingsDialog
        source = inspect.getsource(ForgeSettingsDialog._build_forge_tab)
        assert "shipwright_llm_classify" in source

    def test_license_tab_has_activate(self):
        from forge.ui.settings_dialog import ForgeSettingsDialog
        assert hasattr(ForgeSettingsDialog, '_activate_passport')

    def test_license_tab_has_deactivate(self):
        from forge.ui.settings_dialog import ForgeSettingsDialog
        assert hasattr(ForgeSettingsDialog, '_deactivate_passport')

    def test_license_tab_has_tier_table(self):
        from forge.ui.settings_dialog import ForgeSettingsDialog
        assert hasattr(ForgeSettingsDialog, '_build_tier_table')

    def test_tab_list_includes_new_tabs(self):
        from forge.ui.settings_dialog import ForgeSettingsDialog
        source = inspect.getsource(ForgeSettingsDialog.__init__)
        assert '"Forge"' in source
        assert '"License"' in source


class TestDashboardCards:
    def test_card_ids_includes_new(self):
        from forge.ui.dashboard import CARD_IDS
        assert "autoforge" in CARD_IDS
        assert "shipwright" in CARD_IDS
        assert "license" in CARD_IDS

    def test_autoforge_card_builder_exists(self):
        from forge.ui.dashboard import ForgeLauncher
        assert hasattr(ForgeLauncher, '_build_autoforge_card')

    def test_shipwright_card_builder_exists(self):
        from forge.ui.dashboard import ForgeLauncher
        assert hasattr(ForgeLauncher, '_build_shipwright_card')

    def test_license_card_builder_exists(self):
        from forge.ui.dashboard import ForgeLauncher
        assert hasattr(ForgeLauncher, '_build_license_card')

    def test_apply_state_handles_autoforge(self):
        from forge.ui.dashboard import ForgeLauncher
        source = inspect.getsource(ForgeLauncher._apply_state_data)
        assert "autoforge" in source
        assert "af_status" in source

    def test_apply_state_handles_shipwright(self):
        from forge.ui.dashboard import ForgeLauncher
        source = inspect.getsource(ForgeLauncher._apply_state_data)
        assert "shipwright" in source
        assert "sw_version" in source

    def test_apply_state_handles_license(self):
        from forge.ui.dashboard import ForgeLauncher
        source = inspect.getsource(ForgeLauncher._apply_state_data)
        assert '"license"' in source or "'license'" in source
        assert "lic_maturity" in source

    def test_hud_menu_has_fleet_manager(self):
        from forge.ui.dashboard import ForgeLauncher
        source = inspect.getsource(ForgeLauncher._open_hud_menu)
        assert "Fleet Manager" in source


class TestEngineIntegration:
    def test_engine_has_autoforge_snapshot(self):
        from forge.engine import ForgeEngine
        assert hasattr(ForgeEngine, '_get_autoforge_snapshot')

    def test_engine_has_shipwright_snapshot(self):
        from forge.engine import ForgeEngine
        assert hasattr(ForgeEngine, '_get_shipwright_snapshot')

    def test_engine_has_license_snapshot(self):
        from forge.engine import ForgeEngine
        assert hasattr(ForgeEngine, '_get_license_snapshot')

    def test_engine_inits_puppet_mgr(self):
        source = inspect.getsource(
            __import__('forge.engine', fromlist=['ForgeEngine']).ForgeEngine.__init__)
        assert "_puppet_mgr" in source
        assert "PuppetManager" in source

    def test_engine_syncs_puppet_on_exit(self):
        from forge.engine import ForgeEngine
        source = inspect.getsource(ForgeEngine._print_exit_summary)
        assert "sync_to_master" in source


class TestPuppetCommands:
    def test_puppet_command_registered(self):
        from forge.commands import CommandHandler
        assert "/puppet" in CommandHandler._COMMANDS

    def test_puppet_command_has_subcommands(self):
        from forge.commands import CommandHandler
        source = inspect.getsource(CommandHandler._cmd_puppet)
        for sub in ["status", "activate", "join", "generate",
                     "list", "revoke", "sync", "seats"]:
            assert f'"{sub}"' in source or f"'{sub}'" in source


class TestPuppetManagerGUI:
    def test_gui_class_exists(self):
        from forge.ui.puppet_manager import PuppetManagerDialog
        assert PuppetManagerDialog is not None

    def test_gui_has_git_identity(self):
        from forge.ui.puppet_manager import PuppetManagerDialog
        assert hasattr(PuppetManagerDialog, '_save_git_identity')

    def test_gui_has_generate(self):
        from forge.ui.puppet_manager import PuppetManagerDialog
        assert hasattr(PuppetManagerDialog, '_on_generate')

    def test_gui_has_revoke(self):
        from forge.ui.puppet_manager import PuppetManagerDialog
        assert hasattr(PuppetManagerDialog, '_on_revoke')
