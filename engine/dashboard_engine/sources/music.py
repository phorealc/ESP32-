"""Source musique : session media Windows (winsdk / GlobalSystemMediaTransportControls).

Fonctionne avec tout lecteur qui publie une session SMTC : Spotify, Windows
Media Player, YouTube dans Chrome/Firefox/Edge, Deezer, foobar2000...

Le module s'importe sans erreur hors Windows (les tests tournent sous Linux) :
`is_supported()` renvoie alors False et la fabrique retourne une source inactive.
"""

from __future__ import annotations

import logging

from dashboard_engine.config import MusicConfig
from dashboard_engine.models import Music, MusicControls
from dashboard_engine.sources.base import DisabledSource, Source

log = logging.getLogger(__name__)

try:  # pragma: no cover - depend de la plateforme
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as _SessionManager,
    )
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as _PlaybackStatus,
    )
    from winsdk.windows.storage.streams import Buffer, DataReader, InputStreamOptions

    _IMPORT_ERROR: str | None = None
except Exception as exc:  # ImportError sous Linux/macOS, OSError si WinRT absent
    _SessionManager = None  # type: ignore[assignment]
    _PlaybackStatus = None  # type: ignore[assignment]
    Buffer = DataReader = InputStreamOptions = None  # type: ignore[assignment]
    _IMPORT_ERROR = f"winsdk indisponible ({type(exc).__name__}: {exc})"

MAX_ART_BYTES = 4 * 1024 * 1024
"""Garde-fou : une pochette au-dela de 4 Mio est ignoree."""

TICKS_PER_SECOND = 10_000_000
"""WinRT compte les durees en intervalles de 100 ns."""

# Commandes acceptees par `POST /api/music/command`, et le nom de la methode
# SMTC correspondante.
ACTIONS: dict[str, str] = {
    "play": "try_play_async",
    "pause": "try_pause_async",
    "toggle": "try_toggle_play_pause_async",
    "next": "try_skip_next_async",
    "previous": "try_skip_previous_async",
    "stop": "try_stop_async",
    "seek": "try_change_playback_position_async",
}


class MusicUnavailable(RuntimeError):
    """Aucune session media a piloter, ou plateforme non supportee."""


def is_supported() -> bool:
    """True si l'API media Windows est utilisable dans ce processus."""
    return _SessionManager is not None


def unsupported_reason() -> str:
    return _IMPORT_ERROR or ""


async def _read_stream_bytes(thumbnail) -> bytes:  # pragma: no cover - Windows uniquement
    """Lit une `IRandomAccessStreamReference` (pochette) en memoire.

    Les differentes versions de `winsdk` projettent `DataReader.read_bytes`
    tantot avec un tampon en parametre de sortie, tantot avec une taille en
    entree ; on gere les deux plutot que d'epingler une version precise.
    """
    stream = await thumbnail.open_read_async()
    if stream.size == 0 or stream.size > MAX_ART_BYTES:
        return b""
    buffer = Buffer(stream.size)
    await stream.read_async(buffer, buffer.capacity, InputStreamOptions.READ_AHEAD)
    reader = DataReader.from_buffer(buffer)
    try:
        out = bytearray(buffer.length)
        reader.read_bytes(out)
        return bytes(out)
    except TypeError:
        return bytes(reader.read_bytes(buffer.length))


def read_controls(playback) -> MusicControls:
    """Traduit les capacites annoncees par SMTC.

    Les attributs manquants sont traites comme indisponibles : mieux vaut un
    bouton grise a tort qu'un bouton actif qui ne fait rien.
    """
    controls = getattr(playback, "controls", None)
    if controls is None:
        return MusicControls()

    def enabled(name: str) -> bool:
        return bool(getattr(controls, name, False))

    return MusicControls(
        can_play=enabled("is_play_enabled"),
        can_pause=enabled("is_pause_enabled"),
        can_next=enabled("is_next_enabled"),
        can_previous=enabled("is_previous_enabled"),
        can_seek=enabled("is_playback_position_enabled"),
    )


class MusicSource(Source[Music]):
    """Interroge la session media courante de Windows."""

    name = "music"

    def __init__(self, config: MusicConfig) -> None:
        super().__init__(config.interval_s, Music())
        self._manager = None
        self.art_bytes: bytes = b""
        self.art_rev = 0
        self._art_key: tuple[str, str, str] | None = None

    async def _get_manager(self):  # pragma: no cover - Windows uniquement
        if self._manager is None:
            self._manager = await _SessionManager.request_async()
        return self._manager

    async def fetch(self) -> Music:  # pragma: no cover - Windows uniquement
        manager = await self._get_manager()
        session = manager.get_current_session()
        if session is None:
            # Aucun lecteur actif : ce n'est pas une erreur, juste un silence.
            return Music(playing=False, art_rev=self.art_rev)

        props = await session.try_get_media_properties_async()
        playback = session.get_playback_info()
        timeline = session.get_timeline_properties()

        music = Music(
            playing=playback.playback_status == _PlaybackStatus.PLAYING,
            title=props.title or "",
            artist=props.artist or "",
            album=props.album_title or "",
            app=session.source_app_user_model_id or "",
            position_s=timeline.position.total_seconds() if timeline.position else 0.0,
            duration_s=timeline.end_time.total_seconds() if timeline.end_time else 0.0,
        )
        music.controls = read_controls(playback)
        await self._update_art(music, props)
        music.art_rev = self.art_rev
        return music

    async def command(self, action: str, position_s: float = 0.0) -> None:
        """Execute une commande de lecture sur la session courante.

        Leve `MusicUnavailable` si aucun lecteur n'est actif : le lecteur peut
        avoir ete ferme entre l'affichage du bouton et l'appui dessus.
        """
        method_name = ACTIONS.get(action)
        if method_name is None:
            raise ValueError(f"commande inconnue: {action}")

        manager = await self._get_manager()
        session = manager.get_current_session()
        if session is None:
            raise MusicUnavailable("aucun lecteur actif")

        method = getattr(session, method_name)
        if action == "seek":
            await method(int(max(0.0, position_s) * TICKS_PER_SECOND))
        else:
            await method()
        # Le prochain cycle de collecte publiera l'etat reel ; on ne devine pas
        # ici ce que le lecteur a fait de la commande.

    async def _update_art(self, music: Music, props) -> None:  # pragma: no cover
        """Ne relit la pochette que lorsque le morceau change."""
        key = (music.title, music.artist, music.album)
        if key == self._art_key:
            return
        self._art_key = key
        thumbnail = getattr(props, "thumbnail", None)
        if thumbnail is None:
            self.art_bytes = b""
            self.art_rev += 1
            return
        try:
            self.art_bytes = await _read_stream_bytes(thumbnail)
        except Exception as exc:
            log.debug("pochette illisible: %s", exc)
            self.art_bytes = b""
        self.art_rev += 1


def build_music_source(config: MusicConfig) -> Source[Music]:
    """Retourne la source musique, ou une source inactive si indisponible."""
    if not config.enabled:
        return DisabledSource("music", Music(), "module desactive en configuration")
    if not is_supported():
        return DisabledSource("music", Music(), unsupported_reason())
    return MusicSource(config)
