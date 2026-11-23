"""tools/image_consistency.py: an image passes only when it is built from the very kernel, firmware and payload
given; swapping any one of them, or a manifest that recorded other files, fails. Fixtures only."""
import gzip
import hashlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'tests'))
import fatimage  # noqa: E402
import verify_bootimg as vb  # noqa: E402
from image_consistency import check  # noqa: E402

KERNEL = b'\xcf\xfa\xed\xfe' + b'K' * 5000
FIRMWARE = b'_FVH' + b'F' * 9000
SHIM = bytearray(4096)
SHIM[56:60] = b'ARM\x64'


def payload(kernel=KERNEL):
    return fatimage.build({'EFI/UniXNU/unixnu.toml': b'version = 1\n', 'EFI/UniXNU/Payloads/kernel.macho': kernel,
                           'EFI/UniXNU/Payloads/kernel.macho.adt': b'ADT'})


def image(fv=FIRMWARE, pl=None):
    return vb.build_v0(gzip.compress(bytes(SHIM) + fv, mtime=0), pl if pl is not None else payload(), page=2048,
                       kernel_addr=0x10008000)


def fails(results):
    return [t for level, t in results if level == 'FAIL']


class Consistency(unittest.TestCase):
    def test_matching_pieces_pass(self):
        self.assertEqual(fails(check(image(), KERNEL, FIRMWARE, payload())), [])

    def test_other_kernel_in_payload_fails(self):
        other = payload(b'\xcf\xfa\xed\xfe' + b'X' * 5000)
        self.assertTrue(any('built kernel' in t for t in fails(check(image(pl=other), KERNEL, FIRMWARE, other))))

    def test_other_firmware_fails(self):
        self.assertTrue(any('built firmware' in t for t in fails(check(image(fv=b'_FVH' + b'G' * 9000), KERNEL, FIRMWARE, payload()))))

    def test_image_larger_than_the_boot_partition_fails(self):
        img = image()
        self.assertTrue(any('fits the boot partition' in t for t in fails(check(img, KERNEL, FIRMWARE, payload(), max_bytes=len(img) - 1))))
        self.assertEqual(fails(check(img, KERNEL, FIRMWARE, payload(), max_bytes=len(img))), [])

    def test_img4_strings_of_the_kernel_are_a_note_not_a_failure(self):
        kernel = KERNEL + b'no img4_object provided'
        pl = payload(kernel)
        results = check(image(pl=pl), kernel, FIRMWARE, pl)
        self.assertEqual(fails(results), [])
        self.assertTrue(any(level == 'NOTE' for level, _ in results))

    def test_im4p_anywhere_fails(self):
        kernel = KERNEL + b'IM4P'
        pl = payload(kernel)
        self.assertTrue(fails(check(image(pl=pl), kernel, FIRMWARE, pl)))

    def test_appended_device_tree(self):
        fdt = bytes.fromhex('d00dfeed') + (16).to_bytes(4, 'big') + bytes(8)
        pl = payload()
        img = vb.build_v0(gzip.compress(bytes(SHIM) + FIRMWARE, mtime=0) + fdt, pl, page=2048, kernel_addr=0x10008000)
        self.assertEqual(fails(check(img, KERNEL, FIRMWARE, pl, dtb=fdt)), [])
        self.assertTrue(any('given --dtb' in t for t in fails(check(img, KERNEL, FIRMWARE, pl, dtb=fdt[:-1] + b'x'))))
        bad = vb.build_v0(gzip.compress(bytes(SHIM) + FIRMWARE, mtime=0) + b'junk', pl, page=2048, kernel_addr=0x10008000)
        self.assertTrue(any('one FDT' in t for t in fails(check(bad, KERNEL, FIRMWARE, pl))))

    def test_other_payload_fails(self):
        self.assertTrue(any('ramdisk is payload.img' in t for t in fails(check(image(), KERNEL, FIRMWARE, payload() + b'\0'))))

    def test_manifest_must_record_the_same_files(self):
        img, pl = image(), payload()
        h = lambda d: hashlib.sha256(d).hexdigest()
        good = {'unixnu_files': [{'path': 'out/pipa/kernel/kernel.macho', 'sha256': h(KERNEL)},
                                 {'path': 'out/pipa/payload/payload.img', 'sha256': h(pl)},
                                 {'path': 'out/pipa/boot/boot.img', 'sha256': h(img)}],
                'uefi_files': [{'path': 'Build/pipaPkg/DEBUG_CLANGPDB/FV/SILICIUM_UEFI.fd', 'sha256': h(FIRMWARE)}]}
        self.assertEqual(fails(check(img, KERNEL, FIRMWARE, pl, good)), [])
        stale = dict(good, uefi_files=[{'path': 'Build/x/SILICIUM_UEFI.fd', 'sha256': '0' * 64}])
        self.assertTrue(any('SILICIUM_UEFI.fd' in t for t in fails(check(img, KERNEL, FIRMWARE, pl, stale))))


if __name__ == '__main__':
    unittest.main()
