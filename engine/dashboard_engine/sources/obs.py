"""Client minimal pour obs-websocket v5 (protocole natif d'OBS >= 28).

On n'utilise qu'une poignee de requetes (statut du stream, de l'enregistrement,
scene courante, stats), donc une implementation directe sur `websockets` evite
une dependance supplementaire.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import uuid

import websockets

from dashboard_engine.config import ObsConfig
from dashboard_engine.models import ObsState

log = logging.getLogger(__name__)

# Codes d'operation du protocole obs-websocket v5.
OP_HELLO = 0
OP_IDENTIFY = 1
OP_IDENTIFIED = 2
OP_REQUEST = 6
OP_REQUEST_RESPONSE = 7

RPC_VERSION = 1
RESPONSE_TIMEOUT_S = 5.0


def compute_auth(password: str, salt: str, challenge: str) -> str:
    """Calcule la chaine d'authentification attendue par obs-websocket v5.

    base64(sha256(base64(sha256(password + salt)) + challenge))
    """
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest()).decode()
    return base64.b64encode(hashlib.sha256((secret + challenge).encode()).digest()).decode()


class ObsClient:
    """Connexion persistante a OBS, reconnectee paresseusement a chaque cycle."""

    def __init__(self, config: ObsConfig) -> None:
        self._config = config
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._ws is not None

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _connect(self) -> None:
        ws = await websockets.connect(self._config.url, open_timeout=RESPONSE_TIMEOUT_S)
        try:
            hello = json.loads(await asyncio.wait_for(ws.recv(), RESPONSE_TIMEOUT_S))
            identify: dict = {"op": OP_IDENTIFY, "d": {"rpcVersion": RPC_VERSION}}
            auth = (hello.get("d") or {}).get("authentication")
            if auth:
                if not self._config.password:
                    raise RuntimeError("OBS exige un mot de passe (voir [stream.obs].password)")
                identify["d"]["authentication"] = compute_auth(
                    self._config.password, auth["salt"], auth["challenge"]
                )
            await ws.send(json.dumps(identify))
            reply = json.loads(await asyncio.wait_for(ws.recv(), RESPONSE_TIMEOUT_S))
            if reply.get("op") != OP_IDENTIFIED:
                raise RuntimeError(f"handshake OBS refuse: {reply}")
        except Exception:
            await ws.close()
            raise
        self._ws = ws

    async def request(self, request_type: str, data: dict | None = None) -> dict:
        """Envoie une requete et renvoie `responseData` (dict vide si sans contenu)."""
        async with self._lock:
            if self._ws is None:
                await self._connect()
            assert self._ws is not None
            request_id = uuid.uuid4().hex
            await self._ws.send(
                json.dumps(
                    {
                        "op": OP_REQUEST,
                        "d": {
                            "requestType": request_type,
                            "requestId": request_id,
                            "requestData": data or {},
                        },
                    }
                )
            )
            # Les evenements diffuses par OBS (op 5) sont ignores : on attend
            # la reponse portant notre requestId.
            while True:
                message = json.loads(await asyncio.wait_for(self._ws.recv(), RESPONSE_TIMEOUT_S))
                payload = message.get("d") or {}
                is_response = message.get("op") == OP_REQUEST_RESPONSE
                if is_response and payload.get("requestId") == request_id:
                    status = payload.get("requestStatus") or {}
                    if not status.get("result", False):
                        raise RuntimeError(f"{request_type}: {status.get('comment', 'echec')}")
                    return payload.get("responseData") or {}

    async def poll(self) -> ObsState:
        """Recupere l'etat d'OBS. Une deconnexion renvoie un etat non connecte."""
        try:
            stream = await self.request("GetStreamStatus")
            record = await self.request("GetRecordStatus")
            scene = await self.request("GetCurrentProgramScene")
            stats = await self.request("GetStats")
        except Exception as exc:
            log.debug("OBS injoignable: %s", exc)
            self._ws = None
            return ObsState(connected=False)

        total = stream.get("outputTotalFrames") or 0
        skipped = stream.get("outputSkippedFrames") or 0
        return ObsState(
            connected=True,
            streaming=bool(stream.get("outputActive")),
            recording=bool(record.get("outputActive")),
            scene=scene.get("currentProgramSceneName") or scene.get("sceneName") or "",
            fps=round(float(stats.get("activeFps", 0.0)), 1),
            dropped_frames_pct=round(100.0 * skipped / total, 2) if total else 0.0,
        )
