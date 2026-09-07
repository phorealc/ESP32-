// Configuration du firmware — copier en `app_config.h` puis adapter.
// `app_config.h` est ignore par git : les identifiants Wi-Fi n'ont rien a faire
// dans l'historique du depot.

#pragma once

// --- Reseau ----------------------------------------------------------------
#define WIFI_SSID     "MonReseau"
#define WIFI_PASSWORD "MonMotDePasse"

// Adresse du PC qui fait tourner le moteur Python. Le moteur l'affiche au
// demarrage : « URL a renseigner dans l'ESP32 : http://192.168.1.x:8787 ».
#define ENGINE_HOST "192.168.1.20"
#define ENGINE_PORT 8787

// Doit correspondre a `[server].token` cote moteur ; laisser vide si non utilise.
#define ENGINE_TOKEN ""

// --- Cadences --------------------------------------------------------------
// La musique bouge en permanence, la meteo non : un seul intervalle suffit car
// le moteur sert un cache, mais on evite d'inonder le Wi-Fi pour rien.
#define POLL_INTERVAL_MS   1000
#define HTTP_TIMEOUT_MS    4000
#define WIFI_RETRY_MS      5000

// --- Interface -------------------------------------------------------------
// Rotation LVGL : 0 = paysage (defaut), 2 = paysage retourne.
#define UI_ROTATION 0

// Cadence de rafraichissement de l'affichage. Plus court que le polling
// reseau : la barre de progression du morceau doit rester fluide.
#define UI_REFRESH_MS 250

// Duree d'inactivite avant reduction du retroeclairage (0 = jamais).
#define UI_DIM_AFTER_MS 0
