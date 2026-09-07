// Miroir embarque du payload `/api/state?slim=1`.
//
// Tout est en buffers de taille fixe : sur un appareil qui tourne des semaines
// sans redemarrer, remplacer des `String` mille fois par heure fragmente le tas
// jusqu'a l'echec d'allocation. Ici l'etat occupe une taille connue a la
// compilation et ne provoque aucune allocation apres le boot.

#pragma once

#include <stdint.h>
#include <string.h>

static const uint8_t MAX_SERVERS = 6;
static const uint8_t MAX_CHECKLIST_ITEMS = 20;

static const uint8_t LEN_SHORT = 24;   // id, code icone, version
static const uint8_t LEN_LABEL = 48;   // nom de serveur, ville, scene OBS
static const uint8_t LEN_TEXT = 96;    // titre de morceau, titre de stream

struct MusicState {
  bool available = false;
  bool playing = false;
  char title[LEN_TEXT] = "";
  char artist[LEN_TEXT] = "";
  float position_s = 0.0f;
  float duration_s = 0.0f;
  int32_t art_rev = 0;
};

struct ServerEntry {
  char name[LEN_LABEL] = "";
  bool online = false;
  int16_t players_online = 0;
  int16_t players_max = 0;
  char version[LEN_SHORT] = "";
  int16_t latency_ms = 0;
};

struct ServersState {
  bool available = false;
  uint8_t count = 0;
  ServerEntry items[MAX_SERVERS];

  int16_t total_players() const {
    int16_t total = 0;
    for (uint8_t i = 0; i < count; i++) {
      if (items[i].online) total += items[i].players_online;
    }
    return total;
  }
};

struct WeatherState {
  bool available = false;
  char city[LEN_LABEL] = "";
  char description[LEN_LABEL] = "";
  char icon[LEN_SHORT] = "";
  float temp_c = 0.0f;
  float feels_like_c = 0.0f;
  int16_t humidity = 0;
  float wind_kph = 0.0f;
};

struct ObsState {
  bool connected = false;
  bool streaming = false;
  bool recording = false;
  char scene[LEN_LABEL] = "";
  float fps = 0.0f;
  float dropped_frames_pct = 0.0f;
};

struct StreamState {
  bool available = false;
  bool live = false;
  char title[LEN_TEXT] = "";
  char game[LEN_LABEL] = "";
  int32_t viewers = 0;
  int32_t followers = 0;
  uint32_t uptime_s = 0;
  ObsState obs;
};

struct ChecklistItem {
  char id[LEN_SHORT] = "";
  char label[LEN_TEXT] = "";
  bool done = false;
};

struct ChecklistState {
  uint32_t rev = 0;
  uint8_t count = 0;
  ChecklistItem items[MAX_CHECKLIST_ITEMS];
};

// Etat de la liaison avec le moteur, affiche dans la barre de statut.
enum class LinkStatus : uint8_t {
  Booting,
  WifiConnecting,
  WifiConnected,   // Wi-Fi ok mais moteur pas encore joint
  Online,
  EngineUnreachable,
};

struct DashboardState {
  LinkStatus link = LinkStatus::Booting;
  uint32_t seq = 0;             // incremente a chaque payload accepte
  uint32_t last_update_ms = 0;  // millis() de la derniere reponse valide
  int32_t rssi = 0;

  MusicState music;
  ServersState servers;
  WeatherState weather;
  StreamState stream;
  ChecklistState checklist;
};

// Copie bornee garantissant la terminaison.
//
// `strncpy` ne terminerait pas la chaine en cas de troncature ; on mesure donc
// d'abord la longueur utile, ce qui evite aussi l'avertissement
// -Wstringop-truncation que la troncature volontaire declenche.
inline void copy_text(char* dest, size_t size, const char* src) {
  if (size == 0) return;
  if (src == nullptr) {
    dest[0] = '\0';
    return;
  }
  const size_t length = strnlen(src, size - 1);
  memcpy(dest, src, length);
  dest[length] = '\0';
}
