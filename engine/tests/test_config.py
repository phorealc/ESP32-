from __future__ import annotations

from pathlib import Path

import pytest

from dashboard_engine import config as config_module
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


# --- emplacement de la configuration pour l'application installee ----------


def test_user_config_dir_per_platform(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(config_module.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    assert config_module.user_config_dir() == tmp_path / "Roaming/Phorealc/Dashboard"

    monkeypatch.setattr(config_module.sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert config_module.user_config_dir() == tmp_path / "cfg/phorealc-dashboard"


def test_local_config_wins_over_user_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Un config.toml dans le repertoire courant l'emporte : c'est le mode dev."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "ailleurs"))

    # Sans fichier local, on vise le dossier utilisateur.
    assert config_module.default_config_path().parent == tmp_path / "ailleurs/phorealc-dashboard"

    (tmp_path / "config.toml").write_text("", encoding="utf-8")
    assert config_module.default_config_path() == tmp_path / "config.toml"


def test_ensure_config_file_creates_from_template(tmp_path: Path) -> None:
    target = tmp_path / "nouveau" / "config.toml"

    assert config_module.ensure_config_file(target) is True
    assert target.is_file()
    # Le modele doit rester un TOML valide et chargeable tel quel.
    loaded = load_config(target)
    assert loaded.server.port == 8787
    assert loaded.checklist.default_items

    # Idempotent : un second appel n'ecrase pas la configuration de l'utilisateur.
    target.write_text("[server]\nport = 9999\n", encoding="utf-8")
    assert config_module.ensure_config_file(target) is False
    assert load_config(target).server.port == 9999


def test_template_ships_with_the_package() -> None:
    """Le modele doit etre installe avec le paquet, pas seulement present en source."""
    assert config_module.template_path().is_file()


def test_base_dir_follows_config_even_when_absent(tmp_path: Path) -> None:
    """La checklist se range a cote du config.toml, meme s'il n'existe pas encore."""
    missing = tmp_path / "profil" / "config.toml"
    assert load_config(missing).checklist_path() == tmp_path / "profil" / "checklist.json"
