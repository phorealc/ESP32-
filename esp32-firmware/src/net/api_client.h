// Appels HTTP vers le moteur Python.

#pragma once

#include "model/dashboard_state.h"

// GET /api/state?slim=1 puis remplissage de `out`.
// `out` n'est modifie qu'en cas de succes : une reponse tronquee ne doit pas
// effacer l'affichage courant.
bool api_fetch_state(DashboardState& out);

// POST /api/music/command — pilote le lecteur du PC.
bool api_music_command(const char* action);

// POST /api/checklist/toggle — force l'etat d'une case.
bool api_toggle_checklist(const char* item_id, bool done);
