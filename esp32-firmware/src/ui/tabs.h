// Interface commune aux onglets : chacun construit ses widgets une fois, puis
// se contente de rafraichir les textes a chaque nouvel etat.

#pragma once

#include <lvgl.h>

#include "model/dashboard_state.h"

void tab_music_create(lv_obj_t* parent);
void tab_music_update(const DashboardState& state);

void tab_servers_create(lv_obj_t* parent);
void tab_servers_update(const DashboardState& state);

void tab_weather_create(lv_obj_t* parent);
void tab_weather_update(const DashboardState& state);

void tab_stream_create(lv_obj_t* parent);
void tab_stream_update(const DashboardState& state);

void tab_checklist_create(lv_obj_t* parent);
void tab_checklist_update(const DashboardState& state);
