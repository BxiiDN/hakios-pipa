"""tools/owner_trust.py: CDHash from a code signature, the NGPUADD2 reader, and the bundle layout."""
import hashlib
import importlib.util
import struct
import unittest
import uuid
import zlib
from pathlib import Path

spec = importlib.util.spec_from_file_location('owner_trust', Path(__file__).resolve().parents[1] / 'tools/owner_trust.py')
ot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ot)


def signed_macho(code=b'\x1f\x20\x03\xd5' * 8, hash_type=2):
    # CodeDirectory: magic, length, then version..hashType at offset 37
    cd = bytearray(struct.pack('>2I', 0xfade0c02, 0) + bytes(40) + code)
    cd[37] = hash_type
    struct.pack_into('>I', cd, 4, len(cd))
    sb = struct.pack('>3I', 0xfade0cc0, 12 + 8 + len(cd), 1) + struct.pack('>2I', 0, 20) + bytes(cd)
    header_len = 32 + 16
    off = header_len + 16
    head = struct.pack('<8I', 0xfeedfacf, 0x0100000c, 0, 6, 1, 16, 0, 0) + struct.pack('<4I', 0x1d, 16, off, len(sb))
    return head + bytes(off - len(head)) + sb, hashlib.sha256(bytes(cd)).hexdigest()[:40]


def ngpuadd2(files):
    pad = lambda b: b + bytes(-len(b) % 8)
    body = b''
    for name, mode, data in files:
        enc, packed = name.encode() + b'\0', zlib.compress(data, 9)
        body += struct.pack('<IIQQ', len(enc), mode, len(data), len(packed)) + pad(enc) + pad(packed)
    return b'NGPUADD2' + struct.pack('<IIQ', len(files), 0, 24 + len(body)) + body


class OwnerTrust(unittest.TestCase):
    def test_cdhash(self):
        macho, expected = signed_macho()
        self.assertEqual(ot.cdhash(macho), expected)

    def test_cdhash_refuses_sha1_and_unsigned(self):
        with self.assertRaises(ValueError):
            ot.cdhash(signed_macho(hash_type=1)[0])
        with self.assertRaises(ValueError):
            ot.cdhash(struct.pack('<8I', 0xfeedfacf, 0x0100000c, 0, 6, 0, 0, 0, 0))

    def test_addon_reader(self):
        files = [('bin/a', 0o755, b'x' * 1000), ('daemons/b.plist', 0o644, b'<plist/>')]
        self.assertEqual(ot.addon_files(ngpuadd2(files)), files)
        with self.assertRaises(ValueError):
            ot.addon_files(ngpuadd2(files) + b'\0' * 8)   # length field no longer matches

    def test_bundle_layout(self):
        static, system = struct.pack('<I16sI', 2, bytes(16), 1) + bytes(24), struct.pack('<I16sI', 2, bytes(16), 0)
        original = struct.pack('<3I', 2, 12, 12 + len(static)) + static + system
        saved = ot.ORIGINAL_SHA256
        try:
            ot.ORIGINAL_SHA256 = hashlib.sha256(original).hexdigest()
            hashes = ['bb' * 20, 'aa' * 20]
            b = ot.bundle(original, hashes)
        finally:
            ot.ORIGINAL_SHA256 = saved
        count, s0, s1, s2 = struct.unpack_from('<4I', b)
        self.assertEqual(count, 3)
        version, ident, n = struct.unpack_from('<I16sI', b, s0)
        self.assertEqual((version, n), (2, 2))
        self.assertEqual(ident, uuid.uuid5(uuid.NAMESPACE_URL, 'org.blu-sharky.adreno-metal:' + 'aa' * 20 + 'bb' * 20).bytes)
        self.assertEqual(b[s0 + 24:s0 + 44], bytes.fromhex('aa' * 20))   # sorted
        self.assertEqual(b[s1:s2], static)
        self.assertEqual(b[s2:], system)

    def test_bundle_refuses_other_original(self):
        with self.assertRaises(ValueError):
            ot.bundle(b'\2\0\0\0' + bytes(8), [])


if __name__ == '__main__':
    unittest.main()
