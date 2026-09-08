"""Source stream : Twitch (Helix) + etat local d'OBS."""

from __future__ import annotations

import time
from datetime import datetime

import httpx

from dashboard_engine.config import BroadcasterConfig, StreamConfig
from dashboard_engine.models import Stream
from dashboard_engine.sources.base import DisabledSource, Source
from dashboard_engine.sources.obs import ObsClient
from dashboard_engine.sources.streamlabs_desktop import StreamlabsDesktopClient

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
HELIX_URL = "https://api.twitch.tv/helix"

TOKEN_MARGIN_S = 60.0
"""On renouvelle le jeton une minute avant son expiration reelle."""


def parse_started_at(value: str) -> int:
    """Convertit un `started_at` ISO 8601 Twitch en duree de live (secondes)."""
    if not value:
        return 0
    try:
        started = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(0, int(time.time() - started.timestamp()))


class TwitchClient:
    """Client Helix utilisant un jeton applicatif (client credentials).

    Ce type de jeton suffit pour lire l'etat public d'une chaine : statut du
    live, titre, categorie, spectateurs, et le total de followers.
    """

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._client = httpx.AsyncClient(timeout=10.0)
        self._token = ""
        self._token_expiry = 0.0
        self._user_id = ""

    async def close(self) -> None:
        await self._client.aclose()

    async def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expiry:
            return self._token
        response = await self._client.post(
            TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
            },
        )
        response.raise_for_status()
        payload = response.json()
        self._token = payload["access_token"]
        self._token_expiry = time.time() + float(payload.get("expires_in", 3600)) - TOKEN_MARGIN_S
        return self._token

    async def _get(self, path: str, params: dict) -> dict:
        token = await self._ensure_token()
        response = await self._client.get(
            f"{HELIX_URL}{path}",
            params=params,
            headers={"Client-Id": self._client_id, "Authorization": f"Bearer {token}"},
        )
        if response.status_code == 401:
            # Jeton revoque cote Twitch : on force un renouvellement au prochain cycle.
            self._token = ""
        response.raise_for_status()
        return response.json()

    async def user_id(self, login: str) -> str:
        if not self._user_id:
            data = (await self._get("/users", {"login": login})).get("data") or []
            if not data:
                raise RuntimeError(f"chaine Twitch introuvable: {login}")
            self._user_id = data[0]["id"]
        return self._user_id

    async def snapshot(self, login: str) -> Stream:
        """Etat public de la chaine, live ou hors ligne."""
        broadcaster_id = await self.user_id(login)
        stream = Stream()

        live_data = (await self._get("/streams", {"user_login": login})).get("data") or []
        if live_data:
            entry = live_data[0]
            stream.live = entry.get("type") == "live"
            stream.title = entry.get("title") or ""
            stream.game = entry.get("game_name") or ""
            stream.viewers = int(entry.get("viewer_count", 0))
            stream.uptime_s = parse_started_at(entry.get("started_at", ""))
        else:
            # Hors ligne : on affiche quand meme le dernier titre/categorie configures.
            channels = (
                await self._get("/channels", {"broadcaster_id": broadcaster_id})
            ).get("data") or []
            if channels:
                stream.title = channels[0].get("title") or ""
                stream.game = channels[0].get("game_name") or ""

        try:
            followers = await self._get(
                "/channels/followers", {"broadcaster_id": broadcaster_id, "first": 1}
            )
            stream.followers = int(followers.get("total", 0))
        except Exception:
            # Le total de followers depend des scopes du jeton : son absence ne
            # doit pas invalider tout le reste du payload.
            pass
        return stream


class StreamSource(Source[Stream]):
    name = "stream"

    def __init__(self, config: StreamConfig) -> None:
        super().__init__(config.interval_s, Stream())
        self._config = config
        self._twitch: TwitchClient | None = None
        if config.twitch_client_id and config.twitch_client_secret and config.twitch_login:
            self._twitch = TwitchClient(config.twitch_client_id, config.twitch_client_secret)
        self._broadcaster = build_broadcaster_client(config.broadcaster)

    async def fetch(self) -> Stream:
        stream = Stream()
        errors: list[str] = []

        if self._twitch is not None:
            try:
                stream = await self._twitch.snapshot(self._config.twitch_login)
            except Exception as exc:
                errors.append(f"twitch: {type(exc).__name__}")

        if self._broadcaster is not None:
            stream.broadcaster = await self._broadcaster.poll()

        if errors and not stream.broadcaster.connected:
            # Les deux moities sont muettes : on remonte l'echec pour declencher
            # le recul exponentiel du socle.
            raise RuntimeError(", ".join(errors))
        return stream

    async def close(self) -> None:
        if self._twitch is not None:
            await self._twitch.close()
        if self._broadcaster is not None:
            await self._broadcaster.close()


def build_broadcaster_client(config: BroadcasterConfig):
    """Client du logiciel de diffusion, ou `None` si aucun n'est demande."""
    if config.kind == "obs":
        return ObsClient(config)
    if config.kind == "streamlabs":
        return StreamlabsDesktopClient(
            token=config.token,
            host=config.host,
            port=config.port,
            use_pipe=config.use_pipe,
        )
    return None


def build_stream_source(config: StreamConfig) -> Source[Stream]:
    if not config.enabled:
        return DisabledSource("stream", Stream(), "module desactive en configuration")
    has_twitch = bool(
        config.twitch_client_id and config.twitch_client_secret and config.twitch_login
    )
    if not has_twitch and config.broadcaster.kind == "none":
        return DisabledSource(
            "stream", Stream(), "ni identifiants Twitch ni logiciel de diffusion configures"
        )
    return StreamSource(config)
