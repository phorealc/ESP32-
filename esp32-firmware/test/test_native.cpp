// Tests natifs de la logique du firmware qui ne depend ni d'Arduino ni de LVGL.
//
// Le portage croise ESP32 demande une chaine de compilation complete ; ces
// fonctions-la (decoupage UTF-8, formatage, bornes de copie) se verifient sur
// PC en une seconde, et ce sont elles qui cassent silencieusement.
//
// Lancement : esp32-firmware/test/run_native_tests.sh

#include <cstdio>
#include <cstring>
#include <string>

#include "model/dashboard_state.h"
#include "ui/text_util.h"

namespace {

int g_failures = 0;
int g_checks = 0;

void check(bool condition, const char* what) {
  g_checks++;
  if (!condition) {
    g_failures++;
    std::printf("  ECHEC  %s\n", what);
  }
}

void check_str(const char* actual, const char* expected, const char* what) {
  g_checks++;
  if (std::strcmp(actual, expected) != 0) {
    g_failures++;
    std::printf("  ECHEC  %s : attendu \"%s\", obtenu \"%s\"\n", what, expected, actual);
  }
}

void test_ascii_fold() {
  char out[64];

  ascii_fold(out, sizeof(out), "Ciel degage");
  check_str(out, "Ciel degage", "ASCII inchange");

  ascii_fold(out, sizeof(out), "Ciel dégagé");
  check_str(out, "Ciel degage", "accents replies");

  ascii_fold(out, sizeof(out), "Où est passé le café ?");
  check_str(out, "Ou est passe le cafe ?", "accents multiples");

  ascii_fold(out, sizeof(out), "ÉTÉ");
  check_str(out, "ETE", "majuscules accentuees");

  ascii_fold(out, sizeof(out), "");
  check_str(out, "", "chaine vide");

  ascii_fold(out, sizeof(out), nullptr);
  check_str(out, "", "source nulle");

  // Un caractere non couvert (ideogramme, emoji) doit consommer toute la
  // sequence UTF-8, sinon les octets de continuation ressortent en vrac.
  ascii_fold(out, sizeof(out), "a日b");
  check_str(out, "a?b", "sequence multi-octets inconnue consommee entierement");

  ascii_fold(out, sizeof(out), "a🎵b");
  check_str(out, "a?b", "emoji 4 octets consomme entierement");

  // Troncature : la sortie doit rester terminee et ne jamais deborder.
  char small[6];
  ascii_fold(small, sizeof(small), "abcdefghij");
  check_str(small, "abcde", "troncature a la taille du tampon");
  check(std::strlen(small) == 5, "troncature terminee par NUL");

  // Un accent en toute fin de tampon ne doit pas ecrire hors bornes.
  char tight[4];
  ascii_fold(tight, sizeof(tight), "aéé");
  check(std::strlen(tight) <= 3, "accent tronque sans debordement");
}

void test_format_duration() {
  char out[16];

  format_duration(out, sizeof(out), 0);
  check_str(out, "0:00", "duree nulle");

  format_duration(out, sizeof(out), 7);
  check_str(out, "0:07", "secondes sur deux chiffres");

  format_duration(out, sizeof(out), 187);
  check_str(out, "3:07", "minutes et secondes");

  format_duration(out, sizeof(out), 3600);
  check_str(out, "1:00:00", "passage aux heures");

  format_duration(out, sizeof(out), 3753);
  check_str(out, "1:02:33", "heures, minutes, secondes");
}

void test_weather_icon_label() {
  check_str(weather_icon_label("01d"), "Ciel degage", "icone 01d");
  check_str(weather_icon_label("01n"), "Ciel degage", "icone 01n (nuit)");
  check_str(weather_icon_label("10d"), "Pluie", "icone 10d");
  check_str(weather_icon_label("50n"), "Brouillard", "icone 50n");
  check_str(weather_icon_label("99z"), "", "icone inconnue");
  check_str(weather_icon_label(""), "", "icone vide");
  check_str(weather_icon_label(nullptr), "", "icone nulle");
}

void test_copy_text() {
  char dest[8];

  copy_text(dest, sizeof(dest), "court");
  check_str(dest, "court", "copie simple");

  copy_text(dest, sizeof(dest), "beaucoup trop long");
  check(std::strlen(dest) == 7, "copie tronquee a size-1");
  check(dest[7] == '\0', "copie toujours terminee");

  copy_text(dest, sizeof(dest), nullptr);
  check_str(dest, "", "source nulle donne une chaine vide");
}

void test_total_players() {
  ServersState servers;
  servers.count = 3;
  servers.items[0].online = true;
  servers.items[0].players_online = 4;
  servers.items[1].online = false;
  servers.items[1].players_online = 99;  // serveur hors ligne : ne compte pas
  servers.items[2].online = true;
  servers.items[2].players_online = 3;

  check(servers.total_players() == 7, "les serveurs hors ligne sont exclus du total");

  ServersState empty;
  check(empty.total_players() == 0, "total nul sans serveur");
}

}  // namespace

int main() {
  std::printf("Tests natifs du firmware\n");
  test_ascii_fold();
  test_format_duration();
  test_weather_icon_label();
  test_copy_text();
  test_total_players();

  std::printf("%d verifications, %d echec(s)\n", g_checks, g_failures);
  return g_failures == 0 ? 0 : 1;
}
