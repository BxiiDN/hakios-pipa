/* B5 entry shim (hakios-pipa docs/MODE-B.md, B5): the decision of tools/b5_shim_model.py, in C for the bare-metal shim and
   for the host tests. No library, no global data, nothing but the device tree in x0 is written. */
#ifndef B5_SHIM_H
#define B5_SHIM_H
typedef unsigned char u8;
typedef unsigned int u32;
typedef unsigned long long u64;

enum { B5_ANDROID = 0, B5_MENU = 1 };

/* 0: branch to the stock Image unchanged; 1: /chosen linux,initrd-start/-end now name [payload, payload + bytes) and the
   menu (BootShim + firmware) is entered. Every doubt gives 0. */
int b5_decide(u8 *dtb, u64 payload_addr, u64 payload_bytes);
#endif
