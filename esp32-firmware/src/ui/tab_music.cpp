// Onglet Musique : morceau en cours et progression.

#include <stdio.h>

#include "tabs.h"
#include "text_util.h"
#include "theme.h"

namespace {

lv_obj_t* g_title = nullptr;
lv_obj_t* g_artist = nullptr;
lv_obj_t* g_state = nullptr;
lv_obj_t* g_bar = nullptr;
lv_obj_t* g_elapsed = nullptr;
lv_obj_t* g_total = nullptr;

// Resolution de la barre : LVGL travaille en entiers, on ramene la position a
// un pourcentage en millièmes pour rester fluide sur des morceaux longs.
constexpr int32_t BAR_RANGE = 1000;

}  // namespace

void tab_music_create(lv_obj_t* parent) {
  lv_obj_t* card = card_create(parent);
  lv_obj_set_size(card, LV_PCT(100), LV_PCT(100));

  g_state = label_create(card, "—", &lv_font_montserrat_14, COLOR_ACCENT_2);
  lv_obj_align(g_state, LV_ALIGN_TOP_LEFT, 0, 0);
  lv_obj_set_style_text_letter_space(g_state, 2, LV_PART_MAIN);

  g_title = label_create(card, "Aucune lecture", &lv_font_montserrat_28, COLOR_TEXT);
  lv_obj_align(g_title, LV_ALIGN_TOP_LEFT, 0, 42);
  lv_obj_set_width(g_title, LV_PCT(100));
  // Un titre trop long defile plutot que d'etre coupe.
  lv_label_set_long_mode(g_title, LV_LABEL_LONG_SCROLL_CIRCULAR);

  g_artist = label_create(card, "", &lv_font_montserrat_20, COLOR_MUTED);
  lv_obj_align(g_artist, LV_ALIGN_TOP_LEFT, 0, 88);
  lv_obj_set_width(g_artist, LV_PCT(100));
  lv_label_set_long_mode(g_artist, LV_LABEL_LONG_DOT);

  g_bar = lv_bar_create(card);
  lv_obj_set_size(g_bar, LV_PCT(100), 8);
  lv_obj_align(g_bar, LV_ALIGN_BOTTOM_MID, 0, -28);
  lv_bar_set_range(g_bar, 0, BAR_RANGE);
  lv_bar_set_value(g_bar, 0, LV_ANIM_OFF);
  lv_obj_set_style_radius(g_bar, LV_RADIUS_CIRCLE, LV_PART_MAIN);
  lv_obj_set_style_bg_color(g_bar, COLOR_SURFACE_2, LV_PART_MAIN);
  lv_obj_set_style_bg_color(g_bar, COLOR_ACCENT, LV_PART_INDICATOR);
  lv_obj_set_style_radius(g_bar, LV_RADIUS_CIRCLE, LV_PART_INDICATOR);

  g_elapsed = label_create(card, "0:00", &lv_font_montserrat_14, COLOR_MUTED);
  lv_obj_align(g_elapsed, LV_ALIGN_BOTTOM_LEFT, 0, 0);

  g_total = label_create(card, "0:00", &lv_font_montserrat_14, COLOR_MUTED);
  lv_obj_align(g_total, LV_ALIGN_BOTTOM_RIGHT, 0, 0);
}

void tab_music_update(const DashboardState& state) {
  const MusicState& music = state.music;

  if (!music.available) {
    label_set_text_if_changed(g_state, "MODULE INDISPONIBLE");
    lv_obj_set_style_text_color(g_state, COLOR_MUTED, LV_PART_MAIN);
    label_set_text_if_changed(g_title, "Musique hors service");
    label_set_text_if_changed(g_artist, "Le moteur ne lit pas la session media du PC");
    lv_bar_set_value(g_bar, 0, LV_ANIM_OFF);
    label_set_text_if_changed(g_elapsed, "0:00");
    label_set_text_if_changed(g_total, "0:00");
    return;
  }

  const bool has_track = music.title[0] != '\0';
  label_set_text_if_changed(g_state, music.playing ? "EN LECTURE" : (has_track ? "EN PAUSE" : "SILENCE"));
  lv_obj_set_style_text_color(g_state, music.playing ? COLOR_ACCENT_2 : COLOR_MUTED, LV_PART_MAIN);

  char buffer[LEN_TEXT];
  ascii_fold(buffer, sizeof(buffer), has_track ? music.title : "Aucune lecture");
  label_set_text_if_changed(g_title, buffer);

  ascii_fold(buffer, sizeof(buffer), music.artist);
  label_set_text_if_changed(g_artist, buffer);

  const int32_t value =
      music.duration_s > 0.0f
          ? static_cast<int32_t>((music.position_s / music.duration_s) * BAR_RANGE)
          : 0;
  lv_bar_set_value(g_bar, value < 0 ? 0 : (value > BAR_RANGE ? BAR_RANGE : value), LV_ANIM_OFF);

  char time_text[16];
  format_duration(time_text, sizeof(time_text), static_cast<uint32_t>(music.position_s));
  label_set_text_if_changed(g_elapsed, time_text);
  format_duration(time_text, sizeof(time_text), static_cast<uint32_t>(music.duration_s));
  label_set_text_if_changed(g_total, time_text);
}
