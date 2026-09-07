#!/usr/bin/env bash
# Compile et execute les tests natifs du firmware (aucune carte requise).
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(dirname "$here")"
out="$(mktemp -d)"
trap 'rm -rf "$out"' EXIT

g++ -std=gnu++17 -Wall -Wextra -Werror -O1 \
    -I "$root/src" \
    "$here/test_native.cpp" \
    "$root/src/ui/text_util.cpp" \
    -o "$out/test_native"

"$out/test_native"
