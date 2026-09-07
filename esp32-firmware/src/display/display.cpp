#include "display.h"

#include <Arduino.h>
#include <Arduino_GFX_Library.h>
#include <Wire.h>
#include <esp_heap_caps.h>
#include <lvgl.h>

#include "app_config.h"
#include "board_config.h"
#include "touch_gt911.h"

namespace {

Arduino_ESP32RGBPanel* g_panel = nullptr;
Arduino_RGB_Display* g_gfx = nullptr;
bool g_has_touch = false;

lv_disp_draw_buf_t g_draw_buf;
lv_disp_drv_t g_disp_drv;
lv_indev_drv_t g_indev_drv;

// Hauteur du tampon de rendu, en lignes. LVGL redessine par bandes : 40 lignes
// (64 kio en RGB565) tiennent en RAM interne, bien plus rapide que la PSRAM.
constexpr uint16_t DRAW_BUFFER_LINES = 40;

void flush_cb(lv_disp_drv_t* drv, const lv_area_t* area, lv_color_t* pixels) {
  const uint32_t w = area->x2 - area->x1 + 1;
  const uint32_t h = area->y2 - area->y1 + 1;
  g_gfx->draw16bitRGBBitmap(area->x1, area->y1, reinterpret_cast<uint16_t*>(pixels), w, h);
  lv_disp_flush_ready(drv);
}

void touch_read_cb(lv_indev_drv_t*, lv_indev_data_t* data) {
  const TouchPoint point = touch_read();
  data->state = point.pressed ? LV_INDEV_STATE_PRESSED : LV_INDEV_STATE_RELEASED;
  if (point.pressed) {
    data->point.x = point.x;
    data->point.y = point.y;
  }
}

#if BOARD_USE_CH422G
// Le CH422G porte le retroeclairage et les resets de la dalle et du tactile.
// On pilote les huit sorties en bloc : la carte n'a rien d'autre derriere
// l'expandeur, et le mapping bit a bit varie selon les revisions.
bool ch422g_write(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

void ch422g_begin() {
  Wire.begin(TOUCH_PIN_SDA, TOUCH_PIN_SCL, TOUCH_I2C_HZ);
  ch422g_write(CH422G_ADDR_MODE, CH422G_MODE_OUTPUT);
  // Toutes les sorties hautes : retroeclairage allume, resets relaches.
  ch422g_write(CH422G_ADDR_OUTPUT, 0xFF);
  delay(50);  // laisse la dalle et le GT911 sortir de reset
}
#endif

}  // namespace

bool display_has_touch() { return g_has_touch; }

void display_set_backlight(bool on) {
#if BOARD_USE_CH422G
  ch422g_write(CH422G_ADDR_OUTPUT, on ? 0xFF : 0xFB);  // EXIO3 bas = retroeclairage eteint
#else
  (void)on;
#endif
}

bool display_begin() {
#if BOARD_USE_CH422G
  ch422g_begin();
#endif

  g_panel = new Arduino_ESP32RGBPanel(
      LCD_PIN_DE, LCD_PIN_VSYNC, LCD_PIN_HSYNC, LCD_PIN_PCLK,
      LCD_PIN_R0, LCD_PIN_R1, LCD_PIN_R2, LCD_PIN_R3, LCD_PIN_R4,
      LCD_PIN_G0, LCD_PIN_G1, LCD_PIN_G2, LCD_PIN_G3, LCD_PIN_G4, LCD_PIN_G5,
      LCD_PIN_B0, LCD_PIN_B1, LCD_PIN_B2, LCD_PIN_B3, LCD_PIN_B4,
      LCD_HSYNC_POLARITY, LCD_HSYNC_FRONT_PORCH, LCD_HSYNC_PULSE_WIDTH, LCD_HSYNC_BACK_PORCH,
      LCD_VSYNC_POLARITY, LCD_VSYNC_FRONT_PORCH, LCD_VSYNC_PULSE_WIDTH, LCD_VSYNC_BACK_PORCH,
      /*pclk_active_neg=*/1, LCD_PCLK_HZ);

  g_gfx = new Arduino_RGB_Display(LCD_WIDTH, LCD_HEIGHT, g_panel, UI_ROTATION, /*auto_flush=*/true);
  if (!g_gfx->begin()) {
    Serial.println("[display] echec de l'initialisation de la dalle RGB");
    return false;
  }
  g_gfx->fillScreen(BLACK);

  lv_init();

  const uint32_t pixels = LCD_WIDTH * DRAW_BUFFER_LINES;
  const size_t bytes = pixels * sizeof(lv_color_t);
  // La RAM interne est preferable ; on se rabat sur la PSRAM si elle est prise.
  auto* buf1 = static_cast<lv_color_t*>(heap_caps_malloc(bytes, MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT));
  if (buf1 == nullptr) {
    buf1 = static_cast<lv_color_t*>(heap_caps_malloc(bytes, MALLOC_CAP_SPIRAM));
    Serial.println("[display] tampon LVGL en PSRAM (rendu plus lent)");
  }
  if (buf1 == nullptr) {
    Serial.println("[display] memoire insuffisante pour le tampon LVGL");
    return false;
  }
  lv_disp_draw_buf_init(&g_draw_buf, buf1, nullptr, pixels);

  lv_disp_drv_init(&g_disp_drv);
  g_disp_drv.hor_res = LCD_WIDTH;
  g_disp_drv.ver_res = LCD_HEIGHT;
  g_disp_drv.flush_cb = flush_cb;
  g_disp_drv.draw_buf = &g_draw_buf;
  g_disp_drv.full_refresh = 0;
  lv_disp_drv_register(&g_disp_drv);

  g_has_touch = touch_begin();
  if (g_has_touch) {
    Serial.printf("[display] GT911 detecte a l'adresse 0x%02X\n", touch_address());
    lv_indev_drv_init(&g_indev_drv);
    g_indev_drv.type = LV_INDEV_TYPE_POINTER;
    g_indev_drv.read_cb = touch_read_cb;
    lv_indev_drv_register(&g_indev_drv);
  } else {
    Serial.println("[display] GT911 absent — interface en lecture seule");
  }
  return true;
}
