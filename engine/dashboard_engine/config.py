"""Chargement de la configuration (TOML + surcharges par variables d'environnement).

Les secrets (cles API, mots de passe) peuvent rester hors du fichier TOML et
etre fournis par l'environnement, ce qui evite de les committer par accident.
"""

from __future__ import annotations

import os
import shutil
import sys
import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_CONFIG_NAME = "config.toml"
TEMPLATE_NAME = "config.example.toml"
APP_DIR_NAME = "Phorealc/Dashboard"

# Variable d'environnement -> chemin pointe dans la config, en notation pointee.
ENV_OVERRIDES: dict[str, str] = {
    "DASHBOARD_HOST": "server.host",
    "DASHBOARD_PORT": "server.port",
    "DASHBOARD_TOKEN": "server.token",
    "DASHBOARD_WEATHER_API_KEY": "weather.api_key",
    "DASHBOARD_WEATHER_CITY": "weather.city",
    "DASHBOARD_TWITCH_CLIENT_ID": "stream.twitch_client_id",
    "DASHBOARD_TWITCH_CLIENT_SECRET": "stream.twitch_client_secret",
    "DASHBOARD_TWITCH_LOGIN": "stream.twitch_login",
    "DASHBOARD_OBS_PASSWORD": "stream.obs.password",
    "DASHBOARD_OBS_URL": "stream.obs.url",
}


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8787
    token: str = ""
    """Si renseigne, les requetes doivent porter l'en-tete `X-Dashboard-Token`."""

    cors_origins: list[str] = Field(default_factory=lambda: ["*"])


class MusicConfig(BaseModel):
    enabled: bool = True
    interval_s: float = 1.0
    """La position de lecture avance vite : un intervalle court reste peu couteux
    car winsdk lit une session locale."""


class MinecraftServerConfig(BaseModel):
    name: str
    host: str
    """`hote` ou `hote:port`. Le port par defaut (25565) est implicite."""

    bedrock: bool = False


class MinecraftConfig(BaseModel):
    enabled: bool = True
    interval_s: float = 30.0
    timeout_s: float = 5.0
    servers: list[MinecraftServerConfig] = Field(default_factory=list)


class WeatherConfig(BaseModel):
    enabled: bool = True
    interval_s: float = 600.0
    api_key: str = ""
    city: str = "Paris,FR"
    units: str = "metric"
    lang: str = "fr"
    forecast_points: int = 6
    """Nombre de creneaux de prevision a 3 h conserves (0 pour desactiver)."""


class ObsConfig(BaseModel):
    enabled: bool = True
    url: str = "ws://127.0.0.1:4455"
    password: str = ""


class StreamConfig(BaseModel):
    enabled: bool = True
    interval_s: float = 60.0
    twitch_client_id: str = ""
    twitch_client_secret: str = ""
    twitch_login: str = ""
    obs: ObsConfig = Field(default_factory=ObsConfig)


class ChecklistConfig(BaseModel):
    path: str = "checklist.json"
    """Chemin relatif au fichier de configuration, ou absolu."""

    default_items: list[str] = Field(default_factory=list)


class Config(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    music: MusicConfig = Field(default_factory=MusicConfig)
    minecraft: MinecraftConfig = Field(default_factory=MinecraftConfig)
    weather: WeatherConfig = Field(default_factory=WeatherConfig)
    stream: StreamConfig = Field(default_factory=StreamConfig)
    checklist: ChecklistConfig = Field(default_factory=ChecklistConfig)

    base_dir: Path = Field(default_factory=Path.cwd, exclude=True)
    """Repertoire de reference pour resoudre les chemins relatifs."""

    def checklist_path(self) -> Path:
        path = Path(self.checklist.path)
        return path if path.is_absolute() else self.base_dir / path


def _set_dotted(data: dict, dotted: str, value: object) -> None:
    """Ecrit `value` dans `data` au chemin `a.b.c`, en creant les niveaux manquants."""
    *parents, leaf = dotted.split(".")
    node = data
    for key in parents:
        child = node.get(key)
        if not isinstance(child, dict):
            child = {}
            node[key] = child
        node = child
    node[leaf] = value


def apply_env_overrides(data: dict, env: dict[str, str] | None = None) -> dict:
    """Applique les surcharges d'environnement sur un dict de configuration brut.

    Les valeurs vides sont ignorees : exporter `DASHBOARD_TOKEN=""` ne doit pas
    effacer un token defini dans le TOML.
    """
    env = os.environ if env is None else env
    for var, dotted in ENV_OVERRIDES.items():
        raw = env.get(var)
        if raw is None or raw == "":
            continue
        value: object = raw
        if dotted == "server.port":
            try:
                value = int(raw)
            except ValueError:
                continue
        _set_dotted(data, dotted, value)
    return data


def user_config_dir() -> Path:
    """Dossier de configuration par utilisateur, selon la plateforme.

    C'est la que l'application installee range `config.toml` et
    `checklist.json` : un binaire lance par Tauri (ou au demarrage de session)
    n'a pas de repertoire courant previsible, et son dossier d'installation
    n'est pas inscriptible.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
        return base / APP_DIR_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support" / APP_DIR_NAME
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "phorealc-dashboard"


def template_path() -> Path:
    """Modele de configuration livre avec le paquet.

    Sous PyInstaller les donnees sont extraites dans `sys._MEIPASS` ; en
    developpement le modele est simplement a cote du module.
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle is not None:
        bundled = Path(bundle) / "dashboard_engine" / TEMPLATE_NAME
        if bundled.is_file():
            return bundled
    return Path(__file__).parent / TEMPLATE_NAME


def default_config_path() -> Path:
    """Emplacement du `config.toml` a utiliser quand aucun n'est impose.

    Un fichier dans le repertoire courant l'emporte : c'est le mode de
    developpement (`python -m dashboard_engine` depuis `engine/`). Sinon on
    prend le dossier utilisateur, celui de l'application installee.
    """
    local = Path.cwd() / DEFAULT_CONFIG_NAME
    return local if local.is_file() else user_config_dir() / DEFAULT_CONFIG_NAME


def ensure_config_file(path: Path) -> bool:
    """Cree `path` a partir du modele s'il n'existe pas. True si cree.

    Sans ca, un utilisateur qui installe le .exe n'a aucun fichier a editer et
    doit deviner le format ; la, il trouve un modele commente a la bonne place.
    """
    if path.exists():
        return False
    template = template_path()
    if not template.is_file():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, path)
    return True


def load_config(path: str | Path | None = None) -> Config:
    """Charge la configuration depuis un TOML, puis applique l'environnement.

    Un fichier absent n'est pas une erreur : les valeurs par defaut suffisent a
    demarrer le moteur (les modules sans cle API se signalent simplement comme
    indisponibles).
    """
    config_path = Path(path) if path else default_config_path()
    data: dict = {}
    if config_path.is_file():
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
    data = apply_env_overrides(data)
    config = Config.model_validate(data)
    # `base_dir` ancre les chemins relatifs (checklist.json) a cote du fichier
    # de configuration, meme quand celui-ci n'existe pas encore.
    config.base_dir = config_path.parent
    return config
