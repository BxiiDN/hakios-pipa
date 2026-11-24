"""tools/b5_compose.py: code0 relocation (the port Image starts with "b", 0x14a74000), refusals, and the layout."""
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import b5_compose as c  # noqa: E402


def target(insn, at):
    imm = insn & 0x3ffffff
    if imm & (1 << 25):
        imm -= 1 << 26
    return at + imm * 4


class Compose(unittest.TestCase):
    def test_b_is_reencoded_to_the_same_target(self):
        code0 = 0x14a74000
        moved = c.relocate_code0(code0, 0x3262000 + 0x70 + 40)
        self.assertEqual(target(moved, 0x3262000 + 0x70 + 40), target(code0, 0))

    def test_efi_stub_add_is_copied_and_others_refused(self):
        self.assertEqual(c.relocate_code0(c.EFI_STUB_CODE0, 0x1000), c.EFI_STUB_CODE0)
        with self.assertRaises(c.ComposeError):
            c.relocate_code0(0xd503201f, 0x1000)                 # a NOP is not an Image code0 we know

    def test_layout_and_refusals(self):
        image = bytearray(0x10000)
        struct.pack_into('<I', image, 0, 0x14a74000)
        image[56:60] = b'ARMd'
        h = bytearray(4096)
        h[:8] = b'ANDROID!'
        struct.pack_into('<II', h, 8, len(image), 4096)
        struct.pack_into('<I', h, 40, 3)
        boot = bytes(h) + bytes(image) + b'R' * 4096
        shim = b'\0' * 0x70 + b'HKB5' + b'\0' * 0x200
        out, info = c.compose(boot, b'B' * 5000, b'\0' * 8192, shim)
        k = out[4096:4096 + info['kernel_bytes']]
        self.assertEqual(target(struct.unpack_from('<I', k, 0)[0], 0), info['shim_offset'])
        d = info['shim_offset'] + 0x70
        self.assertEqual(struct.unpack_from('<QQQQ', k, d + 8),
                         (info['shim_offset'], info['bootshim_offset'], info['payload_offset'], 8192))
        self.assertEqual(target(struct.unpack_from('<I', k, d + 44)[0], d + 44), 4)        # back to Image+4
        self.assertEqual(out[4096 + -(-len(k) // 4096) * 4096:][:4096], b'R' * 4096)      # stock ramdisk kept
        with self.assertRaises(c.ComposeError):
            c.compose(boot, b'B', b'\0' * 1000, shim)                                        # payload not in sectors


if __name__ == '__main__':
    unittest.main()
