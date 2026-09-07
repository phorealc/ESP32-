#include "engine_link.h"

#include <Arduino.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/semphr.h>
#include <freertos/task.h>
#include <string.h>

#include "api_client.h"
#include "app_config.h"
#include "wifi_manager.h"

namespace {

struct ToggleRequest {
  char id[LEN_SHORT];
  bool done;
};

constexpr uint8_t TOGGLE_QUEUE_DEPTH = 8;
constexpr uint32_t TASK_STACK_WORDS = 8192;
constexpr UBaseType_t TASK_PRIORITY = 2;
constexpr BaseType_t NETWORK_CORE = 0;
constexpr TickType_t MUTEX_WAIT = pdMS_TO_TICKS(50);

DashboardState g_state;
SemaphoreHandle_t g_mutex = nullptr;
QueueHandle_t g_toggle_queue = nullptr;

void drain_toggle_queue() {
  ToggleRequest request;
  while (xQueueReceive(g_toggle_queue, &request, 0) == pdTRUE) {
    if (!api_toggle_checklist(request.id, request.done)) {
      // L'echec n'est pas rejoue : le prochain GET fera foi et corrigera
      // l'affichage optimiste. Reessayer en boucle risquerait d'annuler une
      // action que l'utilisateur a entre-temps refaite dans l'autre sens.
      Serial.printf("[link] bascule %s perdue, resynchronisation au prochain cycle\n", request.id);
    }
  }
}

void update_link_status(bool fetched) {
  if (!wifi_connected()) {
    g_state.link = LinkStatus::WifiConnecting;
  } else if (fetched) {
    g_state.link = LinkStatus::Online;
  } else if (g_state.seq == 0) {
    g_state.link = LinkStatus::WifiConnected;
  } else {
    g_state.link = LinkStatus::EngineUnreachable;
  }
  g_state.rssi = wifi_connected() ? wifi_rssi() : 0;
}

void network_task(void*) {
  wifi_begin();
  for (;;) {
    wifi_loop();
    drain_toggle_queue();

    // On travaille sur une copie hors mutex : le parsing JSON dure plusieurs
    // millisecondes, inutile de bloquer l'interface pendant ce temps.
    DashboardState scratch;
    if (xSemaphoreTake(g_mutex, MUTEX_WAIT) == pdTRUE) {
      scratch = g_state;
      xSemaphoreGive(g_mutex);
    }

    const bool fetched = api_fetch_state(scratch);

    if (xSemaphoreTake(g_mutex, MUTEX_WAIT) == pdTRUE) {
      if (fetched) {
        // Les bascules empilees pendant le GET sont conservees : le payload
        // qui arrive peut precéder le POST correspondant.
        const uint32_t pending = uxQueueMessagesWaiting(g_toggle_queue);
        if (pending == 0) g_state = scratch;
        else {
          const ChecklistState keep = g_state.checklist;
          g_state = scratch;
          g_state.checklist = keep;
        }
      }
      update_link_status(fetched);
      xSemaphoreGive(g_mutex);
    }

    vTaskDelay(pdMS_TO_TICKS(POLL_INTERVAL_MS));
  }
}

}  // namespace

void engine_link_begin() {
  g_mutex = xSemaphoreCreateMutex();
  g_toggle_queue = xQueueCreate(TOGGLE_QUEUE_DEPTH, sizeof(ToggleRequest));
  xTaskCreatePinnedToCore(network_task, "engine-link", TASK_STACK_WORDS, nullptr, TASK_PRIORITY,
                          nullptr, NETWORK_CORE);
}

bool engine_link_snapshot(DashboardState& out) {
  if (g_mutex == nullptr) return false;
  if (xSemaphoreTake(g_mutex, MUTEX_WAIT) != pdTRUE) return false;
  out = g_state;
  xSemaphoreGive(g_mutex);
  return true;
}

bool engine_link_request_toggle(const char* item_id, bool done) {
  if (g_toggle_queue == nullptr) return false;

  // Mise a jour optimiste : la case doit reagir sous le doigt, pas au bout
  // d'un aller-retour reseau.
  if (xSemaphoreTake(g_mutex, MUTEX_WAIT) == pdTRUE) {
    for (uint8_t i = 0; i < g_state.checklist.count; i++) {
      if (strcmp(g_state.checklist.items[i].id, item_id) == 0) {
        g_state.checklist.items[i].done = done;
        break;
      }
    }
    xSemaphoreGive(g_mutex);
  }

  ToggleRequest request{};
  copy_text(request.id, sizeof(request.id), item_id);
  request.done = done;
  return xQueueSend(g_toggle_queue, &request, 0) == pdTRUE;
}
