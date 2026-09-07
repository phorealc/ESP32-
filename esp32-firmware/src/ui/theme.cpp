#include "theme.h"

#include <string.h>

void theme_apply() {
  lv_obj_t* screen = lv_scr_act();
  lv_obj_set_style_bg_color(screen, COLOR_BG, LV_PART_MAIN);
  lv_obj_set_style_bg_opa(screen, LV_OPA_COVER, LV_PART_MAIN);
  lv_obj_set_style_text_color(screen, COLOR_TEXT, LV_PART_MAIN);
  lv_obj_set_style_pad_all(screen, 0, LV_PART_MAIN);
}

lv_obj_t* card_create(lv_obj_t* parent) {
  lv_obj_t* card = lv_obj_create(parent);
  lv_obj_set_style_bg_color(card, COLOR_SURFACE, LV_PART_MAIN);
  lv_obj_set_style_border_color(card, COLOR_BORDER, LV_PART_MAIN);
  lv_obj_set_style_border_width(card, 1, LV_PART_MAIN);
  lv_obj_set_style_radius(card, RADIUS_CARD, LV_PART_MAIN);
  lv_obj_set_style_pad_all(card, PAD_CARD, LV_PART_MAIN);
  lv_obj_clear_flag(card, LV_OBJ_FLAG_SCROLLABLE);
  return card;
}

lv_obj_t* label_create(lv_obj_t* parent, const char* text, const lv_font_t* font,
                       lv_color_t color) {
  lv_obj_t* label = lv_label_create(parent);
  lv_label_set_text(label, text);
  if (font != nullptr) lv_obj_set_style_text_font(label, font, LV_PART_MAIN);
  lv_obj_set_style_text_color(label, color, LV_PART_MAIN);
  return label;
}

void label_set_text_if_changed(lv_obj_t* label, const char* text) {
  if (label == nullptr || text == nullptr) return;
  const char* current = lv_label_get_text(label);
  if (current != nullptr && strcmp(current, text) == 0) return;
  lv_label_set_text(label, text);
}
