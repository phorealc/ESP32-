"""Client pour l'API de Streamlabs Desktop (ex-Streamlabs OBS).

Streamlabs Desktop ne parle pas obs-websocket : il expose sa propre API
JSON-RPC 2.0, en messages termines par un saut de ligne, sur deux transports :

- un **tube nomme** `\\\\.\\pipe\\slobs` sous Windows — disponible sans reglage ;
- **TCP** sur 127.0.0.1:59650 — a activer dans *Parametres > Remote Control*,
  et protege par un jeton.

Le tube nomme est prefere quand il existe : rien a configurer pour
l'utilisateur. Le TCP sert de repli, et permet aussi de viser une autre machine.

⚠ Les noms de services et de champs ci-dessous suivent l'API publique de
Streamlabs Desktop, mais elle evolue d'une version a l'autre et n'est pas
versionnee. En cas de doute, `python -m dashboard_engine.diagnose streamlabs`
affiche les reponses brutes de VOTRE installation : c'est la reference.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

from dashboard_engine.models import BroadcasterState

log = logging.getLogger(__name__)

PIPE_PATH = r"\\.\pipe\slobs"
DEFAULT_TCP_HOST = "127.0.0.1"
DEFAULT_TCP_PORT = 59650

REQUEST_TIMEOUT_S = 5.0
MAX_LINE_BYTES = 1_000_000
"""Garde-fou : une reponse d'un mega-octet signale un flux qui a deraille."""

# Statuts consideres comme « en cours ». Streamlabs distingue les phases de
# transition (`starting`, `ending`, `reconnecting`) que l'on veut afficher
# comme actives, sinon l'indicateur clignote a chaque changement de scene.
STREAMING_ACTIVE = {"live", "starting", "reconnecting"}
RECORDING_ACTIVE = {"recording", "starting"}


class StreamlabsError(RuntimeError):
    """Erreur de protocole ou d'authentification cote Streamlabs."""


class StreamlabsDesktopClient:
    """Connexion JSON-RPC a Streamlabs Desktop, rouverte a la demande."""

    def __init__(
        self,
        token: str = "",
        host: str = DEFAULT_TCP_HOST,
        port: int = DEFAULT_TCP_PORT,
        use_pipe: bool = True,
    ) -> None:
        self._token = token
        self._host = host
        self._port = port
        self._use_pipe = use_pipe
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._next_id = 0
        self._lock = asyncio.Lock()
        self.transport = ""
        """`pipe` ou `tcp` — utile au diagnostic."""

    # --- connexion -------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._writer is not None

    async def close(self) -> None:
        writer, self._writer, self._reader = self._writer, None, None
        if writer is not None:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, asyncio.CancelledError):
                pass

    async def _open_pipe(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        """Ouvre le tube nomme Windows.

        `asyncio` n'expose pas les tubes nommes directement : on ouvre le
        fichier en binaire et on l'enveloppe dans les flux asyncio.
        """
        loop = asyncio.get_running_loop()
        handle = await loop.run_in_executor(None, lambda: open(PIPE_PATH, "r+b", buffering=0))
        reader = asyncio.StreamReader(limit=MAX_LINE_BYTES)
        protocol = asyncio.StreamReaderProtocol(reader)
        transport, _ = await loop.connect_read_pipe(lambda: protocol, handle)
        write_transport, write_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, handle
        )
        writer = asyncio.StreamWriter(write_transport, write_protocol, reader, loop)
        _ = transport
        return reader, writer

    async def _connect(self) -> None:
        if self._use_pipe and sys.platform == "win32":
            try:
                self._reader, self._writer = await self._open_pipe()
                self.transport = "pipe"
                return
            except OSError as exc:
                # Streamlabs ferme, ou trop ancien pour exposer le tube :
                # on tente le TCP, qui peut etre active manuellement.
                log.debug("tube nomme indisponible (%s), essai en TCP", exc)

        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port), timeout=REQUEST_TIMEOUT_S
        )
        self.transport = "tcp"
        if self._token:
            await self._request("auth", "TcpServerService", [self._token])
        # Sans jeton, Streamlabs refuse la premiere requete metier : on laisse
        # l'erreur remonter telle quelle, elle est explicite.

    # --- protocole -------------------------------------------------------

    async def _request(self, method: str, resource: str, args: list | None = None) -> object:
        if self._writer is None or self._reader is None:
            raise StreamlabsError("non connecte")

        self._next_id += 1
        request_id = self._next_id
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": {"resource": resource, "args": args or []},
        }
        self._writer.write(json.dumps(payload).encode() + b"\n")
        await self._writer.drain()

        # Streamlabs pousse aussi des evenements non sollicites : on lit
        # jusqu'a retrouver la reponse portant notre identifiant.
        while True:
            line = await asyncio.wait_for(self._reader.readline(), timeout=REQUEST_TIMEOUT_S)
            if not line:
                raise StreamlabsError("connexion fermee par Streamlabs")
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise StreamlabsError(f"reponse illisible: {exc}") from exc
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message["error"]
                raise StreamlabsError(str(error.get("message") or error))
            return message.get("result")

    async def request(self, method: str, resource: str, args: list | None = None) -> object:
        """Requete unitaire, en (re)ouvrant la connexion si besoin."""
        async with self._lock:
            if self._writer is None:
                await self._connect()
            try:
                return await self._request(method, resource, args)
            except (TimeoutError, StreamlabsError, OSError):
                await self.close()
                raise

    # --- lecture de l'etat ------------------------------------------------

    async def poll(self) -> BroadcasterState:
        """Etat courant. Une deconnexion renvoie un etat non connecte."""
        try:
            streaming = await self.request("getModel", "StreamingService")
            scene = await self.request("activeScene", "ScenesService")
            performance = await self.request("getModel", "PerformanceService")
        except Exception as exc:
            log.debug("Streamlabs Desktop injoignable: %s", exc)
            return BroadcasterState(kind="streamlabs", connected=False)

        return build_state(streaming, scene, performance)


def build_state(streaming: object, scene: object, performance: object) -> BroadcasterState:
    """Assemble l'etat a partir des trois reponses brutes.

    Fonction pure : c'est elle qui porte la correspondance entre les champs de
    Streamlabs et notre modele, donc c'est elle qu'on teste.
    """
    streaming = streaming if isinstance(streaming, dict) else {}
    scene = scene if isinstance(scene, dict) else {}
    performance = performance if isinstance(performance, dict) else {}

    return BroadcasterState(
        kind="streamlabs",
        connected=True,
        streaming=str(streaming.get("streamingStatus", "")).lower() in STREAMING_ACTIVE,
        recording=str(streaming.get("recordingStatus", "")).lower() in RECORDING_ACTIVE,
        scene=str(scene.get("name") or ""),
        fps=round(float(performance.get("frameRate") or 0.0), 1),
        dropped_frames_pct=round(float(performance.get("percentageDroppedFrames") or 0.0), 2),
    )
