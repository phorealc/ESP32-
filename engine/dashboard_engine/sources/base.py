"""Socle commun aux sources de donnees.

Chaque source tourne dans sa propre tache asyncio et rafraichit un payload en
memoire. L'API HTTP ne fait que servir ce cache : une requete de l'ESP32 ne
declenche jamais d'appel reseau sortant, ce qui garde les reponses instantanees
meme quand OpenWeatherMap ou Twitch sont lents.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Generic, TypeVar

from dashboard_engine.models import SourceMeta

log = logging.getLogger(__name__)

T = TypeVar("T", bound=SourceMeta)

MAX_BACKOFF_FACTOR = 8
"""Plafond du recul exponentiel : une source en echec est reinterrogee au pire
toutes les `interval_s * 8` secondes."""


class Source(Generic[T]):
    """Source periodique produisant un payload typé.

    Les sous-classes implementent `fetch()` et retournent le payload a jour.
    Une exception levee par `fetch()` est capturee : le payload precedent est
    conserve et annote d'une erreur, pour que l'ecran affiche la derniere
    valeur connue plutot qu'un vide.
    """

    name: str = "source"

    def __init__(self, interval_s: float, payload: T) -> None:
        self.interval_s = max(0.2, interval_s)
        self.payload: T = payload
        self._task: asyncio.Task | None = None
        self._stopping = asyncio.Event()
        self._failures = 0

    async def fetch(self) -> T:
        """Recupere les donnees. A implementer par les sous-classes."""
        raise NotImplementedError

    async def close(self) -> None:
        """Libere les ressources (clients HTTP, websockets...) si besoin."""

    async def refresh(self) -> None:
        """Execute un cycle de collecte et met a jour le payload."""
        try:
            payload = await self.fetch()
        except Exception as exc:  # une source cassee ne doit pas tuer le moteur
            self._failures += 1
            self.payload.error = f"{type(exc).__name__}: {exc}"
            log.warning("source %s en echec (%d): %s", self.name, self._failures, exc)
            return
        payload.available = True
        payload.error = None
        payload.updated_at = time.time()
        self.payload = payload
        self._failures = 0

    @property
    def _next_delay(self) -> float:
        """Intervalle courant, allonge tant que la source echoue."""
        factor = min(2**self._failures, MAX_BACKOFF_FACTOR)
        return self.interval_s * factor

    async def _loop(self) -> None:
        while not self._stopping.is_set():
            await self.refresh()
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self._next_delay)
            except TimeoutError:
                continue

    def start(self) -> None:
        if self._task is None:
            self._stopping.clear()
            self._task = asyncio.create_task(self._loop(), name=f"source:{self.name}")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self.close()


class DisabledSource(Source[T]):
    """Source inactive : garde le payload par defaut, ne lance aucune tache.

    Utilisee quand un module est desactive en configuration ou qu'il lui manque
    une cle API. L'ESP32 recoit alors `available: false` et affiche un placeholder.
    """

    def __init__(self, name: str, payload: T, reason: str) -> None:
        super().__init__(3600.0, payload)
        self.name = name
        self.payload.error = reason

    def start(self) -> None:  # pas de tache de fond
        return

    async def stop(self) -> None:
        return
