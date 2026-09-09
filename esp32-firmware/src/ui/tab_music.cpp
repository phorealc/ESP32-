// Onglet Musique : morceau en cours et progression.

#include <stdio.h>

#include "net/engine_link.h"
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
lv_obj_t* g_previous = nullptr;
lv_obj_t* g_play_pause = nullptr;
lv_obj_t* g_play_icon = nullptr;
lv_obj_t* g_next = nullptr;

constexpr int16_t BUTTON_W = 78;
constexpr int16_t BUTTON_H = 52;

// Resolution de la barre : LVGL travaille en entiers, on ramene la position a
// un pourcentage en millièmes pour rester fluide sur des morceaux longs.
constexpr int32_t BAR_RANGE = 1000;

void on_transport_clicked(lv_event_t* event) {
  const char* action = static_cast<const char*>(lv_event_get_user_data(event));
  engine_link_send_music(action);
}

// Bouton de transport : large, car il faut pouvoir l'atteindre au doigt sans
// viser, et sans risque de toucher son voisin.
lv_obj_t* transport_button(lv_obj_t* parent, const char* symbol, const char* action,
                           lv_obj_t** icon_out) {
  lv_obj_t* button = lv_btn_create(parent);
  lv_obj_set_size(button, BUTTON_W, BUTTON_H);
  lv_obj_set_style_radius(button, 10, LV_PART_MAIN);
  lv_obj_set_style_bg_color(button, COLOR_SURFACE_2, LV_PART_MAIN);
  lv_obj_set_style_bg_color(button, COLOR_ACCENT, LV_PART_MAIN | LV_STATE_PRESSED);
  // Un bouton grise doit se lire comme tel, pas seulement refuser le clic.
  lv_obj_set_style_bg_opa(button, LV_OPA_40, LV_PART_MAIN | LV_STATE_DISABLED);
  lv_obj_set_style_text_opa(button, LV_OPA_40, LV_PART_MAIN | LV_STATE_DISABLED);
  lv_obj_set_style_shadow_width(button, 0, LV_PART_MAIN);
  lv_obj_add_event_cb(button, on_transport_clicked, LV_EVENT_CLICKED,
                      const_cast<char*>(action));

  lv_obj_t* icon = label_create(button, symbol, &lv_font_montserrat_20, COLOR_TEXT);
  lv_obj_center(icon);
  if (icon_out != nullptr) *icon_out = icon;
  return button;
}

void set_enabled(lv_obj_t* button, bool enabled) {
  if (enabled) {
    lv_obj_clear_state(button, LV_STATE_DISABLED);
  } else {
    lv_obj_add_state(button, LV_STATE_DISABLED);
  }
}

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

  lv_obj_t* transport = lv_obj_create(card);
  lv_obj_set_size(transport, BUTTON_W * 3 + 24, BUTTON_H);
  lv_obj_align(transport, LV_ALIGN_BOTTOM_MID, 0, -58);
  lv_obj_set_style_bg_opa(transport, LV_OPA_TRANSP, LV_PART_MAIN);
  lv_obj_set_style_border_width(transport, 0, LV_PART_MAIN);
  lv_obj_set_style_pad_all(transport, 0, LV_PART_MAIN);
  lv_obj_set_style_pad_column(transport, 12, LV_PART_MAIN);
  lv_obj_set_flex_flow(transport, LV_FLEX_FLOW_ROW);
  lv_obj_clear_flag(transport, LV_OBJ_FLAG_SCROLLABLE);

  g_previous = transport_button(transport, LV_SYMBOL_PREV, "previous", nullptr);
  g_play_pause = transport_button(transport, LV_SYMBOL_PLAY, "toggle", &g_play_icon);
  g_next = transport_button(transport, LV_SYMBOL_NEXT, "next", nullptr);

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
    set_enabled(g_previous, false);
    set_enabled(g_play_pause, false);
    set_enabled(g_next, false);
    label_set_text_if_changed(g_state, "MODULE INDISPONIBLE");
    lv_obj_set_style_text_color(g_state, COLOR_MUTED, LV_PART_MAIN);
    label_set_text_if_changed(g_title, "Musique hors service");
    label_set_text_if_changed(g_artist, "Le moteur ne lit pas la session media du PC");
    lv_bar_set_value(g_bar, 0, LV_ANIM_OFF);
    label_set_text_if_changed(g_elapsed, "0:00");
    label_set_text_if_changed(g_total, "0:00");
    return;
  }

  // Les capacites viennent du lecteur : Spotify accepte « suivant », un
  // onglet YouTube souvent non. On grise plutot que de ne rien faire.
  set_enabled(g_previous, music.controls.can_previous);
  set_enabled(g_next, music.controls.can_next);
  set_enabled(g_play_pause, music.playing ? music.controls.can_pause : music.controls.can_play);
  label_set_text_if_changed(g_play_icon, music.playing ? LV_SYMBOL_PAUSE : LV_SYMBOL_PLAY);

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
