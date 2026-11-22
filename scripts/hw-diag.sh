#!/usr/bin/env bash
# What Android sees of the hardware, read-only, for comparing with a port's results: input devices, I2C/SPI devices,
# panel, sound cards, Wi-Fi/BT chips, CPU and memory. private/hw-diag.txt.
source "$(dirname "$0")/adb-lib.sh"
need_android
out=$PRIVATE/hw-diag.txt
{ echo "## cpu"; adb shell cat /proc/cpuinfo | grep -E 'processor|CPU part' | paste - - | head -8
  echo "## memory"; adb shell cat /proc/meminfo | head -3
  echo "## input"; adb shell cat /proc/bus/input/devices | grep -E '^N:'
  echo "## i2c/spi"; adb shell 'for d in /sys/bus/i2c/devices/* /sys/bus/spi/devices/*; do echo "$d $(cat $d/name 2>/dev/null) $(readlink $d/driver 2>/dev/null | xargs basename 2>/dev/null)"; done'
  echo "## sound"; adb shell cat /proc/asound/cards
  echo "## display"; adb shell dumpsys display | grep -m3 -E 'mBaseDisplayInfo|supportedModes'
  echo "## partitions"; adb shell cat /proc/partitions | awk 'NR>2 && $4 ~ /^sd[a-h]$/' ; } | tr -d '\r' > "$out"
cat "$out"; say "written: $out"
