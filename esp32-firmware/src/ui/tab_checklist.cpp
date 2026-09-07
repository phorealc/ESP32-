// Onglet Checklist : cases a cocher tactiles, synchronisees avec le PC.

#include <stdio.h>
#include <string.h>

#include "net/engine_link.h"
#include "tabs.h"
#include "text_util.h"
#include "theme.h"

namespace {

struct ChecklistRow {
  lv_obj_t* root = nullptr;
  lv_obj_t* box = nullptr;   // carre d'etat
  lv_obj_t* mark = nullptr;  // coche affichee quand la tache est faite
  lv_obj_t* label = nullptr;
};

ChecklistRow g_rows[MAX_CHECKLIST_ITEMS];
lv_obj_t* g_progress = nullptr;
lv_obj_t* g_bar = nullptr;
lv_obj_t* g_empty = nullptr;

// Miroir des identifiants affiches, indexe comme `g_rows`. Le callback tactile
// n'a acces qu'a l'indice de la ligne ; il retrouve l'id ici. Ecrit et lu
// depuis la seule tache LVGL, donc sans verrou.
char g_row_ids[MAX_CHECKLIST_ITEMS][LEN_SHORT];
bool g_row_done[MAX_CHECKLIST_ITEMS];

constexpr int16_t ROW_HEIGHT = 52;
constexpr int16_t BOX_SIZE = 26;

void on_row_clicked(lv_event_t* event) {
  const uint32_t index = reinterpret_cast<uintptr_t>(lv_event_get_user_data(event));
  if (index >= MAX_CHECKLIST_ITEMS) return;
  if (g_row_ids[index][0] == '\0') return;

  // On envoie l'etat cible plutot qu'une bascule : si le POST se perd et que
  // l'utilisateur retouche, l'intention reste sans ambiguite.
  engine_link_request_toggle(g_row_ids[index], !g_row_done[index]);
}

void build_row(ChecklistRow& row, lv_obj_t* parent, uint32_t index) {
  row.root = card_create(parent);
  lv_obj_set_size(row.root, LV_PCT(100), ROW_HEIGHT);
  lv_obj_set_style_pad_all(row.root, 10, LV_PART_MAIN);
  lv_obj_set_style_bg_color(row.root, COLOR_SURFACE, LV_PART_MAIN);
  // Retour visuel a l'appui : indispensable sur un ecran tactile sans clic.
  lv_obj_set_style_bg_color(row.root, COLOR_SURFACE_2, LV_PART_MAIN | LV_STATE_PRESSED);
  lv_obj_add_flag(row.root, LV_OBJ_FLAG_CLICKABLE);
  lv_obj_add_event_cb(row.root, on_row_clicked, LV_EVENT_CLICKED,
                      reinterpret_cast<void*>(static_cast<uintptr_t>(index)));

  row.box = lv_obj_create(row.root);
  lv_obj_set_size(row.box, BOX_SIZE, BOX_SIZE);
  lv_obj_align(row.box, LV_ALIGN_LEFT_MID, 0, 0);
  lv_obj_set_style_radius(row.box, 7, LV_PART_MAIN);
  lv_obj_set_style_border_width(row.box, 2, LV_PART_MAIN);
  lv_obj_set_style_border_color(row.box, COLOR_BORDER, LV_PART_MAIN);
  lv_obj_set_style_bg_opa(row.box, LV_OPA_TRANSP, LV_PART_MAIN);
  lv_obj_clear_flag(row.box, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_clear_flag(row.box, LV_OBJ_FLAG_CLICKABLE);  // le clic appartient a la ligne

  row.mark = label_create(row.box, LV_SYMBOL_OK, &lv_font_montserrat_14, COLOR_BG);
  lv_obj_center(row.mark);

  row.label = label_create(row.root, "", &lv_font_montserrat_16, COLOR_TEXT);
  lv_obj_align(row.label, LV_ALIGN_LEFT_MID, BOX_SIZE + 14, 0);
  lv_obj_set_width(row.label, LV_PCT(80));
  lv_label_set_long_mode(row.label, LV_LABEL_LONG_DOT);
}

}  // namespace

void tab_checklist_create(lv_obj_t* parent) {
  lv_obj_set_flex_flow(parent, LV_FLEX_FLOW_COLUMN);
  lv_obj_set_style_pad_row(parent, 8, LV_PART_MAIN);

  lv_obj_t* header = lv_obj_create(parent);
  lv_obj_set_size(header, LV_PCT(100), 34);
  lv_obj_set_style_bg_opa(header, LV_OPA_TRANSP, LV_PART_MAIN);
  lv_obj_set_style_border_width(header, 0, LV_PART_MAIN);
  lv_obj_set_style_pad_all(header, 0, LV_PART_MAIN);
  lv_obj_clear_flag(header, LV_OBJ_FLAG_SCROLLABLE);

  g_progress = label_create(header, "0 / 0", &lv_font_montserrat_14, COLOR_MUTED);
  lv_obj_align(g_progress, LV_ALIGN_TOP_LEFT, 0, 0);
  lv_obj_set_style_text_letter_space(g_progress, 2, LV_PART_MAIN);

  g_bar = lv_bar_create(header);
  lv_obj_set_size(g_bar, LV_PCT(100), 6);
  lv_obj_align(g_bar, LV_ALIGN_BOTTOM_MID, 0, 0);
  lv_bar_set_range(g_bar, 0, 100);
  lv_bar_set_value(g_bar, 0, LV_ANIM_OFF);
  lv_obj_set_style_radius(g_bar, LV_RADIUS_CIRCLE, LV_PART_MAIN);
  lv_obj_set_style_bg_color(g_bar, COLOR_SURFACE_2, LV_PART_MAIN);
  lv_obj_set_style_bg_color(g_bar, COLOR_OK, LV_PART_INDICATOR);
  lv_obj_set_style_radius(g_bar, LV_RADIUS_CIRCLE, LV_PART_INDICATOR);

  for (uint32_t i = 0; i < MAX_CHECKLIST_ITEMS; i++) {
    build_row(g_rows[i], parent, i);
    lv_obj_add_flag(g_rows[i].root, LV_OBJ_FLAG_HIDDEN);
    g_row_ids[i][0] = '\0';
    g_row_done[i] = false;
  }

  g_empty = label_create(parent, "Checklist vide — ajoutez des taches depuis le PC",
                         &lv_font_montserrat_16, COLOR_MUTED);
}

void tab_checklist_update(const DashboardState& state) {
  const ChecklistState& checklist = state.checklist;

  uint8_t done_count = 0;
  for (uint8_t i = 0; i < checklist.count; i++) {
    if (checklist.items[i].done) done_count++;
  }

  char buffer[LEN_TEXT];
  snprintf(buffer, sizeof(buffer), "%d / %d", static_cast<int>(done_count),
           static_cast<int>(checklist.count));
  label_set_text_if_changed(g_progress, buffer);
  lv_bar_set_value(g_bar, checklist.count > 0 ? (100 * done_count) / checklist.count : 0,
                   LV_ANIM_ON);

  if (checklist.count > 0) {
    lv_obj_add_flag(g_empty, LV_OBJ_FLAG_HIDDEN);
  } else {
    lv_obj_clear_flag(g_empty, LV_OBJ_FLAG_HIDDEN);
  }

  for (uint8_t i = 0; i < MAX_CHECKLIST_ITEMS; i++) {
    ChecklistRow& row = g_rows[i];
    if (i >= checklist.count) {
      lv_obj_add_flag(row.root, LV_OBJ_FLAG_HIDDEN);
      g_row_ids[i][0] = '\0';
      continue;
    }
    lv_obj_clear_flag(row.root, LV_OBJ_FLAG_HIDDEN);

    const ChecklistItem& item = checklist.items[i];
    copy_text(g_row_ids[i], sizeof(g_row_ids[i]), item.id);
    g_row_done[i] = item.done;

    ascii_fold(buffer, sizeof(buffer), item.label);
    label_set_text_if_changed(row.label, buffer);

    if (item.done) {
      lv_obj_set_style_bg_opa(row.box, LV_OPA_COVER, LV_PART_MAIN);
      lv_obj_set_style_bg_color(row.box, COLOR_OK, LV_PART_MAIN);
      lv_obj_set_style_border_color(row.box, COLOR_OK, LV_PART_MAIN);
      lv_obj_clear_flag(row.mark, LV_OBJ_FLAG_HIDDEN);
      lv_obj_set_style_text_color(row.label, COLOR_MUTED, LV_PART_MAIN);
      lv_obj_set_style_text_decor(row.label, LV_TEXT_DECOR_STRIKETHROUGH, LV_PART_MAIN);
    } else {
      lv_obj_set_style_bg_opa(row.box, LV_OPA_TRANSP, LV_PART_MAIN);
      lv_obj_set_style_border_color(row.box, COLOR_BORDER, LV_PART_MAIN);
      lv_obj_add_flag(row.mark, LV_OBJ_FLAG_HIDDEN);
      lv_obj_set_style_text_color(row.label, COLOR_TEXT, LV_PART_MAIN);
      lv_obj_set_style_text_decor(row.label, LV_TEXT_DECOR_NONE, LV_PART_MAIN);
    }
  }
}
