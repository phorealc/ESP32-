"""Tests du client Streamlabs Desktop contre un faux serveur JSON-RPC.

Streamlabs ne tourne que sous Windows et ne peut pas etre lance en CI : on
verifie donc ce qui est verifiable sans lui — le cadrage des messages, le flux
d'authentification, la tolerance aux evenements non sollicites et la
correspondance des champs. Ce qui reste non couvert, ce sont les noms exacts
des services de VOTRE version : `python -m dashboard_engine.diagnose streamlabs`
les affiche.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from dashboard_engine.sources.streamlabs_desktop import (
    StreamlabsDesktopClient,
    StreamlabsError,
    build_state,
)

STREAMING = {"streamingStatus": "live", "recordingStatus": "recording"}
SCENE = {"name": "Ecran principal", "id": "scene_1"}
PERFORMANCE = {"frameRate": 59.94, "percentageDroppedFrames": 0.42, "CPU": 12.5}


class FakeStreamlabs:
    """Serveur TCP minimal parlant le meme dialecte que Streamlabs Desktop."""

    def __init__(self, *, token: str = "", emit_noise: bool = False) -> None:
        self.token = token
        self.emit_noise = emit_noise
        self.requests: list[dict] = []
        self.authenticated = False
        self._server: asyncio.Server | None = None
        self.port = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    def _result(self, request: dict) -> object:
        resource = (request.get("params") or {}).get("resource")
        method = request.get("method")
        if method == "auth":
            args = (request.get("params") or {}).get("args") or []
            self.authenticated = bool(args) and args[0] == self.token
            return self.authenticated
        if self.token and not self.authenticated:
            raise PermissionError("jeton requis")
        if resource == "StreamingService":
            return STREAMING
        if resource == "ScenesService":
            return SCENE
        if resource == "PerformanceService":
            return PERFORMANCE
        raise LookupError(f"service inconnu: {resource}")

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        while True:
            line = await reader.readline()
            if not line:
                break
            request = json.loads(line)
            self.requests.append(request)

            if self.emit_noise:
                # Streamlabs pousse des evenements non sollicites : le client
                # doit les ignorer au lieu de les prendre pour sa reponse.
                writer.write(
                    json.dumps({"jsonrpc": "2.0", "result": {"_type": "EVENT"}}).encode() + b"\n"
                )

            try:
                payload = {"jsonrpc": "2.0", "id": request["id"], "result": self._result(request)}
            except Exception as exc:
                payload = {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "error": {"code": -32600, "message": str(exc)},
                }
            writer.write(json.dumps(payload).encode() + b"\n")
            await writer.drain()


@pytest.fixture
async def server():
    fake = FakeStreamlabs()
    await fake.start()
    yield fake
    await fake.stop()


def client_for(fake: FakeStreamlabs, token: str = "") -> StreamlabsDesktopClient:
    # `use_pipe=False` : le tube nomme n'existe que sous Windows.
    return StreamlabsDesktopClient(token=token, host="127.0.0.1", port=fake.port, use_pipe=False)


# --- protocole ------------------------------------------------------------


async def test_poll_reads_the_three_services(server: FakeStreamlabs) -> None:
    client = client_for(server)
    state = await client.poll()
    await client.close()

    assert state.connected is True
    assert state.kind == "streamlabs"
    assert state.scene == "Ecran principal"
    assert state.streaming is True
    assert state.recording is True
    assert state.fps == pytest.approx(59.9)
    assert state.dropped_frames_pct == pytest.approx(0.42)

    resources = [(r["method"], r["params"]["resource"]) for r in server.requests]
    assert resources == [
        ("getModel", "StreamingService"),
        ("activeScene", "ScenesService"),
        ("getModel", "PerformanceService"),
    ]


async def test_request_ids_are_unique(server: FakeStreamlabs) -> None:
    client = client_for(server)
    await client.poll()
    await client.close()
    ids = [request["id"] for request in server.requests]
    assert len(ids) == len(set(ids))


async def test_unsolicited_events_are_ignored() -> None:
    fake = FakeStreamlabs(emit_noise=True)
    await fake.start()
    try:
        client = client_for(fake)
        state = await client.poll()
        await client.close()
        assert state.scene == "Ecran principal"
    finally:
        await fake.stop()


async def test_token_is_sent_before_any_request() -> None:
    fake = FakeStreamlabs(token="secret")
    await fake.start()
    try:
        client = client_for(fake, token="secret")
        state = await client.poll()
        await client.close()
        assert state.connected is True
        assert fake.requests[0]["method"] == "auth"
        assert fake.requests[0]["params"]["args"] == ["secret"]
    finally:
        await fake.stop()


async def test_wrong_token_reports_disconnected() -> None:
    fake = FakeStreamlabs(token="attendu")
    await fake.start()
    try:
        client = client_for(fake, token="faux")
        state = await client.poll()
        await client.close()
        # Un mauvais jeton ne doit pas faire tomber le moteur : la carte
        # s'affiche simplement comme deconnectee.
        assert state.connected is False
        assert state.kind == "streamlabs"
    finally:
        await fake.stop()


async def test_server_error_raises_streamlabs_error(server: FakeStreamlabs) -> None:
    client = client_for(server)
    with pytest.raises(StreamlabsError):
        await client.request("getModel", "ServiceInexistant")
    await client.close()


async def test_closed_connection_is_reopened(server: FakeStreamlabs) -> None:
    client = client_for(server)
    await client.poll()
    await client.close()
    assert client.connected is False

    state = await client.poll()  # doit se reconnecter tout seul
    await client.close()
    assert state.connected is True


async def test_unreachable_server_is_not_fatal() -> None:
    # Port ferme : `poll` doit renvoyer un etat deconnecte, pas lever.
    client = StreamlabsDesktopClient(host="127.0.0.1", port=1, use_pipe=False)
    state = await client.poll()
    assert state.connected is False


# --- correspondance des champs -------------------------------------------


@pytest.mark.parametrize(
    ("status", "expected"),
    [("live", True), ("starting", True), ("reconnecting", True), ("offline", False), ("", False)],
)
def test_streaming_status_mapping(status: str, expected: bool) -> None:
    # Les phases de transition comptent comme « en direct », sinon l'indicateur
    # clignoterait a chaque reconnexion.
    state = build_state({"streamingStatus": status}, {}, {})
    assert state.streaming is expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [("recording", True), ("starting", True), ("offline", False)],
)
def test_recording_status_mapping(status: str, expected: bool) -> None:
    assert build_state({"recordingStatus": status}, {}, {}).recording is expected


def test_build_state_tolerates_missing_fields() -> None:
    state = build_state({}, {}, {})
    assert state.connected is True
    assert state.scene == ""
    assert state.fps == 0.0


def test_build_state_tolerates_wrong_types() -> None:
    # Une version de Streamlabs qui renverrait autre chose qu'un objet ne doit
    # pas faire planter le moteur.
    state = build_state("inattendu", None, [1, 2, 3])
    assert state.connected is True
    assert state.scene == ""
