#include "ui.h"

#include <stdio.h>

#include "tabs.h"
#include "theme.h"

namespace {

constexpr int16_t TOPBAR_HEIGHT = 40;
constexpr int16_t TABBAR_HEIGHT = 54;

lv_obj_t* g_status_dot = nullptr;
lv_obj_t* g_status_text = nullptr;
lv_obj_t* g_rssi_text = nullptr;

struct StatusStyle {
  const char* text;
  lv_color_t color;
};

StatusStyle status_style(const DashboardState& state) {
  switch (state.link) {
    case LinkStatus::Online:
      return {"Connecte", COLOR_OK};
    case LinkStatus::WifiConnecting:
      return {"Wi-Fi...", COLOR_WARN};
    case LinkStatus::WifiConnected:
      return {"Recherche du moteur...", COLOR_WARN};
    case LinkStatus::EngineUnreachable:
      return {"Moteur injoignable", COLOR_ERROR};
    case LinkStatus::Booting:
    default:
      return {"Demarrage", COLOR_MUTED};
  }
}

void build_topbar(lv_obj_t* parent) {
  lv_obj_t* bar = lv_obj_create(parent);
  lv_obj_set_size(bar, LV_PCT(100), TOPBAR_HEIGHT);
  lv_obj_align(bar, LV_ALIGN_TOP_MID, 0, 0);
  lv_obj_set_style_bg_color(bar, COLOR_SURFACE, LV_PART_MAIN);
  lv_obj_set_style_border_width(bar, 0, LV_PART_MAIN);
  lv_obj_set_style_radius(bar, 0, LV_PART_MAIN);
  lv_obj_set_style_pad_hor(bar, PAD_CARD, LV_PART_MAIN);
  lv_obj_set_style_pad_ver(bar, 0, LV_PART_MAIN);
  lv_obj_clear_flag(bar, LV_OBJ_FLAG_SCROLLABLE);

  lv_obj_t* title = label_create(bar, "PHOREALC  ·  DASHBOARD", &lv_font_montserrat_14, COLOR_ACCENT);
  lv_obj_align(title, LV_ALIGN_LEFT_MID, 0, 0);
  lv_obj_set_style_text_letter_space(title, 2, LV_PART_MAIN);

  g_rssi_text = label_create(bar, "", &lv_font_montserrat_14, COLOR_MUTED);
  lv_obj_align(g_rssi_text, LV_ALIGN_RIGHT_MID, 0, 0);

  g_status_text = label_create(bar, "Demarrage", &lv_font_montserrat_14, COLOR_MUTED);
  lv_obj_align_to(g_status_text, g_rssi_text, LV_ALIGN_OUT_LEFT_MID, -14, 0);

  // Pastille d'etat : un point de couleur se lit d'un coup d'œil a 2 m.
  g_status_dot = lv_obj_create(bar);
  lv_obj_set_size(g_status_dot, 10, 10);
  lv_obj_set_style_radius(g_status_dot, LV_RADIUS_CIRCLE, LV_PART_MAIN);
  lv_obj_set_style_border_width(g_status_dot, 0, LV_PART_MAIN);
  lv_obj_clear_flag(g_status_dot, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_align_to(g_status_dot, g_status_text, LV_ALIGN_OUT_LEFT_MID, -8, 0);
}

lv_obj_t* build_tabview(lv_obj_t* parent) {
  lv_obj_t* tabview = lv_tabview_create(parent, LV_DIR_TOP, TABBAR_HEIGHT);
  lv_obj_set_size(tabview, LV_PCT(100), lv_obj_get_height(parent) - TOPBAR_HEIGHT);
  lv_obj_align(tabview, LV_ALIGN_TOP_MID, 0, TOPBAR_HEIGHT);
  lv_obj_set_style_bg_color(tabview, COLOR_BG, LV_PART_MAIN);

  lv_obj_t* buttons = lv_tabview_get_tab_btns(tabview);
  lv_obj_set_style_bg_color(buttons, COLOR_BG, LV_PART_MAIN);
  lv_obj_set_style_text_color(buttons, COLOR_MUTED, LV_PART_ITEMS);
  lv_obj_set_style_text_font(buttons, &lv_font_montserrat_16, LV_PART_ITEMS);
  lv_obj_set_style_border_width(buttons, 0, LV_PART_ITEMS);
  lv_obj_set_style_text_color(buttons, COLOR_TEXT, LV_PART_ITEMS | LV_STATE_CHECKED);
  lv_obj_set_style_border_color(buttons, COLOR_ACCENT, LV_PART_ITEMS | LV_STATE_CHECKED);
  lv_obj_set_style_border_width(buttons, 3, LV_PART_ITEMS | LV_STATE_CHECKED);
  lv_obj_set_style_border_side(buttons, LV_BORDER_SIDE_BOTTOM, LV_PART_ITEMS | LV_STATE_CHECKED);
  return tabview;
}

void style_tab_page(lv_obj_t* page) {
  lv_obj_set_style_bg_color(page, COLOR_BG, LV_PART_MAIN);
  lv_obj_set_style_bg_opa(page, LV_OPA_COVER, LV_PART_MAIN);
  lv_obj_set_style_pad_all(page, GAP_CARD, LV_PART_MAIN);
  lv_obj_set_style_border_width(page, 0, LV_PART_MAIN);
}

}  // namespace

void ui_create() {
  theme_apply();
  lv_obj_t* screen = lv_scr_act();
  lv_obj_clear_flag(screen, LV_OBJ_FLAG_SCROLLABLE);

  build_topbar(screen);
  lv_obj_t* tabview = build_tabview(screen);

  struct TabSpec {
    const char* name;
    void (*create)(lv_obj_t*);
  };
  const TabSpec specs[] = {
      {"Musique", tab_music_create},
      {"Serveurs", tab_servers_create},
      {"Meteo", tab_weather_create},
      {"Stream", tab_stream_create},
      {"Checklist", tab_checklist_create},
  };

  for (const TabSpec& spec : specs) {
    lv_obj_t* page = lv_tabview_add_tab(tabview, spec.name);
    style_tab_page(page);
    spec.create(page);
  }
}

void ui_update(const DashboardState& state) {
  const StatusStyle style = status_style(state);
  label_set_text_if_changed(g_status_text, style.text);
  lv_obj_set_style_text_color(g_status_text, style.color, LV_PART_MAIN);
  lv_obj_set_style_bg_color(g_status_dot, style.color, LV_PART_MAIN);
  lv_obj_align_to(g_status_dot, g_status_text, LV_ALIGN_OUT_LEFT_MID, -8, 0);

  char rssi[24] = "";
  if (state.rssi != 0) snprintf(rssi, sizeof(rssi), "%ld dBm", static_cast<long>(state.rssi));
  label_set_text_if_changed(g_rssi_text, rssi);

  tab_music_update(state);
  tab_servers_update(state);
  tab_weather_update(state);
  tab_stream_update(state);
  tab_checklist_update(state);
}
