// Onglet Stream : etat Twitch et sante d'OBS.

#include <stdio.h>
#include <string.h>

#include "tabs.h"
#include "text_util.h"
#include "theme.h"

namespace {

lv_obj_t* g_badge = nullptr;
lv_obj_t* g_badge_label = nullptr;
lv_obj_t* g_title = nullptr;
lv_obj_t* g_game = nullptr;
lv_obj_t* g_viewers = nullptr;
lv_obj_t* g_followers = nullptr;
lv_obj_t* g_uptime = nullptr;
lv_obj_t* g_obs_dot = nullptr;
lv_obj_t* g_obs_text = nullptr;
lv_obj_t* g_obs_details = nullptr;

lv_obj_t* build_metric(lv_obj_t* parent, const char* caption, lv_obj_t** value_out) {
  lv_obj_t* tile = card_create(parent);
  lv_obj_set_flex_grow(tile, 1);
  lv_obj_set_height(tile, LV_PCT(100));
  lv_obj_set_style_bg_color(tile, COLOR_SURFACE_2, LV_PART_MAIN);

  lv_obj_t* label = label_create(tile, caption, &lv_font_montserrat_14, COLOR_MUTED);
  lv_obj_align(label, LV_ALIGN_TOP_LEFT, 0, 0);
  lv_obj_set_style_text_letter_space(label, 1, LV_PART_MAIN);

  *value_out = label_create(tile, "—", &lv_font_montserrat_28, COLOR_TEXT);
  lv_obj_align(*value_out, LV_ALIGN_BOTTOM_LEFT, 0, 0);
  return tile;
}

}  // namespace

void tab_stream_create(lv_obj_t* parent) {
  lv_obj_set_flex_flow(parent, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_style_pad_row(parent, GAP_CARD, LV_PART_MAIN);

  lv_obj_t* hero = card_create(parent);
  lv_obj_set_width(hero, LV_PCT(100));
  lv_obj_set_flex_grow(hero, 1);

  g_badge = lv_obj_create(hero);
  lv_obj_set_size(g_badge, 88, 28);
  lv_obj_align(g_badge, LV_ALIGN_TOP_LEFT, 0, 0);
  lv_obj_set_style_radius(g_badge, 6, LV_PART_MAIN);
  lv_obj_set_style_border_width(g_badge, 0, LV_PART_MAIN);
  lv_obj_set_style_bg_color(g_badge, COLOR_SURFACE_2, LV_PART_MAIN);
  lv_obj_clear_flag(g_badge, LV_OBJ_FLAG_SCROLLABLE);

  g_badge_label = label_create(g_badge, "HORS LIGNE", &lv_font_montserrat_14, COLOR_MUTED);
  lv_obj_center(g_badge_label);

  g_title = label_create(hero, "—", &lv_font_montserrat_20, COLOR_TEXT);
  lv_obj_align(g_title, LV_ALIGN_TOP_LEFT, 0, 44);
  lv_obj_set_width(g_title, LV_PCT(100));
  lv_label_set_long_mode(g_title, LV_LABEL_LONG_DOT);

  g_game = label_create(hero, "", &lv_font_montserrat_16, COLOR_MUTED);
  lv_obj_align(g_game, LV_ALIGN_TOP_LEFT, 0, 76);

  lv_obj_t* row = lv_obj_create(parent);
  lv_obj_set_size(row, LV_PCT(100), 96);
  lv_obj_set_style_bg_opa(row, LV_OPA_TRANSP, LV_PART_MAIN);
  lv_obj_set_style_border_width(row, 0, LV_PART_MAIN);
  lv_obj_set_style_pad_all(row, 0, LV_PART_MAIN);
  lv_obj_set_style_pad_column(row, GAP_CARD, LV_PART_MAIN);
  lv_obj_set_flex_flow(row, LV_FLEX_FLOW_ROW);
  lv_obj_clear_flag(row, LV_OBJ_FLAG_SCROLLABLE);

  build_metric(row, "SPECTATEURS", &g_viewers);
  build_metric(row, "FOLLOWERS", &g_followers);
  build_metric(row, "A L'ANTENNE", &g_uptime);

  lv_obj_t* obs = card_create(parent);
  lv_obj_set_size(obs, LV_PCT(100), 72);

  g_obs_dot = lv_obj_create(obs);
  lv_obj_set_size(g_obs_dot, 12, 12);
  lv_obj_set_style_radius(g_obs_dot, LV_RADIUS_CIRCLE, LV_PART_MAIN);
  lv_obj_set_style_border_width(g_obs_dot, 0, LV_PART_MAIN);
  lv_obj_clear_flag(g_obs_dot, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_align(g_obs_dot, LV_ALIGN_TOP_LEFT, 0, 5);

  g_obs_text = label_create(obs, "OBS deconnecte", &lv_font_montserrat_16, COLOR_TEXT);
  lv_obj_align(g_obs_text, LV_ALIGN_TOP_LEFT, 24, 0);

  g_obs_details = label_create(obs, "", &lv_font_montserrat_14, COLOR_MUTED);
  lv_obj_align(g_obs_details, LV_ALIGN_BOTTOM_LEFT, 0, 0);
}

void tab_stream_update(const DashboardState& state) {
  const StreamState& stream = state.stream;
  char buffer[LEN_TEXT];

  if (stream.live) {
    label_set_text_if_changed(g_badge_label, "EN DIRECT");
    lv_obj_set_style_bg_color(g_badge, COLOR_ERROR, LV_PART_MAIN);
    lv_obj_set_style_text_color(g_badge_label, COLOR_TEXT, LV_PART_MAIN);
  } else {
    label_set_text_if_changed(g_badge_label, stream.available ? "HORS LIGNE" : "INDISPO.");
    lv_obj_set_style_bg_color(g_badge, COLOR_SURFACE_2, LV_PART_MAIN);
    lv_obj_set_style_text_color(g_badge_label, COLOR_MUTED, LV_PART_MAIN);
  }

  ascii_fold(buffer, sizeof(buffer), stream.title[0] != '\0' ? stream.title : "Pas de titre");
  label_set_text_if_changed(g_title, buffer);

  ascii_fold(buffer, sizeof(buffer), stream.game);
  label_set_text_if_changed(g_game, buffer);

  snprintf(buffer, sizeof(buffer), "%ld", static_cast<long>(stream.viewers));
  label_set_text_if_changed(g_viewers, stream.live ? buffer : "—");
  lv_obj_set_style_text_color(g_viewers, stream.live ? COLOR_ACCENT_2 : COLOR_MUTED, LV_PART_MAIN);

  snprintf(buffer, sizeof(buffer), "%ld", static_cast<long>(stream.followers));
  label_set_text_if_changed(g_followers, stream.followers > 0 ? buffer : "—");

  if (stream.live && stream.uptime_s > 0) {
    format_duration(buffer, sizeof(buffer), stream.uptime_s);
  } else {
    snprintf(buffer, sizeof(buffer), "—");
  }
  label_set_text_if_changed(g_uptime, buffer);

  const BroadcasterState& obs = stream.broadcaster;
  // Le logiciel est nomme d'apres ce que le moteur annonce : afficher « OBS »
  // a quelqu'un qui utilise Streamlabs le ferait chercher au mauvais endroit.
  const char* software = strcmp(obs.kind, "streamlabs") == 0 ? "Streamlabs" : "OBS";

  lv_obj_set_style_bg_color(g_obs_dot, obs.connected ? (obs.streaming ? COLOR_ERROR : COLOR_OK)
                                                     : COLOR_MUTED,
                            LV_PART_MAIN);

  if (!obs.connected) {
    snprintf(buffer, sizeof(buffer), "%s deconnecte", software);
    label_set_text_if_changed(g_obs_text, buffer);
    label_set_text_if_changed(g_obs_details,
                              obs.kind[0] == '\0' ? "Aucun logiciel de diffusion configure"
                                                  : "Le logiciel de diffusion est-il lance ?");
    return;
  }

  char scene[LEN_LABEL];
  ascii_fold(scene, sizeof(scene), obs.scene);
  snprintf(buffer, sizeof(buffer), "%s · %s%s", software,
           scene[0] != '\0' ? scene : "sans scene", obs.recording ? "  ·  REC" : "");
  label_set_text_if_changed(g_obs_text, buffer);

  snprintf(buffer, sizeof(buffer), "%.0f fps  ·  %.1f %% d'images perdues", obs.fps,
           obs.dropped_frames_pct);
  label_set_text_if_changed(g_obs_details, buffer);
  // Au-dela de 1 % d'images perdues, le rendu se voit a l'antenne.
  lv_obj_set_style_text_color(g_obs_details,
                              obs.dropped_frames_pct > 1.0f ? COLOR_WARN : COLOR_MUTED,
                              LV_PART_MAIN);
}
