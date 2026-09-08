# Contrat d'API

Le moteur Python est la seule source de verite. L'ESP32 et la coquille PC en
sont deux clients equivalents : tout ce qui s'affiche des deux cotes vient d'ici.

Base : `http://<ip-du-pc>:8787`

## Authentification

Optionnelle. Si `[server].token` est renseigne dans `config.toml`, toutes les
routes `/api/*` (sauf `/api/health`) exigent le jeton :

- en-tete `X-Dashboard-Token: <jeton>`, ou
- parametre de requete `?token=<jeton>` (utilise par le websocket).

`/api/health` reste ouvert : c'est la sonde de demarrage de la coquille Tauri.

Le jeton empeche un autre appareil du reseau local de modifier la checklist.
Ce n'est pas de l'authentification : le trafic reste en HTTP clair.

## Lecture

| Methode | Route | Reponse |
| --- | --- | --- |
| GET | `/api/health` | disponibilite de chaque module |
| GET | `/api/state` | etat complet (voir ci-dessous) |
| GET | `/api/state?slim=1` | meme etat, allege pour l'ESP32 |
| GET | `/api/music` | bloc `music` seul |
| GET | `/api/music/art` | pochette du morceau (JPEG/PNG), 404 si absente |
| GET | `/api/servers` | bloc `servers` seul |
| GET | `/api/weather` | bloc `weather` seul |
| GET | `/api/stream` | bloc `stream` seul |
| GET | `/api/donations` | alertes Streamlabs |
| GET | `/api/checklist` | checklist seule |
| WS | `/ws` | etat complet pousse toutes les 500 ms |

## Ecriture (checklist)

| Methode | Route | Corps | Effet |
| --- | --- | --- | --- |
| POST | `/api/checklist/toggle` | `{"id": "a1b2", "done": true}` | force l'etat (idempotent) |
| POST | `/api/checklist/toggle` | `{"id": "a1b2"}` | bascule l'etat courant |
| POST | `/api/checklist/items` | `{"label": "Lancer OBS"}` | ajoute (201) |
| PATCH | `/api/checklist/items/{id}` | `{"label": "...", "done": true}` | renomme et/ou coche |
| DELETE | `/api/checklist/items/{id}` | — | supprime |
| POST | `/api/checklist/reset` | — | decoche tout |
| POST | `/api/checklist/reorder` | `{"ids": ["a1", "a2"]}` | reordonne |

Toutes renvoient la checklist complete apres modification, ce qui evite au
client un GET de confirmation.

Un `id` inconnu renvoie 404. **`done` explicite est preferable a la bascule**
pour un client peu fiable : si la reponse se perd et que l'ESP32 reessaie,
l'etat final reste celui voulu par l'utilisateur.

## Etat complet

```jsonc
{
  "version": 1,
  "ts": 1757270400.12,

  "music": {
    "available": true,      // false = module desactive ou en echec
    "error": null,          // raison de l'indisponibilite, sinon null
    "updated_at": 1757270400.0,
    "playing": true,
    "title": "Nuit blanche",
    "artist": "Etienne Daho",
    "album": "Eden",
    "app": "Spotify.exe",
    "position_s": 97.0,
    "duration_s": 231.0,
    "art_rev": 3            // change de valeur a chaque nouvelle pochette
  },

  "servers": {
    "available": true, "error": null, "updated_at": 1757270400.0,
    "items": [
      { "name": "Survie", "host": "mc.exemple.net", "online": true,
        "players_online": 7, "players_max": 20, "version": "1.21.1",
        "latency_ms": 24, "motd": "Bienvenue", "error": null }
    ]
  },

  "weather": {
    "available": true, "error": null, "updated_at": 1757270400.0,
    "city": "Paris", "temp_c": 18.4, "feels_like_c": 17.2,
    "temp_min_c": 16.0, "temp_max_c": 20.0,
    "description": "Ciel degage", "icon": "01d",
    "humidity": 62, "wind_kph": 11.5,
    "sunrise": 1757216400, "sunset": 1757265600,
    "forecast": [ { "ts": 1757281200, "temp_c": 17.2, "icon": "02n" } ]
  },

  "stream": {
    "available": true, "error": null, "updated_at": 1757270400.0,
    "live": true, "title": "...", "game": "...",
    "viewers": 142, "followers": 3187, "uptime_s": 5430,
    "broadcaster": { "kind": "streamlabs",   // "obs" | "streamlabs" | "none"
                     "connected": true, "streaming": true, "recording": false,
                     "scene": "Ecran principal", "fps": 60.0,
                     "dropped_frames_pct": 0.3 }
  },

  "donations": {
    "available": true, "error": null, "updated_at": 1757270400.0,
    "total": 42.5,          // cumul depuis le demarrage du moteur, pas depuis toujours
    "currency": "EUR",
    "last_follower": "Bob",
    "last_subscriber": "Carol",
    "recent": [ { "kind": "donation", "name": "Alice", "amount": 5.0,
                  "currency": "EUR", "message": "Continue !", "ts": 1757270390.0 } ]
  },

  "checklist": {
    "rev": 12,              // incremente a chaque modification
    "items": [ { "id": "a1b2c3d4", "label": "Lancer OBS", "done": true, "order": 0 } ]
  }
}
```

### `available` et `error`

Un module indisponible n'est pas une erreur de l'API : la reponse reste 200 et
le bloc conserve sa forme, avec `available: false` et un `error` explicatif
(« cle API OpenWeatherMap manquante », « module desactive en configuration »...).
Les deux clients affichent alors une carte grisee plutot qu'un vide.

Quand une source tombe **apres** avoir fonctionne, la derniere valeur connue est
conservee et seul `error` est renseigne : l'ecran continue d'afficher la derniere
meteo connue au lieu de se vider a la premiere coupure reseau.

### Projection `slim`

`?slim=1` retire les champs que l'ESP32 n'affiche pas, pour economiser sa RAM :

| Bloc | Champs retires |
| --- | --- |
| tous | `error`, `updated_at` |
| `music` | `album`, `app` |
| `donations` | `recent` (les totaux suffisent a l'ESP32) |
| `weather` | `forecast`, `temp_min_c`, `temp_max_c`, `sunrise`, `sunset` |
| `servers.items[]` | `motd`, `error` |

La checklist n'est **jamais** tronquee : c'est la seule donnee que l'ESP32
modifie, elle doit rester complete des deux cotes.

## Faire evoluer le contrat

### Historique

| Version | Changement |
| --- | --- |
| 2 | `stream.obs` devient `stream.broadcaster`, avec un champ `kind` (`obs` / `streamlabs` / `none`) : Streamlabs Desktop n'est pas OBS et ne parle pas son protocole. Ajout du bloc `donations`. |
| 1 | Version initiale. |

`version` (constante `API_VERSION` dans `engine/dashboard_engine/models.py`)
identifie le contrat. Ajouter un champ ne casse aucun client : ArduinoJson et
le frontend ignorent ce qu'ils ne connaissent pas. En revanche, renommer ou
supprimer un champ impose d'incrementer `version` et de mettre a jour :

1. `engine/dashboard_engine/models.py` — le modele Pydantic ;
2. `esp32-firmware/src/net/api_client.cpp` — le parseur ;
3. `esp32-firmware/src/model/dashboard_state.h` — le miroir embarque ;
4. `app-pc/src/main.js` — le rendu PC ;
5. ce document.
