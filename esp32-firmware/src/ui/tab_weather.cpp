// Onglet Meteo : temperature du moment et details.

#include <stdio.h>

#include "tabs.h"
#include "text_util.h"
#include "theme.h"

namespace {

lv_obj_t* g_city = nullptr;
lv_obj_t* g_temp = nullptr;
lv_obj_t* g_description = nullptr;
lv_obj_t* g_feels = nullptr;
lv_obj_t* g_humidity = nullptr;
lv_obj_t* g_wind = nullptr;

// Petite tuile « libelle / valeur » reutilisee pour les trois details.
lv_obj_t* build_stat(lv_obj_t* parent, const char* caption) {
  lv_obj_t* tile = card_create(parent);
  lv_obj_set_flex_grow(tile, 1);
  lv_obj_set_height(tile, LV_PCT(100));
  lv_obj_set_style_bg_color(tile, COLOR_SURFACE_2, LV_PART_MAIN);

  lv_obj_t* label = label_create(tile, caption, &lv_font_montserrat_14, COLOR_MUTED);
  lv_obj_align(label, LV_ALIGN_TOP_LEFT, 0, 0);
  lv_obj_set_style_text_letter_space(label, 1, LV_PART_MAIN);

  lv_obj_t* value = label_create(tile, "—", &lv_font_montserrat_20, COLOR_TEXT);
  lv_obj_align(value, LV_ALIGN_BOTTOM_LEFT, 0, 0);
  return value;
}

}  // namespace

void tab_weather_create(lv_obj_t* parent) {
  lv_obj_set_flex_flow(parent, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_style_pad_row(parent, GAP_CARD, LV_PART_MAIN);

  lv_obj_t* hero = card_create(parent);
  lv_obj_set_width(hero, LV_PCT(100));
  lv_obj_set_flex_grow(hero, 1);

  g_city = label_create(hero, "—", &lv_font_montserrat_16, COLOR_ACCENT_2);
  lv_obj_align(g_city, LV_ALIGN_TOP_LEFT, 0, 0);
  lv_obj_set_style_text_letter_space(g_city, 2, LV_PART_MAIN);

  g_temp = label_create(hero, "--°", &lv_font_montserrat_48, COLOR_TEXT);
  lv_obj_align(g_temp, LV_ALIGN_LEFT_MID, 0, 8);

  g_description = label_create(hero, "", &lv_font_montserrat_20, COLOR_MUTED);
  lv_obj_align(g_description, LV_ALIGN_BOTTOM_LEFT, 0, 0);
  lv_obj_set_width(g_description, LV_PCT(100));
  lv_label_set_long_mode(g_description, LV_LABEL_LONG_DOT);

  lv_obj_t* row = lv_obj_create(parent);
  lv_obj_set_size(row, LV_PCT(100), 96);
  lv_obj_set_style_bg_opa(row, LV_OPA_TRANSP, LV_PART_MAIN);
  lv_obj_set_style_border_width(row, 0, LV_PART_MAIN);
  lv_obj_set_style_pad_all(row, 0, LV_PART_MAIN);
  lv_obj_set_style_pad_column(row, GAP_CARD, LV_PART_MAIN);
  lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
  lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);

  g_feels = build_stat(row, "RESSENTI");
  g_humidity = build_stat(row, "HUMIDITE");
  g_wind = build_stat(row, "VENT");
}

void tab_weather_update(const DashboardState& state) {
  const WeatherState& weather = state.weather;

  if (!weather.available) {
    label_set_text_if_changed(g_city, "MODULE INDISPONIBLE");
    label_set_text_if_changed(g_temp, "--°");
    label_set_text_if_changed(g_description, "Cle API OpenWeatherMap absente ou module desactive");
    label_set_text_if_changed(g_feels, "—");
    label_set_text_if_changed(g_humidity, "—");
    label_set_text_if_changed(g_wind, "—");
    return;
  }

  char buffer[LEN_TEXT];
  ascii_fold(buffer, sizeof(buffer), weather.city);
  label_set_text_if_changed(g_city, buffer);

  snprintf(buffer, sizeof(buffer), "%.0f°", weather.temp_c);
  label_set_text_if_changed(g_temp, buffer);

  // Le moteur renvoie deja un libelle localise ; le code icone sert de repli
  // quand OpenWeatherMap ne fournit pas de description.
  char described[LEN_LABEL];
  ascii_fold(described, sizeof(described), weather.description);
  label_set_text_if_changed(g_description,
                            described[0] != '\0' ? described : weather_icon_label(weather.icon));

  snprintf(buffer, sizeof(buffer), "%.0f°", weather.feels_like_c);
  label_set_text_if_changed(g_feels, buffer);

  snprintf(buffer, sizeof(buffer), "%d %%", static_cast<int>(weather.humidity));
  label_set_text_if_changed(g_humidity, buffer);

  snprintf(buffer, sizeof(buffer), "%.0f km/h", weather.wind_kph);
  label_set_text_if_changed(g_wind, buffer);
}
