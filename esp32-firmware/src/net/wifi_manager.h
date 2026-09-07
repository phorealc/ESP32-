// Connexion Wi-Fi avec reconnexion automatique, non bloquante.

#pragma once

#include <stdbool.h>

void wifi_begin();

// A appeler regulierement : relance une tentative si la liaison est tombee.
void wifi_loop();

bool wifi_connected();
int32_t wifi_rssi();
