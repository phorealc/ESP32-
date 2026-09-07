# Architecture

## Vue d'ensemble

```
                         ┌───────────────────────────┐
      Windows (SMTC) ───▶│                           │
      mcstatus       ───▶│      engine/ (Python)     │
      OpenWeatherMap ───▶│   sources → cache → JSON  │
      Twitch / OBS   ───▶│   FastAPI sur :8787       │
                         └────────┬─────────┬────────┘
                         websocket│         │HTTP (polling)
                                  ▼         ▼
                        ┌─────────────┐  ┌──────────────────┐
                        │  app-pc/    │  │ esp32-firmware/  │
                        │  Tauri      │  │ LVGL, 7", tactile│
                        └─────────────┘  └──────────────────┘
                                  ▲         │
                                  └─────────┘
                              checklist (POST)
```

## Principe directeur

**Toute la logique vit dans le moteur ; les deux ecrans ne font que rendre.**

Consequence pratique : ajouter une source de donnees ne demande de toucher ni au
firmware ni a la coquille tant que le contrat JSON ne change pas. Et les deux
affichages ne peuvent pas diverger, puisqu'ils lisent le meme etat.

## engine/ — le moteur

Chaque source tourne dans sa propre tache asyncio et remplit un cache
(`Source` dans `sources/base.py`). L'API sert ce cache : une requete de l'ESP32
ne declenche jamais d'appel sortant, donc la reponse est immediate meme si
OpenWeatherMap met trois secondes a repondre.

Trois comportements sont assures par le socle, pour toutes les sources :

- **Une source en echec conserve sa derniere valeur.** L'ecran garde la derniere
  meteo connue plutot que de se vider a la premiere coupure.
- **Recul exponentiel.** Une source qui echoue est reinterrogee de moins en
  moins souvent (jusqu'a 8x son intervalle), ce qui evite de marteler une API
  en panne — et de se faire limiter par Twitch.
- **Un module non configure devient une `DisabledSource`.** Pas de cle API
  meteo ? Le bloc reste present avec `available: false` et une raison lisible.
  Aucune source ne peut faire tomber le moteur.

Le `Hub` (`hub.py`) assemble les payloads et detient la checklist.

## esp32-firmware/ — l'ecran

Deux cœurs, deux roles :

| Cœur | Tache | Role |
| --- | --- | --- |
| 0 | `engine-link` | Wi-Fi, HTTP, parsing JSON |
| 1 | `loop()` | LVGL, rendu, tactile |

Ils ne partagent que `DashboardState`, copie sous mutex. Un GET qui traine ne
fige donc jamais l'affichage, et LVGL — qui n'est pas thread-safe — n'est
touche que depuis `loop()`.

Deux choix guides par la contrainte materielle :

- **Aucune allocation dynamique dans l'etat.** Tampons de taille fixe et
  listes bornees (`MAX_SERVERS`, `MAX_CHECKLIST_ITEMS`) : sur un appareil qui
  tourne des semaines, remplacer des chaines mille fois par heure finit par
  fragmenter le tas jusqu'a l'echec d'allocation.
- **Les widgets LVGL sont crees une fois** puis masques/reveles. Detruire et
  recreer des objets a chaque cycle aurait le meme effet.

La checklist est **optimiste** : la case reagit sous le doigt, le POST part
depuis la tache reseau, et le cycle de polling suivant fait foi.

## app-pc/ — la coquille

Tauri v2. Le Rust ne fait que trois choses : lancer le moteur en sidecar,
afficher la fenetre, vivre dans la barre des taches. Fermer la fenetre replie
l'application au lieu de quitter — le moteur doit continuer a alimenter l'ESP32.

Le frontend (HTML/CSS/JS sans framework) se connecte au websocket et se
reconnecte indefiniment : le moteur peut redemarrer sans relancer la coquille.

Si le sidecar est absent, la coquille se rabat sur un moteur deja lance
(`python -m dashboard_engine`), ce qui est le mode de developpement normal.

## Ce qui reste a faire

- **Pochettes d'album sur l'ESP32.** L'endpoint `/api/music/art` existe et sert
  l'image ; le firmware ne l'affiche pas encore (il faut un decodeur JPEG et un
  redimensionnement — a faire cote moteur pour epargner la carte).
- **Previsions meteo sur l'ESP32.** Presentes dans `/api/state`, retirees de la
  projection `slim`, pas encore affichees.
- **Heure a l'ecran.** Demande une synchronisation NTP dans le firmware.
- **Accents sur l'ESP32.** Voir la section « Polices » du README du firmware.
