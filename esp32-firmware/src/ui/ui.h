// Construction et rafraichissement de l'interface LVGL.

#pragma once

#include "model/dashboard_state.h"

// Construit la barre de statut et les cinq onglets. A appeler apres display_begin().
void ui_create();

// Repercute un nouvel etat sur l'affichage.
void ui_update(const DashboardState& state);
