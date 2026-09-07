// Onglet Serveurs : une carte par serveur Minecraft.

#include <stdio.h>

#include "tabs.h"
#include "text_util.h"
#include "theme.h"

namespace {

// Les cartes sont creees une fois pour toutes (MAX_SERVERS) puis masquees :
// creer/detruire des objets LVGL a chaque cycle fragmenterait le tas.
struct ServerCard {
  lv_obj_t* root = nullptr;
  lv_obj_t* dot = nullptr;
  lv_obj_t* name = nullptr;
  lv_obj_t* players = nullptr;
  lv_obj_t* details = nullptr;
};

ServerCard g_cards[MAX_SERVERS];
lv_obj_t* g_summary = nullptr;
lv_obj_t* g_empty = nullptr;

constexpr int16_t CARD_HEIGHT = 84;

void build_card(ServerCard& card, lv_obj_t* parent) {
  card.root = card_create(parent);
  lv_obj_set_size(card.root, LV_PCT(100), CARD_HEIGHT);

  card.dot = lv_obj_create(card.root);
  lv_obj_set_size(card.dot, 12, 12);
  lv_obj_set_style_radius(card.dot, LV_RADIUS_CIRCLE, LV_PART_MAIN);
  lv_obj_set_style_border_width(card.dot, 0, LV_PART_MAIN);
  lv_obj_clear_flag(card.dot, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_align(card.dot, LV_ALIGN_TOP_LEFT, 0, 6);

  card.name = label_create(card.root, "", &lv_font_montserrat_20, COLOR_TEXT);
  lv_obj_align(card.name, LV_ALIGN_TOP_LEFT, 24, 0);

  card.details = label_create(card.root, "", &lv_font_montserrat_14, COLOR_MUTED);
  lv_obj_align(card.details, LV_ALIGN_BOTTOM_LEFT, 0, 0);

  card.players = label_create(card.root, "", &lv_font_montserrat_28, COLOR_ACCENT_2);
  lv_obj_align(card.players, LV_ALIGN_RIGHT_MID, 0, 0);
}

}  // namespace

void tab_servers_create(lv_obj_t* parent) {
  lv_obj_set_flex_flow(parent, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_style_pad_row(parent, GAP_CARD, LV_PART_MAIN);

  g_summary = label_create(parent, "", &lv_font_montserrat_14, COLOR_MUTED);
  lv_obj_set_style_text_letter_space(g_summary, 2, LV_PART_MAIN);

  for (ServerCard& card : g_cards) {
    build_card(card, parent);
    lv_obj_add_flag(card.root, LV_OBJ_FLAG_HIDDEN);
  }

  g_empty = label_create(parent, "Aucun serveur declare dans config.toml",
                         &lv_font_montserrat_16, COLOR_MUTED);
}

void tab_servers_update(const DashboardState& state) {
  const ServersState& servers = state.servers;

  char summary[64];
  if (!servers.available) {
    snprintf(summary, sizeof(summary), "MODULE INDISPONIBLE");
  } else {
    snprintf(summary, sizeof(summary), "%d JOUEURS EN LIGNE",
             static_cast<int>(servers.total_players()));
  }
  label_set_text_if_changed(g_summary, summary);

  const bool has_items = servers.count > 0;
  if (has_items) {
    lv_obj_add_flag(g_empty, LV_OBJ_FLAG_HIDDEN);
  } else {
    lv_obj_clear_flag(g_empty, LV_OBJ_FLAG_HIDDEN);
  }

  for (uint8_t i = 0; i < MAX_SERVERS; i++) {
    ServerCard& card = g_cards[i];
    if (i >= servers.count) {
      lv_obj_add_flag(card.root, LV_OBJ_FLAG_HIDDEN);
      continue;
    }
    lv_obj_clear_flag(card.root, LV_OBJ_FLAG_HIDDEN);

    const ServerEntry& entry = servers.items[i];
    char buffer[LEN_TEXT];

    ascii_fold(buffer, sizeof(buffer), entry.name);
    label_set_text_if_changed(card.name, buffer);

    lv_obj_set_style_bg_color(card.dot, entry.online ? COLOR_OK : COLOR_ERROR, LV_PART_MAIN);

    if (entry.online) {
      snprintf(buffer, sizeof(buffer), "%d/%d", static_cast<int>(entry.players_online),
               static_cast<int>(entry.players_max));
      label_set_text_if_changed(card.players, buffer);
      lv_obj_set_style_text_color(card.players, COLOR_ACCENT_2, LV_PART_MAIN);

      char version[LEN_SHORT];
      ascii_fold(version, sizeof(version), entry.version);
      snprintf(buffer, sizeof(buffer), "%s  ·  %d ms", version, static_cast<int>(entry.latency_ms));
    } else {
      label_set_text_if_changed(card.players, "—");
      lv_obj_set_style_text_color(card.players, COLOR_ERROR, LV_PART_MAIN);
      snprintf(buffer, sizeof(buffer), "Hors ligne");
    }
    label_set_text_if_changed(card.details, buffer);
  }
}
