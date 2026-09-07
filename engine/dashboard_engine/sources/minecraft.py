"""Source serveurs Minecraft (mcstatus, Java et Bedrock)."""

from __future__ import annotations

import asyncio
import logging

from dashboard_engine.config import MinecraftConfig, MinecraftServerConfig
from dashboard_engine.models import MinecraftServer, Servers
from dashboard_engine.sources.base import DisabledSource, Source

log = logging.getLogger(__name__)

MOTD_MAX_CHARS = 80
"""Le MOTD est tronque : l'ecran de l'ESP32 n'affiche qu'une ligne."""


def clean_motd(raw: str) -> str:
    """Aplatit un MOTD multi-lignes et retire les codes couleur `§x`."""
    text = " ".join(raw.split())
    out: list[str] = []
    skip_next = False
    for char in text:
        if skip_next:
            skip_next = False
            continue
        if char == "§":
            skip_next = True
            continue
        out.append(char)
    cleaned = " ".join("".join(out).split())
    if len(cleaned) > MOTD_MAX_CHARS:
        cleaned = cleaned[: MOTD_MAX_CHARS - 1].rstrip() + "…"
    return cleaned


async def _query_java(entry: MinecraftServerConfig, timeout_s: float) -> MinecraftServer:
    from mcstatus import JavaServer

    server = await JavaServer.async_lookup(entry.host, timeout=timeout_s)
    status = await server.async_status()
    motd = status.motd.to_plain() if hasattr(status, "motd") else str(status.description)
    return MinecraftServer(
        name=entry.name,
        host=entry.host,
        online=True,
        players_online=status.players.online,
        players_max=status.players.max,
        version=status.version.name,
        latency_ms=int(status.latency),
        motd=clean_motd(motd),
    )


async def _query_bedrock(entry: MinecraftServerConfig, timeout_s: float) -> MinecraftServer:
    from mcstatus import BedrockServer

    server = BedrockServer.lookup(entry.host, timeout=timeout_s)
    status = await server.async_status()
    motd = status.motd.to_plain() if hasattr(status, "motd") else str(status.description)
    return MinecraftServer(
        name=entry.name,
        host=entry.host,
        online=True,
        players_online=status.players.online,
        players_max=status.players.max,
        version=status.version.name,
        latency_ms=int(status.latency),
        motd=clean_motd(motd),
    )


async def query_server(entry: MinecraftServerConfig, timeout_s: float) -> MinecraftServer:
    """Interroge un serveur ; un serveur eteint renvoie `online=False`, pas une exception."""
    try:
        query = _query_bedrock if entry.bedrock else _query_java
        return await asyncio.wait_for(query(entry, timeout_s), timeout=timeout_s + 2)
    except Exception as exc:
        log.debug("serveur %s injoignable: %s", entry.host, exc)
        return MinecraftServer(
            name=entry.name,
            host=entry.host,
            online=False,
            error=f"{type(exc).__name__}",
        )


class MinecraftSource(Source[Servers]):
    name = "servers"

    def __init__(self, config: MinecraftConfig) -> None:
        super().__init__(config.interval_s, Servers())
        self._config = config

    async def fetch(self) -> Servers:
        results = await asyncio.gather(
            *(query_server(entry, self._config.timeout_s) for entry in self._config.servers)
        )
        return Servers(items=list(results))


def build_minecraft_source(config: MinecraftConfig) -> Source[Servers]:
    if not config.enabled:
        return DisabledSource("servers", Servers(), "module desactive en configuration")
    if not config.servers:
        return DisabledSource(
            "servers", Servers(), "aucun serveur declare dans [[minecraft.servers]]"
        )
    return MinecraftSource(config)
