"""Tests for forge.config — ForgeConfig loader and YAML parser."""

import pytest
from pathlib import Path
from forge.config import (
    ForgeConfig, DEFAULTS, _parse_yaml_simple, _dump_yaml_simple,
)


# ---------------------------------------------------------------------------
# test_defaults
# ---------------------------------------------------------------------------

class TestDefaults:
    def test_all_defaults_present(self, tmp_path):
        cfg = ForgeConfig(config_dir=tmp_path)
        for key, default_val in DEFAULTS.items():
            assert cfg.get(key) == default_val, \
                f"Default mismatch for '{key}': expected {default_val!r}, got {cfg.get(key)!r}"

    def test_get_unknown_key(self, tmp_path):
        cfg = ForgeConfig(config_dir=tmp_path)
        assert cfg.get("nonexistent_key") is None
        assert cfg.get("nonexistent_key", 42) == 42

    def test_contains(self, tmp_path):
        cfg = ForgeConfig(config_dir=tmp_path)
        assert "safety_level" in cfg
        assert "nonexistent" not in cfg

    def test_getitem(self, tmp_path):
        cfg = ForgeConfig(config_dir=tmp_path)
        assert cfg["safety_level"] == 1
        with pytest.raises(KeyError):
            _ = cfg["nonexistent"]


# ---------------------------------------------------------------------------
# test_create_default_file
# ---------------------------------------------------------------------------

class TestCreateDefaultFile:
    def test_creates_config_file(self, tmp_path):
        ForgeConfig(config_dir=tmp_path)
        config_path = tmp_path / "config.yaml"
        assert config_path.exists()

    def test_default_file_parseable(self, tmp_path):
        ForgeConfig(config_dir=tmp_path)
        config_path = tmp_path / "config.yaml"
        content = config_path.read_text(encoding="utf-8")
        parsed = _parse_yaml_simple(content)
        assert "safety_level" in parsed
        assert parsed["safety_level"] == 1

    def test_config_dir_created(self, tmp_path):
        subdir = tmp_path / "deeply" / "nested"
        ForgeConfig(config_dir=subdir)
        assert subdir.exists()

    def test_path_property(self, tmp_path):
        cfg = ForgeConfig(config_dir=tmp_path)
        assert cfg.path == tmp_path / "config.yaml"


# ---------------------------------------------------------------------------
# test_load_and_override
# ---------------------------------------------------------------------------

class TestLoadAndOverride:
    def test_override_int(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("safety_level: 3\n", encoding="utf-8")
        cfg = ForgeConfig(config_dir=tmp_path)
        assert cfg.get("safety_level") == 3

    def test_override_bool(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("sandbox_enabled: true\n", encoding="utf-8")
        cfg = ForgeConfig(config_dir=tmp_path)
        assert cfg.get("sandbox_enabled") is True

    def test_override_float(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("context_safety_margin: 0.95\n", encoding="utf-8")
        cfg = ForgeConfig(config_dir=tmp_path)
        assert cfg.get("context_safety_margin") == 0.95

    def test_override_string(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text('default_model: "my-custom-model"\n', encoding="utf-8")
        cfg = ForgeConfig(config_dir=tmp_path)
        assert cfg.get("default_model") == "my-custom-model"

    def test_override_list(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "sandbox_roots:\n  - /home/user/projects\n  - /tmp/safe\n",
            encoding="utf-8")
        cfg = ForgeConfig(config_dir=tmp_path)
        roots = cfg.get("sandbox_roots")
        assert isinstance(roots, list)
        assert len(roots) == 2
        assert "/home/user/projects" in roots
        assert "/tmp/safe" in roots

    def test_unrecognized_keys_ignored(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text(
            "safety_level: 2\nunknown_key: 42\n", encoding="utf-8")
        cfg = ForgeConfig(config_dir=tmp_path)
        assert cfg.get("safety_level") == 2
        # unknown key should not appear in config
        assert cfg.get("unknown_key") is None

    def test_defaults_preserved_for_missing_keys(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("safety_level: 0\n", encoding="utf-8")
        cfg = ForgeConfig(config_dir=tmp_path)
        assert cfg.get("safety_level") == 0
        # All other defaults should still be present
        assert cfg.get("default_model") == DEFAULTS["default_model"]
        assert cfg.get("max_agent_iterations") == DEFAULTS["max_agent_iterations"]


# ---------------------------------------------------------------------------
# test_set_and_save
# ---------------------------------------------------------------------------

class TestSetAndSave:
    def test_set_in_memory(self, tmp_path):
        cfg = ForgeConfig(config_dir=tmp_path)
        cfg.set("safety_level", 3)
        assert cfg.get("safety_level") == 3

    def test_save_persists(self, tmp_path):
        cfg = ForgeConfig(config_dir=tmp_path)
        cfg.set("safety_level", 0)
        cfg.set("sandbox_enabled", True)
        cfg.save()

        # Reload and verify
        cfg2 = ForgeConfig(config_dir=tmp_path)
        assert cfg2.get("safety_level") == 0
        assert cfg2.get("sandbox_enabled") is True

    def test_save_preserves_all_keys(self, tmp_path):
        cfg = ForgeConfig(config_dir=tmp_path)
        cfg.set("persona", "hacker")
        cfg.save()

        cfg2 = ForgeConfig(config_dir=tmp_path)
        assert cfg2.get("persona") == "hacker"
        # Other defaults should still be present
        assert cfg2.get("safety_level") == DEFAULTS["safety_level"]


# ---------------------------------------------------------------------------
# test_reload
# ---------------------------------------------------------------------------

class TestReload:
    def test_reload_picks_up_changes(self, tmp_path):
        cfg = ForgeConfig(config_dir=tmp_path)
        assert cfg.get("safety_level") == 1

        # Externally modify the file
        config_path = tmp_path / "config.yaml"
        config_path.write_text("safety_level: 3\n", encoding="utf-8")

        cfg.reload()
        assert cfg.get("safety_level") == 3

    def test_reload_resets_to_defaults_first(self, tmp_path):
        cfg = ForgeConfig(config_dir=tmp_path)
        cfg.set("safety_level", 0)  # in-memory change

        # File still says safety_level: 1 (default template)
        cfg.reload()
        assert cfg.get("safety_level") == 1

    def test_reload_after_file_deleted(self, tmp_path):
        cfg = ForgeConfig(config_dir=tmp_path)
        config_path = tmp_path / "config.yaml"
        config_path.unlink()  # delete it

        cfg.reload()
        # Should recreate default and load it
        assert config_path.exists()
        assert cfg.get("safety_level") == DEFAULTS["safety_level"]


# ---------------------------------------------------------------------------
# test_yaml_parser
# ---------------------------------------------------------------------------

class TestYamlParser:
    def test_simple_int(self):
        result = _parse_yaml_simple("safety_level: 1\n")
        assert result["safety_level"] == 1

    def test_simple_float(self):
        result = _parse_yaml_simple("margin: 0.85\n")
        assert result["margin"] == 0.85

    def test_simple_string(self):
        result = _parse_yaml_simple('model: "qwen2.5-coder:14b"\n')
        assert result["model"] == "qwen2.5-coder:14b"

    def test_string_single_quotes(self):
        result = _parse_yaml_simple("name: 'hello'\n")
        assert result["name"] == "hello"

    def test_bool_true(self):
        result = _parse_yaml_simple("enabled: true\n")
        assert result["enabled"] is True

    def test_bool_false(self):
        result = _parse_yaml_simple("disabled: false\n")
        assert result["disabled"] is False

    def test_bool_case_insensitive(self):
        result = _parse_yaml_simple("a: True\nb: FALSE\n")
        assert result["a"] is True
        assert result["b"] is False

    def test_empty_list(self):
        result = _parse_yaml_simple("items: []\n")
        assert result["items"] == []

    def test_list_with_items(self):
        yaml = "roots:\n  - /home/user\n  - /tmp/safe\n"
        result = _parse_yaml_simple(yaml)
        assert result["roots"] == ["/home/user", "/tmp/safe"]

    def test_list_terminated_by_blank_line(self):
        yaml = "items:\n  - first\n  - second\n\nother: 42\n"
        result = _parse_yaml_simple(yaml)
        assert result["items"] == ["first", "second"]
        assert result["other"] == 42

    def test_comments_stripped(self):
        yaml = "# This is a comment\nkey: 42  # inline comment\n"
        result = _parse_yaml_simple(yaml)
        assert result["key"] == 42

    def test_blank_lines_ignored(self):
        yaml = "\n\nkey: value\n\n\n"
        result = _parse_yaml_simple(yaml)
        assert result["key"] == "value"

    def test_multiple_keys(self):
        yaml = "a: 1\nb: 2\nc: 3\n"
        result = _parse_yaml_simple(yaml)
        assert result == {"a": 1, "b": 2, "c": 3}

    def test_empty_value_becomes_list(self):
        yaml = "items:\n  - one\n"
        result = _parse_yaml_simple(yaml)
        assert result["items"] == ["one"]

    def test_string_without_quotes(self):
        result = _parse_yaml_simple("model: qwen2.5-coder\n")
        assert result["model"] == "qwen2.5-coder"

    def test_full_config_template(self, tmp_path):
        """The actual default config template should parse without errors."""
        cfg = ForgeConfig(config_dir=tmp_path)
        config_text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        result = _parse_yaml_simple(config_text)
        assert "safety_level" in result
        assert result["safety_level"] == 1
        assert result["sandbox_enabled"] is False

    def test_list_at_end_of_file(self):
        yaml = "items:\n  - alpha\n  - beta"  # no trailing newline
        result = _parse_yaml_simple(yaml)
        assert result["items"] == ["alpha", "beta"]

    def test_quoted_list_items(self):
        yaml = 'paths:\n  - "C:/Users/me/projects"\n  - "/home/me"\n'
        result = _parse_yaml_simple(yaml)
        assert result["paths"] == ["C:/Users/me/projects", "/home/me"]


# ---------------------------------------------------------------------------
# test_yaml_dumper
# ---------------------------------------------------------------------------

class TestYamlDumper:
    def test_dump_int(self):
        out = _dump_yaml_simple({"x": 42})
        assert "x: 42" in out

    def test_dump_float(self):
        out = _dump_yaml_simple({"x": 3.14})
        assert "x: 3.14" in out

    def test_dump_string(self):
        out = _dump_yaml_simple({"name": "hello"})
        assert 'name: "hello"' in out

    def test_dump_bool_true(self):
        out = _dump_yaml_simple({"flag": True})
        assert "flag: true" in out

    def test_dump_bool_false(self):
        out = _dump_yaml_simple({"flag": False})
        assert "flag: false" in out

    def test_dump_empty_list(self):
        out = _dump_yaml_simple({"items": []})
        assert "items: []" in out

    def test_dump_list_with_items(self):
        out = _dump_yaml_simple({"roots": ["/a", "/b"]})
        assert "roots:" in out
        assert "  - /a" in out
        assert "  - /b" in out

    def test_roundtrip(self):
        """Dump then parse should produce the same data."""
        original = {
            "level": 1,
            "enabled": True,
            "model": "test-model",
            "margin": 0.85,
            "roots": ["/home", "/tmp"],
            "empty": [],
        }
        yaml_text = _dump_yaml_simple(original)
        parsed = _parse_yaml_simple(yaml_text)
        assert parsed == original

    def test_ends_with_newline(self):
        out = _dump_yaml_simple({"key": "val"})
        assert out.endswith("\n")
