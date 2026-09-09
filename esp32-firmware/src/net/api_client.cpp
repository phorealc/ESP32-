#include "api_client.h"

#include <Arduino.h>
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>

#include "app_config.h"

namespace {

// Le payload « slim » d'un dashboard complet tient largement sous 8 kio ;
// on refuse au-dela pour ne pas se faire manger le tas par une reponse
// inattendue (page d'erreur d'un proxy, mauvaise adresse...).
constexpr size_t MAX_RESPONSE_BYTES = 8192;

String base_url() {
  return String("http://") + ENGINE_HOST + ":" + String(ENGINE_PORT);
}

void apply_token(HTTPClient& http) {
  if (strlen(ENGINE_TOKEN) > 0) http.addHeader("X-Dashboard-Token", ENGINE_TOKEN);
}

void parse_music(JsonObjectConst src, MusicState& out) {
  out.available = src["available"] | false;
  out.playing = src["playing"] | false;
  copy_text(out.title, sizeof(out.title), src["title"] | "");
  copy_text(out.artist, sizeof(out.artist), src["artist"] | "");
  out.position_s = src["position_s"] | 0.0f;
  out.duration_s = src["duration_s"] | 0.0f;
  out.art_rev = src["art_rev"] | 0;

  JsonObjectConst controls = src["controls"];
  out.controls.can_play = controls["can_play"] | false;
  out.controls.can_pause = controls["can_pause"] | false;
  out.controls.can_next = controls["can_next"] | false;
  out.controls.can_previous = controls["can_previous"] | false;
  out.controls.can_seek = controls["can_seek"] | false;
}

void parse_servers(JsonObjectConst src, ServersState& out) {
  out.available = src["available"] | false;
  out.count = 0;
  for (JsonObjectConst entry : src["items"].as<JsonArrayConst>()) {
    if (out.count >= MAX_SERVERS) break;
    ServerEntry& item = out.items[out.count++];
    copy_text(item.name, sizeof(item.name), entry["name"] | "");
    item.online = entry["online"] | false;
    item.players_online = entry["players_online"] | 0;
    item.players_max = entry["players_max"] | 0;
    copy_text(item.version, sizeof(item.version), entry["version"] | "");
    item.latency_ms = entry["latency_ms"] | 0;
  }
}

void parse_weather(JsonObjectConst src, WeatherState& out) {
  out.available = src["available"] | false;
  copy_text(out.city, sizeof(out.city), src["city"] | "");
  copy_text(out.description, sizeof(out.description), src["description"] | "");
  copy_text(out.icon, sizeof(out.icon), src["icon"] | "");
  out.temp_c = src["temp_c"] | 0.0f;
  out.feels_like_c = src["feels_like_c"] | 0.0f;
  out.humidity = src["humidity"] | 0;
  out.wind_kph = src["wind_kph"] | 0.0f;
}

void parse_stream(JsonObjectConst src, StreamState& out) {
  out.available = src["available"] | false;
  out.live = src["live"] | false;
  copy_text(out.title, sizeof(out.title), src["title"] | "");
  copy_text(out.game, sizeof(out.game), src["game"] | "");
  out.viewers = src["viewers"] | 0;
  out.followers = src["followers"] | 0;
  out.uptime_s = src["uptime_s"] | 0;

  JsonObjectConst broadcaster = src["broadcaster"];
  copy_text(out.broadcaster.kind, sizeof(out.broadcaster.kind), broadcaster["kind"] | "");
  out.broadcaster.connected = broadcaster["connected"] | false;
  out.broadcaster.streaming = broadcaster["streaming"] | false;
  out.broadcaster.recording = broadcaster["recording"] | false;
  copy_text(out.broadcaster.scene, sizeof(out.broadcaster.scene), broadcaster["scene"] | "");
  out.broadcaster.fps = broadcaster["fps"] | 0.0f;
  out.broadcaster.dropped_frames_pct = broadcaster["dropped_frames_pct"] | 0.0f;
}

void parse_checklist(JsonObjectConst src, ChecklistState& out) {
  out.rev = src["rev"] | 0;
  out.count = 0;
  for (JsonObjectConst entry : src["items"].as<JsonArrayConst>()) {
    if (out.count >= MAX_CHECKLIST_ITEMS) break;
    ChecklistItem& item = out.items[out.count++];
    copy_text(item.id, sizeof(item.id), entry["id"] | "");
    copy_text(item.label, sizeof(item.label), entry["label"] | "");
    item.done = entry["done"] | false;
  }
}

}  // namespace

bool api_fetch_state(DashboardState& out) {
  if (WiFi.status() != WL_CONNECTED) return false;

  WiFiClient client;
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  // Une connexion reutilisee evite une poignee de main TCP par seconde.
  http.setReuse(true);

  if (!http.begin(client, base_url() + "/api/state?slim=1")) return false;
  apply_token(http);

  const int status = http.GET();
  if (status != HTTP_CODE_OK) {
    Serial.printf("[api] /api/state a repondu %d\n", status);
    http.end();
    return false;
  }
  if (http.getSize() > static_cast<int>(MAX_RESPONSE_BYTES)) {
    Serial.printf("[api] reponse trop volumineuse (%d octets)\n", http.getSize());
    http.end();
    return false;
  }

  JsonDocument doc;
  const DeserializationError error = deserializeJson(doc, http.getStream());
  http.end();
  if (error) {
    Serial.printf("[api] JSON invalide: %s\n", error.c_str());
    return false;
  }

  // On ne recopie dans `out` qu'une fois le document complet valide.
  parse_music(doc["music"], out.music);
  parse_servers(doc["servers"], out.servers);
  parse_weather(doc["weather"], out.weather);
  parse_stream(doc["stream"], out.stream);
  parse_checklist(doc["checklist"], out.checklist);
  out.seq++;
  out.last_update_ms = millis();
  return true;
}

bool api_music_command(const char* action) {
  if (WiFi.status() != WL_CONNECTED) return false;

  WiFiClient client;
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.setConnectTimeout(HTTP_TIMEOUT_MS);

  if (!http.begin(client, base_url() + "/api/music/command")) return false;
  http.addHeader("Content-Type", "application/json");
  apply_token(http);

  JsonDocument body;
  body["action"] = action;
  String payload;
  serializeJson(body, payload);

  const int status = http.POST(payload);
  http.end();
  if (status != HTTP_CODE_OK) {
    // 409 = plus aucun lecteur actif, 503 = module indisponible. Dans les deux
    // cas le prochain cycle de polling remettra l'affichage d'aplomb.
    Serial.printf("[api] commande musique %s a repondu %d\n", action, status);
    return false;
  }
  return true;
}

bool api_toggle_checklist(const char* item_id, bool done) {
  if (WiFi.status() != WL_CONNECTED) return false;

  WiFiClient client;
  HTTPClient http;
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.setConnectTimeout(HTTP_TIMEOUT_MS);

  if (!http.begin(client, base_url() + "/api/checklist/toggle")) return false;
  http.addHeader("Content-Type", "application/json");
  apply_token(http);

  // `done` explicite plutot qu'une bascule : si la reponse se perd et que
  // l'ESP32 reessaie, l'etat final reste celui voulu par l'utilisateur.
  JsonDocument body;
  body["id"] = item_id;
  body["done"] = done;
  String payload;
  serializeJson(body, payload);

  const int status = http.POST(payload);
  http.end();
  if (status != HTTP_CODE_OK) {
    Serial.printf("[api] toggle %s a repondu %d\n", item_id, status);
    return false;
  }
  return true;
}
