// Tache de fond qui maintient la liaison avec le moteur et publie l'etat.
//
// Le reseau tourne sur le cœur 0, l'interface LVGL sur le cœur 1 : un GET qui
// traine ne fige jamais l'affichage. L'echange se fait par copie sous mutex,
// l'interface ne voit donc jamais un etat a moitie ecrit.

#pragma once

#include "model/dashboard_state.h"

void engine_link_begin();

// Copie l'etat courant dans `out`. Retourne false si le mutex est indisponible
// (l'appelant garde alors sa copie precedente).
bool engine_link_snapshot(DashboardState& out);

// Envoie une commande de lecture ("toggle", "next", "previous"...).
// L'appel rend la main immediatement : le POST part de la tache reseau.
bool engine_link_send_music(const char* action);

// Demande la bascule d'une case. L'etat local est mis a jour immediatement
// (retour tactile instantane) et le POST part depuis la tache reseau.
bool engine_link_request_toggle(const char* item_id, bool done);
