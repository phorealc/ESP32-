// Utilitaires de texte pour l'affichage.

#pragma once

#include <stddef.h>
#include <stdint.h>

// Replie les accents UTF-8 courants sur leur equivalent ASCII (« é » -> « e »).
//
// Les polices Montserrat fournies avec LVGL ne contiennent que l'ASCII : sans
// ce repli, « Ciel dégagé » s'afficherait avec des carres vides. Pour de vrais
// accents, generez une police etendue (voir README, section Polices) et
// remplacez les appels a cette fonction par une copie directe.
void ascii_fold(char* dest, size_t size, const char* src);

// Formate une duree en « 3:07 » (ou « 1:02:33 » au-dela de l'heure).
void format_duration(char* dest, size_t size, uint32_t seconds);

// Libelle court en francais pour un code icone OpenWeatherMap (« 01d »...).
const char* weather_icon_label(const char* icon);
