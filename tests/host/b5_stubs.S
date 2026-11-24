// QEMU stand-ins for tests/test_b5_shim_qemu.py: a fake Android Image (header + "android" stub at +0x40) and a "menu"
// stub in place of BootShim + firmware. Each writes, by semihosting, its own load address (8 bytes) and the device tree
// it was given in x0 to a host file, then exits QEMU with 0x10 (Android) or 0x20 (menu). Assembled twice: -DIMAGE / -DMENU.
        .macro  semihost op
        mov     w0, #\op
        hlt     #0xf000
        .endm

        .macro  dump name, code
1:      mov     x19, x0                         // the device tree
        adr     x20, 1b                         // where this stub was loaded
        adr     x9, where
        str     x20, [x9]
        adr     x1, open_args
        adr     x9, name_str
        str     x9, [x1]                        // position independent: the name's address is taken at run time
        semihost 0x01                           // SYS_OPEN name, "wb"
        mov     x21, x0
        adr     x1, write_args
        str     x21, [x1]
        adr     x9, where
        str     x9, [x1, #8]
        mov     x9, #8
        str     x9, [x1, #16]
        semihost 0x05                           // SYS_WRITE 8 bytes: the load address
        adr     x1, write_args
        str     x19, [x1, #8]
        ldr     w9, [x19, #4]
        rev     w9, w9
        str     x9, [x1, #16]
        semihost 0x05                           // SYS_WRITE the device tree (totalsize bytes)
        adr     x1, exit_args
        mov     x9, #\code
        str     x9, [x1, #8]
        semihost 0x18                           // SYS_EXIT (ADP_Stopped_ApplicationExit, code)
0:      b       0b
        .balign 8
where:      .quad 0
open_args:  .quad 0, 4, name_end - name_str - 1
write_args: .quad 0, 0, 0
exit_args:  .quad 0x20026, 0
name_str:   .asciz "\name"
name_end:
        .endm

        .text
#ifdef IMAGE
image:
        .word   0x91005a4d                      // code0: add x13, x18, #0x16 (as an EFI-stub Image)
        b       android                         // code1
        .quad   0                               // text_offset
        .quad   0x10000                         // image_size (the composer raises it)
        .quad   0                               // flags
        .quad   0, 0, 0
        .ascii  "ARMd"
        .word   0
android:
        dump    android.out, 0x10
#else
menu:
        dump    menu.out, 0x20
#endif
