"""Tests du client d'alertes Streamlabs.

Le service reel demande un jeton de chaine et ne peut pas etre appele en CI.
On verifie donc le protocole (cadrage Engine.IO / Socket.IO, reponse au ping,
bascule de revision) contre un faux serveur, et la correspondance des champs
sur des charges utiles representatives.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import websockets

from dashboard_engine.config import StreamlabsAlertsConfig
from dashboard_engine.models import Donations
from dashboard_engine.sources.base import DisabledSource
from dashboard_engine.sources.streamlabs_alerts import (
    StreamlabsAlertsSource,
    apply_events,
    build_alerts_source,
    parse_event,
    socket_url,
)

DONATION = {
    "type": "donation",
    "message": [
        {"name": "Alice", "amount": "5.00", "currency": "EUR", "message": "Continue !"}
    ],
}
FOLLOW = {"type": "follow", "message": [{"name": "Bob"}]}
SUBSCRIPTION = {"type": "subscription", "message": [{"name": "Carol", "months": 3}]}


# --- correspondance des champs -------------------------------------------


def test_parse_donation() -> None:
    events = parse_event(DONATION)
    assert len(events) == 1
    event = events[0]
    assert event.kind == "donation"
    assert event.name == "Alice"
    assert event.amount == pytest.approx(5.0)
    assert event.currency == "EUR"
    assert event.message == "Continue !"


def test_parse_accepts_a_single_object() -> None:
    # Streamlabs envoie normalement une liste, mais tolerons l'objet seul.
    assert len(parse_event({"type": "follow", "message": {"name": "Bob"}})) == 1


def test_parse_batches_multiple_messages() -> None:
    payload = {"type": "follow", "message": [{"name": "A"}, {"name": "B"}]}
    assert [event.name for event in parse_event(payload)] == ["A", "B"]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"type": "alertPlaying", "message": [{"name": "X"}]},  # type ignore
        {"type": "donation"},  # sans message
        {"type": "donation", "message": "pas une liste"},
        "pas un objet",
        None,
    ],
)
def test_parse_ignores_noise(payload: object) -> None:
    assert parse_event(payload) == []


def test_parse_tolerates_unusable_amount() -> None:
    payload = {"type": "donation", "message": [{"name": "A", "amount": "cinq euros"}]}
    assert parse_event(payload)[0].amount == 0.0


# --- accumulation ---------------------------------------------------------


def test_apply_events_accumulates_total() -> None:
    state = Donations()
    apply_events(state, parse_event(DONATION), keep=8)
    apply_events(state, parse_event(DONATION), keep=8)
    assert state.total == pytest.approx(10.0)
    assert state.currency == "EUR"
    assert len(state.recent) == 2


def test_apply_events_tracks_last_follower_and_subscriber() -> None:
    state = Donations()
    apply_events(state, parse_event(FOLLOW), keep=8)
    apply_events(state, parse_event(SUBSCRIPTION), keep=8)
    assert state.last_follower == "Bob"
    assert state.last_subscriber == "Carol"
    # Un follow n'ajoute rien au total des dons.
    assert state.total == 0.0


def test_recent_is_bounded_and_newest_first() -> None:
    state = Donations()
    for index in range(10):
        payload = {"type": "follow", "message": [{"name": f"n{index}"}]}
        apply_events(state, parse_event(payload), keep=3)
    assert [event.name for event in state.recent] == ["n9", "n8", "n7"]


def test_url_carries_token_and_version() -> None:
    url = socket_url("jeton", 3)
    assert "token=jeton" in url and "EIO=3" in url and url.startswith("wss://")


# --- fabrique -------------------------------------------------------------


def test_disabled_without_token() -> None:
    source = build_alerts_source(StreamlabsAlertsConfig(enabled=True, socket_token=""))
    assert isinstance(source, DisabledSource)
    assert "jeton" in (source.payload.error or "")


def test_disabled_when_module_off() -> None:
    config = StreamlabsAlertsConfig(enabled=False, socket_token="x")
    assert isinstance(build_alerts_source(config), DisabledSource)


# --- protocole contre un faux serveur ------------------------------------


class FakeSocketServer:
    """Serveur Socket.IO minimal : poignee de main, ping, puis un evenement."""

    def __init__(self, *, accept_versions: set[int]) -> None:
        self.accept_versions = accept_versions
        self.pongs = 0
        self.seen_versions: list[int] = []
        self._server = None
        self.port = 0

    async def start(self) -> None:
        self._server = await websockets.serve(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, socket) -> None:
        path = getattr(socket, "request", None)
        target = path.path if path is not None else ""
        version = 4 if "EIO=4" in target else 3
        self.seen_versions.append(version)
        if version not in self.accept_versions:
            await socket.close(code=1002, reason="version refusee")
            return

        await socket.send('0{"sid":"abc","pingInterval":100,"pingTimeout":500}')
        await socket.send("40")
        await socket.send("42" + json.dumps(["event", DONATION]))
        await socket.send("2")  # ping serveur : le client doit repondre « 3 »
        try:
            async for message in socket:
                if message == "3":
                    self.pongs += 1
        except websockets.ConnectionClosed:
            pass


async def drain_source(source: StreamlabsAlertsSource, port: int, predicate) -> None:
    """Pointe la source sur le faux serveur et attend une condition."""
    from dashboard_engine.sources import streamlabs_alerts as module

    original = module.socket_url
    module.socket_url = lambda token, version: (
        f"ws://127.0.0.1:{port}/socket.io/?token={token}&EIO={version}&transport=websocket"
    )
    try:
        source.start()
        for _ in range(100):
            await asyncio.sleep(0.05)
            if predicate():
                return
        raise AssertionError("condition jamais atteinte")
    finally:
        module.socket_url = original
        await source.stop()


async def test_receives_and_accumulates_a_donation() -> None:
    server = FakeSocketServer(accept_versions={4})
    await server.start()
    try:
        source = StreamlabsAlertsSource(StreamlabsAlertsConfig(socket_token="jeton"))
        await drain_source(source, server.port, lambda: source._state.total > 0)
        assert source._state.total == pytest.approx(5.0)
        assert source._state.recent[0].name == "Alice"
    finally:
        await server.stop()


async def test_replies_to_server_ping() -> None:
    server = FakeSocketServer(accept_versions={4})
    await server.start()
    try:
        source = StreamlabsAlertsSource(StreamlabsAlertsConfig(socket_token="jeton"))
        await drain_source(source, server.port, lambda: server.pongs > 0)
        assert server.pongs >= 1
    finally:
        await server.stop()


async def test_falls_back_to_older_protocol() -> None:
    # Un serveur qui refuse EIO=4 doit etre rejoint en EIO=3 sans intervention.
    server = FakeSocketServer(accept_versions={3})
    await server.start()
    try:
        source = StreamlabsAlertsSource(StreamlabsAlertsConfig(socket_token="jeton"))
        await drain_source(source, server.port, lambda: source._state.total > 0)
        assert server.seen_versions[0] == 4  # la 4 est bien tentee en premier
        assert 3 in server.seen_versions
    finally:
        await server.stop()


async def test_fetch_fails_while_disconnected() -> None:
    source = StreamlabsAlertsSource(StreamlabsAlertsConfig(socket_token="jeton"))
    # Sans connexion, `fetch` doit lever pour que le socle marque le module
    # indisponible plutot que de publier un etat vide comme s'il etait valide.
    with pytest.raises(RuntimeError):
        await source.fetch()
