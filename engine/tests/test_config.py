from __future__ import annotations

from pathlib import Path

from dashboard_engine.config import apply_env_overrides, load_config

SAMPLE = """
[server]
port = 9000
token = "depuis-le-toml"

[[minecraft.servers]]
name = "Survie"
host = "mc.exemple.net"

[stream.obs]
url = "ws://192.168.1.5:4455"
"""


def test_load_missing_file_uses_defaults(tmp_path: Path) -> None:
    config = load_config(tmp_path / "absent.toml")
    assert config.server.port == 8787
    assert config.minecraft.servers == []


def test_load_toml(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(SAMPLE, encoding="utf-8")
    config = load_config(path)

    assert config.server.port == 9000
    assert config.server.token == "depuis-le-toml"
    assert config.minecraft.servers[0].name == "Survie"
    assert config.stream.obs.url == "ws://192.168.1.5:4455"
    # Les chemins relatifs se resolvent a cote du fichier de configuration.
    assert config.checklist_path() == tmp_path / "checklist.json"


def test_env_overrides_win_over_toml() -> None:
    data = {"server": {"port": 9000, "token": "toml"}}
    apply_env_overrides(data, {"DASHBOARD_PORT": "1234", "DASHBOARD_TOKEN": "env"})
    assert data["server"] == {"port": 1234, "token": "env"}


def test_env_overrides_create_missing_sections() -> None:
    data: dict = {}
    apply_env_overrides(data, {"DASHBOARD_OBS_PASSWORD": "secret"})
    assert data == {"stream": {"obs": {"password": "secret"}}}


def test_empty_env_does_not_erase_toml_value() -> None:
    data = {"server": {"token": "toml"}}
    apply_env_overrides(data, {"DASHBOARD_TOKEN": ""})
    assert data["server"]["token"] == "toml"


def test_invalid_port_is_ignored() -> None:
    data = {"server": {"port": 8787}}
    apply_env_overrides(data, {"DASHBOARD_PORT": "pas-un-nombre"})
    assert data["server"]["port"] == 8787


def test_absolute_checklist_path_is_respected(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    absolute = tmp_path / "ailleurs" / "liste.json"
    path.write_text(f'[checklist]\npath = "{absolute.as_posix()}"\n', encoding="utf-8")
    assert load_config(path).checklist_path() == absolute
