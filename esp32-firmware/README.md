# Firmware ESP32 — Dashboard Phorealc

Interface LVGL a onglets sur ecran tactile 7 pouces, alimentee par le moteur
Python en Wi-Fi.

Cible : **Waveshare ESP32-S3-Touch-LCD-7** (800×480, ST7262 RGB + GT911,
8 Mio de PSRAM, 16 Mio de flash).

## Compilation

```bash
cp include/app_config.example.h include/app_config.h   # SSID, mot de passe, IP du PC
pio run              # compiler
pio run -t upload    # televerser
pio device monitor   # trace serie (115200 bauds)
```

`app_config.h` est ignore par git.

## ⚠ Avant le premier flash : verifier le brochage

`include/board_config.h` contient le brochage de la dalle RGB, du tactile et de
l'expandeur CH422G. **Waveshare a publie plusieurs revisions de cette carte
(7 / 7B) dont le bus RGB differe.** Comparez les valeurs au schema de votre
carte (wiki Waveshare → *Resources* → *Schematic*) avant de soupconner le reste
du code.

C'est le seul fichier a modifier pour porter le firmware sur un autre ecran.

### Symptomes courants

| Ce que vous voyez | Piste |
| --- | --- |
| Ecran noir, trace serie normale | retroeclairage : bits du CH422G (`display_set_backlight`) |
| Image decalee ou repliee | porches `LCD_*_FRONT_PORCH` / `BACK_PORCH` |
| Dechirures horizontales | baisser `LCD_PCLK_HZ` (16 MHz → 12 MHz) |
| Couleurs fausses | ordre des broches R/G/B |
| `GT911 absent` au demarrage | `TOUCH_PIN_SDA` / `SCL`, ou adresse I2C (0x5D vs 0x14) |
| Tactile decale | `UI_ROTATION` incoherent avec l'orientation physique |

## Organisation

```
include/
  app_config.h        # ← a creer : Wi-Fi, adresse du moteur, cadences
  board_config.h      # brochage (le seul fichier lie au materiel)
  lv_conf.h           # config LVGL, derivee du template officiel 8.3.11
src/
  main.cpp            # setup/loop, repartition des cœurs
  model/              # miroir embarque du JSON, en tampons de taille fixe
  display/            # dalle RGB + LVGL + pilote tactile GT911
  net/                # Wi-Fi, client HTTP, tache de fond `engine-link`
  ui/                 # theme, utilitaires texte, cinq onglets
test/                 # tests natifs (aucune carte requise)
```

## Tests

La logique portable (decoupage UTF-8, formatage, bornes de copie) se teste sur
PC, sans carte ni chaine de compilation croisee :

```bash
./test/run_native_tests.sh
```

C'est la partie qui casse silencieusement ; le reste demande du materiel.

## Polices et accents

Les polices Montserrat fournies avec LVGL **ne contiennent que l'ASCII**. Sans
traitement, « Ciel dégagé » s'afficherait avec des carres vides. Le firmware
replie donc les accents avant affichage (`ascii_fold`, dans `src/ui/text_util.cpp`) :
« Ciel degage ».

Pour de vrais accents, generez une police etendue :

```bash
npm install -g lv_font_conv
lv_font_conv --font Montserrat-Medium.ttf \
  --range 0x20-0x7F,0xA0-0xFF \
  --size 16 --bpp 4 --format lvgl \
  -o src/ui/font_montserrat_16_latin.c
```

Declarez-la ensuite dans `lv_conf.h`, remplacez `&lv_font_montserrat_16` par la
votre dans les onglets, et remplacez les appels a `ascii_fold` par `copy_text`.
Comptez ~10 kio de flash par taille.

## Limites connues

- **Pas de pochette d'album.** `/api/music/art` sert bien l'image, mais
  l'afficher demanderait un decodeur JPEG et un redimensionnement — a faire
  cote moteur plutot que sur la carte.
- **Pas d'heure a l'ecran** : demande une synchronisation NTP.
- **Listes bornees** : 6 serveurs, 20 taches de checklist
  (`src/model/dashboard_state.h`). Au-dela, le surplus est ignore ; augmentez
  les constantes si besoin, en gardant un œil sur la RAM.
- **HTTP en clair** sur le reseau local. Le jeton partage empeche les
  modifications accidentelles depuis un autre appareil, il ne chiffre rien.
