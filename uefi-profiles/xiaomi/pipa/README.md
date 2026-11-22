# U-Boot profile: Xiaomi Pad 6 (pipa)

Upstream U-Boot (pinned by hakios-uefi, v2026.07) already has the SM8250's clocks and pins
(`drivers/clk/qcom/clock-sm8250.c`, `drivers/pinctrl/qcom/pinctrl-sm8250.c`) and builds the tablet's tree from
Linux's `sm8250-xiaomi-pipa.dts`, which has a `simple-framebuffer` on `cont_splash` (so the menu can be drawn).
This profile adds only: the tree's name, the HakiOS command, and a boot menu (`board/xiaomi/pipa.env`).

The image is an Android boot image for `fastboot boot`: it is never flashed by anything in this repository.

## Test log

| Step (hakios-uefi docs/porting-a-board.md §7) | State |
| --- | --- |
| Build, boot-image header checked | NOT TESTED (no AArch64 GCC or flex in the session that wrote this) |
| `fastboot boot`, menu on the display | NOT TESTED (needs the tablet) |
| Volume keys / Power in the menu | NOT TESTED |
| Android entry returns to Android | NOT TESTED |
| Recovery / Fastboot entry | NOT TESTED: depends on ABL reading the held key on a warm reset |
| HakiOS entry starts loader.efi | NOT TESTED |
