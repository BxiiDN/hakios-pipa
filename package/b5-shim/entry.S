// B5 entry shim, the first code the Android Image runs (its code0 is replaced by a branch here, tools/b5_compose.py).
// Arm64 boot protocol: x0 = device tree, x1..x3 = 0, MMU off. Nothing is touched but the device tree, and only by
// b5_decide() on the menu path; the Android path restores x0..x3 and runs the Image's own first instruction.
        .section .text.entry, "ax"
        .global shim_entry
shim_entry:
        mov     x19, x0
        mov     x20, x1
        mov     x21, x2
        mov     x22, x3
        adr     x9, stack_top
        mov     sp, x9
        adr     x23, shim_entry
        ldr     x24, desc_shim_off
        sub     x25, x23, x24                   // the Image's load address
        ldr     x1, desc_payload_off
        add     x1, x25, x1
        ldr     x2, desc_payload_bytes
        mov     x0, x19
        bl      b5_decide
        cbnz    w0, menu
        mov     x0, x19
        mov     x1, x20
        mov     x2, x21
        mov     x3, x22
        b       orig_code0
menu:
        ldr     x9, desc_bootshim_off
        add     x9, x25, x9
        mov     x0, x19
        mov     x1, xzr
        mov     x2, xzr
        mov     x3, xzr
        br      x9

        .balign 8
        .global b5_descriptor
b5_descriptor:                                  // filled by tools/b5_compose.py
        .ascii  "HKB5"
        .word   1                               // version
desc_shim_off:      .quad 0                     // shim_entry - Image start
desc_bootshim_off:  .quad 0                     // BootShim + firmware - Image start
desc_payload_off:   .quad 0                     // payload volume - Image start
desc_payload_bytes: .quad 0
orig_code0:         .word 0xd503201f            // the Image's original code0 (composer), NOP until then
back_to_image:      .word 0xd503201f            // "b Image+4" (composer)

        .balign 16
stack_bottom:
        .space  8192
stack_top:
