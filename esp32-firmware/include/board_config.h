// Brochage de la carte Waveshare ESP32-S3-Touch-LCD-7 (800x480, ST7262 + GT911).
//
// ⚠ A VERIFIER avant le premier flash : Waveshare a publie plusieurs revisions
// de cette carte (7 / 7B) dont le brochage RGB differe. Les valeurs ci-dessous
// correspondent a l'ESP32-S3-Touch-LCD-7 ; comparez-les au schema de VOTRE carte
// (wiki Waveshare > Resources > Schematic) avant de suspecter le reste du code.
// C'est le seul fichier a toucher pour porter le firmware sur un autre ecran.

#pragma once

// --- Dalle -----------------------------------------------------------------
#define LCD_WIDTH  800
#define LCD_HEIGHT 480

// Signaux de synchronisation du bus RGB parallele.
#define LCD_PIN_DE     5
#define LCD_PIN_VSYNC  3
#define LCD_PIN_HSYNC 46
#define LCD_PIN_PCLK   7

// Bus de donnees RGB565. Les bits de poids faible de chaque composante ne sont
// pas cables : R0-R2, G0-G1 et B0-B2 sont absents du connecteur.
#define LCD_PIN_R0  1   // R3
#define LCD_PIN_R1  2   // R4
#define LCD_PIN_R2 42   // R5
#define LCD_PIN_R3 41   // R6
#define LCD_PIN_R4 40   // R7

#define LCD_PIN_G0 39   // G2
#define LCD_PIN_G1  0   // G3
#define LCD_PIN_G2 45   // G4
#define LCD_PIN_G3 48   // G5
#define LCD_PIN_G4 47   // G6
#define LCD_PIN_G5 21   // G7

#define LCD_PIN_B0 14   // B3
#define LCD_PIN_B1 38   // B4
#define LCD_PIN_B2 18   // B5
#define LCD_PIN_B3 17   // B6
#define LCD_PIN_B4 10   // B7

// Timings du ST7262. Un PCLK trop eleve provoque des dechirures horizontales ;
// 16 MHz est le compromis retenu par Waveshare pour cette dalle.
#define LCD_PCLK_HZ        16000000
#define LCD_HSYNC_POLARITY 0
#define LCD_HSYNC_FRONT_PORCH 8
#define LCD_HSYNC_PULSE_WIDTH 4
#define LCD_HSYNC_BACK_PORCH  8
#define LCD_VSYNC_POLARITY 0
#define LCD_VSYNC_FRONT_PORCH 8
#define LCD_VSYNC_PULSE_WIDTH 4
#define LCD_VSYNC_BACK_PORCH  8

// --- Tactile GT911 (bus I2C partage avec l'expandeur) ----------------------
#define TOUCH_PIN_SDA 8
#define TOUCH_PIN_SCL 9
#define TOUCH_PIN_INT 4
#define TOUCH_I2C_HZ  400000

// Le GT911 repond a 0x5D ou 0x14 selon l'etat de INT au reset : on essaie les deux.
#define TOUCH_ADDR_PRIMARY   0x5D
#define TOUCH_ADDR_SECONDARY 0x14

// --- Expandeur d'E/S CH422G ------------------------------------------------
// Sur cette carte, le retroeclairage et les broches de reset (dalle, tactile)
// ne sont pas cables directement sur l'ESP32 mais derriere un CH422G.
#define BOARD_USE_CH422G 1
#define CH422G_ADDR_MODE   0x24  // registre de configuration
#define CH422G_ADDR_OUTPUT 0x38  // registre de sortie (EXIO1..EXIO8)
#define CH422G_MODE_OUTPUT 0x01  // EXIO en sortie push-pull
