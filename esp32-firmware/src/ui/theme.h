// Palette et styles partages — identite visuelle Phorealc.
//
// ⚠ Les teintes ci-dessous sont un point de depart sombre/violet. Remplacez-les
// par les couleurs exactes de la charte : tout le firmware et la coquille PC
// s'alignent sur ces deux fichiers (`theme.h` ici, `:root` dans app-pc/src/styles.css).

#pragma once

#include <lvgl.h>

#define COLOR_BG        lv_color_hex(0x0E0E13)  // fond general
#define COLOR_SURFACE   lv_color_hex(0x181820)  // cartes
#define COLOR_SURFACE_2 lv_color_hex(0x23232F)  // cartes imbriquees, barres
#define COLOR_BORDER    lv_color_hex(0x2E2E3C)

#define COLOR_TEXT      lv_color_hex(0xF2F2F7)
#define COLOR_MUTED     lv_color_hex(0x8A8A9C)

#define COLOR_ACCENT    lv_color_hex(0x7C5CFF)  // violet Phorealc
#define COLOR_ACCENT_2  lv_color_hex(0x25E0C8)  // cyan secondaire

#define COLOR_OK        lv_color_hex(0x3DDC84)
#define COLOR_WARN      lv_color_hex(0xFFB020)
#define COLOR_ERROR     lv_color_hex(0xFF4D5E)

#define PAD_CARD 14
#define GAP_CARD 12
#define RADIUS_CARD 14

// Applique le theme global (fond, police, couleurs par defaut).
void theme_apply();

// Carte au style maison : fond `COLOR_SURFACE`, coins arrondis, sans scrollbar.
lv_obj_t* card_create(lv_obj_t* parent);

// Libelle pret a l'emploi. `font` peut etre nullptr pour la police par defaut.
lv_obj_t* label_create(lv_obj_t* parent, const char* text, const lv_font_t* font, lv_color_t color);

// N'ecrit que si le texte a change : evite une reallocation et un
// re-rendu complets a chaque cycle de polling.
void label_set_text_if_changed(lv_obj_t* label, const char* text);
