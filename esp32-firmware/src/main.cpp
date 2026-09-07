// Dashboard ESP32 (Phorealc) — point d'entree du firmware.
//
// Repartition des cœurs :
//   cœur 0 — tache `engine-link` : Wi-Fi, HTTP, parsing JSON
//   cœur 1 — `loop()` : LVGL et rendu
// Les deux ne partagent que `DashboardState`, copie sous mutex.

#include <Arduino.h>
#include <lvgl.h>

#include "app_config.h"
#include "display/display.h"
#include "model/dashboard_state.h"
#include "net/engine_link.h"
#include "ui/ui.h"

namespace {

uint32_t g_last_ui_refresh = 0;
bool g_backlight_on = true;

// LVGL n'est pas thread-safe : tout ce qui touche a l'interface reste dans
// `loop()`. La tache reseau ne fait que remplir l'etat partage.
void refresh_ui() {
  DashboardState snapshot;
  if (engine_link_snapshot(snapshot)) ui_update(snapshot);
}

void handle_backlight_timeout() {
#if UI_DIM_AFTER_MS > 0
  const bool idle = lv_disp_get_inactive_time(nullptr) > UI_DIM_AFTER_MS;
  if (idle == g_backlight_on) {
    g_backlight_on = !idle;
    display_set_backlight(g_backlight_on);
  }
#endif
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n[boot] Dashboard ESP32 — Phorealc");

  if (!display_begin()) {
    Serial.println("[boot] ecran indisponible, arret");
    // Sans affichage il n'y a rien a montrer a l'utilisateur : on clignote sur
    // le port serie plutot que de redemarrer en boucle.
    for (;;) {
      Serial.println("[boot] verifiez board_config.h (brochage de la dalle)");
      delay(5000);
    }
  }

  ui_create();
  DashboardState initial;
  ui_update(initial);

  engine_link_begin();
  Serial.printf("[boot] pret — moteur attendu sur http://%s:%d\n", ENGINE_HOST, ENGINE_PORT);
}

void loop() {
  lv_timer_handler();

  const uint32_t now = millis();
  if (now - g_last_ui_refresh >= UI_REFRESH_MS) {
    g_last_ui_refresh = now;
    refresh_ui();
  }
  handle_backlight_timeout();

  // 5 ms laissent respirer les taches de fond sans nuire a la fluidite :
  // LVGL vise ~30 fps, soit une passe toutes les 33 ms.
  delay(5);
}
