from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from dashboard_engine.config import Config
from dashboard_engine.hub import slim_state
from dashboard_engine.models import API_VERSION, DashboardState, MinecraftServer
from dashboard_engine.server import create_app


def test_health_lists_modules(client: TestClient) -> None:
    payload = client.get("/api/health").json()
    assert payload["ok"] is True
    assert payload["api_version"] == API_VERSION
    assert set(payload["modules"]) == {"music", "servers", "weather", "stream", "donations"}
    assert payload["modules"]["weather"]["available"] is False


def test_state_shape(client: TestClient) -> None:
    payload = client.get("/api/state").json()
    assert payload["version"] == API_VERSION
    assert set(payload) >= {"ts", "music", "servers", "weather", "stream", "donations", "checklist"}
    assert payload["checklist"]["items"][0]["label"] == "Lancer OBS"
    # Le contrat doit rester validable par le modele.
    DashboardState.model_validate(payload)


def test_state_is_not_cached(client: TestClient) -> None:
    assert client.get("/api/state").headers["cache-control"] == "no-store"


def test_slim_state_drops_heavy_fields(client: TestClient) -> None:
    full = client.get("/api/state").json()
    slim = client.get("/api/state", params={"slim": True}).json()

    assert "forecast" in full["weather"] and "forecast" not in slim["weather"]
    assert "album" in full["music"] and "album" not in slim["music"]
    assert "title" in slim["music"]  # l'essentiel reste
    assert slim["checklist"] == full["checklist"]  # la checklist n'est jamais tronquee


def test_slim_state_drops_motd_per_server() -> None:
    state = DashboardState()
    state.servers.items.append(
        MinecraftServer(name="Survie", host="mc.test", motd="Bienvenue", players_online=3)
    )
    item = slim_state(state)["servers"]["items"][0]
    assert "motd" not in item
    assert item["players_online"] == 3


def test_per_module_endpoints(client: TestClient) -> None:
    for path in ("/api/music", "/api/servers", "/api/weather", "/api/stream", "/api/donations"):
        payload = client.get(path).json()
        assert payload["available"] is False
        assert payload["error"]  # explique pourquoi le module est muet


def test_music_art_absent_returns_404(client: TestClient) -> None:
    assert client.get("/api/music/art").status_code == 404


# --- checklist ------------------------------------------------------------


def test_checklist_toggle_round_trip(client: TestClient) -> None:
    initial = client.get("/api/checklist").json()
    item_id = initial["items"][0]["id"]

    toggled = client.post("/api/checklist/toggle", json={"id": item_id}).json()
    assert toggled["items"][0]["done"] is True
    assert toggled["rev"] == initial["rev"] + 1

    # La modification est bien visible dans l'etat global.
    assert client.get("/api/state").json()["checklist"]["items"][0]["done"] is True


def test_checklist_toggle_with_explicit_done_is_idempotent(client: TestClient) -> None:
    item_id = client.get("/api/checklist").json()["items"][0]["id"]
    first = client.post("/api/checklist/toggle", json={"id": item_id, "done": True}).json()
    second = client.post("/api/checklist/toggle", json={"id": item_id, "done": True}).json()
    assert first["rev"] == second["rev"]


def test_checklist_unknown_id_is_404(client: TestClient) -> None:
    response = client.post("/api/checklist/toggle", json={"id": "zzzz"})
    assert response.status_code == 404
    assert "zzzz" in response.json()["detail"]


def test_checklist_crud(client: TestClient) -> None:
    created = client.post("/api/checklist/items", json={"label": "Nouvelle tache"})
    assert created.status_code == 201
    item_id = created.json()["items"][-1]["id"]

    renamed = client.patch(f"/api/checklist/items/{item_id}", json={"label": "Tache renommee"})
    assert renamed.json()["items"][-1]["label"] == "Tache renommee"

    deleted = client.delete(f"/api/checklist/items/{item_id}")
    assert all(item["id"] != item_id for item in deleted.json()["items"])


def test_checklist_rejects_empty_label(client: TestClient) -> None:
    assert client.post("/api/checklist/items", json={"label": ""}).status_code == 422


def test_checklist_reset(client: TestClient) -> None:
    for item in client.get("/api/checklist").json()["items"]:
        client.post("/api/checklist/toggle", json={"id": item["id"], "done": True})
    assert all(not item["done"] for item in client.post("/api/checklist/reset").json()["items"])


def test_checklist_reorder(client: TestClient) -> None:
    ids = [item["id"] for item in client.get("/api/checklist").json()["items"]]
    reordered = client.post("/api/checklist/reorder", json={"ids": list(reversed(ids))}).json()
    assert [item["id"] for item in reordered["items"]] == list(reversed(ids))


# --- jeton partage --------------------------------------------------------


def test_token_is_required_when_configured(config: Config) -> None:
    config.server.token = "secret"
    with TestClient(create_app(config)) as client:
        assert client.get("/api/state").status_code == 401
        assert client.get("/api/state", headers={"X-Dashboard-Token": "secret"}).status_code == 200
        assert client.get("/api/state", params={"token": "secret"}).status_code == 200
        assert client.get("/api/state", params={"token": "faux"}).status_code == 401
        # `/api/health` reste ouvert : c'est la sonde utilisee par la coquille Tauri.
        assert client.get("/api/health").status_code == 200


def test_websocket_pushes_state(client: TestClient) -> None:
    with client.websocket_connect("/ws") as websocket:
        payload = websocket.receive_json()
    assert payload["version"] == API_VERSION
    DashboardState.model_validate(payload)


def test_websocket_rejects_bad_token(config: Config) -> None:
    config.server.token = "secret"
    with TestClient(create_app(config)) as client:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws") as websocket:
                websocket.receive_json()
    # 1008 = violation de politique, le code renvoye par le garde de jeton.
    assert excinfo.value.code == 1008
