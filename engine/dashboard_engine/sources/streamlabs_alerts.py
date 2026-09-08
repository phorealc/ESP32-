"""Alertes Streamlabs en direct (dons, follows, abonnements) via leur API socket.

Streamlabs diffuse ses alertes en Socket.IO. On implemente ici le strict
necessaire par-dessus `websockets` — deja utilise pour OBS — plutot que de
tirer `python-socketio` : cette bibliotheque code en dur `EIO=4` et ne sait donc
pas parler a un serveur Socket.IO 2.x. Comme la version exacte de Streamlabs
n'est pas garantie, on essaie les deux revisions du protocole.

Le jeton se recupere sur streamlabs.com > Parametres > API Settings >
API Tokens > *Socket API Token*. Il donne acces en lecture aux alertes de la
chaine : traitez-le comme un mot de passe.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time

import websockets

from dashboard_engine.config import StreamlabsAlertsConfig
from dashboard_engine.models import DonationEvent, Donations
from dashboard_engine.sources.base import DisabledSource, Source

log = logging.getLogger(__name__)

SOCKET_HOST = "sockets.streamlabs.com"

# Codes Engine.IO (couche transport).
EIO_OPEN = "0"
EIO_CLOSE = "1"
EIO_PING = "2"
EIO_PONG = "3"
EIO_MESSAGE = "4"

# Codes Socket.IO (couche applicative, a l'interieur d'un message Engine.IO).
SIO_CONNECT = "0"
SIO_EVENT = "2"

# Revisions tentees, dans l'ordre. La 4 est la plus courante aujourd'hui ; la 3
# reste utilisee par les deploiements Socket.IO 2.x.
PROTOCOL_VERSIONS = (4, 3)

CONNECT_TIMEOUT_S = 10.0
DEFAULT_PING_INTERVAL_S = 25.0

# Types d'alertes retenus. Streamlabs en emet d'autres (merch, alertPlaying...)
# qui n'ont pas leur place sur un tableau de bord.
KEPT_TYPES = {"donation", "follow", "subscription", "bits", "host", "raid"}


def socket_url(token: str, version: int) -> str:
    return (
        f"wss://{SOCKET_HOST}/socket.io/?token={token}"
        f"&EIO={version}&transport=websocket"
    )


def _as_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def parse_event(payload: object) -> list[DonationEvent]:
    """Convertit un evenement Streamlabs en alertes internes.

    Streamlabs envoie `{"type": "donation", "message": [ {...}, ... ]}` : le
    champ `message` est toujours une liste, meme pour un evenement unique.
    Fonction pure, donc testable sans le service.
    """
    if not isinstance(payload, dict):
        return []
    kind = str(payload.get("type") or "").lower()
    if kind not in KEPT_TYPES:
        return []

    entries = payload.get("message")
    if isinstance(entries, dict):
        entries = [entries]
    if not isinstance(entries, list):
        return []

    now = time.time()
    events: list[DonationEvent] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        events.append(
            DonationEvent(
                kind=kind,
                name=str(entry.get("name") or entry.get("from") or ""),
                amount=_as_float(entry.get("amount")),
                currency=str(entry.get("currency") or ""),
                message=str(entry.get("message") or ""),
                ts=now,
            )
        )
    return events


def apply_events(state: Donations, events: list[DonationEvent], keep: int) -> Donations:
    """Integre des alertes dans l'etat courant (pure, donc testable).

    Le total ne couvre que la session en cours : l'API socket ne diffuse que le
    direct, elle ne rejoue pas l'historique.
    """
    for event in events:
        if event.kind == "donation":
            state.total = round(state.total + event.amount, 2)
            if event.currency:
                state.currency = event.currency
        elif event.kind == "follow":
            state.last_follower = event.name
        elif event.kind == "subscription":
            state.last_subscriber = event.name
    if events:
        # Les plus recentes en tete, liste bornee.
        state.recent = (events[::-1] + state.recent)[:keep]
    return state


class UnsupportedProtocol(RuntimeError):
    """Le serveur ne parle pas la revision Socket.IO tentee."""


class StreamlabsAlertsSource(Source[Donations]):
    """Ecoute permanente des alertes, avec reconnexion.

    Contrairement aux autres sources, celle-ci ne sonde rien : les evenements
    arrivent quand ils arrivent. La boucle heritee ne sert donc qu'a publier
    l'etat accumule et a refleter la connectivite du socket.
    """

    name = "donations"

    def __init__(self, config: StreamlabsAlertsConfig) -> None:
        super().__init__(5.0, Donations())
        self._config = config
        self._state = Donations()
        self._connected = False
        self._listener: asyncio.Task | None = None
        self._last_error = ""

    # --- cycle de vie -----------------------------------------------------

    def start(self) -> None:
        super().start()
        if self._listener is None:
            self._listener = asyncio.create_task(self._listen_forever(), name="streamlabs-alerts")

    async def stop(self) -> None:
        if self._listener is not None:
            self._listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener
            self._listener = None
        await super().stop()

    async def fetch(self) -> Donations:
        if not self._connected:
            raise RuntimeError(self._last_error or "socket Streamlabs non connecte")
        return self._state.model_copy(deep=True)

    # --- socket -----------------------------------------------------------

    async def _listen_forever(self) -> None:
        """Reconnecte indefiniment : un stream dure des heures, le socket non."""
        delay = 2.0
        while True:
            try:
                await self._listen_once()
                delay = 2.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._connected = False
                self._last_error = f"{type(exc).__name__}: {exc}"
                log.debug("socket Streamlabs: %s", self._last_error)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60.0)

    async def _listen_once(self) -> None:
        last_error: Exception | None = None
        for version in PROTOCOL_VERSIONS:
            try:
                await self._run_session(version)
                return
            except UnsupportedProtocol as exc:
                # Mauvaise revision : on essaie la suivante avant de conclure
                # a une panne. Un serveur peut refuser soit des la poignee de
                # main HTTP, soit en fermant juste apres l'upgrade — les deux
                # arrivent, d'ou une exception dediee plutot qu'une liste de
                # types a rallonge.
                last_error = exc
                log.debug("Streamlabs EIO=%d refuse (%s)", version, exc)
        if last_error is not None:
            raise last_error

    async def _run_session(self, version: int) -> None:
        url = socket_url(self._config.socket_token, version)
        try:
            connection = await websockets.connect(url, open_timeout=CONNECT_TIMEOUT_S)
        except (websockets.InvalidHandshake, OSError) as exc:
            raise UnsupportedProtocol(f"EIO={version} refuse a la connexion: {exc}") from exc

        handshaked = False
        async with connection as socket:
            ping_interval = DEFAULT_PING_INTERVAL_S
            self._last_error = ""

            # En EIO 3 c'est le client qui envoie les pings ; en EIO 4 c'est le
            # serveur, et le client se contente de repondre.
            pinger: asyncio.Task | None = None
            try:
                async for raw in socket:
                    message = raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
                    if not message:
                        continue
                    code, body = message[0], message[1:]

                    if code == EIO_OPEN:
                        handshake = json.loads(body or "{}")
                        ping_interval = float(handshake.get("pingInterval", 25000)) / 1000.0
                        handshaked = True
                        self._connected = True
                        log.info("alertes Streamlabs connectees (EIO=%d)", version)
                        if version == 3 and pinger is None:
                            pinger = asyncio.create_task(self._ping_loop(socket, ping_interval))
                    elif code == EIO_PING:
                        await socket.send(EIO_PONG)
                    elif code == EIO_MESSAGE:
                        self._handle_socketio(body)
                    elif code == EIO_CLOSE:
                        break
            except websockets.ConnectionClosed as exc:
                if not handshaked:
                    raise UnsupportedProtocol(f"EIO={version} ferme aussitot: {exc}") from exc
            finally:
                self._connected = False
                if pinger is not None:
                    pinger.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await pinger

        # Fermeture propre sans jamais avoir recu la trame d'ouverture : le
        # serveur ne parle pas cette revision du protocole.
        if not handshaked:
            raise UnsupportedProtocol(f"EIO={version} n'a pas repondu a la poignee de main")

    async def _ping_loop(self, socket, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            await socket.send(EIO_PING)

    def _handle_socketio(self, body: str) -> None:
        if not body:
            return
        kind, payload = body[0], body[1:]
        if kind == SIO_CONNECT:
            return
        if kind != SIO_EVENT:
            return
        try:
            frame = json.loads(payload)
        except json.JSONDecodeError:
            return
        # Forme attendue : ["event", {...}]
        if not isinstance(frame, list) or len(frame) < 2:
            return
        events = parse_event(frame[1])
        if events:
            apply_events(self._state, events, self._config.keep_events)


def build_alerts_source(config: StreamlabsAlertsConfig) -> Source[Donations]:
    if not config.enabled:
        return DisabledSource("donations", Donations(), "module desactive en configuration")
    if not config.socket_token:
        return DisabledSource(
            "donations", Donations(), "jeton socket Streamlabs manquant"
        )
    return StreamlabsAlertsSource(config)
