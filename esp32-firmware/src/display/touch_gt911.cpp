#include "touch_gt911.h"

#include <Arduino.h>
#include <Wire.h>

#include "board_config.h"

namespace {

// Registres du GT911 (adresses sur 16 bits, poids fort en premier).
constexpr uint16_t REG_PRODUCT_ID = 0x8140;
constexpr uint16_t REG_STATUS = 0x814E;
constexpr uint16_t REG_POINT_1 = 0x8150;

constexpr uint8_t POINT_STRIDE = 8;
constexpr uint8_t STATUS_BUFFER_READY = 0x80;
constexpr uint8_t STATUS_POINT_MASK = 0x0F;

uint8_t g_address = 0;

bool write_register(uint16_t reg, uint8_t value) {
  Wire.beginTransmission(g_address);
  Wire.write(static_cast<uint8_t>(reg >> 8));
  Wire.write(static_cast<uint8_t>(reg & 0xFF));
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool read_registers(uint16_t reg, uint8_t* buffer, size_t length) {
  Wire.beginTransmission(g_address);
  Wire.write(static_cast<uint8_t>(reg >> 8));
  Wire.write(static_cast<uint8_t>(reg & 0xFF));
  // `false` : pas de STOP, le GT911 exige un RESTART avant la lecture.
  if (Wire.endTransmission(false) != 0) return false;

  if (Wire.requestFrom(g_address, static_cast<uint8_t>(length)) != length) return false;
  for (size_t i = 0; i < length; i++) buffer[i] = Wire.read();
  return true;
}

bool probe(uint8_t address) {
  g_address = address;
  uint8_t id[4] = {0};
  if (!read_registers(REG_PRODUCT_ID, id, sizeof(id))) return false;
  // Le GT911 annonce "911\0" ; on se contente des deux premiers caracteres car
  // certains clones renvoient une chaine legerement differente.
  return id[0] == '9' && id[1] == '1';
}

}  // namespace

uint8_t touch_address() { return g_address; }

bool touch_begin() {
  pinMode(TOUCH_PIN_INT, INPUT);
  Wire.begin(TOUCH_PIN_SDA, TOUCH_PIN_SCL, TOUCH_I2C_HZ);

  if (probe(TOUCH_ADDR_PRIMARY) || probe(TOUCH_ADDR_SECONDARY)) return true;
  g_address = 0;
  return false;
}

TouchPoint touch_read() {
  TouchPoint point;
  if (g_address == 0) return point;

  uint8_t status = 0;
  if (!read_registers(REG_STATUS, &status, 1)) return point;
  if ((status & STATUS_BUFFER_READY) == 0) return point;

  const uint8_t count = status & STATUS_POINT_MASK;
  if (count > 0) {
    uint8_t raw[POINT_STRIDE] = {0};
    if (read_registers(REG_POINT_1, raw, sizeof(raw))) {
      point.pressed = true;
      point.x = static_cast<int16_t>(raw[1] | (raw[2] << 8));
      point.y = static_cast<int16_t>(raw[3] | (raw[4] << 8));
    }
  }

  // Le registre de statut doit etre remis a zero, sinon le GT911 cesse de
  // publier de nouveaux points.
  write_register(REG_STATUS, 0);
  return point;
}
