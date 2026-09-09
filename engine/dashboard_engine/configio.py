"""Lecture et ecriture du fichier de configuration depuis l'interface.

Editer un TOML a la main dans `%APPDATA%` est une barriere reelle : ce module
permet a la coquille PC de proposer des champs a remplir a la place.

Deux precautions structurent tout le fichier :

- **les secrets ne ressortent jamais en clair.** `GET /api/config` renvoie des
  valeurs masquees ; une valeur masquee renvoyee telle quelle signifie
  « inchangee » et n'ecrase rien. Sans ca, ouvrir l'ecran de reglages
  reecrirait les cles par leur propre masque.
- **l'ecriture est atomique.** Une coupure en cours d'ecriture laisserait
  sinon un TOML tronque, et le moteur redemarrerait sans configuration.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import tomli_w

MASK = "••••"
"""Prefixe des valeurs masquees. Une valeur qui commence par ce prefixe est
consideree comme inchangee lors d'une ecriture."""

VISIBLE_SUFFIX = 4
"""Nombre de caracteres laisses lisibles, pour reconnaitre quelle cle est en
place sans la reveler."""

# Champs traites comme des secrets, en notation pointee.
SECRET_FIELDS: frozenset[str] = frozenset({
    "server.token",
    "weather.api_key",
    "stream.twitch_client_secret",
    "stream.broadcaster.password",
    "stream.broadcaster.token",
    "stream.streamlabs.socket_token",
})

# Sections exposees a l'ecran de reglages. Le reste de la configuration
# (cadences, seuils) reste reserve au fichier : l'interface ne doit pas devenir
# un formulaire de cent champs.
EDITABLE_SECTIONS: tuple[str, ...] = ("server", "music", "minecraft", "weather", "stream")

HEADER = (
    "# Configuration du Dashboard Phorealc.\n"
    "#\n"
    "# Ce fichier est reecrit par l'ecran de reglages de l'application : les\n"
    "# commentaires ajoutes a la main y seront perdus. Le modele documente reste\n"
    "# disponible dans le depot, dans engine/dashboard_engine/config.example.toml\n"
)


def mask_secret(value: str) -> str:
    """Masque une valeur en laissant ses derniers caracteres lisibles."""
    if not value:
        return ""
    if len(value) <= VISIBLE_SUFFIX:
        return MASK
    return MASK + value[-VISIBLE_SUFFIX:]


def is_masked(value: object) -> bool:
    """True si la valeur est un masque, donc a ignorer lors d'une ecriture."""
    return isinstance(value, str) and value.startswith(MASK)


def _walk(data: dict, prefix: str = "") -> list[tuple[str, dict, str]]:
    """Parcourt les dictionnaires imbriques : (chemin pointe, parent, cle)."""
    found: list[tuple[str, dict, str]] = []
    for key, value in data.items():
        path = f"{prefix}{key}"
        found.append((path, data, key))
        if isinstance(value, dict):
            found.extend(_walk(value, f"{path}."))
    return found


def mask_config(data: dict) -> dict:
    """Copie de la configuration avec les secrets masques."""
    masked = copy.deepcopy(data)
    for path, parent, key in _walk(masked):
        if path in SECRET_FIELDS and isinstance(parent[key], str):
            parent[key] = mask_secret(parent[key])
    return masked


def merge_config(current: dict, patch: dict) -> dict:
    """Fusionne `patch` dans `current`, en profondeur.

    Les listes (comme `minecraft.servers`) sont **remplacees** et non fusionnees :
    fusionner element par element rendrait impossible la suppression d'un serveur.
    Les valeurs masquees sont ignorees, ce qui preserve les secrets existants.
    """
    result = copy.deepcopy(current)
    for key, value in patch.items():
        if is_masked(value):
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_config(result[key], value)
        else:
            result[key] = value
    return result


def _prune(data: Any) -> Any:
    """Retire les valeurs `None`, que TOML ne sait pas representer."""
    if isinstance(data, dict):
        return {key: _prune(value) for key, value in data.items() if value is not None}
    if isinstance(data, list):
        return [_prune(item) for item in data]
    return data


def write_config(path: Path, data: dict) -> None:
    """Ecrit la configuration en TOML, de facon atomique."""
    path.parent.mkdir(parents=True, exist_ok=True)
    body = HEADER + "\n" + tomli_w.dumps(_prune(data))
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(body, encoding="utf-8")
    temp.replace(path)


def editable_view(data: dict) -> dict:
    """Restreint la configuration aux sections proposees a l'ecran."""
    return {section: data[section] for section in EDITABLE_SECTIONS if section in data}
