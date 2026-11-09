#!/bin/bash
# Compila el firmware del ESP32 y lo simula en Wokwi sin navegador (wokwi-cli).
#
#   MQTT_USER=esp32 MQTT_PASS=<clave> WOKWI_CLI_TOKEN=<token CI de wokwi.com> ./build_y_simular.sh [segundos]
#
# Las credenciales entran como -D al compilar: NO quedan en el codigo ni en el repositorio.
# Requisitos: PlatformIO (pio), esptool (pip install esptool) y wokwi-cli (github.com/wokwi/wokwi-cli).
set -e
SEG="${1:-300}"
AQUI="$(cd "$(dirname "$0")" && pwd)"
PIO="${PIO:-pio}"
WOKWI_CLI="${WOKWI_CLI:-wokwi-cli}"
BOOT_APP0="${BOOT_APP0:-$HOME/.platformio/packages/framework-arduinoespressif32/tools/partitions/boot_app0.bin}"
command -v cygpath >/dev/null && BOOT_APP0="$(cygpath -m "$BOOT_APP0")"
: "${MQTT_USER:?}" "${MQTT_PASS:?}" "${WOKWI_CLI_TOKEN:?}"
HOST="${MQTT_HOST:-campussense-unab.northcentralus.cloudapp.azure.com}"
export WOKWI_CLI_TOKEN
export PLATFORMIO_BUILD_FLAGS="-DMQTT_HOST=\\\"$HOST\\\" -DMQTT_USER=\\\"$MQTT_USER\\\" -DMQTT_PASS=\\\"$MQTT_PASS\\\""
cd "$AQUI/esp32-campus"
"$PIO" run
B=.pio/build/esp32dev
python -m esptool --chip esp32 merge-bin -o "$B/firmware_merged.bin" --flash-mode dio --flash-size 4MB \
  0x1000 "$B/bootloader.bin" 0x8000 "$B/partitions.bin" 0xe000 "$BOOT_APP0" 0x10000 "$B/firmware.bin"
"$WOKWI_CLI" --timeout $((SEG * 1000)) .
