"""Tests du pilotage de la lecture.

L'API media de Windows n'existe pas sur les runners Linux : on couvre donc ce
qui l'est — validation des commandes, correspondance des capacites, codes
d'erreur — avec une session SMTC simulee pour verifier que chaque action
appelle bien la methode correspondante.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dashboard_engine.config import Config, MusicConfig
from dashboard_engine.models import MusicControls
from dashboard_engine.server import create_app
from dashboard_engine.sources.music import (
    ACTIONS,
    TICKS_PER_SECOND,
    MusicSource,
    MusicUnavailable,
    read_controls,
)

# --- capacites annoncees par le lecteur ----------------------------------


class FakeControls:
    def __init__(self, **flags: bool) -> None:
        self.is_play_enabled = flags.get("play", False)
        self.is_pause_enabled = flags.get("pause", False)
        self.is_next_enabled = flags.get("next", False)
        self.is_previous_enabled = flags.get("previous", False)
        self.is_playback_position_enabled = flags.get("seek", False)


class FakePlayback:
    def __init__(self, controls: object) -> None:
        self.controls = controls


def test_read_controls_maps_every_flag() -> None:
    every = FakeControls(play=True, pause=True, next=True, previous=True, seek=True)
    playback = FakePlayback(every)
    assert read_controls(playback) == MusicControls(
        can_play=True, can_pause=True, can_next=True, can_previous=True, can_seek=True
    )


def test_read_controls_reflects_a_limited_player() -> None:
    # Cas typique de YouTube dans un navigateur : lecture/pause seulement.
    controls = read_controls(FakePlayback(FakeControls(play=True, pause=True)))
    assert controls.can_pause is True
    assert controls.can_next is False
    assert controls.can_seek is False


def test_read_controls_without_controls_object() -> None:
    assert read_controls(FakePlayback(None)) == MusicControls()
    assert read_controls(object()) == MusicControls()


def test_missing_attributes_default_to_disabled() -> None:
    """Un bouton grise a tort vaut mieux qu'un bouton qui ne fait rien."""

    class Partial:
        is_play_enabled = True  # les autres attributs manquent

    controls = read_controls(FakePlayback(Partial()))
    assert controls.can_play is True
    assert controls.can_next is False


# --- dispatch des commandes ----------------------------------------------


class FakeSession:
    """Session SMTC simulee : enregistre les appels au lieu de les executer."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    def __getattr__(self, name: str):
        if not name.startswith("try_"):
            raise AttributeError(name)

        async def recorder(*args):
            self.calls.append((name, args))

        return recorder


class FakeManager:
    def __init__(self, session: FakeSession | None) -> None:
        self._session = session

    def get_current_session(self) -> FakeSession | None:
        return self._session


def source_with(session: FakeSession | None) -> MusicSource:
    source = MusicSource(MusicConfig())
    source._manager = FakeManager(session)
    return source


@pytest.mark.parametrize(("action", "method"), sorted(ACTIONS.items()))
async def test_each_action_calls_its_smtc_method(action: str, method: str) -> None:
    session = FakeSession()
    await source_with(session).command(action, position_s=12.0)
    assert session.calls[0][0] == method


async def test_seek_converts_seconds_to_ticks() -> None:
    session = FakeSession()
    await source_with(session).command("seek", position_s=90.0)
    name, args = session.calls[0]
    assert name == "try_change_playback_position_async"
    assert args == (90 * TICKS_PER_SECOND,)


async def test_seek_clamps_negative_position() -> None:
    session = FakeSession()
    await source_with(session).command("seek", position_s=-5.0)
    assert session.calls[0][1] == (0,)


async def test_non_seek_actions_take_no_argument() -> None:
    session = FakeSession()
    await source_with(session).command("next", position_s=42.0)
    assert session.calls[0][1] == ()


async def test_unknown_action_is_rejected() -> None:
    with pytest.raises(ValueError):
        await source_with(FakeSession()).command("autodestruction")


async def test_command_without_player_raises() -> None:
    # Le lecteur peut avoir ete ferme entre l'affichage du bouton et l'appui.
    with pytest.raises(MusicUnavailable):
        await source_with(None).command("next")


# --- endpoint HTTP --------------------------------------------------------


def test_command_on_disabled_module_is_503(client: TestClient) -> None:
    response = client.post("/api/music/command", json={"action": "next"})
    assert response.status_code == 503
    assert "desactive" in response.json()["detail"]


def test_unknown_action_is_rejected_by_validation(client: TestClient) -> None:
    assert client.post("/api/music/command", json={"action": "danser"}).status_code == 422


def test_negative_seek_is_rejected_by_validation(client: TestClient) -> None:
    body = {"action": "seek", "position_s": -1}
    assert client.post("/api/music/command", json=body).status_code == 422


def test_command_requires_the_token_when_configured(config: Config) -> None:
    config.server.token = "secret"
    with TestClient(create_app(config)) as client:
        body = {"action": "next"}
        assert client.post("/api/music/command", json=body).status_code == 401
        assert client.post(
            "/api/music/command", json=body, headers={"X-Dashboard-Token": "secret"}
        ).status_code == 503  # authentifie, mais module desactive dans ce test


def test_controls_are_exposed_in_state(client: TestClient) -> None:
    controls = client.get("/api/state").json()["music"]["controls"]
    assert set(controls) == {"can_play", "can_pause", "can_next", "can_previous", "can_seek"}


def test_controls_survive_the_slim_projection(client: TestClient) -> None:
    # L'ESP32 doit savoir quels boutons afficher : les capacites ne sont pas
    # de la decoration, elles ne peuvent pas etre elaguees.
    slim = client.get("/api/state", params={"slim": True}).json()
    assert "controls" in slim["music"]
