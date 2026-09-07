"""Agregateur central : demarre les sources et assemble l'etat complet."""

from __future__ import annotations

import asyncio
import logging
import time

from dashboard_engine.checklist import ChecklistStore
from dashboard_engine.config import Config
from dashboard_engine.models import DashboardState
from dashboard_engine.sources.base import Source
from dashboard_engine.sources.minecraft import build_minecraft_source
from dashboard_engine.sources.music import MusicSource, build_music_source
from dashboard_engine.sources.stream import build_stream_source
from dashboard_engine.sources.weather import build_weather_source

log = logging.getLogger(__name__)


class Hub:
    """Detient les sources, la checklist et l'etat agrege servi par l'API."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.music = build_music_source(config.music)
        self.servers = build_minecraft_source(config.minecraft)
        self.weather = build_weather_source(config.weather)
        self.stream = build_stream_source(config.stream)
        self.checklist = ChecklistStore(config.checklist_path(), config.checklist.default_items)
        self.started_at = time.time()

    @property
    def sources(self) -> list[Source]:
        return [self.music, self.servers, self.weather, self.stream]

    async def start(self) -> None:
        for source in self.sources:
            source.start()
        log.info(
            "moteur demarre — modules actifs: %s",
            ", ".join(s.name for s in self.sources if s.payload.error is None) or "aucun",
        )

    async def stop(self) -> None:
        await asyncio.gather(*(source.stop() for source in self.sources), return_exceptions=True)

    def state(self) -> DashboardState:
        return DashboardState(
            music=self.music.payload,
            servers=self.servers.payload,
            weather=self.weather.payload,
            stream=self.stream.payload,
            checklist=self.checklist.state(),
        )

    def art_bytes(self) -> bytes:
        """Pochette du morceau courant (vide si aucune)."""
        return self.music.art_bytes if isinstance(self.music, MusicSource) else b""


# Champs retires de la projection « slim » servie a l'ESP32. La carte n'a que
# quelques centaines de kio de heap libre une fois LVGL initialise : on evite de
# lui envoyer des previsions et des MOTD qu'elle n'affiche pas.
SLIM_DROP = {
    "music": ("album", "app", "error", "updated_at"),
    "servers": ("error", "updated_at"),
    "weather": ("forecast", "temp_min_c", "temp_max_c", "sunrise", "sunset", "error", "updated_at"),
    "stream": ("error", "updated_at"),
}
SLIM_DROP_SERVER_ITEM = ("motd", "error")


def slim_state(state: DashboardState) -> dict:
    """Version allegee de l'etat, destinee au firmware ESP32."""
    data = state.model_dump()
    for section, fields in SLIM_DROP.items():
        block = data.get(section)
        if isinstance(block, dict):
            for field in fields:
                block.pop(field, None)
    for item in data.get("servers", {}).get("items", []):
        for field in SLIM_DROP_SERVER_ITEM:
            item.pop(field, None)
    return data
