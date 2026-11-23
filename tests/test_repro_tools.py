"""tools/macho_fingerprint.py and tools/binary_diff.py on files written by the test."""
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'tools/{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fp, bd = load('macho_fingerprint'), load('binary_diff')


def kernel(text=b'\x1f\x20\x03\xd5' * 8, uuid=b'\x11' * 16, version=b'Darwin Kernel Version 23.6.0: Mon Nov 23'):
    body = text + b'\0' + version + b'\0'
    cmds = struct.pack('<2I16s4Q4I', 0x19, 72 + 80, b'__TEXT', 0xfffffff007004000, 0x4000, 0, 0, 5, 5, 1, 0)
    section = struct.pack('<16s16s2Q8I', b'__text', b'__TEXT', 0xfffffff007004000, len(body), 0, 0, 0, 0, 0x80000400, 0, 0, 0)
    assert len(section) == 80
    cmds += section
    cmds += struct.pack('<2I16s', 0x1b, 24, uuid)
    header = struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 2, 2, len(cmds), 0, 0)
    off = len(header) + len(cmds)
    cmds = bytearray(cmds)
    struct.pack_into('<4Q', cmds, 24, 0xfffffff007004000, 0x4000, off, len(body))   # segment fileoff/filesize
    struct.pack_into('<I', cmds, 72 + 48, off)                                        # section offset
    return bytes(header + cmds + body)


class Fingerprint(unittest.TestCase):
    def test_same_build_identical(self):
        self.assertEqual(fp.compare(fp.fingerprint(kernel()), fp.fingerprint(kernel())), [])

    def test_uuid_and_version_string_are_named(self):
        a = fp.fingerprint(kernel())
        b = fp.fingerprint(kernel(uuid=b'\x22' * 16, version=b'Darwin Kernel Version 23.6.0: Tue Nov 24'))
        diff = '\n'.join(fp.compare(a, b))
        self.assertIn('DIFF uuid', diff)
        self.assertIn('Tue Nov 24', diff)
        self.assertIn('__TEXT,__text', diff)
        self.assertTrue(any('Darwin Kernel Version' in s for s in a['version_strings']))

    def test_not_macho(self):
        with self.assertRaises(SystemExit):
            fp.fingerprint(b'\0' * 64)


def pe(stamp):
    img = bytearray(0x400)
    img[0:2] = b'MZ'
    struct.pack_into('<I', img, 60, 0x80)
    img[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HHI', img, 0x84, 0xaa64, 1, stamp)
    struct.pack_into('<H', img, 0x80 + 20, 0xf0)
    struct.pack_into('<H', img, 0x98, 0x20b)
    struct.pack_into('<I', img, 0x98 + 56, 0x400)
    return bytes(img)


class BinaryDiff(unittest.TestCase):
    def test_timestamp_is_classified(self):
        d = Path(tempfile.mkdtemp())
        (d / 'a').write_bytes(b'\xff' * 64 + pe(1000))
        (d / 'b').write_bytes(b'\xff' * 64 + pe(2000))
        self.assertEqual(bd.main([str(d / 'a'), str(d / 'b'), '--json', str(d / 'r.json')]), 1)
        report = json.loads((d / 'r.json').read_text())
        self.assertEqual([r['kind'] for r in report['ranges']], ['COFF TimeDateStamp'])

    def test_identical(self):
        d = Path(tempfile.mkdtemp())
        (d / 'a').write_bytes(pe(5))
        (d / 'b').write_bytes(pe(5))
        self.assertEqual(bd.main([str(d / 'a'), str(d / 'b')]), 0)

    def test_outside_pe_and_length(self):
        self.assertEqual(bd.ranges(b'abcd', b'abXdZ'), [(2, 3), (4, 5)])


if __name__ == '__main__':
    unittest.main()
