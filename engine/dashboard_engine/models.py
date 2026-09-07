"""Modeles de donnees exposes par l'API.

Ces modeles constituent le contrat partage entre le moteur Python, le firmware
ESP32 et la coquille Tauri. Toute modification ici doit etre repercutee dans
`docs/api.md` ainsi que dans le parseur JSON du firmware.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

API_VERSION = 1


class SourceMeta(BaseModel):
    """Etat technique d'une source (commun a tous les modules)."""

    available: bool = False
    """False tant qu'aucune donnee exploitable n'a ete recuperee."""

    error: str | None = None
    """Derniere erreur rencontree, `None` si la derniere collecte a reussi."""

    updated_at: float = 0.0
    """Horodatage epoch de la derniere collecte reussie."""


class Music(SourceMeta):
    playing: bool = False
    title: str = ""
    artist: str = ""
    album: str = ""
    app: str = ""
    """Application source (Spotify, firefox.exe, ...)."""

    position_s: float = 0.0
    duration_s: float = 0.0
    art_rev: int = 0
    """Incremente a chaque nouvelle pochette. 0 = pas de pochette disponible.

    La pochette elle-meme se recupere sur `/api/music/art` (l'ESP32 n'a pas
    assez de RAM pour du base64 dans le payload principal).
    """


class MinecraftServer(BaseModel):
    name: str
    host: str
    online: bool = False
    players_online: int = 0
    players_max: int = 0
    version: str = ""
    latency_ms: int = 0
    motd: str = ""
    error: str | None = None


class Servers(SourceMeta):
    items: list[MinecraftServer] = Field(default_factory=list)

    @property
    def total_players(self) -> int:
        return sum(s.players_online for s in self.items if s.online)


class ForecastPoint(BaseModel):
    ts: int
    temp_c: float
    icon: str = ""


class Weather(SourceMeta):
    city: str = ""
    temp_c: float = 0.0
    feels_like_c: float = 0.0
    temp_min_c: float = 0.0
    temp_max_c: float = 0.0
    description: str = ""
    icon: str = ""
    """Code icone OpenWeatherMap (`01d`, `10n`, ...)."""

    humidity: int = 0
    wind_kph: float = 0.0
    sunrise: int = 0
    sunset: int = 0
    forecast: list[ForecastPoint] = Field(default_factory=list)


class ObsState(BaseModel):
    connected: bool = False
    streaming: bool = False
    recording: bool = False
    scene: str = ""
    fps: float = 0.0
    dropped_frames_pct: float = 0.0


class Stream(SourceMeta):
    live: bool = False
    title: str = ""
    game: str = ""
    viewers: int = 0
    followers: int = 0
    uptime_s: int = 0
    obs: ObsState = Field(default_factory=ObsState)


class ChecklistItem(BaseModel):
    id: str
    label: str
    done: bool = False
    order: int = 0


class Checklist(BaseModel):
    rev: int = 0
    """Incremente a chaque modification. Permet a l'ESP32 de detecter un
    changement venu du PC sans comparer toute la liste."""

    items: list[ChecklistItem] = Field(default_factory=list)


class DashboardState(BaseModel):
    """Payload complet renvoye par `GET /api/state`."""

    version: int = API_VERSION
    ts: float = Field(default_factory=time.time)
    music: Music = Field(default_factory=Music)
    servers: Servers = Field(default_factory=Servers)
    weather: Weather = Field(default_factory=Weather)
    stream: Stream = Field(default_factory=Stream)
    checklist: Checklist = Field(default_factory=Checklist)
