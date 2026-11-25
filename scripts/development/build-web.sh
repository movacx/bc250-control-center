#!/usr/bin/env bash
# Compila la web (Kotlin Multiplataforma, WebAssembly) y la deja lista en frontends/web/dist.
set -euo pipefail
cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../../frontends/web/app"
./gradlew --no-configuration-cache :webApp:wasmJsBrowserDistribution "$@"
python3 ../../../scripts/development/publicar_web.py
