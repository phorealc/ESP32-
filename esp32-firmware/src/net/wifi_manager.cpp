#include "wifi_manager.h"

#include <Arduino.h>
#include <WiFi.h>

#include "app_config.h"

namespace {
uint32_t g_last_attempt_ms = 0;
bool g_was_connected = false;
}  // namespace

void wifi_begin() {
  WiFi.mode(WIFI_STA);
  // Le dashboard est alimente en permanence : on privilegie la latence a
  // l'economie d'energie, sinon le premier paquet apres une pause traine.
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  g_last_attempt_ms = millis();
  Serial.printf("[wifi] connexion a %s...\n", WIFI_SSID);
}

void wifi_loop() {
  const bool connected = WiFi.status() == WL_CONNECTED;

  if (connected && !g_was_connected) {
    Serial.printf("[wifi] connecte — IP %s (%d dBm)\n", WiFi.localIP().toString().c_str(),
                  WiFi.RSSI());
  } else if (!connected && g_was_connected) {
    Serial.println("[wifi] liaison perdue");
  }
  g_was_connected = connected;

  if (!connected && millis() - g_last_attempt_ms > WIFI_RETRY_MS) {
    g_last_attempt_ms = millis();
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
}

bool wifi_connected() { return WiFi.status() == WL_CONNECTED; }

int32_t wifi_rssi() { return WiFi.RSSI(); }
