// Bring-up de la dalle RGB et branchement de LVGL.

#pragma once

#include <stdbool.h>
#include <stdint.h>

// Initialise l'expandeur, la dalle, LVGL et le tactile.
// Retourne false si la dalle n'a pas pu demarrer (le tactile absent n'est pas
// bloquant : l'affichage reste utile en lecture seule).
bool display_begin();

// Allume ou eteint le retroeclairage.
void display_set_backlight(bool on);

// True si le GT911 a repondu au demarrage.
bool display_has_touch();
