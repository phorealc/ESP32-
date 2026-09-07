// Pilote minimal pour le controleur tactile capacitif GT911.
//
// Les bibliotheques existantes tirent des dependances Arduino supplementaires
// pour une poignee de registres ; le protocole tient en une page, on le lit
// directement.

#pragma once

#include <stdint.h>

struct TouchPoint {
  bool pressed = false;
  int16_t x = 0;
  int16_t y = 0;
};

// Initialise le bus I2C et detecte l'adresse du GT911 (0x5D ou 0x14).
// Retourne false si aucun controleur ne repond.
bool touch_begin();

// Dernier point de contact. `pressed` est faux quand le doigt est releve.
TouchPoint touch_read();

// Adresse effectivement detectee (0 si aucune), utile au diagnostic serie.
uint8_t touch_address();
