#include "text_util.h"

#include <stdio.h>
#include <string.h>

namespace {

// Correspondances UTF-8 -> ASCII pour le supplement Latin-1, suffisant pour le
// francais et la plupart des titres europeens.
struct Fold {
  const char* utf8;
  char ascii;
};

const Fold FOLDS[] = {
    {"à", 'a'}, {"â", 'a'}, {"ä", 'a'}, {"á", 'a'}, {"ã", 'a'}, {"å", 'a'},
    {"é", 'e'}, {"è", 'e'}, {"ê", 'e'}, {"ë", 'e'},
    {"î", 'i'}, {"ï", 'i'}, {"í", 'i'}, {"ì", 'i'},
    {"ô", 'o'}, {"ö", 'o'}, {"ó", 'o'}, {"ò", 'o'}, {"õ", 'o'}, {"ø", 'o'},
    {"ù", 'u'}, {"û", 'u'}, {"ü", 'u'}, {"ú", 'u'},
    {"ç", 'c'}, {"ñ", 'n'}, {"ý", 'y'}, {"ÿ", 'y'},
    {"À", 'A'}, {"Â", 'A'}, {"Ä", 'A'}, {"Á", 'A'},
    {"É", 'E'}, {"È", 'E'}, {"Ê", 'E'}, {"Ë", 'E'},
    {"Î", 'I'}, {"Ï", 'I'},
    {"Ô", 'O'}, {"Ö", 'O'}, {"Ó", 'O'},
    {"Ù", 'U'}, {"Û", 'U'}, {"Ü", 'U'},
    {"Ç", 'C'}, {"Ñ", 'N'},
};

constexpr size_t FOLD_COUNT = sizeof(FOLDS) / sizeof(FOLDS[0]);

}  // namespace

void ascii_fold(char* dest, size_t size, const char* src) {
  if (dest == nullptr || size == 0) return;
  if (src == nullptr) {
    dest[0] = '\0';
    return;
  }

  size_t out = 0;
  while (*src != '\0' && out + 1 < size) {
    const unsigned char c = static_cast<unsigned char>(*src);
    if (c < 0x80) {  // ASCII : recopie directe
      dest[out++] = *src++;
      continue;
    }

    bool folded = false;
    for (size_t i = 0; i < FOLD_COUNT; i++) {
      const size_t len = strlen(FOLDS[i].utf8);
      if (strncmp(src, FOLDS[i].utf8, len) == 0) {
        dest[out++] = FOLDS[i].ascii;
        src += len;
        folded = true;
        break;
      }
    }
    if (folded) continue;

    // Caractere non-ASCII inconnu : on saute la sequence UTF-8 complete pour ne
    // pas laisser d'octets orphelins qui casseraient le rendu LVGL.
    dest[out++] = '?';
    src++;
    while ((static_cast<unsigned char>(*src) & 0xC0) == 0x80) src++;
  }
  dest[out] = '\0';
}

void format_duration(char* dest, size_t size, uint32_t seconds) {
  const uint32_t hours = seconds / 3600;
  const uint32_t minutes = (seconds % 3600) / 60;
  const uint32_t secs = seconds % 60;
  if (hours > 0) {
    snprintf(dest, size, "%lu:%02lu:%02lu", static_cast<unsigned long>(hours),
             static_cast<unsigned long>(minutes), static_cast<unsigned long>(secs));
  } else {
    snprintf(dest, size, "%lu:%02lu", static_cast<unsigned long>(minutes),
             static_cast<unsigned long>(secs));
  }
}

const char* weather_icon_label(const char* icon) {
  if (icon == nullptr || strlen(icon) < 2) return "";
  // Les codes OWM sont « NNd » ou « NNn » ; seuls les deux chiffres comptent.
  const char a = icon[0];
  const char b = icon[1];
  if (a == '0' && b == '1') return "Ciel degage";
  if (a == '0' && b == '2') return "Peu nuageux";
  if (a == '0' && (b == '3' || b == '4')) return "Nuageux";
  if (a == '0' && (b == '9')) return "Averses";
  if (a == '1' && b == '0') return "Pluie";
  if (a == '1' && b == '1') return "Orage";
  if (a == '1' && b == '3') return "Neige";
  if (a == '5' && b == '0') return "Brouillard";
  return "";
}
