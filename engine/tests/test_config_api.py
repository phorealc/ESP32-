"""Tests de l'ecran de reglages cote moteur.

Le point sensible est le traitement des secrets : ils ne doivent jamais
ressortir en clair, et ouvrir puis enregistrer l'ecran sans y toucher ne doit
pas remplacer une cle par son propre masque.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dashboard_engine.config import Config, load_config
from dashboard_engine.configio import (
    MASK,
    is_masked,
    mask_config,
    mask_secret,
    merge_config,
    write_config,
)
from dashboard_engine.server import create_app

# --- masquage -------------------------------------------------------------


def test_mask_keeps_only_the_tail() -> None:
    masked = mask_secret("c43194a78bcde889cd1594790a1bf43a")
    assert masked == MASK + "f43a"
    assert "c43194" not in masked


def test_mask_short_and_empty_values() -> None:
    assert mask_secret("abc") == MASK  # trop court pour laisser une queue
    assert mask_secret("") == ""


def test_mask_config_covers_every_secret() -> None:
    data = {
        "server": {"token": "jeton-partage-long", "port": 8787},
        "weather": {"api_key": "cle-meteo-secrete", "city": "Paris,FR"},
        "stream": {
            "twitch_client_secret": "secret-twitch-long",
            "twitch_client_id": "identifiant-public",
            "broadcaster": {"password": "mot-de-passe-obs", "kind": "obs"},
            "streamlabs": {"socket_token": "jeton-socket-long"},
        },
    }
    masked = mask_config(data)

    assert masked["server"]["token"].startswith(MASK)
    assert masked["weather"]["api_key"].startswith(MASK)
    assert masked["stream"]["twitch_client_secret"].startswith(MASK)
    assert masked["stream"]["broadcaster"]["password"].startswith(MASK)
    assert masked["stream"]["streamlabs"]["socket_token"].startswith(MASK)

    # Ce qui n'est pas secret reste lisible, sinon l'ecran ne sert a rien.
    assert masked["server"]["port"] == 8787
    assert masked["weather"]["city"] == "Paris,FR"
    assert masked["stream"]["twitch_client_id"] == "identifiant-public"
    # L'original n'est pas modifie au passage.
    assert data["weather"]["api_key"] == "cle-meteo-secrete"


# --- fusion ---------------------------------------------------------------


def test_merge_is_deep_and_partial() -> None:
    current = {"weather": {"api_key": "cle", "city": "Paris,FR", "enabled": True}}
    merged = merge_config(current, {"weather": {"city": "Lyon,FR"}})
    assert merged["weather"] == {"api_key": "cle", "city": "Lyon,FR", "enabled": True}


def test_masked_values_never_overwrite_a_secret() -> None:
    """Ouvrir l'ecran puis enregistrer sans y toucher ne doit rien perdre."""
    current = {"weather": {"api_key": "la-vraie-cle"}}
    merged = merge_config(current, {"weather": {"api_key": MASK + "-cle"}})
    assert merged["weather"]["api_key"] == "la-vraie-cle"


def test_lists_are_replaced_not_merged() -> None:
    # Fusionner element par element rendrait impossible la suppression.
    current = {"minecraft": {"servers": [{"name": "A"}, {"name": "B"}]}}
    merged = merge_config(current, {"minecraft": {"servers": [{"name": "A"}]}})
    assert merged["minecraft"]["servers"] == [{"name": "A"}]


def test_is_masked() -> None:
    assert is_masked(MASK + "1234") is True
    assert is_masked("vraie-valeur") is False
    assert is_masked(8787) is False


# --- ecriture -------------------------------------------------------------


def test_write_then_reload_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    write_config(path, {
        "server": {"port": 9001},
        "weather": {"api_key": "cle", "city": "Lyon,FR"},
        "minecraft": {"servers": [{"name": "Survie", "host": "mc.test", "bedrock": False}]},
    })
    reloaded = load_config(path)
    assert reloaded.server.port == 9001
    assert reloaded.weather.city == "Lyon,FR"
    assert reloaded.minecraft.servers[0].name == "Survie"


def test_write_is_atomic(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    write_config(path, {"server": {"port": 8787}})
    assert not path.with_suffix(".toml.tmp").exists()


def test_write_drops_none_values(tmp_path: Path) -> None:
    # TOML ne sait pas representer `None` ; un `error: null` du modele ferait
    # echouer l'ecriture.
    path = tmp_path / "config.toml"
    write_config(path, {"server": {"port": 8787, "absent": None}})
    assert "absent" not in path.read_text(encoding="utf-8")


# --- endpoints ------------------------------------------------------------


@pytest.fixture
def writable_client(tmp_path: Path):
    """Client dont la configuration est un vrai fichier, modifiable."""
    config = Config()
    config.base_dir = tmp_path
    config.music.enabled = False
    config.minecraft.enabled = False
    config.weather.enabled = False
    config.stream.enabled = False
    config.stream.streamlabs.enabled = False
    # `client=` fait passer les requetes pour locales : sans ca le garde-fou
    # qui protege l'ecriture les refuse, a juste titre.
    with TestClient(create_app(config), client=("127.0.0.1", 50000)) as client:
        yield client, tmp_path


def test_get_config_exposes_editable_sections(writable_client) -> None:
    client, _ = writable_client
    payload = client.get("/api/config").json()
    assert {"server", "music", "minecraft", "weather", "stream"} <= set(payload)
    assert payload["_meta"]["path"].endswith("config.toml")


def test_get_config_never_leaks_a_secret(writable_client) -> None:
    client, _ = writable_client
    client.patch("/api/config", json={"weather": {"api_key": "cle-tres-secrete-1234"}})
    body = client.get("/api/config").text
    assert "cle-tres-secrete" not in body
    assert MASK in body


def test_patch_writes_and_applies(writable_client) -> None:
    client, tmp_path = writable_client
    response = client.patch(
        "/api/config",
        json={"weather": {"enabled": True, "api_key": "ma-cle-meteo", "city": "Lyon,FR"}},
    )
    assert response.status_code == 200
    assert response.json()["weather"]["city"] == "Lyon,FR"

    # Ecrit sur le disque...
    assert "Lyon,FR" in (tmp_path / "config.toml").read_text(encoding="utf-8")
    # ...et applique a chaud : le module meteo n'est plus « desactive ».
    modules = client.get("/api/health").json()["modules"]
    assert "desactive" not in (modules["weather"]["error"] or "")


def test_patch_can_add_servers(writable_client) -> None:
    client, _ = writable_client
    body = {
        "minecraft": {
            "enabled": True,
            "servers": [{"name": "Survie", "host": "mc.test", "bedrock": False}],
        }
    }
    payload = client.patch("/api/config", json=body).json()
    assert payload["minecraft"]["servers"][0]["name"] == "Survie"


def test_patch_rejects_unknown_sections(writable_client) -> None:
    client, _ = writable_client
    response = client.patch("/api/config", json={"checklist": {"path": "/ailleurs"}})
    assert response.status_code == 400
    assert "checklist" in response.json()["detail"]


def test_patch_rejects_invalid_values_before_writing(writable_client) -> None:
    client, tmp_path = writable_client
    before = (tmp_path / "config.toml").exists()
    response = client.patch("/api/config", json={"server": {"port": "pas-un-nombre"}})
    assert response.status_code == 422
    # Un fichier invalide empecherait le moteur de redemarrer : rien ne doit
    # avoir ete ecrit.
    assert (tmp_path / "config.toml").exists() == before


def test_patch_preserves_untouched_secrets(writable_client) -> None:
    client, _ = writable_client
    client.patch("/api/config", json={"weather": {"api_key": "cle-originale-9999"}})

    # L'interface renvoie ce qu'elle a recu, masque compris.
    masked = client.get("/api/config").json()
    client.patch("/api/config", json={"weather": {"api_key": masked["weather"]["api_key"]}})

    assert client.get("/api/config").json()["weather"]["api_key"] == MASK + "9999"


def test_config_requires_the_token(tmp_path: Path) -> None:
    config = Config()
    config.base_dir = tmp_path
    config.server.token = "secret"
    with TestClient(create_app(config)) as client:
        assert client.get("/api/config").status_code == 401
        headers = {"X-Dashboard-Token": "secret"}
        assert client.get("/api/config", headers=headers).status_code == 200


def test_writes_from_another_machine_are_refused(tmp_path: Path) -> None:
    """Le moteur ecoute sur tout le reseau pour l'ESP32.

    Un autre appareil pourrait sinon reecrire la configuration — et notamment
    le jeton partage. La lecture reste permise : elle ne revele aucun secret.
    """
    config = Config()
    config.base_dir = tmp_path
    with TestClient(create_app(config), client=("192.168.1.42", 50000)) as client:
        assert client.get("/api/config").status_code == 200
        response = client.patch("/api/config", json={"weather": {"city": "Lyon,FR"}})
        assert response.status_code == 403
        assert "PC qui heberge" in response.json()["detail"]
