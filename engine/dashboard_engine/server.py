"""Serveur HTTP local (FastAPI) servant l'etat agrege.

Consommateurs : le firmware ESP32 (polling HTTP) et la coquille Tauri
(websocket `/ws`, ou polling en repli).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ValidationError
from starlette.websockets import WebSocketDisconnect

from dashboard_engine.config import DEFAULT_CONFIG_NAME, Config, load_config
from dashboard_engine.configio import (
    EDITABLE_SECTIONS,
    editable_view,
    mask_config,
    merge_config,
    write_config,
)
from dashboard_engine.hub import Hub, slim_state
from dashboard_engine.models import API_VERSION, Checklist
from dashboard_engine.sources.music import MusicSource, MusicUnavailable

log = logging.getLogger(__name__)

WS_PUSH_INTERVAL_S = 0.5
"""Cadence de diffusion sur le websocket : assez fine pour une barre de
progression fluide, assez lente pour rester negligeable en CPU."""

TOKEN_HEADER = "X-Dashboard-Token"

LOCAL_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
"""Le moteur ecoute sur tout le reseau local pour que l'ESP32 le joigne. Ecrire
la configuration depuis un autre appareil n'a en revanche aucune raison d'etre,
et permettrait de changer le jeton partage."""


# --- corps de requetes ----------------------------------------------------


class ToggleRequest(BaseModel):
    id: str
    done: bool | None = None
    """`None` = bascule l'etat courant ; sinon force la valeur (idempotent)."""


class MusicCommandRequest(BaseModel):
    action: Literal["play", "pause", "toggle", "next", "previous", "stop", "seek"]
    position_s: float = Field(default=0.0, ge=0)
    """Position visee, en secondes. Utilise seulement par `seek`."""


class AddItemRequest(BaseModel):
    label: str = Field(min_length=1, max_length=120)


class UpdateItemRequest(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    done: bool | None = None


class ReorderRequest(BaseModel):
    ids: list[str]


# --- application ----------------------------------------------------------


def create_app(config: Config | None = None) -> FastAPI:
    config = config or load_config()
    hub = Hub(config)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await hub.start()
        try:
            yield
        finally:
            await hub.stop()

    app = FastAPI(
        title="Dashboard Engine",
        version=str(API_VERSION),
        description="Moteur d'agregation du Dashboard ESP32 (Phorealc)",
        lifespan=lifespan,
    )
    app.state.hub = hub
    app.state.config = config

    def current_config_path() -> Path:
        """Fichier ou ecrire. La checklist vit a cote, donc son dossier fait foi.

        Le chemin est resolu : l'ecran de reglages l'affiche pour que
        l'utilisateur retrouve le fichier, un chemin relatif n'y aiderait pas.
        """
        return (hub.config.base_dir / DEFAULT_CONFIG_NAME).resolve()

    if config.server.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.server.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def require_token(request: Request) -> None:
        """Verifie le jeton partage, si la configuration en definit un.

        Le jeton protege surtout contre un autre appareil du reseau local qui
        modifierait la checklist ; ce n'est pas un mecanisme d'authentification.
        """
        expected = config.server.token
        if not expected:
            return
        provided = request.headers.get(TOKEN_HEADER) or request.query_params.get("token")
        if provided != expected:
            raise HTTPException(status_code=401, detail="jeton invalide ou manquant")

    guard = Depends(require_token)

    # --- lecture ----------------------------------------------------------

    @app.get("/", include_in_schema=False)
    async def index() -> dict:
        return {
            "name": "dashboard-engine",
            "api_version": API_VERSION,
            "endpoints": ["/api/state", "/api/music", "/api/servers", "/api/weather",
                          "/api/stream", "/api/donations",
                          "/api/checklist", "/ws"],
        }

    @app.get("/api/health")
    async def health() -> dict:
        return {
            "ok": True,
            "api_version": API_VERSION,
            "uptime_s": round(time.time() - hub.started_at, 1),
            "modules": {
                source.name: {
                    "available": source.payload.available,
                    "error": source.payload.error,
                }
                for source in hub.sources
            },
        }

    @app.get("/api/state", dependencies=[guard])
    async def get_state(
        slim: bool = Query(False, description="Projection allegee pour l'ESP32"),
    ) -> Response:
        state = hub.state()
        payload = slim_state(state) if slim else state.model_dump()
        return JSONResponse(payload, headers={"Cache-Control": "no-store"})

    @app.get("/api/music", dependencies=[guard])
    async def get_music() -> dict:
        return hub.music.payload.model_dump()

    @app.post("/api/music/command", dependencies=[guard])
    async def music_command(body: MusicCommandRequest) -> dict:
        """Pilote le lecteur du PC depuis l'ESP32 ou la coquille.

        Les codes d'erreur distinguent les trois causes possibles, qui
        appellent des reactions differentes cote client : module indisponible,
        aucun lecteur actif, ou refus du lecteur.
        """
        source = hub.music
        if not isinstance(source, MusicSource):
            raise HTTPException(
                status_code=503,
                detail=source.payload.error or "module musique indisponible",
            )
        try:
            await source.command(body.action, body.position_s)
        except MusicUnavailable as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except Exception as exc:
            log.warning("commande musique %s refusee: %s", body.action, exc)
            raise HTTPException(
                status_code=502, detail=f"le lecteur a refuse la commande: {exc}"
            ) from None
        return {"ok": True, "action": body.action}

    @app.get("/api/music/art", dependencies=[guard])
    async def get_music_art() -> Response:
        art = hub.art_bytes()
        if not art:
            raise HTTPException(status_code=404, detail="pas de pochette pour ce morceau")
        # Les pochettes SMTC sont des JPEG ou des PNG ; on laisse le client
        # renifler le format a partir des magic bytes plutot que de mentir.
        media_type = "image/png" if art[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
        return Response(art, media_type=media_type, headers={"Cache-Control": "no-store"})

    @app.get("/api/servers", dependencies=[guard])
    async def get_servers() -> dict:
        return hub.servers.payload.model_dump()

    @app.get("/api/weather", dependencies=[guard])
    async def get_weather() -> dict:
        return hub.weather.payload.model_dump()

    @app.get("/api/stream", dependencies=[guard])
    async def get_stream() -> dict:
        return hub.stream.payload.model_dump()

    @app.get("/api/donations", dependencies=[guard])
    async def get_donations() -> dict:
        return hub.donations.payload.model_dump()

    # --- configuration ----------------------------------------------------

    def require_local(request: Request) -> None:
        """Refuse les ecritures venues d'ailleurs que de cette machine."""
        host = request.client.host if request.client else ""
        if host not in LOCAL_HOSTS:
            raise HTTPException(
                status_code=403,
                detail="la configuration ne se modifie que depuis le PC qui heberge le moteur",
            )

    @app.get("/api/config", dependencies=[guard])
    async def get_config() -> dict:
        """Configuration modifiable, secrets masques.

        Les valeurs masquees permettent a l'interface de montrer qu'une cle est
        en place sans jamais la reveler — y compris a un appareil du reseau.
        """
        data = mask_config(editable_view(hub.config.model_dump(mode="json")))
        path = current_config_path()
        return {
            **data,
            "_meta": {
                "path": str(path),
                "exists": path.is_file(),
                "checklist_path": str(hub.config.checklist_path()),
            },
        }

    @app.patch("/api/config", dependencies=[guard, Depends(require_local)])
    async def patch_config(patch: dict) -> dict:
        """Enregistre des reglages et les applique sans redemarrer.

        Le corps est un fragment : seules les cles fournies sont modifiees, et
        une valeur masquee laisse le secret existant en place.
        """
        unknown = set(patch) - set(EDITABLE_SECTIONS)
        if unknown:
            raise HTTPException(
                status_code=400, detail=f"sections non modifiables: {', '.join(sorted(unknown))}"
            )

        merged = merge_config(hub.config.model_dump(mode="json"), patch)
        try:
            new_config = Config.model_validate(merged)
        except ValidationError as exc:
            # On refuse avant d'ecrire : un fichier invalide empecherait le
            # moteur de redemarrer, et l'ecran de reglages avec lui.
            raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from None

        path = current_config_path()
        new_config.base_dir = path.parent
        try:
            write_config(path, merged)
        except OSError as exc:
            raise HTTPException(
                status_code=500, detail=f"ecriture impossible dans {path}: {exc}"
            ) from None

        await hub.reload(new_config)
        log.info("configuration enregistree dans %s", path)
        return await get_config()

    # --- checklist --------------------------------------------------------

    @app.get("/api/checklist", dependencies=[guard])
    async def get_checklist() -> Checklist:
        return hub.checklist.state()

    @app.post("/api/checklist/toggle", dependencies=[guard])
    async def toggle_item(body: ToggleRequest) -> Checklist:
        try:
            if body.done is None:
                return hub.checklist.toggle(body.id)
            return hub.checklist.set_done(body.id, body.done)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"element inconnu: {body.id}") from None

    @app.post("/api/checklist/items", dependencies=[guard], status_code=201)
    async def add_item(body: AddItemRequest) -> Checklist:
        try:
            return hub.checklist.add(body.label)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.patch("/api/checklist/items/{item_id}", dependencies=[guard])
    async def update_item(item_id: str, body: UpdateItemRequest) -> Checklist:
        try:
            state = hub.checklist.state()
            if body.label is not None:
                state = hub.checklist.rename(item_id, body.label)
            if body.done is not None:
                state = hub.checklist.set_done(item_id, body.done)
            return state
        except KeyError:
            raise HTTPException(status_code=404, detail=f"element inconnu: {item_id}") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None

    @app.delete("/api/checklist/items/{item_id}", dependencies=[guard])
    async def delete_item(item_id: str) -> Checklist:
        try:
            return hub.checklist.remove(item_id)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"element inconnu: {item_id}") from None

    @app.post("/api/checklist/reset", dependencies=[guard])
    async def reset_checklist() -> Checklist:
        return hub.checklist.uncheck_all()

    @app.post("/api/checklist/reorder", dependencies=[guard])
    async def reorder_checklist(body: ReorderRequest) -> Checklist:
        try:
            return hub.checklist.reorder(body.ids)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"element inconnu: {exc}") from None

    # --- websocket --------------------------------------------------------

    @app.websocket("/ws")
    async def websocket_state(websocket: WebSocket) -> None:
        """Diffuse l'etat complet a la coquille Tauri."""
        expected = config.server.token
        if expected and websocket.query_params.get("token") != expected:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(hub.state().model_dump())
                await asyncio.sleep(WS_PUSH_INTERVAL_S)
        except (WebSocketDisconnect, RuntimeError, ConnectionError):
            return

    return app
